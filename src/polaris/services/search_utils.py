"""Shared search utilities for prospect discovery."""

import re
from urllib.parse import urljoin, urlparse

import httpx

EMAIL_PATTERN = re.compile(
    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
)
EMAIL_SKIP = re.compile(
    r'@(example|test|domain|email|youremail|sentry|wix|squarespace|wordpress|'
    r'googleapis|schema|goog|facebook|instagram|twitter|tiktok|yelp|amazon|'
    r'microsoft|apple|adobe|cloudflare|w3|png|jpg|jpeg|gif|svg)\.',
    re.IGNORECASE,
)

MAILTO_PATTERN = re.compile(r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', re.IGNORECASE)

FACEBOOK_PATTERN = re.compile(
    r'(?:https?://)?(?:www\.)?facebook\.com/([a-zA-Z0-9._\-]+)/?',
    re.IGNORECASE,
)
FACEBOOK_SKIP = {
    "sharer", "share", "dialog", "plugins", "pages", "groups", "events",
    "marketplace", "watch", "photo", "photos", "video", "videos", "hashtag",
    "login", "logout", "help", "settings", "profile", "home", "about",
    "notifications", "messages", "bookmarks", "gaming", "fundraisers",
}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

_CONTACT_SLUGS = ["/contact", "/contact-us", "/about", "/about-us", "/reach-us", "/get-in-touch"]


def extract_email_from_html(html: str) -> str:
    """Extract the first valid-looking email from raw HTML.

    Prefers mailto: links as they are the most reliable signal.
    """
    # Prefer explicit mailto: links
    for match in MAILTO_PATTERN.findall(html):
        if not EMAIL_SKIP.search(match):
            return match.lower()
    # Fall back to plain email pattern
    for match in EMAIL_PATTERN.findall(html):
        if not EMAIL_SKIP.search(match):
            return match.lower()
    return ""


def extract_facebook_url_from_html(html: str) -> str:
    """Extract a Facebook business page URL from website HTML."""
    for match in FACEBOOK_PATTERN.findall(html):
        slug = match.lower().rstrip("/")
        # Skip generic Facebook slugs and tracker redirects (l.php, tr, etc.)
        if slug not in FACEBOOK_SKIP and not slug.startswith("tr") and "." not in slug:
            return f"https://www.facebook.com/{match.rstrip('/')}"
    return ""


def scrape_email_from_website(website_url: str, timeout: float = 8.0) -> str:
    """Fetch homepage + common contact/about pages and return the first email found."""
    if not website_url:
        return ""

    base = f"{urlparse(website_url).scheme}://{urlparse(website_url).netloc}"
    pages_to_try = [website_url] + [urljoin(base, slug) for slug in _CONTACT_SLUGS]

    try:
        with httpx.Client(headers=_HEADERS, timeout=timeout, follow_redirects=True) as client:
            for url in pages_to_try:
                try:
                    resp = client.get(url)
                    if resp.status_code == 200:
                        email = extract_email_from_html(resp.text)
                        if email:
                            return email
                except Exception:
                    continue
    except Exception:
        pass
    return ""


def scrape_email_from_instagram_bio(handle: str, timeout: float = 8.0) -> str:
    """Check an Instagram profile bio for an email address."""
    username = handle.lstrip("@")
    if not username:
        return ""
    try:
        with httpx.Client(headers=_HEADERS, timeout=timeout, follow_redirects=True) as client:
            resp = client.get(f"https://www.instagram.com/{username}/")
            if resp.status_code == 200:
                # Instagram embeds profile data as JSON in the page source
                bio_match = re.search(r'"biography"\s*:\s*"([^"]*)"', resp.text)
                if bio_match:
                    # Decode unicode escapes Instagram uses (e.g. \u0040 for @)
                    bio = bio_match.group(1).encode().decode("unicode_escape", errors="ignore")
                    email_match = EMAIL_PATTERN.search(bio)
                    if email_match and not EMAIL_SKIP.search(email_match.group()):
                        return email_match.group().lower()
                # Fallback: scan full page HTML for any email
                return extract_email_from_html(resp.text)
    except Exception:
        pass
    return ""


def scrape_email_from_facebook_page(fb_url: str, timeout: float = 8.0) -> str:
    """Attempt to extract an email from a Facebook business page."""
    if not fb_url:
        return ""
    try:
        with httpx.Client(headers=_HEADERS, timeout=timeout, follow_redirects=True) as client:
            resp = client.get(fb_url)
            if resp.status_code == 200:
                return extract_email_from_html(resp.text)
    except Exception:
        pass
    return ""


def search_email_online(business_name: str, location: str, timeout: float = 6.0) -> str:
    """Kept for backwards compatibility — no longer used."""
    return ""
