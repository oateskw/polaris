"""
Screencast demo for Meta App Review — instagram_business_basic permission.

Demonstrates:
1. How an Instagram professional account connects to Polaris via OAuth
2. Profile information (username, profile pic URL, follower count, etc.)
   retrieved and displayed after connection

Run this while screen recording.
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, "src")

import sqlite3
import httpx
import time
import webbrowser
from http.server import HTTPServer

BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
DIM    = "\033[2m"
RESET  = "\033[0m"
ORANGE = "\033[38;5;208m"

def pause(s=1.4):
    time.sleep(s)

def header(text):
    print()
    print(f"{BOLD}{CYAN}{'='*62}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'='*62}{RESET}")
    pause()

def step(n, text):
    print(f"\n{BOLD}{ORANGE}[ STEP {n} ]{RESET}  {BOLD}{text}{RESET}")
    pause(0.8)

def info(label, value):
    print(f"    {DIM}{label:<28}{RESET}{BOLD}{value}{RESET}")

# ── Load settings ─────────────────────────────────────────────────────────
from polaris.config import get_settings
from polaris.services.instagram.auth import InstagramAuth, OAuthCallbackHandler

settings = get_settings()

header("Polaris Innovations — instagram_business_basic Screencast")

print(f"""
  This recording demonstrates two things required for App Review:

    1.  How an Instagram professional account connects to Polaris
    2.  Where profile information is displayed after connection

  {DIM}App ID: {settings.meta_app_id}{RESET}
""")
pause(2)

# ── STEP 1: Start the OAuth connect flow ─────────────────────────────────
step(1, "Connect an Instagram Professional Account")

auth = InstagramAuth(settings)
auth_url, state = auth.get_authorization_url()

print(f"""
  Polaris uses Meta's standard OAuth 2.0 flow to connect an
  Instagram Business or Creator account.

  The user runs:  {BOLD}polaris accounts add{RESET}

  Polaris generates the authorisation URL and opens it in the
  default browser:

  {YELLOW}{auth_url}{RESET}

  Opening browser now...
""")
pause(1)
webbrowser.open(auth_url)

print(f"""  {DIM}(The user logs in to Facebook, selects their Instagram
  Professional account, and approves the requested permissions.
  Facebook redirects back to localhost:8000/callback with an
  authorisation code which Polaris exchanges for a long-lived
  Page access token.){RESET}
""")

# Start callback server
print(f"  {CYAN}Waiting for OAuth callback on http://localhost:8000/callback ...{RESET}")
OAuthCallbackHandler.auth_code = None
OAuthCallbackHandler.state     = None
OAuthCallbackHandler.error     = None

server = HTTPServer(("localhost", 8000), OAuthCallbackHandler)
server.timeout = 300
server.handle_request()

if OAuthCallbackHandler.error:
    print(f"\n  {YELLOW}OAuth error: {OAuthCallbackHandler.error}{RESET}")
    sys.exit(1)

if not OAuthCallbackHandler.auth_code:
    print(f"\n  {YELLOW}No callback received — exiting.{RESET}")
    sys.exit(1)

print(f"\n  {GREEN}Authorisation code received. Exchanging for access token...{RESET}")
pause()

token_data  = auth.exchange_code_for_token(OAuthCallbackHandler.auth_code)
ig_account  = auth.get_instagram_account(token_data["access_token"])
access_token = ig_account["page_access_token"]
ig_user_id   = ig_account["instagram_user_id"]

print(f"  {GREEN}Access token obtained. Saving account to Polaris...{RESET}")
pause()

# Persist to DB
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from polaris.repositories import AccountRepository

engine  = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)
session = Session()
repo    = AccountRepository(session)

existing = repo.get_by_instagram_id(ig_user_id)
if existing:
    repo.update_token(existing.id, access_token, token_data["expires_at"])
else:
    repo.create(
        instagram_user_id=ig_user_id,
        username=ig_account.get("username", ""),
        name=ig_account.get("name"),
        access_token=access_token,
        token_expires_at=token_data["expires_at"],
        profile_picture_url=ig_account.get("profile_picture_url"),
        followers_count=ig_account.get("followers_count"),
        following_count=ig_account.get("follows_count"),
        media_count=ig_account.get("media_count"),
    )
repo.commit()
session.close()

print(f"  {GREEN}Account connected and saved successfully.{RESET}\n")
pause(1.5)

# ── STEP 2: Fetch and display full profile information ────────────────────
step(2, "Profile Information Retrieved and Displayed")

print(f"\n  Using instagram_business_basic, Polaris now fetches the full")
print(f"  profile for the connected account:\n")
pause()

r = httpx.get(
    f"https://graph.facebook.com/v18.0/{ig_user_id}",
    params={
        "fields": "id,username,name,biography,profile_picture_url,"
                  "followers_count,follows_count,media_count,website",
        "access_token": access_token,
    }
)
d = r.json()

print(f"  {GREEN}Profile data received:{RESET}\n")
info("Instagram User ID:",  d.get("id", "—"))
info("Username:",           f"@{d.get('username', '—')}")
info("Display Name:",       d.get("name", "—"))
info("Bio:",                (d.get("biography") or "—")[:55])
info("Profile Picture URL:", (d.get("profile_picture_url") or "—")[:55])
info("Followers:",          d.get("followers_count", "—"))
info("Following:",          d.get("follows_count",   "—"))
info("Total Posts:",        d.get("media_count",     "—"))
info("Website:",            d.get("website",         "—"))
pause(2)

# ── STEP 3: Show where profile info appears in Polaris CLI ────────────────
step(3, "Where Profile Information is Displayed in Polaris")

print(f"""
  After connecting, profile information is visible in two places:

  {BOLD}A)  polaris accounts list{RESET}
  {DIM}    Shows username, display name, followers, post count, and
      token status for every connected account.{RESET}
