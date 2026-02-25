"""Run this directly in your terminal to re-authenticate Instagram."""
import sys
sys.path.insert(0, "src")

from polaris.config import get_settings
from polaris.services.instagram.auth import InstagramAuth, OAuthCallbackHandler
from http.server import HTTPServer

settings = get_settings()
auth = InstagramAuth(settings)
url, state = auth.get_authorization_url()

print()
print("=" * 70)
print("  STEP 1: Open this URL in your browser")
print("=" * 70)
print()
print(url)
print()
print("=" * 70)
print("  STEP 2: Log in to Facebook and approve the permissions")
print("  STEP 3: You'll be redirected to localhost — come back here")
print("=" * 70)
print()
print("Waiting for callback on http://localhost:8000/callback ...")
print("(You have 5 minutes)")
print()

OAuthCallbackHandler.auth_code = None
OAuthCallbackHandler.state = None
OAuthCallbackHandler.error = None

server = HTTPServer(("localhost", 8000), OAuthCallbackHandler)
server.timeout = 300
server.handle_request()

if OAuthCallbackHandler.error:
    print(f"Error from Facebook: {OAuthCallbackHandler.error}")
    sys.exit(1)

if not OAuthCallbackHandler.auth_code:
    print("Timed out — no callback received. Please try again.")
    sys.exit(1)

print("Callback received! Exchanging for token...")
token_data = auth.exchange_code_for_token(OAuthCallbackHandler.auth_code)
ig_account = auth.get_instagram_account(token_data["access_token"])

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from polaris.repositories import AccountRepository

engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)
session = Session()
repo = AccountRepository(session)

existing = repo.get_by_instagram_id(ig_account["instagram_user_id"])
if existing:
    repo.update_token(existing.id, ig_account["page_access_token"], token_data["expires_at"])
    repo.commit()
    print(f"\nToken updated for @{existing.username}")
    print(f"Expires: {token_data['expires_at'].strftime('%Y-%m-%d')}")
else:
    account = repo.create(
        instagram_user_id=ig_account["instagram_user_id"],
        username=ig_account.get("username", ""),
        name=ig_account.get("name"),
        access_token=ig_account["page_access_token"],
        token_expires_at=token_data["expires_at"],
    )
    repo.commit()
    print(f"\nNew account saved: @{account.username}")

session.close()
print("\nDone! You can close this window.")
