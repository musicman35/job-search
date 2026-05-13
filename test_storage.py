"""Unit tests for storage.diff_postings and friends. Run: python test_storage.py"""

import os
import tempfile

from storage import build_new_row, diff_postings, load_csv, save_csv

TODAY = "2026-05-11"
YESTERDAY = "2026-05-10"
OLDER = "2026-04-01"


def _row(job_id, status="open", last_seen=YESTERDAY, notes="", **extra):
    base = {
        "job_id": job_id,
        "company": "TestCo",
        "tier": "1",
        "category": "ic",
        "track": "",
        "title": f"Title {job_id}",
        "location": "Atlanta, GA",
        "remote_type": "",
        "url": f"https://example.com/{job_id}",
        "posted_date": "Posted 5 Days Ago",
        "first_seen": OLDER,
        "last_seen": last_seen,
        "status": status,
        "fit_score": "7",
        "key_reqs": "",
        "notes": notes,
    }
    base.update(extra)
    return base


def _posting(job_id):
    return {
        "job_id": job_id,
        "company": "TestCo",
        "tier": 1,
        "category": "ic",
        "title": f"Title {job_id}",
        "location": "Atlanta, GA",
        "url": f"https://example.com/{job_id}",
        "posted_date": "Posted Today",
    }


def test_new_posting_goes_to_enrichment():
    upd, new, closed = diff_postings([], [_posting("a")], TODAY)
    assert upd == []
    assert [n["job_id"] for n in new] == ["a"]
    assert closed == []


def test_seen_posting_bumps_last_seen():
    upd, new, closed = diff_postings(
        [_row("a", status="open", last_seen=YESTERDAY)],
        [_posting("a")],
        TODAY,
    )
    assert upd[0]["last_seen"] == TODAY
    assert upd[0]["status"] == "open"
    assert new == []
    assert closed == []


def test_missing_open_flips_to_closed():
    upd, _, closed = diff_postings([_row("a", status="open")], [], TODAY)
    assert upd[0]["status"] == "closed"
    assert [c["job_id"] for c in closed] == ["a"]


def test_missing_new_also_flips_to_closed():
    upd, _, closed = diff_postings([_row("a", status="new")], [], TODAY)
    assert upd[0]["status"] == "closed"
    assert [c["job_id"] for c in closed] == ["a"]


def test_missing_applied_status_preserved():
    upd, _, closed = diff_postings(
        [_row("a", status="applied", notes="phone screen Wed")],
        [],
        TODAY,
    )
    assert upd[0]["status"] == "applied"
    assert upd[0]["notes"] == "phone screen Wed"
    assert closed == []


def test_missing_interviewing_preserved():
    upd, _, closed = diff_postings([_row("a", status="interviewing")], [], TODAY)
    assert upd[0]["status"] == "interviewing"
    assert closed == []


def test_missing_rejected_preserved():
    upd, _, closed = diff_postings([_row("a", status="rejected")], [], TODAY)
    assert upd[0]["status"] == "rejected"
    assert closed == []


def test_already_closed_not_re_listed():
    upd, _, closed = diff_postings([_row("a", status="closed")], [], TODAY)
    assert upd[0]["status"] == "closed"
    assert closed == [], "already-closed row should not appear in freshly_closed"


def test_notes_never_touched_on_seen_row():
    upd, _, _ = diff_postings(
        [_row("a", status="open", notes="my own note")],
        [_posting("a")],
        TODAY,
    )
    assert upd[0]["notes"] == "my own note"


def test_diff_does_not_mutate_input_rows():
    original = _row("a", status="open", last_seen=YESTERDAY)
    diff_postings([original], [_posting("a")], TODAY)
    assert original["last_seen"] == YESTERDAY, "input row was mutated"
    assert original["status"] == "open"


def test_new_promotes_to_open_on_next_run():
    """A row with status=new and first_seen<today should flip to open when re-seen."""
    upd, _, _ = diff_postings(
        [_row("a", status="new", last_seen=YESTERDAY, first_seen=YESTERDAY)],
        [_posting("a")],
        TODAY,
    )
    assert upd[0]["status"] == "open"
    assert upd[0]["last_seen"] == TODAY


def test_new_stays_new_when_first_seen_today():
    """Defensive: if a row was just added today and we re-run (e.g., manual run),
    don't immediately promote it to open."""
    upd, _, _ = diff_postings(
        [_row("a", status="new", last_seen=TODAY, first_seen=TODAY)],
        [_posting("a")],
        TODAY,
    )
    assert upd[0]["status"] == "new"


def test_open_stays_open_when_re_seen():
    upd, _, _ = diff_postings(
        [_row("a", status="open", first_seen=OLDER)],
        [_posting("a")],
        TODAY,
    )
    assert upd[0]["status"] == "open"
    assert upd[0]["last_seen"] == TODAY


def test_manual_status_does_not_promote_when_re_seen():
    """applied/interviewing/rejected should not be touched on re-seen."""
    upd, _, _ = diff_postings(
        [_row("a", status="applied", first_seen=OLDER, notes="phone screen Wed")],
        [_posting("a")],
        TODAY,
    )
    assert upd[0]["status"] == "applied"
    assert upd[0]["notes"] == "phone screen Wed"
    assert upd[0]["last_seen"] == TODAY


