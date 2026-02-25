"""
Screencast demo for Meta App Review -- instagram_manage_comments permission.

Demonstrates:
1. How Polaris polls comments on a business owner's Instagram post
2. How keyword matching triggers the comment-to-DM lead pipeline
3. The exact API call that requires instagram_manage_comments

Run this while screen recording.
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, "src")

import sqlite3
import httpx
import time
from datetime import datetime, timezone

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
    print(f"    {DIM}{label:<28}{RESET}{BOLD}{value}{RESET}")

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

cur.execute("""
    SELECT id, post_instagram_media_id, keyword, is_active, last_polled_at
    FROM comment_triggers WHERE id=2
""")
trigger_row = cur.fetchone()
conn.close()

from polaris.config import get_settings
settings = get_settings()

POST_ID = trigger_row[1] if trigger_row else "18187172089320156"
KEYWORD = trigger_row[2].upper() if trigger_row else "AUTOMATE"

# --------------------------------------------------------------------------
header("Polaris Innovations -- instagram_manage_comments Demo")

print(f"""
  {BOLD}Feature:{RESET}  Keyword Comment Detection for Lead Automation

  Polaris watches a business owner's Instagram post for comments
  that contain a specific keyword (e.g. "AUTOMATE"). When a follower
  comments that keyword, Polaris sends them a private DM and begins
  an AI-powered lead qualification conversation.

  Reading comments on a Business Account's own posts requires the
  {BOLD}instagram_manage_comments{RESET} permission.

  {BOLD}Permissions used:{RESET}
    - instagram_manage_comments      (read comments on own posts)
    - instagram_business_manage_messages (send the DM reply)

  {DIM}App ID: {settings.meta_app_id}{RESET}
  {DIM}Account: @{username}{RESET}
""")
pause(2)

# -- STEP 1: Show the configured trigger -----------------------------------
step(1, "Comment Trigger Configured on an Instagram Post")

print(f"""
  The business owner publishes a Reel with a caption ending in:
  "Comment {KEYWORD} below and I'll send you the full breakdown."

  They then run:  {BOLD}polaris leads setup{RESET}

  Polaris stores a CommentTrigger record and begins polling
  every 2 minutes via APScheduler.
""")
pause()

if trigger_row:
    print(f"  {GREEN}Active trigger in Polaris:{RESET}\n")
    info("Trigger ID:",     str(trigger_row[0]))
    info("Post ID:",        trigger_row[1])
    info("Keyword:",        trigger_row[2].upper())
    info("Status:",         f"{GREEN}active{RESET}" if trigger_row[3] else f"{YELLOW}paused{RESET}")
    info("Last polled:",    str(trigger_row[4])[:19] if trigger_row[4] else "never")
pause(2)

# -- STEP 2: The polling call ----------------------------------------------
step(2, "APScheduler Runs poll_triggers() Every 2 Minutes")

print(f"""
  On each tick, Polaris calls the Instagram Graph API to fetch
  comments posted since the last poll:
""")
pause()

api_call(
    "GET",
    f"/v18.0/{POST_ID}/comments",
    "instagram_manage_comments"
)
print(f"    {DIM}params: fields=id,text,username,from,timestamp  limit=100  since=<last_polled_at>{RESET}")
print()
pause()

# Live API call
r = httpx.get(
    f"https://graph.facebook.com/v18.0/{POST_ID}/comments",
    params={
        "fields": "id,text,username,from,timestamp",
        "limit": 100,
        "access_token": token,
    }
)
comments = r.json().get("data", [])

print(f"  {GREEN}Comments fetched: {len(comments)}{RESET}\n")

keyword_matches = []
for c in comments:
    text      = c.get("text", "")
    uname     = c.get("username") or c.get("from", {}).get("username", "unknown")
    ts        = c.get("timestamp", "")[:10]
    ig_uid    = c.get("from", {}).get("id", "")
    is_match  = KEYWORD.lower() in text.lower()
    flag      = f"  {GREEN}[KEYWORD MATCH]{RESET}" if is_match else ""
    print(f"    [{ts}]  \"{text[:60]}\"  @{uname}{flag}")
    if is_match:
        keyword_matches.append({
            "id": c.get("id"),
            "text": text,
            "username": uname,
            "ig_user_id": ig_uid,
        })

if not comments:
    print(f"    {DIM}(No comments yet on this post){RESET}")
    print(f"""
  When a follower comments \"{KEYWORD}\", Polaris would see:

    [2026-02-25]  \"{KEYWORD}\"  @example_follower  {GREEN}[KEYWORD MATCH]{RESET}
