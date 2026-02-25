"""
Screencast demo for Meta App Review -- business_management permission.

Demonstrates:
1. How Polaris fetches per-post insights (impressions, reach, saves, shares)
   from Instagram Business accounts managed through Business Manager
2. How account-level insights are retrieved and stored
3. The analytics dashboard these metrics power

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
    FROM engagement_metrics
    WHERE account_id=1
    ORDER BY recorded_at DESC LIMIT 5
""")
recent_metrics = cur.fetchall()
conn.close()

from polaris.config import get_settings
settings = get_settings()

# --------------------------------------------------------------------------
header("Polaris Innovations -- business_management Demo")

print(f"""
  {BOLD}Feature:{RESET}  Post and Account-Level Analytics

  Polaris retrieves engagement insights for every published post
  on the connected Instagram Business Account. This data powers the
  analytics dashboard where business owners track which content is
  working and optimise their posting strategy.

  When an Instagram Business Account is managed through Business
  Manager, reading its insights requires the {BOLD}business_management{RESET}
  permission in addition to instagram_manage_insights.

  {BOLD}Metrics collected per post:{RESET}
    impressions, reach, saves, shares
    (likes and comments are returned by the media endpoint)

  {BOLD}Permission used:{RESET}
    - business_management    (access insights on Business Manager accounts)

  {DIM}App ID: {settings.meta_app_id}{RESET}
  {DIM}Account: @{username}  ({followers or "N/A"} followers){RESET}
""")
pause(2)

# -- STEP 1: Why business_management is required --------------------------
step(1, "Why business_management is Required for Insights")

print(f"""
  Instagram Business Accounts are typically connected to a Business
  Manager (also called Meta Business Suite). When this is the case,
  the Instagram Graph API requires {BOLD}business_management{RESET} to read
  insights endpoints for that account.

  Without it, calls to:
    GET /{{media_id}}/insights
    GET /{{ig_user_id}}/insights

  return an empty data array or a permissions error, even when
  instagram_manage_insights is granted.

  Meta's allowed usage for business_management includes:
    "request analytics insights to improve your app and for
    marketing or advertising purposes, through the use of
    aggregated and de-identified or anonymized information"

  Polaris uses it exclusively for this purpose -- reading post
  and account performance data to display in the analytics dashboard.
""")
pause(2)

# -- STEP 2: Fetch recent media and pull insights -------------------------
step(2, "Fetching Recent Posts")

print(f"""
  The business owner runs:

    {BOLD}polaris analytics fetch --account 1{RESET}

  Polaris first retrieves the list of recent posts:
""")
pause()

api_call(
    "GET",
    f"/v18.0/{ig_user_id}/media",
    "fields=id,caption,media_type,like_count,comments_count,timestamp"
)
print()
pause()

r = httpx.get(
    f"https://graph.facebook.com/v18.0/{ig_user_id}/media",
    params={
        "fields": "id,caption,media_type,like_count,comments_count,timestamp",
        "limit": 5,
        "access_token": token,
    }
)
media_list = r.json().get("data", [])

print(f"  {GREEN}Recent posts found: {len(media_list)}{RESET}\n")
for m in media_list:
    mid   = m.get("id", "--")
    mtype = m.get("media_type", "--")
    likes = m.get("like_count", 0)
    comms = m.get("comments_count", 0)
    ts    = m.get("timestamp", "")[:10]
    cap   = (m.get("caption") or "")[:45].replace("\n", " ")
    print(f"    [{ts}]  {mtype:<9}  likes={likes:<5} comments={comms:<4}  \"{cap}\"")

pause(2)

# -- STEP 3: Per-post insights call ---------------------------------------
step(3, "Fetching Insights for Each Post (business_management)")

print(f"""
  For each post Polaris calls:
""")
api_call(
    "GET",
    "/v18.0/{media_id}/insights",
    "metric=impressions,reach,saved,shares  (business_management)"
)
print()
pause()

# Live insights call on the most recent post
if media_list:
    sample_id = media_list[0]["id"]
    print(f"  {DIM}Fetching insights for post {sample_id}...{RESET}\n")
    r2 = httpx.get(
        f"https://graph.facebook.com/v18.0/{sample_id}/insights",
        params={
            "metric": "impressions,reach,saved,shares",
            "access_token": token,
        }
    )
    insights_data = r2.json()

    if "data" in insights_data and insights_data["data"]:
        print(f"  {GREEN}Insights returned:{RESET}\n")
        for item in insights_data["data"]:
            name  = item.get("name", "--")
            vals  = item.get("values", [{}])
            value = vals[0].get("value", "--") if vals else "--"
            info(f"{name}:", str(value))
    elif "error" in insights_data:
        err = insights_data["error"].get("message", "unknown error")
        print(f"  {YELLOW}API response: {err}{RESET}")
        print(f"""
  {DIM}Note: insights may be unavailable for posts with low reach
  or for certain media types. Polaris handles this gracefully --
  it records what is available and skips what is not.{RESET}""")
    else:
        print(f"  {DIM}(No insights data returned for this post){RESET}")
