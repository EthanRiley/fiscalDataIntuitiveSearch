"""Fetches and caches the Fiscal Data API metadata catalog."""

import requests

METADATA_URL = "https://api.fiscaldata.treasury.gov/services/dtg/metadata/"

# Boilerplate date/index fields that add no value for chart selection
EXCLUDED_FIELD_NAMES = {
    "src_line_nbr",
    "record_fiscal_year",
    "record_fiscal_quarter",
    "record_calendar_year",
    "record_calendar_quarter",
    "record_calendar_month",
    "record_calendar_day",
}

# Endpoints that are very large and should only be surfaced if clearly the best match.
# These are given a score penalty in search() to deprioritize them.
LARGE_ENDPOINTS = {
    "v1/debt/tror/data_act_compliance",
    "v1/debt/tror",
}

_cache: list | None = None
_compact_cache: list | None = None


def get_metadata() -> list:
    """Return the full metadata catalog, fetching once and caching in memory."""
    global _cache
    if _cache is None:
        resp = requests.get(METADATA_URL, timeout=30)
        resp.raise_for_status()
        _cache = resp.json()
    return _cache


def get_compact_metadata() -> list:
    """
    Return a trimmed metadata list with title, endpoint, and field names + descriptions.
    - Boilerplate date/index fields are excluded.
    - Field types are omitted (the agent can infer from names/descriptions).
    - Used as the searchable index — not sent to Claude directly.
    """
    global _compact_cache
    if _compact_cache is not None:
        return _compact_cache

    raw = get_metadata()
    compact = []

    for dataset in raw:
        for api in dataset.get("apis", []):
            endpoint = (api.get("endpoint_txt") or "").replace("/services/api/fiscal_service/", "")
            fields = [
                {
                    "name": f["column_name"],
                    "description": f.get("definition", ""),
                }
                for f in api.get("fields", [])
                if f["column_name"] not in EXCLUDED_FIELD_NAMES
            ]
            compact.append({
                "title": dataset.get("title", ""),
                "endpoint": endpoint,
                "fields": fields,
            })

    _compact_cache = compact
    return _compact_cache


def search(keywords: list[str], top_n: int = 8) -> list:
    """
    Score every dataset against the provided keywords and return the top_n matches.

    Scoring:
      - Each keyword/word match in the dataset title counts as 3 points
      - Each keyword/word match in a field name counts as 2 points
      - Each keyword/word match in a field description counts as 1 point
    Large/expensive endpoints receive a 50% score penalty so they only surface
    when they are clearly the best match.
    """
    catalog = get_compact_metadata()

    # Build a flat set of search terms: each full phrase plus each individual word
    terms = set()
    for kw in keywords:
        kw = kw.strip().lower()
        if kw:
            terms.add(kw)
            for word in kw.split():
                if len(word) > 2:
                    terms.add(word)

    scored = []
    for dataset in catalog:
        score = 0
        title = dataset["title"].lower()

        for term in terms:
            if term in title:
                score += 3
            for field in dataset["fields"]:
                if term in field["name"].lower():
                    score += 2
                if term in field["description"].lower():
                    score += 1

        if score > 0:
            # Penalize large endpoints so they only appear when clearly best
            if any(dataset["endpoint"].startswith(ep) for ep in LARGE_ENDPOINTS):
                score = score * 0.5
            scored.append((score, dataset))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [dataset for _, dataset in scored[:top_n]]