""")

pause(2)

# -- STEP 3: What Polaris does with each match ----------------------------
step(3, "What Each Comment Field Is Used For")

print(f"""
  The response from GET /{POST_ID}/comments includes:

    {BOLD}id{RESET}
      The comment ID. Used as the unique deduplication key -- Polaris
      checks this against its leads table to avoid double-processing
      the same comment on repeated polls.
      Also passed to POST /<comment_id>/private_replies to send the
      initial DM back to this specific commenter.

    {BOLD}text{RESET}
      The comment body. Polaris checks whether the keyword
      ("{KEYWORD}") appears anywhere in the text (case-insensitive).
      Non-matching comments are discarded without further action.

    {BOLD}from.id{RESET}
      The Instagram-scoped user ID of the commenter. Stored in the
      Lead record and used later as the recipient ID when sending
      AI follow-up DMs via POST /me/messages.

    {BOLD}from.username{RESET}
      The commenter's Instagram handle. Displayed in the Polaris
      leads dashboard and passed to Claude AI as context when
      generating personalised replies.

    {BOLD}timestamp{RESET}
      Used as a cursor. After each poll, Polaris sets last_polled_at
      to the most recent comment timestamp so the next poll only
      fetches new comments (avoids re-processing old ones).
""")
pause(2)

# -- STEP 4: Deduplication and lead creation ------------------------------
step(4, "Deduplication and Lead Creation")

print(f"""
  For each keyword match Polaris:

    1.  Checks the leads table:
          SELECT * FROM leads WHERE comment_id = '<comment_id>'
        If found -> skip (already processed this comment)

    2.  If new:
          - Sends initial DM via POST /<comment_id>/private_replies
          - Inserts a Lead row:
              commenter_ig_user_id  = from.id
              commenter_username    = from.username
              comment_id            = id               {DIM}(unique key){RESET}
              comment_text          = text
              dm_sent               = True
              status                = CONTACTED

  This means instagram_manage_comments drives the {BOLD}top of the lead
  funnel{RESET} -- every lead in Polaris originates from a keyword comment
  detected by this permission.
""")
pause(2)

# Show current leads from DB
conn = sqlite3.connect("polaris.db")
cur  = conn.cursor()
cur.execute("""
    SELECT id, commenter_username, status, comment_text, dm_sent
    FROM leads
    ORDER BY id DESC LIMIT 5
""")
leads = cur.fetchall()
conn.close()

if leads:
    print(f"  {GREEN}Current leads captured via comment polling:{RESET}\n")
    print(f"  +----+--------------------+-----------+----------+--------+")
    print(f"  | ID | Username           | Status    | Keyword  | DM Sent|")
    print(f"  +----+--------------------+-----------+----------+--------+")
    for lead in leads:
        lid, uname, status, ctext, dm = lead
        kw = (ctext or "")[:8].upper()
        dm_flag = f"{GREEN}yes{RESET}" if dm else "no "
        print(f"  |{lid:>3} | @{(uname or ''):<18}| {(status or ''):<9} | {kw:<8} | {dm_flag}    |")
    print(f"  +----+--------------------+-----------+----------+--------+")
    print()
pause(2)

# -- STEP 5: Why read-only access is sufficient ---------------------------
step(5, "Read-Only Usage -- No Comment Modifications")

print(f"""
  Polaris uses instagram_manage_comments exclusively to {BOLD}read{RESET}
  comments. It never:

    - Replies to comments publicly (no POST /<comment_id>/replies)
    - Hides or deletes comments
    - Modifies any comment data

  The only write action in the pipeline is the private DM reply,
  which uses instagram_business_manage_messages (a separate permission).

  This means the impact on the commenter is minimal:
    - They post a public comment as normal
    - They receive a {BOLD}private{RESET} DM (not a public reply)
    - Their comment and profile remain unmodified
""")
pause(2)

# -- STEP 6: API calls summary --------------------------------------------
step(6, "The Single API Call Using instagram_manage_comments")

print(f"""
  {BOLD}Read comments on a post:{RESET}
""")
api_call("GET", f"/v18.0/{{media_id}}/comments", "instagram_manage_comments")
print(f"    {DIM}params: fields=id,text,username,from,timestamp  limit=100  since=<unix_ts>{RESET}")
print(f"""
  Called every 2 minutes by APScheduler for each active trigger.
  One call per watched post per poll cycle.

  The since parameter limits results to new comments only,
  keeping API usage proportional to actual comment volume.
""")
pause(2)

# -- Summary ---------------------------------------------------------------
header("Summary")
print(f"""
  {BOLD}instagram_manage_comments{RESET} allows Polaris to:

    {GREEN}1.{RESET}  Read comments on the business owner's own Instagram posts
       (GET /{{media_id}}/comments)

    {GREEN}2.{RESET}  Detect comments that contain the business owner's
       configured keyword (e.g. "AUTOMATE")

    {GREEN}3.{RESET}  Extract the commenter's Instagram user ID and username
       to create a Lead record and address the follow-up DM

  {BOLD}User consent model:{RESET}
    Only posts explicitly configured by the business owner are
    watched. Only comments containing the exact keyword trigger
    any action. No comments are read for passive monitoring or
    analytics -- polling only runs for active lead triggers.

  {BOLD}Dependency:{RESET}
    instagram_manage_comments feeds the top of the lead funnel.
    The commenter's from.id is then used by
    instagram_business_manage_messages to send the DM reply.

  All data is stored locally on the user's machine.
  Polaris has no backend server. No data is shared externally.

  {DIM}End of demo -- Polaris Innovations{RESET}
""")