def test_mixed_scenario():
    existing = [
        _row("seen_was_open", status="open", first_seen=OLDER),
        _row("seen_was_new", status="new", first_seen=YESTERDAY),
        _row("vanished", status="new"),
        _row("manual_applied", status="applied", notes="recruiter email"),
        _row("manual_interviewing", status="interviewing"),
        _row("already_closed", status="closed"),
    ]
    fetched = [
        _posting("seen_was_open"),
        _posting("seen_was_new"),
        _posting("brand_new"),
    ]
    upd, new, closed = diff_postings(existing, fetched, TODAY)

    by_id = {r["job_id"]: r for r in upd}
    assert by_id["seen_was_open"]["status"] == "open"
    assert by_id["seen_was_open"]["last_seen"] == TODAY
    assert by_id["seen_was_new"]["status"] == "open", "new should auto-promote to open"
    assert by_id["seen_was_new"]["last_seen"] == TODAY
    assert by_id["vanished"]["status"] == "closed"
    assert by_id["manual_applied"]["status"] == "applied"
    assert by_id["manual_applied"]["notes"] == "recruiter email"
    assert by_id["manual_interviewing"]["status"] == "interviewing"
    assert by_id["already_closed"]["status"] == "closed"

    assert [n["job_id"] for n in new] == ["brand_new"]
    assert [c["job_id"] for c in closed] == ["vanished"]


def test_build_new_row_uses_llm_authoritative_fields():
    row = build_new_row(
        _posting("a"),
        {
            "category": "ic",
            "track": "",
            "remote_type": "Hybrid",
            "fit_score": 8,
            "key_reqs": "Python; SQL; ML",
            "location": "Atlanta, GA (Hybrid)",
        },
        TODAY,
    )
    assert row["job_id"] == "a"
    assert row["status"] == "new"
    assert row["first_seen"] == TODAY
    assert row["last_seen"] == TODAY
    assert row["fit_score"] == 8
    assert row["remote_type"] == "Hybrid"
    assert row["location"] == "Atlanta, GA (Hybrid)"  # LLM overrides fetcher value
    assert row["notes"] == ""


def test_build_new_row_falls_back_to_fetcher_when_llm_missing():
    posting = _posting("a")
    row = build_new_row(posting, {}, TODAY)
    assert row["category"] == posting["category"]
    assert row["location"] == posting["location"]
    assert row["remote_type"] == ""
    assert row["track"] == ""


def test_csv_roundtrip_preserves_commas_and_quotes():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "jobs.csv")
        rows = [
            _row("a"),
            _row("b", notes='has, commas "and" quotes'),
        ]
        save_csv(path, rows)
        back = load_csv(path)
        assert len(back) == 2
        assert back[1]["notes"] == 'has, commas "and" quotes'


def test_load_missing_file_returns_empty():
    assert load_csv("/tmp/__nonexistent_dir_xyz__/jobs.csv") == []


def test_save_creates_parent_dir():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "nested", "deeper", "jobs.csv")
        save_csv(path, [_row("a")])
        assert os.path.exists(path)


if __name__ == "__main__":
    import sys
    tests = [
        ("new_posting_goes_to_enrichment", test_new_posting_goes_to_enrichment),
        ("seen_posting_bumps_last_seen", test_seen_posting_bumps_last_seen),
        ("missing_open_flips_to_closed", test_missing_open_flips_to_closed),
        ("missing_new_also_flips_to_closed", test_missing_new_also_flips_to_closed),
        ("missing_applied_preserved", test_missing_applied_status_preserved),
        ("missing_interviewing_preserved", test_missing_interviewing_preserved),
        ("missing_rejected_preserved", test_missing_rejected_preserved),
        ("already_closed_not_re_listed", test_already_closed_not_re_listed),
        ("notes_never_touched_on_seen_row", test_notes_never_touched_on_seen_row),
        ("diff_does_not_mutate_input_rows", test_diff_does_not_mutate_input_rows),
        ("new_promotes_to_open_on_next_run", test_new_promotes_to_open_on_next_run),
        ("new_stays_new_when_first_seen_today", test_new_stays_new_when_first_seen_today),
        ("open_stays_open_when_re_seen", test_open_stays_open_when_re_seen),
        ("manual_status_does_not_promote_when_re_seen", test_manual_status_does_not_promote_when_re_seen),
        ("mixed_scenario", test_mixed_scenario),
        ("build_new_row_uses_llm_authoritative_fields", test_build_new_row_uses_llm_authoritative_fields),
        ("build_new_row_falls_back_to_fetcher_when_llm_missing", test_build_new_row_falls_back_to_fetcher_when_llm_missing),
        ("csv_roundtrip_preserves_commas_and_quotes", test_csv_roundtrip_preserves_commas_and_quotes),
        ("load_missing_file_returns_empty", test_load_missing_file_returns_empty),
        ("save_creates_parent_dir", test_save_creates_parent_dir),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK  {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {name}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERR  {name}: {type(e).__name__}: {e}")
    print()
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
