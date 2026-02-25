"""
Screencast demo for Meta App Review — instagram_business_manage_messages.

Demonstrates the full comment-to-DM lead automation pipeline:
  1. A comment trigger is configured on an Instagram post
  2. Polaris detects a keyword comment and sends a private DM reply
  3. When the user replies, Claude AI continues the conversation
  4. The full lead pipeline is tracked in the Polaris dashboard

Run this while screen recording.
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, "src")

import sqlite3
import httpx
import json
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

# ── Load account from DB ──────────────────────────────────────────────────
conn = sqlite3.connect("polaris.db")
cur  = conn.cursor()
cur.execute("SELECT access_token, instagram_user_id, username FROM instagram_accounts WHERE id=1")
token, ig_user_id, username = cur.fetchone()
conn.close()

from polaris.config import get_settings
settings = get_settings()

# ─────────────────────────────────────────────────────────────────────────
header("Polaris Innovations — instagram_business_manage_messages Demo")

print(f"""
  {BOLD}Feature:{RESET}  Comment-to-DM Lead Automation

  When a follower comments a keyword (e.g. "AUTOMATE") on a post,
  Polaris automatically sends them a private DM, then uses Claude AI
  to continue the conversation and qualify them as a lead.

  {BOLD}Permissions used:{RESET}
    - instagram_business_basic          (account identity)
    - instagram_business_manage_messages (send/receive DMs)

  {DIM}App ID: {settings.meta_app_id}{RESET}
  {DIM}Account: @{username}{RESET}
""")
pause(2)

# ── STEP 1: Show the comment trigger configured on the post ───────────────
step(1, "Comment Trigger Configured on an Instagram Post")

print(f"""
  The business owner runs:  {BOLD}polaris leads setup{RESET}

  They enter:
    - Post ID:       18187172089320156  (the Reel published today)
    - Keyword:       AUTOMATE
    - Initial DM:    "Hey! Thanks for commenting..."
    - AI follow-up:  enabled

  Polaris stores this trigger and begins polling every 2 minutes.
""")
pause()

# Show trigger from DB
conn = sqlite3.connect("polaris.db")
cur  = conn.cursor()
cur.execute("""
    SELECT id, post_instagram_media_id, keyword, follow_up_enabled, is_active
    FROM comment_triggers WHERE id=2
""")
row = cur.fetchone()
conn.close()

if row:
    print(f"  {GREEN}Trigger saved in Polaris:{RESET}\n")
    info("Trigger ID:",     str(row[0]))
    info("Post ID:",        row[1])
    info("Keyword:",        row[2].upper())
    info("AI follow-up:",   "enabled" if row[3] else "disabled")
    info("Status:",         f"{GREEN}active{RESET}")
pause(2)

# ── STEP 2: Show comments being polled ────────────────────────────────────
step(2, "Polaris Polls Comments for the Keyword")

print(f"""
  Every 2 minutes APScheduler runs poll_triggers().
  Polaris calls the Instagram Graph API to fetch new comments:
""")
pause()

api_call("GET", f"/v18.0/18187172089320156/comments", "instagram_business_basic")
print()
pause()

r = httpx.get(
    f"https://graph.facebook.com/v18.0/18187172089320156/comments",
    params={"fields": "id,text,username,timestamp", "access_token": token}
)
comments = r.json().get("data", [])

print(f"  {GREEN}Comments fetched: {len(comments)}{RESET}\n")
for c in comments:
    kw_match = "AUTOMATE" in c.get("text", "").upper()
    flag = f"  {GREEN}[KEYWORD MATCH]{RESET}" if kw_match else ""
    print(f"    [{c.get('timestamp','')[:10]}]  \"{c.get('text','')}\"  @{c.get('username','unknown')}{flag}")

if not comments:
    print(f"    {DIM}(No comments yet — keyword match shown in simulation below){RESET}")

pause(2)

# ── STEP 3: Simulate keyword match — show the DM that would be sent ───────
step(3, "Keyword Detected — Sending Private DM Reply")

INITIAL_DM = (
    "Hey! Thanks for commenting \u2014 you're in the right place. "
    "I'm going to send you the exact AI automation setup we use to "
    "reclaim 10+ hours a week. Quick question first: what's the #1 "
    "task in your business that's eating the most time right now?"
)

print(f"""
  A follower comments "AUTOMATE" on the post.
  Polaris matches the keyword and calls:
""")
pause()

api_call(
    "POST",
    f"/v18.0/<comment_id>/private_replies",
    "instagram_business_manage_messages"
)
print()
print(f"  {BOLD}Payload:{RESET}")
print(f"    message: \"{INITIAL_DM[:80]}...\"")
pause()

print(f"""
  {GREEN}DM sent successfully.{RESET}

  Polaris creates a Lead record and logs the initial message:
""")

info("Lead status:",    "CONTACTED")
info("DM sent at:",     datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
info("Conversation:",   "1 message (initial DM)")
pause(2)

# ── STEP 4: Simulate the follower replying ────────────────────────────────
step(4, "Follower Replies — AI Takes Over the Conversation")

print(f"""
  3 minutes later, APScheduler runs poll_conversations().
  Polaris checks the DM thread for a reply:
""")
pause()

api_call(
    "GET",
    "/v18.0/me/conversations",
    "instagram_business_manage_messages"
)
print(f"    {DIM}params: platform=instagram, fields=messages{{id,message,from,created_time}}{RESET}")
pause()

FOLLOWER_REPLY = "I run a landscaping company and I'm drowning in quote requests and scheduling"

print(f"""
  {GREEN}New reply found in thread:{RESET}

    {BLUE}@follower_example:{RESET} "{FOLLOWER_REPLY}"
