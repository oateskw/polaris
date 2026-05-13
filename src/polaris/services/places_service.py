"""Google Places API service for prospect discovery."""

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

PLACES_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
PLACES_SEARCH_NEW_URL = "https://places.googleapis.com/v1/places:searchText"

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
    name = re.sub(r"'s\b", "s", name)
    name = re.sub(r"[^a-z0-9\s]", "", name)
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


class PlacesService:
    """Find local service businesses via Google Places and discover their Instagram and email."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._client = httpx.Client(timeout=15.0, follow_redirects=True)

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _places_headers(self, field_mask: str) -> dict:
        return {
            "X-Goog-Api-Key": self.settings.google_places_api_key,
            "X-Goog-FieldMask": field_mask,
        }

    def search(self, business_type: str, location: str, limit: int = 20) -> list[dict]:
        """Search Google Maps for local businesses using the Places API (New)."""
        results = []
        next_page_token = None

        while len(results) < limit:
            body = {
                "textQuery": f"{business_type} in {location}",
                "pageSize": min(limit - len(results), 20),
            }
            if next_page_token:
                body["pageToken"] = next_page_token

            response = self._client.post(
                PLACES_SEARCH_NEW_URL,
                json=body,
                headers=self._places_headers(
                    "places.displayName,places.formattedAddress,places.rating,"
                    "places.userRatingCount,places.nationalPhoneNumber,"
                    "places.websiteUri,places.id,nextPageToken"
                ),
            )
            response.raise_for_status()
            data = response.json()

            for place in data.get("places", []):
                if len(results) >= limit:
                    break
                results.append({
                    "name": place.get("displayName", {}).get("text", ""),
                    "address": place.get("formattedAddress", ""),
                    "rating": place.get("rating", ""),
                    "reviews": place.get("userRatingCount", 0),
                    "phone": place.get("nationalPhoneNumber", ""),
                    "website": place.get("websiteUri", ""),
                    "instagram": "",
                    "instagram_guessed": False,
                    "email": "",
                    "place_id": place.get("id", ""),
                })

            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                break

        return results

    def get_website_for_business(self, business_name: str, location: str) -> str:
        """Use Google Places (New API) to find the website for a business."""
        try:
            resp = self._client.post(
                PLACES_SEARCH_NEW_URL,
                json={"textQuery": f"{business_name} {location}"},
                headers={
                    "X-Goog-Api-Key": self.settings.google_places_api_key,
                    "X-Goog-FieldMask": "places.websiteUri",
                },
            )
            places = resp.json().get("places", [])
            if not places:
                return ""
            return places[0].get("websiteUri", "") or ""
        except Exception:
            return ""

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

    def search_with_instagram(self, business_type: str, location: str, limit: int = 20) -> list[dict]:
        """Search for businesses and attempt to find their Instagram and email."""
        results = self.search(business_type, location, limit=limit)
        for result in results:
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
        return results
