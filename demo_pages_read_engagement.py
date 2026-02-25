"""
Screencast demo for Meta App Review -- pages_read_engagement permission.

Demonstrates:
1. How pages_read_engagement enables reading like_count and comments_count
   on Instagram posts accessed via a Page Access Token
2. How this data flows into the Polaris analytics and content dashboards
3. Why this permission is required alongside the Instagram permissions

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
    print(f"    {DIM}{label:<32}{RESET}{BOLD}{value}{RESET}")

def api_call(method, endpoint, note=""):
    print(f"    {DIM}{method:<6}{RESET} {CYAN}{endpoint}{RESET}", end="")
    if note:
        print(f"  {DIM}# {note}{RESET}", end="")
    print()

# -- Load account from DB --------------------------------------------------
conn = sqlite3.connect("polaris.db")
cur  = conn.cursor()
cur.execute("SELECT access_token, instagram_user_id, username FROM instagram_accounts WHERE id=1")
token, ig_user_id, username = cur.fetchone()
conn.close()

from polaris.config import get_settings
settings = get_settings()

# --------------------------------------------------------------------------
header("Polaris Innovations -- pages_read_engagement Demo")

print(f"""
  {BOLD}Feature:{RESET}  Post Engagement Data via Page Access Token

  All Instagram Graph API calls in Polaris authenticate using a
  {BOLD}Page Access Token{RESET} -- obtained during account connection via the
  connected Facebook Page (see pages_show_list demo).

  When reading Instagram posts and their engagement data through
  a Page Access Token, the Graph API requires {BOLD}pages_read_engagement{RESET}
  to return fields such as like_count and comments_count.

  {BOLD}Where this data appears in Polaris:{RESET}
    - polaris content list   (likes and comments per published post)
    - polaris analytics fetch  (engagement metrics snapshot)
    - polaris analytics report (30-day engagement summary)

  {DIM}App ID: {settings.meta_app_id}{RESET}
  {DIM}Account: @{username}{RESET}
""")
pause(2)

# -- STEP 1: Why pages_read_engagement is needed --------------------------
step(1, "Why pages_read_engagement is Required")

print(f"""
  Instagram Business Accounts are accessed in Polaris through a
  {BOLD}Page Access Token{RESET}, not a User Access Token. This is because
  the Instagram Graph API for Business/Creator accounts requires
  Page-scoped authentication (see pages_show_list and
  pages_manage_metadata demos for how this token is obtained).

  When a Page Access Token is used to call Instagram media endpoints,
  the {BOLD}like_count{RESET} and {BOLD}comments_count{RESET} fields on media objects
  are only returned if {BOLD}pages_read_engagement{RESET} is granted.

  Without this permission, the same call returns the media list
  but with like_count and comments_count missing or zero, making
  the analytics and content performance features unusable.
""")
pause(2)

# -- STEP 2: Live media fetch showing engagement fields -------------------
step(2, "Reading Post Engagement via GET /{ig_user_id}/media")

print(f"""
  Polaris fetches recent posts and their engagement counts with:
""")
pause()

api_call(
    "GET",
    f"/v18.0/{ig_user_id}/media",
    "pages_read_engagement"
)
print(f"    {DIM}fields=id,caption,media_type,like_count,comments_count,timestamp{RESET}")
print()
pause()

r = httpx.get(
    f"https://graph.facebook.com/v18.0/{ig_user_id}/media",
    params={
        "fields": "id,caption,media_type,like_count,comments_count,timestamp",
        "limit": 8,
        "access_token": token,
    }
)
media_list = r.json().get("data", [])

if media_list:
    print(f"  {GREEN}Posts with engagement data:{RESET}\n")
    print(f"  +---------------------+-------+-----------+------+----------+")
    print(f"  | Media ID            | Type  | Date      | Likes| Comments |")
    print(f"  +---------------------+-------+-----------+------+----------+")
    for m in media_list:
        mid   = (m.get("id") or "")[:19]
        mtype = (m.get("media_type") or "")[:5]
        ts    = (m.get("timestamp") or "")[:10]
        likes = m.get("like_count", "-")
        comms = m.get("comments_count", "-")
        print(f"  | {mid:<19} | {mtype:<5} | {ts:<9} | {str(likes):<4} | {str(comms):<8} |")
    print(f"  +---------------------+-------+-----------+------+----------+")
else:
    print(f"  {DIM}(No media returned){RESET}")

pause(2)

# -- STEP 3: How these fields flow into analytics -------------------------
step(3, "How Engagement Fields Flow into the Analytics Feature")

print(f"""
  During  {BOLD}polaris analytics fetch --account 1{RESET}  Polaris calls
  GET /{ig_user_id}/media and records each post's engagement:

    like_count       -> stored as   engagement_metrics.likes
    comments_count   -> stored as   engagement_metrics.comments

  These are then combined with per-post insights (impressions,
  reach, saves, shares -- retrieved separately via
  GET /{"{media_id}"}/insights) to build the full metrics record.

  Without pages_read_engagement, like_count and comments_count
  would be absent from the response, leaving those fields empty
  in the analytics dashboard and distorting average engagement
  rate calculations.
