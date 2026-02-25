"""
Screencast demo for Meta App Review -- instagram_basic permission.

Demonstrates:
1. How Polaris reads the connected Instagram account's profile
   via the graph.instagram.com endpoint
2. How it reads the account's media list
3. How instagram_basic and instagram_business_basic work together
   to cover both API base URLs used by the app

Run this while screen recording.
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, "src")

import sqlite3
import httpx
import time

BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
DIM    = "\033[2m"
RESET  = "\033[0m"
ORANGE = "\033[38;5;208m"
BLUE   = "\033[94m"

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
    print(f"    {DIM}{label:<30}{RESET}{BOLD}{value}{RESET}")

def api_call(method, endpoint, note=""):
    print(f"    {DIM}{method:<6}{RESET} {CYAN}{endpoint}{RESET}", end="")
    if note:
        print(f"  {DIM}# {note}{RESET}", end="")
    print()

# -- Load account from DB --------------------------------------------------
conn = sqlite3.connect("polaris.db")
cur  = conn.cursor()
cur.execute("""
    SELECT access_token, instagram_user_id, username, name,
           followers_count, media_count, profile_picture_url
    FROM instagram_accounts WHERE id=1
""")
row = cur.fetchone()
token, ig_user_id, username, name, followers, media_count, pfp_url = row
conn.close()

from polaris.config import get_settings
settings = get_settings()

BASE_URL  = "https://graph.instagram.com"
GRAPH_URL = "https://graph.facebook.com/v18.0"

# --------------------------------------------------------------------------
header("Polaris Innovations -- instagram_basic Demo")

print(f"""
  {BOLD}Feature:{RESET}  Instagram Profile and Media Access

  Polaris uses two distinct base URLs when calling the Instagram
  Graph API. Each requires its own permission grant:

    {CYAN}graph.instagram.com{RESET}          -> {BOLD}instagram_basic{RESET}
      Profile info and media list via the Instagram-native API

    {CYAN}graph.facebook.com/v18.0{RESET}     -> {BOLD}instagram_business_basic{RESET}
      Business account features via the Facebook Graph API

  {BOLD}instagram_basic{RESET} covers two endpoints used throughout Polaris:

    GET /{{ig_user_id}}              (account profile)
    GET /{{ig_user_id}}/media        (post list)

  {DIM}App ID: {settings.meta_app_id}{RESET}
  {DIM}Account: @{username}{RESET}
""")
pause(2)

# -- STEP 1: Two base URLs, two permissions --------------------------------
step(1, "Two Base URLs -- Two Permissions")

print(f"""
  The Polaris Instagram client defines both base URLs:

    {DIM}# src/polaris/services/instagram/client.py{RESET}
    BASE_URL  = "{CYAN}https://graph.instagram.com{RESET}"
    GRAPH_URL = "{CYAN}https://graph.facebook.com/v18.0{RESET}"

  Calls to {BOLD}BASE_URL{RESET} (graph.instagram.com) require {BOLD}instagram_basic{RESET}.
  Calls to {BOLD}GRAPH_URL{RESET} (graph.facebook.com) require {BOLD}instagram_business_basic{RESET}.

  Both permissions are requested together during OAuth so that
  all endpoints across both base URLs are authorised on the
  same access token.
""")
pause(2)

# -- STEP 2: Profile read via graph.instagram.com -------------------------
step(2, "Reading Account Profile via graph.instagram.com")

print(f"""
  When Polaris displays the connected account or checks token
  validity it calls:
""")
pause()

api_call("GET", f"{BASE_URL}/{ig_user_id}", "instagram_basic")
print(f"    {DIM}fields=id,username,name,profile_picture_url,followers_count,follows_count,media_count{RESET}")
print()
pause()

r = httpx.get(
    f"{BASE_URL}/{ig_user_id}",
    params={
        "fields": "id,username,name,profile_picture_url,"
                  "followers_count,follows_count,media_count",
        "access_token": token,
    }
)
d = r.json()

if "error" not in d:
    print(f"  {GREEN}Profile data returned:{RESET}\n")
    info("Instagram User ID:",   d.get("id", "--"))
    info("Username:",            f"@{d.get('username', '--')}")
    info("Display Name:",        d.get("name", "--"))
    info("Followers:",           str(d.get("followers_count", "--")))
    info("Following:",           str(d.get("follows_count", "--")))
    info("Total Posts:",         str(d.get("media_count", "--")))
    pfp = d.get("profile_picture_url", "")
    info("Profile Picture URL:", (pfp[:55] + "...") if len(pfp) > 55 else (pfp or "--"))
else:
    err = d["error"].get("message", "unknown")
    print(f"  {YELLOW}API note: {err}{RESET}")
    print(f"\n  {DIM}Falling back to locally cached profile data:{RESET}\n")
    info("Instagram User ID:",   ig_user_id)
    info("Username:",            f"@{username}")
    info("Display Name:",        name or "--")
    info("Followers:",           str(followers or "--"))
    info("Total Posts:",         str(media_count or "--"))

pause(2)

# -- STEP 3: Media list via graph.instagram.com ---------------------------
step(3, "Reading Post List via graph.instagram.com")

print(f"""
  To build the content list and fetch media IDs for insights,
  Polaris calls:
