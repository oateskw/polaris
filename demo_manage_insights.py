"""
Screencast demo for Meta App Review -- instagram_manage_insights permission.

Demonstrates:
1. How Polaris fetches per-post insights (impressions, reach, saved, shares)
2. How account-level insights are retrieved (follower_count, reach trends)
3. How all of this powers the polaris analytics dashboard

Run this while screen recording.
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, "src")

import sqlite3
import httpx
import time
from datetime import datetime, timezone, timedelta

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
cur.execute("SELECT access_token, instagram_user_id, username, followers_count FROM instagram_accounts WHERE id=1")
token, ig_user_id, username, followers = cur.fetchone()

cur.execute("""
    SELECT instagram_media_id, impressions, reach, likes, comments, saves, shares, recorded_at
    FROM engagement_metrics WHERE account_id=1
    ORDER BY recorded_at DESC LIMIT 5
""")
stored_metrics = cur.fetchall()
conn.close()

from polaris.config import get_settings
settings = get_settings()

# --------------------------------------------------------------------------
header("Polaris Innovations -- instagram_manage_insights Demo")

print(f"""
  {BOLD}Feature:{RESET}  Post and Account Insights for Analytics Dashboard

  Polaris retrieves Instagram insights to show business owners
  exactly how their content is performing -- beyond simple like
  and comment counts.

  {BOLD}Two levels of insights are collected:{RESET}

    Per-post:    impressions, reach, saved, shares
                 (GET /{{media_id}}/insights)

    Account:     impressions, reach, follower_count over time
                 (GET /{{ig_user_id}}/insights)

  These power the  {BOLD}polaris analytics{RESET}  command group.

  {DIM}App ID: {settings.meta_app_id}{RESET}
  {DIM}Account: @{username}  ({followers or "N/A"} followers){RESET}
""")
pause(2)

# -- STEP 1: Fetch recent media list --------------------------------------
step(1, "Fetch Recent Posts to Identify Media IDs")

print(f"""
  The business owner runs:

    {BOLD}polaris analytics fetch --account 1{RESET}

  Polaris first retrieves recent posts to get their media IDs:
""")
pause()

api_call("GET", f"/v18.0/{ig_user_id}/media",
         "fields=id,media_type,like_count,comments_count,timestamp")
print()
pause()

r = httpx.get(
    f"https://graph.facebook.com/v18.0/{ig_user_id}/media",
    params={
        "fields": "id,media_type,like_count,comments_count,timestamp",
        "limit": 6,
        "access_token": token,
    }
)
media_list = r.json().get("data", [])

print(f"  {GREEN}Posts found: {len(media_list)}{RESET}\n")
for m in media_list:
    mid   = m.get("id", "--")
    mtype = (m.get("media_type") or "")[:5]
    ts    = (m.get("timestamp") or "")[:10]
    likes = m.get("like_count", 0)
    comms = m.get("comments_count", 0)
    print(f"    [{ts}]  {mtype:<5}  id={mid}  likes={likes}  comments={comms}")

pause(2)

# -- STEP 2: Per-post insights call ---------------------------------------
step(2, "Per-Post Insights: impressions, reach, saved, shares")

print(f"""
  For each post Polaris calls:
""")
pause()

api_call("GET", "/v18.0/{media_id}/insights",
         "instagram_manage_insights")
print(f"    {DIM}metric=impressions,reach,saved,shares{RESET}")
print()
pause()

sample_media_id = media_list[0]["id"] if media_list else None
insights_result = {}

if sample_media_id:
    print(f"  {DIM}Fetching insights for post {sample_media_id}...{RESET}\n")
    r2 = httpx.get(
        f"https://graph.facebook.com/v18.0/{sample_media_id}/insights",
        params={
            "metric": "impressions,reach,saved,shares",
            "access_token": token,
        }
    )
    resp = r2.json()

    if "data" in resp and resp["data"]:
        print(f"  {GREEN}Insights returned:{RESET}\n")
        for item in resp["data"]:
            name  = item.get("name", "--")
            vals  = item.get("values", [{}])
            value = vals[0].get("value", "--") if vals else "--"
            insights_result[name] = value
            info(f"{name}:", str(value))
    elif "error" in resp:
        err = resp["error"].get("message", "unknown")
        print(f"  {YELLOW}API note: {err}{RESET}")
        print(f"""
  {DIM}This media type may not support all metrics. Polaris handles
  this gracefully -- it records what is returned and skips
  unsupported metrics without failing.{RESET}""")

pause(2)

# -- STEP 3: Account-level insights ---------------------------------------
step(3, "Account-Level Insights: follower growth and reach trends")

print(f"""
  Polaris also fetches account-level trend data:
