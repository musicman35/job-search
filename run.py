"""Daily orchestrator: fetch → diff → enrich (LLM) → write CSV → email.

Run modes:
  python run.py                                  # full daily run
  python run.py --dry-run                        # don't write CSV, don't send email
  python run.py --skip-llm                       # skip LLM enrichment (empty fields)
  python run.py --no-email                       # always skip the email step
  python run.py --companies "LexisNexis,AIG"     # limit to substring-matched companies

Failure model:
  - Per-source fetcher failure: caught, logged, recorded in run_stats.failed.
  - All fetchers failed: exit code 2 (workflow should fail).
  - Per-posting description fetch failure: empty description, LLM still called.
  - LLM batch failure: row written with empty enrichment fields (degraded).
  - Email failure: logged, never fails the run.
"""

import argparse
import datetime
import os
import sys

import config
from dotenv import load_env
from fetchers import phenom, workday
from llm import extract_and_score, extract_and_score_batch
from notify import build_email, send_email
from storage import build_new_row, diff_postings, load_csv, save_csv

FETCHERS_BY_TYPE = {
    "workday": workday,
    "phenom": phenom,
}

_SMTP_VARS = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "EMAIL_FROM", "EMAIL_TO")


def _today() -> str:
    return datetime.date.today().isoformat()


def _label(company: dict, source: dict) -> str:
    leaf = source.get("site") or source.get("host", "")
    return f"{company['name']} ({source['type']}:{leaf})"


def fetch_all(companies: list[dict]) -> tuple[list[dict], list[str], list[tuple[str, str]]]:
    """Run every fetcher. Returns (postings, succeeded_labels, failed_pairs)."""
    postings: list[dict] = []
    succeeded: list[str] = []
    failed: list[tuple[str, str]] = []
    for company in companies:
        for source in company["sources"]:
            label = _label(company, source)
            fetcher = FETCHERS_BY_TYPE.get(source["type"])
            if fetcher is None:
                failed.append((label, f"no fetcher implemented for type={source['type']!r}"))
                print(f"[skip] {label}: fetcher not implemented", flush=True)
                continue
            try:
                hits = fetcher.fetch(company, source)
                postings.extend(hits)
                succeeded.append(label)
                print(f"[ok]   {label}: {len(hits)} matched", flush=True)
            except Exception as e:
                failed.append((label, f"{type(e).__name__}: {e}"))
                print(f"[fail] {label}: {type(e).__name__}: {e}", flush=True)
    return postings, succeeded, failed


def _source_for(posting: dict, companies: list[dict]) -> dict | None:
    """Find the originating source dict for a fetched posting (by company name + url host)."""
    url = posting.get("url", "")
    for company in companies:
        if company["name"] != posting.get("company"):
            continue
        for source in company["sources"]:
            host = source.get("host", "")
            if host and host in url:
                return source
    return None


def _fetch_description_safe(source: dict | None, posting: dict) -> str:
    if source is None:
        return ""
    fetcher = FETCHERS_BY_TYPE.get(source["type"])
    if fetcher is None or not hasattr(fetcher, "fetch_description"):
        return ""
    try:
        return fetcher.fetch_description(source, posting)
    except Exception as e:
        print(f"[warn] description fetch failed for {posting.get('job_id')}: {e}", flush=True)
        return ""


def enrich_new(
    new_postings: list[dict],
    companies: list[dict],
    today: str,
    *,
    use_batch: bool = True,
) -> list[dict]:
    """Fetch descriptions + run LLM + build full CSV rows. Empty if no new postings."""
    if not new_postings:
        return []

    items = []
    for p in new_postings:
        source = _source_for(p, companies)
        desc = _fetch_description_safe(source, p)
        items.append({
            "title": p["title"],
            "company": p["company"],
            "location_hint": p["location"],
            "description": desc,
        })

    try:
        if use_batch:
            print(f"running LLM batch on {len(items)} new postings (Batch API) ...", flush=True)
            llm_results = extract_and_score_batch(items)
        else:
            print(f"running LLM synchronously on {len(items)} new postings ...", flush=True)
            llm_results = [extract_and_score(**it) for it in items]
            for r in llm_results:
                r.pop("_usage", None)
    except Exception as e:
        print(f"[warn] LLM step failed: {type(e).__name__}: {e}; writing rows with empty enrichment", flush=True)
        llm_results = [{} for _ in items]

    return [build_new_row(p, llm, today) for p, llm in zip(new_postings, llm_results)]


