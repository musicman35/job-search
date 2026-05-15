"""CSV load/save + diff logic for tracked job postings."""

import csv
import os
from typing import Iterable

from config import ACTIVE_STATUSES, CSV_COLUMNS


def load_csv(path: str) -> list[dict]:
    """Return all rows. Empty list if the file is missing or empty."""
    if not os.path.exists(path):
        return []
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_csv(path: str, rows: Iterable[dict]) -> None:
    """Write rows in canonical column order. Missing keys become empty strings."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in CSV_COLUMNS})


def diff_postings(
    existing: list[dict],
    fetched: list[dict],
    today: str,
    successful_companies: set[str] | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Diff fetched postings against CSV state.

    Returns (updated_existing, new_to_enrich, freshly_closed):
      updated_existing — every row from `existing`, copied, with `last_seen`
        bumped to `today` for rows still in fetched, and `status` flipped to
        "closed" for rows missing from fetched whose status was new/open.
        Status=new auto-promotes to "open" on any run after first_seen so the
        two states stay distinct: "new" = appeared this run, "open" = still
        posted on a later run, no action taken. Manual statuses
        (applied/interviewing/rejected) and already-closed rows are preserved
        untouched. The `notes` column is never modified.
      new_to_enrich — fetched postings whose job_id is not in existing.
        Orchestrator passes these to the LLM, then to `build_new_row`.
      freshly_closed — subset of updated_existing whose status flipped this
        run (for the email summary). Does not include already-closed rows.

    `successful_companies` — if provided, rows whose `company` field is NOT
    in this set are left untouched (no `last_seen` bump, no closing). This
    prevents a fetcher failure (or a partial `--companies` run) from
    incorrectly marking healthy postings as closed just because we didn't
    check on them this run. Pass None to diff against the full universe.
    """
    fetched_by_id = {p["job_id"]: p for p in fetched}
    existing_ids = {r["job_id"] for r in existing}

    updated_existing: list[dict] = []
    freshly_closed: list[dict] = []
    for src_row in existing:
        row = dict(src_row)  # never mutate caller's data
        if successful_companies is not None and row.get("company") not in successful_companies:
            # This company's sources weren't successfully fetched this run.
            # We have no evidence about whether its postings still exist.
            updated_existing.append(row)
            continue
        if row["job_id"] in fetched_by_id:
            row["last_seen"] = today
            if row.get("status") == "new" and row.get("first_seen") != today:
                row["status"] = "open"
        elif row.get("status") in ACTIVE_STATUSES:
            row["status"] = "closed"
            freshly_closed.append(row)
        updated_existing.append(row)

    new_to_enrich = [p for p in fetched if p["job_id"] not in existing_ids]
    return updated_existing, new_to_enrich, freshly_closed


def build_new_row(posting: dict, llm_fields: dict, today: str) -> dict:
    """Combine a fetched posting + LLM enrichment into a full CSV row.

    The LLM is authoritative for category/location (it has the full description);
    fetcher values are fallbacks. `key_reqs` arrives as a joined string from the
    LLM step (newline- or semicolon-separated, whatever llm.py produces).

    `fit_reasoning` is carried on the row dict so the email step can render
    it, but `save_csv` filters to CSV_COLUMNS so it is NOT persisted.
    """
    return {
        "job_id": posting["job_id"],
        "company": posting["company"],
        "tier": posting["tier"],
        "category": llm_fields.get("category") or posting.get("category", ""),
        "track": llm_fields.get("track", ""),
        "title": posting["title"],
        "location": llm_fields.get("location") or posting.get("location", ""),
        "remote_type": llm_fields.get("remote_type", ""),
        "url": posting["url"],
        "posted_date": posting.get("posted_date", ""),
        "first_seen": today,
        "last_seen": today,
        "status": "new",
        "fit_score": llm_fields.get("fit_score", ""),
        "key_reqs": llm_fields.get("key_reqs", ""),
        "notes": "",
        "fit_reasoning": llm_fields.get("fit_reasoning", ""),  # ephemeral
    }
