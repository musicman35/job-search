"""Phenom careers-site fetcher. Used for State Farm (jobs.statefarm.com).

Public API pattern:
    GET https://{host}/api/jobs?page={N}
Paginated 1-indexed, 10 jobs/page. Each job carries title, full_location,
description, qualifications, and responsibilities inline — no detail
endpoint required for either location resolution or LLM description.
"""

import requests

from filters import categorize_title, company_slug, location_matches

TIMEOUT = 30
USER_AGENT = "Mozilla/5.0 (compatible; job-tracker/1.0)"


def _get_page(host: str, page: int) -> dict:
    url = f"https://{host}/api/jobs?page={page}"
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    r = requests.get(url, headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json() or {}


def _iter_jobs(host: str):
    page = 1
    seen = 0
    total: int | None = None
    while True:
        data = _get_page(host, page)
        jobs = data.get("jobs") or []
        if total is None:
            total = data.get("totalCount") or 0
        if not jobs:
            return
        for entry in jobs:
            d = entry.get("data") or {}
            if d:
                yield d
        seen += len(jobs)
        if total and seen >= total:
            return
        page += 1


def _build_url(d: dict, host: str) -> str:
    # tags7 typically holds the public job-page URL; fall back to slug-based path.
    tags7 = d.get("tags7") or []
    if tags7 and isinstance(tags7[0], str) and tags7[0].startswith("http"):
        return tags7[0]
    slug = d.get("slug") or d.get("req_id") or ""
    return f"https://{host}/main/jobs/{slug}"


def _build_location(d: dict) -> str:
    # `full_location` already joins primary + additional locations.
    full = (d.get("full_location") or "").strip()
    if full:
        return full
    parts = [d.get("location_name")]
    for al in d.get("additional_locations") or []:
        if isinstance(al, dict):
            parts.append(al.get("location_name"))
    return "; ".join(p for p in parts if p)


def fetch(company: dict, source: dict) -> list[dict]:
    host = source["host"]
    out: list[dict] = []
    for d in _iter_jobs(host):
        title = (d.get("title") or "").strip()
        if not title:
            continue
        category = categorize_title(title)
        if not category:
            continue
        location = _build_location(d)
        if not location_matches(location):
            continue
        slug = d.get("slug") or d.get("req_id")
        if not slug:
            continue
        out.append(
            {
                "job_id": f"{company_slug(company['name'])}-{slug}",
                "company": company["name"],
                "tier": company["tier"],
                "category": category,
                "title": title,
                "location": location,
                "url": _build_url(d, host),
                "posted_date": (d.get("posted_date") or "").strip(),
                "_raw_d": d,  # stash raw for description reuse
            }
        )
    return out


def fetch_description(source: dict, posting: dict) -> str:
    """Phenom embeds description inline at list time — no extra HTTP call.

    The orchestrator calls fetch_description on a posting that came from
    fetch(), so the raw dict was stashed under `_raw_d`. If the raw payload
    is missing (e.g., the row was reconstructed from the CSV), fall back to
    a no-op empty string; the LLM will degrade gracefully.
    """
    raw = posting.get("_raw_d") or {}
    parts = [
        raw.get("description") or "",
        raw.get("responsibilities") or "",
        raw.get("qualifications") or "",
    ]
    return "\n\n".join(p for p in parts if p)