""")
pause()

api_call("GET", f"{BASE_URL}/{ig_user_id}/media", "instagram_basic")
print(f"    {DIM}fields=id,caption,media_type,media_url,thumbnail_url,timestamp,like_count,comments_count{RESET}")
print()
pause()

r2 = httpx.get(
    f"{BASE_URL}/{ig_user_id}/media",
    params={
        "fields": "id,caption,media_type,media_url,timestamp,like_count,comments_count",
        "limit": 6,
        "access_token": token,
    }
)
d2 = r2.json()
media_list = d2.get("data", [])

if media_list:
    print(f"  {GREEN}Recent posts returned: {len(media_list)}{RESET}\n")
    print(f"  +---------------------+-------+------------+------+------+")
    print(f"  | Media ID            | Type  | Date       |Likes |Cmts  |")
    print(f"  +---------------------+-------+------------+------+------+")
    for m in media_list:
        mid   = (m.get("id") or "")[:19]
        mtype = (m.get("media_type") or "")[:5]
        ts    = (m.get("timestamp") or "")[:10]
        likes = str(m.get("like_count", "-"))
        comms = str(m.get("comments_count", "-"))
        print(f"  | {mid:<19} | {mtype:<5} | {ts:<10} | {likes:<4} | {comms:<4} |")
    print(f"  +---------------------+-------+------------+------+------+")
elif "error" in d2:
    err = d2["error"].get("message", "unknown")
    print(f"  {YELLOW}API note: {err}{RESET}")
else:
    print(f"  {DIM}(No posts returned){RESET}")

pause(2)

# -- STEP 4: Where these calls appear in the CLI --------------------------
step(4, "Where These Calls Appear in Polaris")

print(f"""
  {BOLD}get_account_info(){RESET}  ->  GET {BASE_URL}/{{ig_user_id}}
  Called by:
    polaris accounts list   -> displays username, followers, posts
    polaris status          -> shows connected account at a glance
    polaris accounts refresh -> verifies token is still valid

  {BOLD}get_media(){RESET}  ->  GET {BASE_URL}/{{ig_user_id}}/media
  Called by:
    polaris analytics fetch -> collects media IDs for insights
    polaris content list    -> cross-references published content
                               with live Instagram media IDs
""")
pause(2)

# -- STEP 5: Contrast with instagram_business_basic -----------------------
step(5, "How instagram_basic and instagram_business_basic Differ")

print(f"""
  Both permissions are requested in the same OAuth flow, but they
  authorise calls to different hosts:

  {BOLD}instagram_basic{RESET}            ->  graph.instagram.com
  ┌─────────────────────────────────────────────────────┐
  │  GET /{{ig_user_id}}          profile fields        │
  │  GET /{{ig_user_id}}/media    post list             │
  └─────────────────────────────────────────────────────┘

  {BOLD}instagram_business_basic{RESET}   ->  graph.facebook.com/v18.0
  ┌─────────────────────────────────────────────────────┐
  │  GET /{{ig_user_id}}          full business profile │
  │  POST /{{ig_user_id}}/media   create container      │
  │  POST /{{ig_user_id}}/media_publish  publish post   │
  │  GET /{{ig_user_id}}/insights account-level metrics │
  └─────────────────────────────────────────────────────┘

  Removing either permission breaks the corresponding set of
  calls. Together they ensure every API call Polaris makes --
  across both hosts -- is properly authorised.
""")
pause(2)

# -- STEP 6: Summary of API calls -----------------------------------------
step(6, "All API Calls Using instagram_basic")

print(f"""
  {BOLD}1. Read account profile:{RESET}
""")
api_call("GET", f"{BASE_URL}/{{ig_user_id}}",
         "fields=id,username,name,profile_picture_url,followers_count,...")

print(f"""
  {BOLD}2. Read post list:{RESET}
""")
api_call("GET", f"{BASE_URL}/{{ig_user_id}}/media",
         "fields=id,caption,media_type,like_count,comments_count,timestamp")

print(f"""
  Both calls use the graph.instagram.com base URL.
  Both are read-only. No content is created or modified.
  Data is stored locally in SQLite -- never sent to a backend server.
""")
pause(2)

# -- Summary ---------------------------------------------------------------
header("Summary")
print(f"""
  {BOLD}instagram_basic{RESET} allows Polaris to:

    {GREEN}1.{RESET}  Read account profile information via graph.instagram.com:
       username, display name, followers, following, post count,
       profile picture URL
       (GET /{ig_user_id})

    {GREEN}2.{RESET}  Read the account's post list via graph.instagram.com:
       media IDs, captions, media type, like/comment counts,
       timestamps
       (GET /{ig_user_id}/media)

  {BOLD}Why it cannot be avoided:{RESET}
    Polaris makes calls to both graph.instagram.com and
    graph.facebook.com/v18.0. The instagram.com endpoints
    require instagram_basic; the facebook.com endpoints require
    instagram_business_basic. Both must be granted on the same
    token for all features to work.

  {BOLD}Relationship to instagram_business_basic:{RESET}
    instagram_basic          -> graph.instagram.com  (profile, media)
    instagram_business_basic -> graph.facebook.com   (publish, insights,
                                                       comments, messages)
    Together they authorise the full set of API calls in Polaris.

  All profile and media data is stored locally in SQLite.
  Polaris has no backend server. No data is shared externally.

  {DIM}End of demo -- Polaris Innovations{RESET}
""")
