# job-tracker

Daily tracker for DS/ML/AI individual-contributor roles and rotational /
development programs across 8 target companies. Runs on GitHub Actions
(8 AM ET cron), writes a CSV back to the repo, and optionally emails a
summary of new postings.

| | |
|---|---|
| **Target companies** | LexisNexis · AIG · Home Depot · Cox · Truist · State Farm · Dick's Sporting Goods · Bank of America |
| **Sources** | 8 Workday tenants (incl. 2 AIG sites) · 1 Phenom site (State Farm) |
| **Filters** | Atlanta-area or US-remote · IC keywords (data scientist, ML, GenAI, MLOps, …) · rotational/development programs |
| **Enrichment** | Claude Haiku 4.5 — extracts location, remote_type, category, track, key_reqs, fit_score (1–10), fit_reasoning |
| **Schedule** | Daily 13:00 UTC (8 AM ET standard / 9 AM ET DST) |

## Quick start (local)

Prerequisites: **Python 3.13**, **[uv](https://github.com/astral-sh/uv)**.

```bash
git clone https://github.com/musicman35/job-search.git
cd job-search
uv venv
uv pip install -r requirements.txt
cp .env.example .env   # then fill in secrets — see below
uv run python run.py --dry-run --skip-llm    # smoke test (no API spend, no CSV write)
```

## `.env` setup

Copy `.env.example` to `.env` and fill in:

```bash
ANTHROPIC_API_KEY=sk-ant-...            # required
SMTP_HOST=smtp.gmail.com                # optional — leave SMTP_* blank to skip email
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASS=xxxx-xxxx-xxxx-xxxx           # Gmail app password (see below)
EMAIL_FROM=you@gmail.com
EMAIL_TO=you@gmail.com
```

### Gmail app password (only if you want email summaries)

Gmail blocks raw-password SMTP. You need a 16-character app password:

1. Enable 2-factor auth at https://myaccount.google.com/security
2. Go to https://myaccount.google.com/apppasswords
3. Name it `job-tracker` and generate. Copy the 16-character string (no spaces)
4. Paste into `.env` as `SMTP_PASS` and copy the same email into `SMTP_USER` /
   `EMAIL_FROM` / `EMAIL_TO`

If you skip these, `run.py` logs a `[skip email]` line and continues — the
CSV still gets written.

## Running

| Command | What it does |
|---|---|
| `uv run python run.py` | Full daily run: fetch → diff → batch LLM → write CSV → email |
| `uv run python run.py --dry-run` | Run the whole pipeline but don't write CSV or send email |
| `uv run python run.py --skip-llm` | Skip the LLM step; new rows get empty enrichment fields |
| `uv run python run.py --sync-llm` | Use synchronous LLM calls instead of Batch API (faster for small runs; 2× the cost) |
| `uv run python run.py --no-email` | Always skip the email step, even if SMTP is configured |
| `uv run python run.py --companies "AIG,Truist"` | Limit to substring-matched company names |

### Failure model

- **One fetcher fails** → caught, logged, surfaced in the email's run-stats
  section; other sources continue
- **All fetchers fail** → exit code 2 (the GitHub Actions workflow fails and
  no commit is made)
- **One posting's description fetch fails** → empty description, LLM still
  called on the rest
- **LLM batch fails entirely** → rows still get written to the CSV with
  empty enrichment fields and a `(LLM error)` note
- **Email fails** → logged as a warning, run completes successfully

## Tests

```bash
uv run python test_storage.py    # 20 unit tests on diff state machine
uv run python test_llm.py        # live LLM test on two real AIG postings — costs ~$0.01
uv run python test_notify.py --preview     # build email preview (no send)
uv run python test_notify.py     # build + send email to EMAIL_TO
```

## GitHub Actions

The workflow at `.github/workflows/daily.yml` runs on cron and on manual
dispatch. Required setup in the repo:

1. Go to **Settings → Secrets and variables → Actions**
2. Add `ANTHROPIC_API_KEY` (required) and the six `SMTP_*` / `EMAIL_*` secrets
   from above (optional — workflow skips email if missing)
3. Workflow permissions are set inside the YAML (`contents: write`) so the
   default `GITHUB_TOKEN` can commit `data/jobs.csv` back

**Manual run:** Go to the Actions tab → "Daily job tracker" → "Run workflow".

**Commit message format:** `daily run: YYYY-MM-DD (N new, M closed)`

## CSV schema (`data/jobs.csv`)

| Column | Source | Notes |
|---|---|---|
| `job_id` | fetcher | `{company-slug}-{req-number}`, stable across runs |
| `company` | config | |
| `tier` | config | 1, 2, or 3 |
| `category` | LLM (or fetcher fallback) | `ic` or `rotational` |
| `track` | LLM | Rotational only — controlled vocabulary, see `config.TRACK_VOCAB` |
| `title` | fetcher | |
| `location` | LLM (or fetcher fallback) | |
| `remote_type` | LLM | `Remote` / `Hybrid` / `Onsite` / `Unclear` |
| `url` | fetcher | Direct link to the posting |
| `posted_date` | fetcher | Raw string from the ATS, e.g. `"Posted 5 Days Ago"` |
| `first_seen` | run.py | ISO date the posting first appeared in a fetch |
| `last_seen` | run.py | ISO date of the most recent fetch that found it |
| `status` | lifecycle | `new` → `open` → `closed`, or manually `applied` / `interviewing` / `rejected` |
| `fit_score` | LLM | 1–10 |
| `key_reqs` | LLM | 3–5 newline-joined bullets |
| `notes` | manual | Free-form; **never touched by the script** |

### Status lifecycle

- **Day 1** the posting is first seen → `new`
- **Day 2+** the posting is still posted → auto-promoted to `open`,
  `last_seen` is bumped
- The posting disappears from the next fetch → flipped to `closed`,
  **unless** you've set the status manually to `applied`, `interviewing`,
  or `rejected` (those are preserved untouched)
- `closed` rows that re-appear (rare — usually a reposting under a new
  job_id) stay `closed`; the new posting comes in as its own `new` row
- Same-day re-runs don't prematurely promote `new` → `open`

## Email top-picks rule

The email's "Top picks" section surfaces new postings meeting **either**:

- `category=ic` with `fit_score ≥ 7`, OR
- `category=rotational` with `fit_score ≥ 6` AND `track` in {Data Science,
  Analytics, Software Engineering, Data Engineering, Mixed Technical}

Everything else new goes to "Other new postings". See
`config.TECHNICAL_TRACKS` for the rotational-track allowlist.

## Customizing

| What | Where |
|---|---|
| Add/remove a company | `COMPANIES` list in `config.py` |
| Change tier | `tier` field in `config.py` |
| Add IC keyword | `IC_KEYWORDS` in `config.py` |
| Add rotational keyword | `ROTATIONAL_KEYWORDS` in `config.py` |
| Adjust location filter | `LOCATION_KEYWORDS` in `config.py` |
| Update profile (used for fit scoring) | `USER_PROFILE` string in `config.py` |
| Add a new ATS type | New module in `fetchers/`, register in `run.py: FETCHERS_BY_TYPE` |

## File layout

```
.
├── config.py                          # companies, filters, profile, schema
├── filters.py                         # categorize_title, location_matches
├── fetchers/
│   ├── workday.py                     # generic Workday (8 of 9 sources)
│   └── phenom.py                      # State Farm
├── storage.py                         # CSV load/save + diff state machine
├── llm.py                             # Claude Haiku 4.5 extract+score
├── notify.py                          # HTML email builder + SMTP send
├── run.py                             # orchestrator
├── dotenv.py                          # minimal .env loader
├── test_storage.py                    # 20 unit tests
├── test_llm.py                        # live LLM smoke test
├── test_notify.py                     # email builder + send test
├── data/
│   └── jobs.csv                       # written by run.py, committed by CI
├── .github/workflows/daily.yml        # GH Actions cron
└── .env.example                       # template for local .env
```

## Known gaps

- **BoA campus rotational programs** (Analyst Development Program, Global
  Tech Analyst, etc.) live on `bankcampuscareers.tal.net` which is
  SSO-locked WCN — no public anonymous API. The Workday `Lateral-US`
  source still catches BoA's experienced IC roles. Monitor campus
  programs manually at
  https://careers.bankofamerica.com/en-us/programs/early-career-programs
  (they post in annual batches).
- **Multi-location Workday postings** are resolved by fetching each
  posting's detail endpoint; this adds a few extra HTTP calls per company
  per run.
- **Prompt caching** is wired but the system prompt is currently below
  Haiku's 1024-token minimum to activate. No cost impact at current
  volume; will activate automatically if the system prompt grows.
