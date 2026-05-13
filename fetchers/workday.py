"""Generic Workday fetcher. Covers any tenant exposing /wday/cxs/{tenant}/{site}/jobs."""

import re

import requests

from filters import categorize_title, company_slug, location_matches

PAGE_LIMIT = 20
TIMEOUT = 30
USER_AGENT = "Mozilla/5.0 (compatible; job-tracker/1.0)"

# Workday collapses 2+ locations into "N Locations" on the list endpoint.
# We then fetch the detail endpoint to recover the actual location list.
_MULTI_LOC_RE = re.compile(r"^\d+\s+locations?$", re.IGNORECASE)


def _post_page(host: str, tenant: str, site: str, offset: int) -> dict:
    url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    body = {
        "appliedFacets": {},
        "limit": PAGE_LIMIT,
        "offset": offset,
        "searchText": "",
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    r = requests.post(url, json=body, headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _iter_raw_postings(host: str, tenant: str, site: str):
    # Workday quirks observed: `total` is only populated on the first page;
    # past the real end, Workday *wraps* and serves offset=0 again forever.
    # So: capture `total` from the first response and stop when reached.
    offset = 0
    total: int | None = None
    while True:
        data = _post_page(host, tenant, site, offset)
        page = data.get("jobPostings") or []
        if total is None:
            total = data.get("total") or 0
        if not page:
            return
        for p in page:
            yield p
        offset += len(page)
        if total and offset >= total:
            return


def _fetch_detail(host: str, tenant: str, site: str, external_path: str) -> dict:
    """GET the Workday detail endpoint for one posting. Raises on non-200."""
    url = f"https://{host}/wday/cxs/{tenant}/{site}{external_path}"
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    r = requests.get(url, headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json() or {}


def _fetch_detail_locations(host: str, tenant: str, site: str, external_path: str) -> list[str]:
    info = _fetch_detail(host, tenant, site, external_path).get("jobPostingInfo") or {}
    locs: list[str] = []
    primary = info.get("location")
    if primary:
        locs.append(str(primary))
    for al in info.get("additionalLocations") or []:
        if isinstance(al, str):
            locs.append(al)
        elif isinstance(al, dict):
            name = al.get("descriptor") or al.get("name")
            if name:
                locs.append(str(name))
    return locs


def fetch_description(source: dict, posting: dict) -> str:
    """Return the raw HTML jobDescription for a single posting."""
    host = source["host"]
    prefix = f"https://{host}"
    url = posting.get("url", "")
    if not url.startswith(prefix):
        return ""
    external_path = url[len(prefix):]
    info = _fetch_detail(host, source["tenant"], source["site"], external_path).get("jobPostingInfo") or {}
    return str(info.get("jobDescription") or "")


def _job_id(company: str, raw: dict) -> str | None:
    """Prefer bulletFields[0] (requisition number); fall back to externalPath tail."""
    bullets = raw.get("bulletFields") or []
    if bullets and bullets[0]:
        return f"{company_slug(company)}-{bullets[0]}"
    path = raw.get("externalPath") or ""
    if "_" in path:
        return f"{company_slug(company)}-{path.rsplit('_', 1)[-1]}"
    return None


def fetch(company: dict, source: dict) -> list[dict]:
    """Fetch + filter + normalize a single Workday source."""
    host, tenant, site = source["host"], source["tenant"], source["site"]
    out: list[dict] = []
    for raw in _iter_raw_postings(host, tenant, site):
        title = (raw.get("title") or "").strip()
        location = (raw.get("locationsText") or "").strip()
        external_path = raw.get("externalPath") or ""
        if not title or not external_path:
            continue
        category = categorize_title(title)
        if not category:
            continue
        # Title matched. Now check location, expanding multi-location postings.
        if not location_matches(location):
            if _MULTI_LOC_RE.match(location):
                detail_locs = _fetch_detail_locations(host, tenant, site, external_path)
                if not any(location_matches(l) for l in detail_locs):
                    continue
                location = "; ".join(detail_locs)
            else:
                continue
        job_id = _job_id(company["name"], raw)
        if not job_id:
            continue
        out.append(
            {
                "job_id": job_id,
                "company": company["name"],
                "tier": company["tier"],
                "category": category,
                "title": title,
                "location": location,
                "url": f"https://{host}{external_path}",
                "posted_date": (raw.get("postedOn") or "").strip(),
            }
        )
    return out