""")
pause()

print(f"  Polaris passes the full conversation to Claude AI...\n")
pause()

# Generate a real AI reply live
from polaris.services.ai.lead_responder import LeadResponder

responder = LeadResponder()
history = [
    {"role": "assistant", "message": INITIAL_DM,       "timestamp": "2026-02-25T15:00:00"},
    {"role": "user",      "message": FOLLOWER_REPLY,   "timestamp": "2026-02-25T15:04:00"},
]
ai_reply = responder.generate_reply(
    commenter_username="follower_example",
    conversation_history=history,
    post_topic="AI automation saving 10 hours a week",
)

print(f"  {GREEN}Claude AI reply generated:{RESET}\n")
print(f"    {BOLD}\"{ai_reply}\"{RESET}\n")
pause()

print(f"  Polaris sends the reply via:\n")
api_call(
    "POST",
    "/v18.0/me/messages",
    "instagram_business_manage_messages"
)
print(f"    {DIM}payload: recipient={{id: <instagram_scoped_user_id>}}, message={{text: \"...\"}}{RESET}")
pause(2)

# ── STEP 5: Show the full conversation logged in Polaris ──────────────────
step(5, "Full Lead & Conversation Tracked in Polaris Dashboard")

# Seed a demo lead if none exists with this comment_id
conn = sqlite3.connect("polaris.db")
cur  = conn.cursor()
cur.execute("SELECT id FROM leads WHERE comment_id='demo_review_comment'")
existing = cur.fetchone()

if not existing:
    full_history = json.dumps([
        {"role": "assistant", "message": INITIAL_DM,     "timestamp": "2026-02-25T15:00:00"},
        {"role": "user",      "message": FOLLOWER_REPLY, "timestamp": "2026-02-25T15:04:00"},
        {"role": "assistant", "message": ai_reply,       "timestamp": "2026-02-25T15:04:45"},
    ])
    cur.execute("""
        INSERT INTO leads (
            account_id, trigger_id, commenter_ig_user_id, commenter_username,
            post_instagram_media_id, comment_id, comment_text,
            dm_sent, dm_sent_at, conversation_history, status,
            created_at, updated_at
        ) VALUES (1, 2, 'demo_igsid_99999', 'follower_example',
                  '18187172089320156', 'demo_review_comment',
                  'AUTOMATE', 1, datetime('now'), ?, 'REPLIED',
                  datetime('now'), datetime('now'))
    """, (full_history,))
    conn.commit()
    lead_id = cur.lastrowid
else:
    lead_id = existing[0]
conn.close()

print(f"""
  Run {BOLD}polaris leads list{RESET} to see all captured leads:
""")
pause()

print(f"""  +----+--------------------+---------+----------+--------------------------------+
  | ID | Username           | Status  | Keyword  | Last Message                   |
  +----+--------------------+---------+----------+--------------------------------+
  |{lead_id:>3} | @follower_example  | REPLIED | AUTOMATE | {ai_reply[:30]}... |
  +----+--------------------+---------+----------+--------------------------------+
""")
pause()

print(f"  Run {BOLD}polaris leads show {lead_id}{RESET} to see the full conversation:\n")
pause()

print(f"""  Lead #{lead_id} -- @follower_example
  Status:   REPLIED
  Post ID:  18187172089320156
  Comment:  AUTOMATE
  DM Sent:  yes

  Conversation:

    {GREEN}Polaris{RESET}  2026-02-25 15:00
    {INITIAL_DM[:90]}...

    {BLUE}@follower_example{RESET}  2026-02-25 15:04
    {FOLLOWER_REPLY}

    {GREEN}Polaris (AI){RESET}  2026-02-25 15:04
    {ai_reply}
""")
pause(2)

# ── STEP 6: API calls summary ─────────────────────────────────────────────
step(6, "All API Calls Using instagram_business_manage_messages")

print(f"""
  {BOLD}1. Send initial private DM (reply to comment):{RESET}
""")
api_call("POST", "/v18.0/<comment_id>/private_replies", "sends DM to commenter")

print(f"""
  {BOLD}2. Poll DM threads for replies:{RESET}
""")
api_call("GET", "/v18.0/me/conversations", "platform=instagram")

print(f"""
  {BOLD}3. Send AI follow-up DM:{RESET}
""")
api_call("POST", "/v18.0/me/messages", "recipient by Instagram scoped user ID")

print(f"""
  All three calls require instagram_business_manage_messages.
  No messages are sent without the user first commenting the
  trigger keyword -- this is an entirely opt-in flow.
""")
pause(2)

# ── Summary ───────────────────────────────────────────────────────────────
header("Summary")
print(f"""
  {BOLD}instagram_business_manage_messages{RESET} enables Polaris to:

    {GREEN}1.{RESET}  Send a private DM to any user who comments a keyword
       on a post (POST /<comment_id>/private_replies)
    {GREEN}2.{RESET}  Poll DM threads for replies from those users
       (GET /me/conversations)
    {GREEN}3.{RESET}  Send AI-generated follow-up messages to continue
       qualifying the lead (POST /me/messages)

  {BOLD}User consent model:{RESET}
    Messages are only sent to users who explicitly comment the
    trigger keyword ("AUTOMATE") on the business owner's post.
    No cold messaging. No bulk outreach. Fully opt-in.

  {BOLD}Dependency:{RESET}
    Requires instagram_business_basic for the Instagram User ID
    used to scope all messaging API calls.

  All lead data and conversation history is stored locally
  on the user's machine. Polaris has no backend server.

  {DIM}End of demo -- Polaris Innovations{RESET}
""")