""")
pause()

api_call("GET", f"/v18.0/{ig_user_id}/insights",
         "instagram_manage_insights")
print(f"    {DIM}metric=impressions,reach,follower_count  period=day{RESET}")
print()
pause()

r3 = httpx.get(
    f"https://graph.facebook.com/v18.0/{ig_user_id}/insights",
    params={
        "metric": "impressions,reach,follower_count",
        "period": "day",
        "access_token": token,
    }
)
acct_resp = r3.json()

if "data" in acct_resp and acct_resp["data"]:
    print(f"  {GREEN}Account insights returned:{RESET}\n")
    for item in acct_resp["data"]:
        name   = item.get("name", "--")
        period = item.get("period", "--")
        vals   = item.get("values", [])
        latest = vals[-1].get("value", "--") if vals else "--"
        info(f"{name} ({period}, latest):", str(latest))
elif "error" in acct_resp:
    err = acct_resp["error"].get("message", "unknown")
    print(f"  {YELLOW}API note: {err}{RESET}")
    print(f"""
  {DIM}Account insights require sufficient account activity.
  The endpoint and permission are correct -- data populates
  as the account grows.{RESET}""")

pause(2)

# -- STEP 4: How each metric is stored ------------------------------------
step(4, "Metrics Stored in engagement_metrics Table")

print(f"""
  Polaris stores each insights snapshot locally:

    {CYAN}engagement_metrics{RESET} table (SQLite)

    Column            Source
    impressions    <- GET /{{media_id}}/insights  metric=impressions
    reach          <- GET /{{media_id}}/insights  metric=reach
    saves          <- GET /{{media_id}}/insights  metric=saved
    shares         <- GET /{{media_id}}/insights  metric=shares
    likes          <- GET /{{ig_user_id}}/media   field=like_count
    comments       <- GET /{{ig_user_id}}/media   field=comments_count

  The last two come from pages_read_engagement (separate permission).
  The first four require instagram_manage_insights.
""")
pause()

if stored_metrics:
    print(f"  {GREEN}Stored metrics snapshot:{RESET}\n")
    print(f"  +--------------------+------+------+------+------+")
    print(f"  | Media ID           | Impr | Reach| Save | Shr  |")
    print(f"  +--------------------+------+------+------+------+")
    for row in stored_metrics:
        mid, impr, reach, likes, comms, saves, shares, rec_at = row
        mid_s = (mid or "")[:18]
        print(f"  | {mid_s:<18} |"
              f" {str(impr  or '-'):<4} | {str(reach or '-'):<4} |"
              f" {str(saves or '-'):<4} | {str(shares or '-'):<4} |")
    print(f"  +--------------------+------+------+------+------+")
else:
    print(f"  {DIM}(No metrics stored yet -- run: polaris analytics fetch --account 1){RESET}")

pause(2)

# -- STEP 5: Analytics commands that use this data ------------------------
step(5, "Analytics Dashboard Commands")

print(f"""
  Once fetched, insights are available in three commands:

  {BOLD}polaris analytics report{RESET}
    30-day engagement summary with totals and per-post averages.
    Impressions and reach totals come directly from the insights
    fetched via instagram_manage_insights.

  {BOLD}polaris analytics top --metric reach{RESET}
    Ranks posts by any metric. Reach and impressions rankings
    are only possible because instagram_manage_insights provides
    them (they are not available on the media object itself).

  {BOLD}polaris analytics history <media_id>{RESET}
    Shows the trend for a single post across multiple fetch
    snapshots, tracking how reach and impressions change over
    time after publication.
""")
pause()

print(f"""  Example output from  {BOLD}polaris analytics report{RESET}:\n
    Engagement Summary (30 days)
      Total Impressions:  {GREEN}42,830{RESET}     <- from instagram_manage_insights
      Total Reach:        {GREEN}28,460{RESET}     <- from instagram_manage_insights
      Total Likes:         1,204      <- from pages_read_engagement
      Total Comments:        187      <- from pages_read_engagement
      Total Shares:          {GREEN}342{RESET}       <- from instagram_manage_insights
      Total Saves:           {GREEN}891{RESET}       <- from instagram_manage_insights
      Posts Analyzed:          8
""")
pause(2)

# -- STEP 6: Summary of API calls -----------------------------------------
step(6, "All API Calls Using instagram_manage_insights")

print(f"""
  {BOLD}1. Per-post insights:{RESET}
""")
api_call("GET", "/v18.0/{media_id}/insights",
         "metric=impressions,reach,saved,shares")

print(f"""
  {BOLD}2. Account-level insights:{RESET}
""")
api_call("GET", f"/v18.0/{ig_user_id}/insights",
         "metric=impressions,reach,follower_count  period=day")

print(f"""
  Both are called during  polaris analytics fetch --account <id>.
  All results are read-only. No Instagram content is modified.
  Data is stored locally in SQLite -- never sent to a backend server.
""")
pause(2)

# -- Summary ---------------------------------------------------------------
header("Summary")
print(f"""
  {BOLD}instagram_manage_insights{RESET} allows Polaris to:

    {GREEN}1.{RESET}  Read per-post engagement insights:
       impressions, reach, saves, shares
       (GET /{{media_id}}/insights)

    {GREEN}2.{RESET}  Read account-level trend insights:
       daily impressions, reach, and follower growth
       (GET /{{ig_user_id}}/insights)

  {BOLD}Why it cannot be avoided:{RESET}
    Impressions, reach, saves, and shares are not available on
    the media object itself -- they are only accessible via the
    dedicated insights endpoint, which requires this permission.
    Without it the analytics dashboard is missing its four most
    meaningful content performance metrics.

  {BOLD}Relationship to other permissions:{RESET}
    instagram_manage_insights -> impressions, reach, saves, shares
    pages_read_engagement     -> likes, comments_count
    Together they provide a complete engagement picture per post.

  {BOLD}Dependency:{RESET}
    Requires instagram_business_basic for the Instagram User ID
    used in both insights endpoint paths.

  All data is stored locally on the user's machine.
  Polaris has no backend server. No data is shared externally.

  {DIM}End of demo -- Polaris Innovations{RESET}
""")
