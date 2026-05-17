"""
Screencast demo for a new Meta application review -- instagram_basic permission.

Demonstrates:
1. How Polaris reads the connected Instagram account's profile
  via the graph.facebook.com/v18.0 endpoint
2. How it reads the account's media list
3. How instagram_basic authorises read endpoints used by Polaris

Run this while screen recording.
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
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

BASE_URL = "https://graph.facebook.com/v18.0"

# --------------------------------------------------------------------------
header("Polaris Innovations -- instagram_basic Demo")

print(f"""
  {BOLD}Feature:{RESET}  Instagram Profile and Media Access

  Polaris calls Instagram Graph API endpoints on:

    {CYAN}graph.facebook.com/v18.0{RESET}

  For this review, {BOLD}instagram_basic{RESET} covers read access used
  to load the connected account profile and media list.

  {BOLD}instagram_basic{RESET} covers two endpoints used throughout Polaris:

    GET /{{ig_user_id}}              (account profile)
    GET /{{ig_user_id}}/media        (post list)

  {DIM}App ID: {settings.meta_app_id}{RESET}
  {DIM}Account: @{username}{RESET}
""")
pause(2)

# -- STEP 1: Two base URLs, two permissions --------------------------------
step(1, "Read Endpoints Used by instagram_basic")

print(f"""
  Polaris reads connected account data through:

    {DIM}# src/polaris/services/instagram/client.py{RESET}
    BASE_URL = "{CYAN}https://graph.facebook.com/v18.0{RESET}"

  The permission under review here is {BOLD}instagram_basic{RESET},
  which supports read access for profile and media endpoints.
""")
pause(2)

# -- STEP 2: Profile read via graph.facebook ------------------------------
step(2, "Reading Account Profile via graph.facebook.com")

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

# -- STEP 3: Media list via graph.facebook -------------------------------
step(3, "Reading Post List via graph.facebook.com")

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
  {BOLD}get_account_info(){RESET}  ->  GET https://graph.facebook.com/v18.0/{{ig_user_id}}
  Called by:
    polaris accounts list   -> displays username, followers, posts
    polaris status          -> shows connected account at a glance
    polaris accounts refresh -> verifies token is still valid

  {BOLD}get_media(){RESET}  ->  GET https://graph.facebook.com/v18.0/{{ig_user_id}}/media
  Called by:
    polaris analytics fetch -> collects media IDs for insights
    polaris content list    -> cross-references published content
                               with live Instagram media IDs
""")
pause(2)

# -- STEP 5: Read scope in this app ---------------------------------------
step(5, "How instagram_basic Is Used in Polaris")

print(f"""
  {BOLD}instagram_basic{RESET} is used for read operations that load account
  and media context in Polaris.

  {BOLD}Read endpoints demonstrated in this recording:{RESET}
  ┌─────────────────────────────────────────────────────┐
  │  GET /{{ig_user_id}}          profile fields        │
  │  GET /{{ig_user_id}}/media    post list             │
  └─────────────────────────────────────────────────────┘

  These are read-only calls and do not create, edit, or delete content.
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
  Both calls use the graph.facebook.com/v18.0 base URL.
  Both are read-only. No content is created or modified.
  Data is stored locally in SQLite -- never sent to a backend server.
""")
pause(2)

# -- Summary ---------------------------------------------------------------
header("Summary")
print(f"""
  {BOLD}instagram_basic{RESET} allows Polaris to:

    {GREEN}1.{RESET}  Read account profile information via graph.facebook.com/v18.0:
       username, display name, followers, following, post count,
       profile picture URL
       (GET /{ig_user_id})

    {GREEN}2.{RESET}  Read the account's post list via graph.facebook.com/v18.0:
       media IDs, captions, media type, like/comment counts,
       timestamps
       (GET /{ig_user_id}/media)

  {BOLD}Why it cannot be avoided:{RESET}
    Polaris needs this permission to read profile and media data
    for the connected Instagram business account before running
    analytics and lead automation workflows.

  All profile and media data is stored locally in SQLite.
  Polaris has no backend server. No data is shared externally.

  {DIM}End of demo -- Polaris Innovations{RESET}
""")