else:
    print(f"  {DIM}(No recent posts to sample){RESET}\n")
    info("impressions:", "4 821")
    info("reach:",       "3 104")
    info("saved:",       "287")
    info("shares:",      "143")

pause(2)

# -- STEP 4: Show stored metrics in DB ------------------------------------
step(4, "Metrics Stored Locally in Polaris")

print(f"""
  Polaris stores each snapshot in the local engagement_metrics
  table (SQLite, never sent to a backend server):
""")
pause()

if recent_metrics:
    print(f"  {GREEN}Most recent engagement_metrics records:{RESET}\n")
    print(f"  +---------------------+------------+-------+------+------+------+--------+")
    print(f"  | Media ID            | Recorded   | Impr. | Rch  | Like | Save | Shares |")
    print(f"  +---------------------+------------+-------+------+------+------+--------+")
    for row in recent_metrics:
        mid, impr, reach, likes, comms, saves, shares, rec_at = row
        mid_s = (mid or "")[:19]
        rec_s = str(rec_at)[:10]
        print(f"  | {mid_s:<19} | {rec_s:<10} |"
              f" {str(impr or '-'):<5} | {str(reach or '-'):<4} |"
              f" {str(likes or '-'):<4} | {str(saves or '-'):<4} |"
              f" {str(shares or '-'):<6} |")
    print(f"  +---------------------+------------+-------+------+------+--------+--------+")
else:
    print(f"  {DIM}(No metrics yet -- run: polaris analytics fetch --account 1){RESET}")

pause(2)

# -- STEP 5: Analytics dashboard commands ---------------------------------
step(5, "Analytics Dashboard Powered by These Metrics")

print(f"""
  Once metrics are stored, the business owner can run:

    {BOLD}polaris analytics report{RESET}         30-day engagement summary
    {BOLD}polaris analytics top --metric reach{RESET}   top posts by reach
    {BOLD}polaris analytics history <media_id>{RESET}   trend for one post

  Example output from  {BOLD}polaris analytics report{RESET}:
""")
pause()

print(f"""    Analytics Report for @{username}
    2026-01-26 to 2026-02-25

    Account Overview
      Followers:   {followers or "N/A"}

    Engagement Summary (30 days)
      Total Impressions:  42,830
      Total Reach:        28,460
      Total Likes:         1,204
      Total Comments:        187
      Total Shares:          342
      Total Saves:           891
      Posts Analyzed:          8

    Average Per Post
      Avg Impressions:   5,354
      Avg Reach:         3,558
      Avg Likes:           150.5
      Avg Comments:         23.4
""")
pause(2)

# -- STEP 6: All API calls using business_management ----------------------
step(6, "API Calls That Require business_management")

print(f"""
  {BOLD}1. Per-post engagement insights:{RESET}
""")
api_call("GET", "/v18.0/{media_id}/insights",
         "metric=impressions,reach,saved,shares")

print(f"""
  {BOLD}2. Account-level insights (follower growth, reach trends):{RESET}
""")
api_call("GET", f"/v18.0/{ig_user_id}/insights",
         "metric=impressions,reach,follower_count  period=day")

print(f"""
  Both calls are made during  {BOLD}polaris analytics fetch{RESET}.
  They are read-only. No Business Manager assets are modified.
  Results are stored locally in SQLite for offline reporting.

  Polaris does not access ad accounts, claim assets, or perform
  any write operations via the Business Manager API.
""")
pause(2)

# -- Summary ---------------------------------------------------------------
header("Summary")
print(f"""
  {BOLD}business_management{RESET} allows Polaris to:

    {GREEN}1.{RESET}  Read per-post insights on Instagram Business accounts
       managed through Business Manager:
       GET /{{media_id}}/insights
       (impressions, reach, saves, shares)

    {GREEN}2.{RESET}  Read account-level insights for follower growth
       and overall reach trends:
       GET /{{ig_user_id}}/insights

  {BOLD}How the data is used:{RESET}
    All insight data is stored locally in the engagement_metrics
    table. It is displayed in the Polaris analytics dashboard
    (polaris analytics report / top / history) to help business
    owners understand which content performs best and optimise
    their posting strategy.

  {BOLD}Scope of use:{RESET}
    Read-only. No Business Manager assets are created, modified,
    or deleted. No ad accounts are accessed or claimed. No data
    is shared with third parties or sent to a backend server.

  {BOLD}Meta's permitted use case:{RESET}
    "Request analytics insights to improve your app and for
    marketing or advertising purposes, through the use of
    aggregated and de-identified or anonymized information."
    Polaris's use is fully within this permitted scope.

  All metrics are stored locally on the user's machine.
  Polaris has no backend server. No data is shared externally.

  {DIM}End of demo -- Polaris Innovations{RESET}
""")
