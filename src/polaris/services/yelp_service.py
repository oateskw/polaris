"""Yelp Fusion API service for prospect discovery."""

import re
from typing import Optional

import httpx

from polaris.config import Settings, get_settings
from polaris.services.search_utils import (
    extract_email_from_html,
    extract_facebook_url_from_html,
    scrape_email_from_facebook_page,
    scrape_email_from_instagram_bio,
    scrape_email_from_website,
)

YELP_SEARCH_URL = "https://api.yelp.com/v3/businesses/search"
YELP_DETAIL_URL = "https://api.yelp.com/v3/businesses/{id}"

INSTAGRAM_PATTERN = re.compile(
    r'instagram\.com/([a-zA-Z0-9._]+)/?',
    re.IGNORECASE,
)
INSTAGRAM_SKIP = {"p", "reel", "stories", "explore", "accounts", "share", "tv"}

_STOP_WORDS = {"llc", "inc", "co", "company", "services", "service", "and", "the", "of", "a"}

_IG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def _generate_username_candidates(business_name: str) -> list[str]:
    """Generate plausible Instagram username candidates from a business name."""
    name = business_name.lower()
    name = re.sub(r"'s\b", "s", name)           # Joe's → Joes
    name = re.sub(r"[^a-z0-9\s]", "", name)     # strip punctuation
    words = [w for w in name.split() if w not in _STOP_WORDS]

    if not words:
        return []

    base = "".join(words)
    base_under = "_".join(words)

    candidates = []
    seen = set()
    for c in [base, base_under, base + "co", base + "llc", words[0]]:
        if c not in seen:
            candidates.append(c)
            seen.add(c)
    return candidates


class YelpService:
    """Find local service businesses via Yelp and discover their Instagram."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._client = httpx.Client(
            timeout=15.0,
            follow_redirects=True,
            headers={"Authorization": f"Bearer {self.settings.yelp_api_key}"},
        )

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def search(self, business_type: str, location: str, limit: int = 20) -> list[dict]:
        """Search Yelp for local businesses."""
        params = {
            "term": business_type,
            "location": location,
            "limit": min(limit, 50),
            "sort_by": "review_count",
        }
        resp = self._client.get(YELP_SEARCH_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for biz in data.get("businesses", []):
            loc = biz.get("location", {})
            city = loc.get("city", "")
            state = loc.get("state", "")
            results.append({
                "id": biz.get("id", ""),
                "name": biz.get("name", ""),
                "address": f"{city}, {state}".strip(", "),
                "rating": biz.get("rating", ""),
                "reviews": biz.get("review_count", 0),
                "phone": biz.get("display_phone", ""),
                "yelp_url": biz.get("url", ""),
                "website": "",
                "instagram": "",
            })
        return results

    def get_website(self, business_id: str) -> str:
        """Fetch the business website URL from Yelp business details."""
        try:
            resp = self._client.get(YELP_DETAIL_URL.format(id=business_id))
            if resp.status_code == 200:
                return resp.json().get("website", "") or ""
        except Exception:
            pass
        return ""

    def find_email(self, website_url: str) -> str:
        """Fetch a business website and extract a contact email address."""
        return self._extract_email(self._fetch_website_html(website_url))

    def find_instagram(self, website_url: str) -> str:
        """Fetch a business website and extract their Instagram handle."""
        return self._extract_instagram(self._fetch_website_html(website_url))

    def guess_instagram(self, business_name: str) -> str:
        """Try common username patterns against Instagram to find a match."""
        candidates = _generate_username_candidates(business_name)
        for username in candidates:
            try:
                resp = httpx.get(
                    f"https://www.instagram.com/{username}/",
                    headers=_IG_HEADERS,
                    timeout=6.0,
                    follow_redirects=True,
                )
                if resp.status_code == 200:
                    return f"@{username}"
            except Exception:
                continue
        return ""

    def search_with_instagram(
        self, business_type: str, location: str, limit: int = 20
    ) -> list[dict]:
        """Search Yelp, fetch websites, and find Instagram handles."""
        from polaris.services.places_service import PlacesService

        results = self.search(business_type, location, limit=limit)

        places = None
        if self.settings.google_places_api_key:
            places = PlacesService(self.settings)

        try:
            for result in results:
                result["instagram_guessed"] = False
                result["email"] = ""

                # Get website — Yelp first, Google Places as fallback
                result["website"] = self.get_website(result["id"])
                if not result["website"] and places:
                    result["website"] = places.get_website_for_business(
                        result["name"], result["address"]
                    )

                fb_url = ""
                if result["website"]:
                    html = self._fetch_website_html(result["website"])
                    result["instagram"] = self._extract_instagram(html)
                    result["email"] = self._extract_email(html)
                    fb_url = extract_facebook_url_from_html(html)

                if not result["instagram"]:
                    result["instagram"] = self.guess_instagram(result["name"])
                    if result["instagram"]:
                        result["instagram_guessed"] = True

                if not result["email"] and result["website"]:
                    result["email"] = scrape_email_from_website(result["website"])
                if not result["email"] and result["instagram"]:
                    result["email"] = scrape_email_from_instagram_bio(result["instagram"])
                if not result["email"] and fb_url:
                    result["email"] = scrape_email_from_facebook_page(fb_url)
        finally:
            if places:
                places.close()

        return results

    def _fetch_website_html(self, url: str) -> str:
        try:
            resp = self._client.get(url, timeout=8.0)
            return resp.text if resp.status_code == 200 else ""
        except Exception:
            return ""

    def _extract_instagram(self, html: str) -> str:
        for match in INSTAGRAM_PATTERN.findall(html):
            if match.lower() not in INSTAGRAM_SKIP:
                return f"@{match}"
        return ""

    def _extract_email(self, html: str) -> str:
        return extract_email_from_html(html)
