"""Claude Haiku 4.5 extract + score with prompt caching.

The system prompt (candidate profile + extraction rules) is identical across
every call, so we cache it with `cache_control: ephemeral`. The user message
holds the per-posting fields (title, company, location hint, description).

Two entry points:
  - extract_and_score(...) — synchronous one-off, useful for testing and
    ad-hoc lookups.
  - extract_and_score_batch(...) — uses the Messages Batch API for the daily
    run (50% cheaper per spec, asynchronous).
"""

import json
import re
import time

import anthropic

from config import LLM_MODEL, TRACK_VOCAB, USER_PROFILE

_INSTRUCTIONS = f"""You extract structured fields from a job posting and score it against the candidate profile below.

# Candidate profile
{USER_PROFILE}

# Output
Return ONLY valid JSON. No commentary, no markdown fences. Exact schema:

{{
  "location": "<short readable location, e.g. 'Atlanta, GA' or 'Remote (US)' or 'Multiple US locations'>",
  "remote_type": "<one of: Remote, Hybrid, Onsite, Unclear>",
  "category": "<one of: ic, rotational>",
  "track": "<for category=rotational only, one of: {', '.join(TRACK_VOCAB)}. For category=ic, use empty string \\"\\">",
  "key_reqs": ["<3 to 5 short strings, each <= 80 chars>"],
  "fit_score": <integer 1-10>,
  "fit_reasoning": "<one sentence, <= 200 chars>"
}}

# Scoring rules
- category=ic: score on alignment with the candidate's GenAI / LLM / RAG / Python / Snowflake / multi-agent background and DS/ML/AI role fit. Penalize roles requiring senior-level engineering experience (8+ years) or domains far from the candidate's profile.
- category=rotational: score on whether the program includes meaningful data, analytics, ML, or engineering exposure. A pure sales/business rotation is a poor fit even if early career. A data/analytics/engineering rotation is a strong fit.
- For multi-track rotational programs (e.g., Bank of America's Analyst Development Program): set track to "Mixed Technical" if at least one rotation is data/analytics/engineering, else "Mixed Business".

# Categorization
Use category="ic" for standard individual-contributor postings.
Use category="rotational" for development programs, rotational programs, early-career programs, leadership development programs, and similar structured early-career tracks.
"""

# Truncate posting descriptions to manage cost; postings rarely need more.
_MAX_DESCRIPTION_CHARS = 12000

# Tag stripper for HTML descriptions returned by Workday/iCIMS detail endpoints.
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(s: str) -> str:
    s = _TAG_RE.sub(" ", s or "")
    return _WS_RE.sub(" ", s).strip()


def _build_user_message(*, title: str, company: str, location_hint: str, description: str) -> str:
    desc = _strip_html(description)
    if len(desc) > _MAX_DESCRIPTION_CHARS:
        desc = desc[:_MAX_DESCRIPTION_CHARS] + "\n[truncated]"
    return (
        f"TITLE: {title}\n"
        f"COMPANY: {company}\n"
        f"LOCATION_HINT: {location_hint}\n\n"
        f"DESCRIPTION:\n{desc}"
    )


def _system_blocks() -> list[dict]:
    return [{"type": "text", "text": _INSTRUCTIONS, "cache_control": {"type": "ephemeral"}}]


def _parse_response(text: str) -> dict:
    """Parse the LLM's JSON. Strip accidental markdown fences if present."""
    t = (text or "").strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", t, re.DOTALL)
    if m:
        t = m.group(1)
    return json.loads(t)


def _normalize(parsed: dict) -> dict:
    """Normalize the parsed dict for storage: key_reqs becomes a joined string."""
    out = dict(parsed)
    reqs = out.get("key_reqs")
    if isinstance(reqs, list):
        out["key_reqs"] = "\n".join(str(r).strip() for r in reqs if str(r).strip())
    return out


def _degraded_result(reason: str = "") -> dict:
    return {
        "location": "",
        "remote_type": "",
        "category": "",
        "track": "",
        "key_reqs": "",
        "fit_score": "",
        "fit_reasoning": f"(LLM error: {reason})" if reason else "(LLM error)",
    }


def extract_and_score(
    *,
    title: str,
    company: str,
    location_hint: str,
    description: str,
    client: anthropic.Anthropic | None = None,
) -> dict:
    """Synchronous single-call extraction + scoring. Returns parsed + normalized dict.

    The returned dict includes a `_usage` key for visibility into cache hits
    during testing; the orchestrator should strip that before writing to CSV.
    """
    cli = client or anthropic.Anthropic()
    user_msg = _build_user_message(
        title=title, company=company, location_hint=location_hint, description=description
    )
    resp = cli.messages.create(
        model=LLM_MODEL,
        max_tokens=1024,
        system=_system_blocks(),
        messages=[{"role": "user", "content": user_msg}],
    )
    text = resp.content[0].text  # type: ignore[union-attr]
    parsed = _parse_response(text)
    out = _normalize(parsed)
    out["_usage"] = {
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "cache_read": getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
        "cache_create": getattr(resp.usage, "cache_creation_input_tokens", 0) or 0,
    }
    return out


def extract_and_score_batch(
    items: list[dict],
    *,
    poll_interval: float = 30.0,
    timeout_seconds: float = 86400.0,  # batches return within 24h
    client: anthropic.Anthropic | None = None,
) -> list[dict]:
    """Submit all postings via the Batch API and return parsed dicts in input order.

    items: list of dicts with keys `title`, `company`, `location_hint`, `description`.
    Failed-to-parse responses become degraded results (empty enrichment fields)
    so the orchestrator can still write the row to CSV.
    """
    cli = client or anthropic.Anthropic()
    if not items:
        return []

    requests = [
        {
            "custom_id": f"job-{i}",
            "params": {
                "model": LLM_MODEL,
                "max_tokens": 1024,
                "system": _system_blocks(),
                "messages": [
                    {
                        "role": "user",
                        "content": _build_user_message(
                            title=it["title"],
                            company=it["company"],
                            location_hint=it["location_hint"],
                            description=it["description"],
                        ),
                    }
                ],
            },
        }
        for i, it in enumerate(items)
    ]

    batch = cli.messages.batches.create(requests=requests)
    started = time.time()
    while batch.processing_status != "ended":
        if time.time() - started > timeout_seconds:
            raise TimeoutError(f"batch {batch.id} did not complete in {timeout_seconds:.0f}s")
        time.sleep(poll_interval)
        batch = cli.messages.batches.retrieve(batch.id)

    by_id: dict[str, object] = {}
    for result in cli.messages.batches.results(batch.id):
        by_id[result.custom_id] = result

    out: list[dict] = []
    for i in range(len(items)):
        r = by_id.get(f"job-{i}")
        if r is None:
            out.append(_degraded_result("missing"))
            continue
        if r.result.type != "succeeded":  # type: ignore[union-attr]
            out.append(_degraded_result(r.result.type))  # type: ignore[union-attr]
            continue
        try:
            text = r.result.message.content[0].text  # type: ignore[union-attr]
            out.append(_normalize(_parse_response(text)))
        except (json.JSONDecodeError, KeyError, IndexError, AttributeError) as e:
            out.append(_degraded_result(type(e).__name__))
    return out