""")
pause()

uname = d.get("username", "—")
name  = (d.get("name") or "—")[:28]
fol   = d.get("followers_count", "—")
posts = d.get("media_count", "—")

print(f"""  +----+------------------------+----------------------------+-----------+-------+--------+
  | ID | Username               | Name                       | Followers | Posts | Status |
  +----+------------------------+----------------------------+-----------+-------+--------+
  |  1 | @{uname:<22}| {name:<26} | {str(fol):<9} | {str(posts):<5} | {GREEN}Active{RESET} |
  +----+------------------------+----------------------------+-----------+-------+--------+
""")
pause(2)

print(f"""  {BOLD}B)  polaris status{RESET}
  {DIM}    Shows connected accounts at a glance alongside content
      and schedule statistics.{RESET}
""")
pause()
print(f"""    Connected Accounts:  1
      - @{uname}
      - Followers: {fol}  |  Posts: {posts}
""")
pause(2)

# ── STEP 4: Confirm permissions ───────────────────────────────────────────
step(4, "Permissions Confirmed on the Connected Token")

r2 = httpx.get(
    "https://graph.facebook.com/v18.0/me/permissions",
    params={"access_token": access_token}
)
perms = {p["permission"]: p["status"] for p in r2.json().get("data", [])}

print(f"\n  {GREEN}Granted permissions on this token:{RESET}\n")
for p, status in sorted(perms.items()):
    marker = f"{GREEN}granted{RESET}" if status == "granted" else f"{DIM}{status}{RESET}"
    bold_p = f"{BOLD}{p}{RESET}" if p == "instagram_business_basic" else p
    print(f"    {bold_p:<42}  {marker}")

pause(2)

# ── Summary ───────────────────────────────────────────────────────────────
header("Summary")
print(f"""
  {BOLD}instagram_business_basic{RESET} allows Polaris to:

    {GREEN}1.{RESET}  Authenticate the user's Instagram Professional account
       via Meta's standard OAuth 2.0 flow
    {GREEN}2.{RESET}  Retrieve profile data (ID, username, name, bio,
       profile picture, follower count, post count)
    {GREEN}3.{RESET}  Display that profile in the accounts dashboard
    {GREEN}4.{RESET}  Scope ALL other features (publishing, analytics,
       comment triggers, lead automation) to this account

  {BOLD}Dependency note:{RESET}
    instagram_business_basic is also requested as a required
    dependency for:
      - instagram_manage_messages  (comment-to-DM automation)
      - instagram_manage_comments  (reading keyword comments)

  All profile data is stored locally on the user's machine.
  Polaris has no backend server. No data is shared externally.

  {DIM}End of demo — Polaris Innovations{RESET}
""")
