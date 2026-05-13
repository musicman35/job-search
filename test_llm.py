"""Live LLM test on two real AIG postings — one IC, one rotational.

Requires ANTHROPIC_API_KEY in the environment. Loads from .env if present.

Run: python test_llm.py
"""

import json
import os
import sys

import requests

# Load .env into os.environ if present (without printing or echoing secrets).
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

if not os.environ.get("ANTHROPIC_API_KEY"):
    print("ANTHROPIC_API_KEY missing — set it in .env or your shell.", file=sys.stderr)
    sys.exit(2)

from llm import extract_and_score  # noqa: E402

WORKDAY_HEADERS = {"Accept": "application/json", "User-Agent": "Mozilla/5.0 (job-tracker test)"}


def fetch_workday_description(host: str, tenant: str, site: str, external_path: str) -> str:
    url = f"https://{host}/wday/cxs/{tenant}/{site}{external_path}"
    r = requests.get(url, headers=WORKDAY_HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()["jobPostingInfo"].get("jobDescription", "")


# Two real AIG postings (Workday tenant=aig, site=aig).
TEST_CASES = [
    {
        "label": "IC: GenAI Data Scientist",
        "title": "Ph.D. Research Data Scientist, GenAI",
        "company": "AIG",
        "location_hint": "GA-Atlanta",
        "external_path": "/job/GA-Atlanta/PhD-Research-Data-Scientist--GenAI_JR2600925",
    },
    {
        "label": "Rotational: Business Analyst Rotational",
        "title": "2026 – Early Career – Global Business Operations – Business Analyst Rotational Apprentice Program – Atlanta, GA",
        "company": "AIG",
        "location_hint": "GA-Atlanta",
        "external_path": "/job/GA-Atlanta/XMLNAME-2026---Early-Career---Global-Business-Operations---Business-Analyst-Rotational-Apprentice-Program---Atlanta--GA_JR2601179",
    },
]


def main() -> int:
    for tc in TEST_CASES:
        print("=" * 80)
        print(f"  {tc['label']}")
        print(f"  {tc['title']}")
        print("=" * 80)
        desc = fetch_workday_description(
            host="aig.wd1.myworkdayjobs.com",
            tenant="aig",
            site="aig",
            external_path=tc["external_path"],
        )
        print(f"description chars: {len(desc)}")
        result = extract_and_score(
            title=tc["title"],
            company=tc["company"],
            location_hint=tc["location_hint"],
            description=desc,
        )
        usage = result.pop("_usage", {})
        print(json.dumps(result, indent=2))
        print(f"usage: {usage}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