def emit_github_output(new_count: int, closed_count: int) -> None:
    """If running inside GitHub Actions, emit step outputs for the commit message."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"new_count={new_count}\n")
        f.write(f"closed_count={closed_count}\n")


def maybe_send_email(
    new_rows: list[dict],
    closed_rows: list[dict],
    run_stats: dict,
    today: str,
    *,
    skip: bool,
) -> None:
    """Build the email, send it. Skipped or missing-creds paths log and return."""
    built = build_email(new_rows, closed_rows, run_stats, today)
    if built is None:
        print("nothing new and nothing closed — no email", flush=True)
        return
    subject, body = built
    if skip:
        print(f"[skip email] subject would have been: {subject!r}", flush=True)
        return
    missing = [v for v in _SMTP_VARS if not os.environ.get(v)]
    if missing:
        print(f"[skip email] SMTP env vars missing: {missing}", flush=True)
        return
    try:
        send_email(subject, body)
        print(f"sent email: {subject!r}", flush=True)
    except Exception as e:
        print(f"[warn] email send failed (continuing): {type(e).__name__}: {e}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily job-tracker run")
    parser.add_argument("--dry-run", action="store_true",
                        help="don't write CSV, don't send email")
    parser.add_argument("--no-email", action="store_true",
                        help="always skip email even when SMTP is configured")
    parser.add_argument("--skip-llm", action="store_true",
                        help="skip LLM enrichment; new rows get empty enrichment fields")
    parser.add_argument("--sync-llm", action="store_true",
                        help="run LLM calls synchronously instead of via Batch API (faster for tiny runs)")
    parser.add_argument("--companies", default="",
                        help="comma-separated company-name substrings to limit the run")
    args = parser.parse_args()

    load_env()

    companies = list(config.COMPANIES)
    if args.companies:
        wants = [w.strip().lower() for w in args.companies.split(",") if w.strip()]
        companies = [c for c in companies if any(w in c["name"].lower() for w in wants)]
        print(f"limited to {len(companies)} compan(ies): {[c['name'] for c in companies]}", flush=True)

    today = _today()
    print(f"=== job-tracker run {today} ===", flush=True)

    fetched, succeeded, failed = fetch_all(companies)

    if not succeeded:
        print("ERROR: every fetcher failed; aborting.", flush=True)
        for label, err in failed:
            print(f"  - {label}: {err}", flush=True)
        return 2

    print(
        f"fetched {len(fetched)} matching posting(s) from {len(succeeded)}/{len(succeeded) + len(failed)} source(s)",
        flush=True,
    )

    existing = load_csv(config.CSV_PATH)
    updated_existing, new_to_enrich, freshly_closed = diff_postings(existing, fetched, today)
    print(
        f"diff: {len(new_to_enrich)} new, {len(freshly_closed)} freshly closed, "
        f"{len(updated_existing)} carried over",
        flush=True,
    )

    if args.skip_llm:
        print(f"[skip llm] building {len(new_to_enrich)} new row(s) with empty enrichment", flush=True)
        new_rows = [build_new_row(p, {}, today) for p in new_to_enrich]
    else:
        new_rows = enrich_new(new_to_enrich, companies, today, use_batch=not args.sync_llm)

    all_rows = updated_existing + new_rows
    if args.dry_run:
        print(f"[dry-run] would write {len(all_rows)} rows to {config.CSV_PATH}", flush=True)
    else:
        save_csv(config.CSV_PATH, all_rows)
        print(f"wrote {len(all_rows)} rows to {config.CSV_PATH}", flush=True)

    run_stats = {"succeeded": succeeded, "failed": failed}
    maybe_send_email(
        new_rows, freshly_closed, run_stats, today,
        skip=args.no_email or args.dry_run,
    )

    emit_github_output(len(new_rows), len(freshly_closed))
    print(f"=== done: {len(new_rows)} new, {len(freshly_closed)} closed ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
