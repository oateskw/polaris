"""Instagram OAuth authentication flow."""

import secrets
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Optional
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from polaris.config import Settings, get_settings


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth callback."""

    auth_code: Optional[str] = None
    state: Optional[str] = None
    error: Optional[str] = None

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default logging."""
        pass

    def do_GET(self) -> None:
        """Handle GET request from OAuth callback."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "error" in params:
            OAuthCallbackHandler.error = params["error"][0]
            self._send_response("Authentication failed. You can close this window.")
        elif "code" in params:
            OAuthCallbackHandler.auth_code = params["code"][0]
            OAuthCallbackHandler.state = params.get("state", [None])[0]
            self._send_response("Authentication successful! You can close this window.")
        else:
            self._send_response("Invalid callback. You can close this window.")

    def _send_response(self, message: str) -> None:
        """Send HTML response."""
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>Polaris Authentication</title></head>
        <body style="font-family: sans-serif; text-align: center; padding: 50px;">
            <h1>Polaris Instagram Manager</h1>
            <p>{message}</p>
        </body>
        </html>
        """
        self.wfile.write(html.encode())


class InstagramAuth:
    """Handle Instagram OAuth authentication."""

    AUTH_URL = "https://www.facebook.com/v18.0/dialog/oauth"
    TOKEN_URL = "https://graph.facebook.com/v18.0/oauth/access_token"
    LONG_LIVED_TOKEN_URL = "https://graph.facebook.com/v18.0/oauth/access_token"

    SCOPES = [
        "instagram_basic",
        "instagram_content_publish",
        "instagram_manage_insights",
        "pages_show_list",
        "pages_read_engagement",
    ]

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._state: Optional[str] = None

    def get_authorization_url(self) -> tuple[str, str]:
        """Generate authorization URL and state token."""
        self._state = secrets.token_urlsafe(32)

        params = {
            "client_id": self.settings.meta_app_id,
            "redirect_uri": self.settings.meta_redirect_uri,
            "scope": ",".join(self.SCOPES),
            "response_type": "code",
            "state": self._state,
        }

        url = f"{self.AUTH_URL}?{urlencode(params)}"
        return url, self._state

    def start_oauth_flow(self, port: int = 8000) -> Optional[dict[str, Any]]:
        """Start the OAuth flow with a local callback server."""
        # Reset callback handler state
        OAuthCallbackHandler.auth_code = None
        OAuthCallbackHandler.state = None
        OAuthCallbackHandler.error = None

        # Generate authorization URL
        auth_url, expected_state = self.get_authorization_url()

        # Start local server
        server = HTTPServer(("localhost", port), OAuthCallbackHandler)
        server.timeout = 300  # 5 minute timeout

        # Open browser
        print(f"Opening browser for authentication...")
        print(f"If browser doesn't open, visit: {auth_url}")
        webbrowser.open(auth_url)

        # Wait for callback
        print("Waiting for authentication callback...")
        server.handle_request()

        if OAuthCallbackHandler.error:
            raise Exception(f"OAuth error: {OAuthCallbackHandler.error}")

        if not OAuthCallbackHandler.auth_code:
            raise Exception("No authorization code received")

        if OAuthCallbackHandler.state != expected_state:
            raise Exception("State mismatch - possible CSRF attack")

        # Exchange code for token
        return self.exchange_code_for_token(OAuthCallbackHandler.auth_code)

    def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        """Exchange authorization code for access token."""
        params = {
            "client_id": self.settings.meta_app_id,
            "client_secret": self.settings.meta_app_secret,
            "redirect_uri": self.settings.meta_redirect_uri,
            "code": code,
        }

        with httpx.Client() as client:
            response = client.get(self.TOKEN_URL, params=params)
            response.raise_for_status()
            data = response.json()

        # Exchange for long-lived token
        return self.exchange_for_long_lived_token(data["access_token"])

    def exchange_for_long_lived_token(self, short_lived_token: str) -> dict[str, Any]:
        """Exchange short-lived token for long-lived token."""
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": self.settings.meta_app_id,
            "client_secret": self.settings.meta_app_secret,
            "fb_exchange_token": short_lived_token,
        }

        with httpx.Client() as client:
            response = client.get(self.LONG_LIVED_TOKEN_URL, params=params)
            response.raise_for_status()
            data = response.json()

        # Calculate expiration time
        expires_in = data.get("expires_in", 5184000)  # Default 60 days
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        return {
            "access_token": data["access_token"],
            "token_type": data.get("token_type", "bearer"),
            "expires_at": expires_at,
        }

    def get_instagram_account(self, access_token: str) -> dict[str, Any]:
        """Get Instagram Business Account linked to the Facebook Page."""
        # First, get the user's Facebook pages
        pages_url = "https://graph.facebook.com/v18.0/me/accounts"

        with httpx.Client(timeout=30.0) as client:
            response = client.get(pages_url, params={"access_token": access_token})
            response.raise_for_status()
            pages_data = response.json()

            pages = pages_data.get("data", [])
            if not pages:
                raise Exception("No Facebook Pages found. Please create a Page and link Instagram.")

            # Get Instagram account for each page
            for page in pages:
                page_id = page["id"]
                page_token = page["access_token"]

                ig_url = f"https://graph.facebook.com/v18.0/{page_id}"
                params = {
                    "fields": "instagram_business_account",
                    "access_token": page_token,
                }

                response = client.get(ig_url, params=params)
                response.raise_for_status()
                ig_data = response.json()

                if "instagram_business_account" in ig_data:
                    ig_account_id = ig_data["instagram_business_account"]["id"]

                    # Get Instagram account details
                    ig_details_url = f"https://graph.facebook.com/v18.0/{ig_account_id}"
                    details_params = {
                        "fields": "id,username,name,profile_picture_url,followers_count,follows_count,media_count",
                        "access_token": page_token,
                    }

                    response = client.get(ig_details_url, params=details_params)
                    response.raise_for_status()
                    ig_details = response.json()

                    return {
                        "instagram_user_id": ig_account_id,
                        "page_access_token": page_token,
                        **ig_details,
                    }

        raise Exception(
            "No Instagram Business Account found. "
            "Please link an Instagram Business Account to your Facebook Page."
        )

    def refresh_token(self, access_token: str) -> dict[str, Any]:
        """Refresh a long-lived token."""
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": self.settings.meta_app_id,
            "client_secret": self.settings.meta_app_secret,
            "fb_exchange_token": access_token,
        }

        with httpx.Client() as client:
            response = client.get(self.LONG_LIVED_TOKEN_URL, params=params)
            response.raise_for_status()
            data = response.json()

        expires_in = data.get("expires_in", 5184000)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        return {
            "access_token": data["access_token"],
            "token_type": data.get("token_type", "bearer"),
            "expires_at": expires_at,
        }
