"""Build a sample email from synthetic data, save a preview, and send.

Run: python test_notify.py            # builds preview + sends
     python test_notify.py --preview  # builds preview only, no send

Loads .env if present.
"""

import os
import sys
import tempfile

# Load .env quietly (no values echoed).
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from notify import build_email, send_email  # noqa: E402

TODAY = "2026-05-11"

# Synthetic data covering all branches: top-pick IC, top-pick rotational,
# below-threshold IC, below-threshold rotational (wrong track), closed rows,
# and a fetcher failure in run_stats.
NEW_ROWS = [
    {
        "job_id": "aig-JR2600925",
        "company": "AIG",
        "tier": "1",
        "category": "ic",
        "track": "",
        "title": "Ph.D. Research Data Scientist, GenAI",
        "location": "Atlanta, GA",
        "url": "https://aig.wd1.myworkdayjobs.com/job/GA-Atlanta/PhD-Research-Data-Scientist--GenAI_JR2600925",
        "fit_score": 8,
        "fit_reasoning": "Strong alignment on RAG, multi-agent systems, GenAI; Ph.D. requirement is a stretch but research portfolio could compensate.",
    },
    {
        "job_id": "lexisnexis-R111919",
        "company": "LexisNexis",
        "tier": "1",
        "category": "ic",
        "track": "",
        "title": "Data Scientist",
        "location": "Remote - USA - Nationwide",
        "url": "https://relx.wd3.myworkdayjobs.com/job/Remote---USA---Nationwide/Data-Scientist_R111919-1",
        "fit_score": 9,
        "fit_reasoning": "Fully remote, mid-level DS role aligned with candidate's profile and recent Truist CLEAR work.",
    },
    {
        "job_id": "boa-ADP-2026",
        "company": "Bank of America",
        "tier": "3",
        "category": "rotational",
        "track": "Mixed Technical",
        "title": "2026 Analyst Development Program — Atlanta",
        "location": "Atlanta, GA",
        "url": "https://bankcampuscareers.tal.net/candidate/jobs/12345",
        "fit_score": 7,
        "fit_reasoning": "Multi-track rotational program with confirmed data/analytics rotation; strong early-career fit.",
    },
    {
        "job_id": "truist-RTP-001",
        "company": "Truist",
        "tier": "2",
        "category": "rotational",
        "track": "Data Engineering",
        "title": "Truist Leadership Development Program — Data Engineering",
        "location": "Atlanta, GA",
        "url": "https://truist.wd1.myworkdayjobs.com/Careers/job/LDP-Data-Eng_R12345",
        "fit_score": 8,
        "fit_reasoning": "Data engineering rotation aligns directly with Truist CLEAR experience and Python/Snowflake background.",
    },
    {
        "job_id": "aig-JR2502924",
        "company": "AIG",
        "tier": "1",
        "category": "ic",
        "track": "",
        "title": "Technical Capability Manager - GenAI",
        "location": "Atlanta, GA",
        "url": "https://aig.wd1.myworkdayjobs.com/job/GA-Atlanta/Technical-Capability-Manager---GenAI_JR2502924",
        "fit_score": 5,
        "fit_reasoning": "Manager-level role with mixed technical/operational responsibilities; experience gap.",
    },
    {
        "job_id": "aig-JR2601179",
        "company": "AIG",
        "tier": "1",
        "category": "rotational",
        "track": "Mixed Business",
        "title": "2026 Business Analyst Rotational Apprentice Program",
        "location": "Atlanta, GA",
        "url": "https://aig.wd1.myworkdayjobs.com/job/GA-Atlanta/JR2601179",
        "fit_score": 3,
        "fit_reasoning": "Pure business operations rotation, no data/ML/eng exposure; candidate overqualified.",
    },
    {
        "job_id": "cox-CR-123",
        "company": "Cox",
        "tier": "2",
        "category": "ic",
        "track": "",
        "title": "Machine Learning Engineer",
        "location": "Atlanta, GA",
        "url": "https://cox.wd1.myworkdayjobs.com/Cox_External_Career_Site_1/job/ML-Eng_CR-123",
        "fit_score": 6,
        "fit_reasoning": "Mid-level ML eng role; reasonable but not exceptional fit.",
    },
]

CLOSED_ROWS = [
    {
        "title": "Senior Data Scientist II",
        "company": "LexisNexis",
    },
    {
        "title": "AI Engineer, GenAI Platform",
        "company": "AIG",
    },
]

RUN_STATS = {
    "succeeded": [
        "LexisNexis",
        "AIG",
        "Home Depot",
        "Cox",
        "Truist",
        "Dick's Sporting Goods",
        "Bank of America",
    ],
    "failed": [
        ("State Farm", "iCIMS endpoint returned HTTP 503"),
    ],
}


def main() -> int:
    preview_only = "--preview" in sys.argv

    built = build_email(NEW_ROWS, CLOSED_ROWS, RUN_STATS, TODAY)
    if built is None:
        print("build_email returned None — nothing to report (unexpected for this test)")
        return 1
    subject, body = built

    # Always write the preview so it can be inspected in a browser.
    preview_path = os.path.join(tempfile.gettempdir(), "job-tracker-email-preview.html")
    with open(preview_path, "w", encoding="utf-8") as f:
        f.write(body)
    print(f"Subject: {subject}")
    print(f"HTML preview written to: {preview_path}  ({len(body)} chars)")
    print(f"  Open with: open {preview_path}")

    if preview_only:
        print("(--preview) skipping send")
        return 0

    missing = [v for v in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "EMAIL_FROM", "EMAIL_TO") if not os.environ.get(v)]
    if missing:
        print(f"\nSMTP env vars missing: {missing}", file=sys.stderr)
        print("Populate .env or set them in the shell before sending. Preview file is ready.", file=sys.stderr)
        return 2

    print(f"\nSending to {os.environ['EMAIL_TO']} via {os.environ['SMTP_HOST']}:{os.environ['SMTP_PORT']} ...")
    send_email(subject, body)
    print("Sent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
