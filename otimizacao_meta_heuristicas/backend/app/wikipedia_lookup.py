"""Real, free, structured team data via the public Wikipedia REST API.

No API key required and no scraping/HTML parsing: Wikipedia's REST summary
endpoint returns a stable JSON payload (title, description, extract, crest/
photo thumbnail, canonical page url). This is the one genuinely reliable
"online base" for team facts and imagery that the app can depend on without
a paid provider.
"""
from __future__ import annotations

from functools import lru_cache
import json
import urllib.error
import urllib.parse
import urllib.request


USER_AGENT = "football-intelligence-platform/0.4 tactical-video-intelligence"
TIMEOUT_SECONDS = 5
LANGUAGES = ("pt", "en")


def _fetch_summary(lang: str, title: str) -> dict | None:
    encoded_title = urllib.parse.quote(title.replace(" ", "_"))
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{encoded_title}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return None


@lru_cache(maxsize=256)
def fetch_team_wikipedia_profile(team_name: str) -> dict | None:
    """Looks up a football team on Wikipedia (pt, then en) and returns a
    small, stable summary. Returns None when no usable page is found."""
    cleaned = " ".join((team_name or "").strip().split())
    if not cleaned:
        return None

    for lang in LANGUAGES:
        data = _fetch_summary(lang, cleaned)
        if not data or data.get("type") == "disambiguation":
            continue
        extract = (data.get("extract") or "").strip()
        if not extract:
            continue
        thumbnail = (data.get("thumbnail") or {}).get("source") or (data.get("originalimage") or {}).get("source")
        page_url = (data.get("content_urls") or {}).get("desktop", {}).get("page")
        return {
            "title": data.get("title") or cleaned,
            "description": data.get("description") or "",
            "summary": extract,
            "crest_url": thumbnail,
            "page_url": page_url,
            "lang": lang,
        }
    return None
