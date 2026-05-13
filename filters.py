"""Shared keyword + location filters. Used by every fetcher."""

import re

from config import (
    IC_EXCLUDES,
    IC_KEYWORDS,
    LOCATION_KEYWORDS,
    ROTATIONAL_KEYWORDS,
)


def categorize_title(title: str) -> str | None:
    """Return 'rotational', 'ic', or None.

    Rotational wins ties: a 'Principal Analytics Rotational Program' title hits
    both keyword lists but should be classified as rotational, where the IC
    exclude list is not applied (per spec).
    """
    t = title.lower()
    if any(k in t for k in ROTATIONAL_KEYWORDS):
        return "rotational"
    if any(k in t for k in IC_KEYWORDS) and not any(x in t for x in IC_EXCLUDES):
        return "ic"
    return None


def location_matches(location: str) -> bool:
    l = location.lower()
    return any(k in l for k in LOCATION_KEYWORDS)


_slug_re = re.compile(r"[^a-z0-9]+")


def company_slug(name: str) -> str:
    return _slug_re.sub("-", name.lower()).strip("-")