""")
pause(2)

# -- STEP 4: How these fields flow into content list ----------------------
step(4, "Engagement Counts in the Content Dashboard")

print(f"""
  Run {BOLD}polaris content list{RESET} to see published posts with their
  engagement at a glance:
""")
pause()

conn = sqlite3.connect("polaris.db")
cur  = conn.cursor()
cur.execute("""
    SELECT c.id, c.media_type, c.instagram_media_id, c.status,
           em.likes, em.comments, em.reach
    FROM contents c
    LEFT JOIN engagement_metrics em
        ON em.instagram_media_id = c.instagram_media_id
    WHERE c.status = 'PUBLISHED'
    ORDER BY c.id DESC LIMIT 5
""")
content_rows = cur.fetchall()
conn.close()

if content_rows:
    print(f"  +----+---------+---------------------+-------+------+------+")
    print(f"  | ID | Type    | Instagram Media ID  | Likes | Cmts | Reach|")
    print(f"  +----+---------+---------------------+-------+------+------+")
    for row in content_rows:
        cid, mtype, mid, status, likes, comms, reach = row
        mid_s = (mid or "")[:19]
        print(f"  |{cid:>3} | {(mtype or ''):<7} | {mid_s:<19} |"
              f" {str(likes or '-'):<5} | {str(comms or '-'):<4} | {str(reach or '-'):<4} |")
    print(f"  +----+---------+---------------------+-------+------+------+")
else:
    print(f"  {DIM}(No published content with metrics yet){RESET}")

pause(2)

# -- STEP 5: Comment count used by lead trigger detection -----------------
step(5, "comments_count as a Pre-Filter for Lead Trigger Polling")

print(f"""
  Polaris also uses comments_count from the media endpoint as a
  lightweight pre-filter before polling individual post comments:

    If comments_count == 0:
      -> skip GET /{"{media_id}"}/comments (save API quota)

    If comments_count > last_known_count:
      -> poll comments immediately (ahead of the 2-min schedule)

  This optimisation requires comments_count to be present in the
  GET /{ig_user_id}/media response, which in turn requires
  pages_read_engagement on the Page Access Token.

  Without it, Polaris would need to poll every watched post's
  comments every 2 minutes regardless of activity, increasing
  unnecessary API usage.
""")
pause(2)

# -- STEP 6: Summary of fields and calls ----------------------------------
step(6, "API Calls and Fields Requiring pages_read_engagement")

print(f"""
  {BOLD}Primary call:{RESET}
""")
api_call("GET", f"/v18.0/{ig_user_id}/media",
         "fields include like_count, comments_count")
print(f"""
  {BOLD}Fields enabled by pages_read_engagement:{RESET}

    like_count          Number of likes on a post
    comments_count      Number of comments on a post

  {BOLD}Used in:{RESET}
    polaris analytics fetch   -> records likes/comments per post
    polaris analytics report  -> includes in engagement totals
    polaris content list      -> displays alongside each post
    poll_triggers()           -> comments_count pre-filter

  {BOLD}Not used for:{RESET}
    Reading or modifying Page-level content (posts, photos,
    events) or other Facebook Page engagement data.
    Polaris only reads Instagram media engagement.
""")
pause(2)

# -- Summary ---------------------------------------------------------------
header("Summary")
print(f"""
  {BOLD}pages_read_engagement{RESET} allows Polaris to:

    {GREEN}1.{RESET}  Read like_count and comments_count on Instagram posts
       when authenticated via a Page Access Token
       (GET /{{ig_user_id}}/media)

    {GREEN}2.{RESET}  Populate the analytics dashboard with complete
       engagement metrics per published post

    {GREEN}3.{RESET}  Use comments_count as a pre-filter to optimise
       comment polling API usage in the lead automation feature

  {BOLD}Why it cannot be avoided:{RESET}
    Polaris authenticates all Instagram Graph API calls using a
    Page Access Token (required by the Instagram Business API).
    In this authentication context, like_count and comments_count
    on media objects are gated by pages_read_engagement.
    Without it these fields are absent and engagement tracking
    is broken.

  {BOLD}Dependency chain:{RESET}
    pages_show_list          -> provides Page Access Token
    pages_manage_metadata    -> resolves Instagram Account ID
    pages_read_engagement    -> unlocks engagement fields on
                                Instagram media via that token

  All engagement data is stored locally in SQLite.
  Polaris has no backend server. No data is shared externally.

  {DIM}End of demo -- Polaris Innovations{RESET}
""")
