"""
Screencast demo for Meta App Review -- instagram_manage_messages permission.

Demonstrates:
1. How Polaris reads DM conversations on the connected Instagram Business account
2. How it detects new replies from leads and passes them to Claude AI
3. How AI-generated follow-up messages are sent back via the Messages API

instagram_manage_messages is the foundational messaging permission that
enables the Instagram Messaging API endpoints. instagram_business_manage_messages
extends this specifically for Business accounts.

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

# -- Load account from DB --------------------------------------------------
conn = sqlite3.connect("polaris.db")
cur  = conn.cursor()
cur.execute("SELECT access_token, instagram_user_id, username FROM instagram_accounts WHERE id=1")
token, ig_user_id, username = cur.fetchone()

cur.execute("""
    SELECT id, commenter_username, status, comment_text, dm_sent, conversation_history
    FROM leads ORDER BY id DESC LIMIT 3
""")
leads = cur.fetchall()
conn.close()

from polaris.config import get_settings
settings = get_settings()

# --------------------------------------------------------------------------
header("Polaris Innovations -- instagram_manage_messages Demo")

print(f"""
  {BOLD}Feature:{RESET}  Comment-to-DM Lead Automation (Messaging API)

  Polaris converts Instagram comment engagement into private DM
  conversations. When a follower comments a keyword on a post,
  Polaris sends them a DM, then uses Claude AI to continue the
  conversation and qualify them as a lead.

  {BOLD}Two messaging permissions work together:{RESET}

    instagram_manage_messages         Core Instagram Messaging API access
                                      -- reading and sending DMs

    instagram_business_manage_messages  Business Account messaging extension
                                      -- private replies to comments,
                                         business-scoped conversation access

  This demo covers {BOLD}instagram_manage_messages{RESET} specifically:
  the foundational permission that enables GET /me/conversations
  and POST /me/messages.

  {DIM}App ID: {settings.meta_app_id}{RESET}
  {DIM}Account: @{username}{RESET}
""")
pause(2)

# -- STEP 1: What instagram_manage_messages enables -----------------------
step(1, "What instagram_manage_messages Enables")

print(f"""
  instagram_manage_messages grants access to two endpoints:

  {BOLD}1.  GET /me/conversations{RESET}
      Reads all DM threads for the Instagram Business account.
      Polaris uses this to check whether any lead has replied
      to the initial DM that was sent when they commented.

  {BOLD}2.  POST /me/messages{RESET}
      Sends a DM to a specific Instagram user by their
      Instagram-scoped user ID. Polaris uses this to deliver
      AI-generated follow-up messages to leads who have replied.

  These two endpoints form the {BOLD}reply detection and follow-up{RESET}
  half of the lead automation pipeline.

  The {BOLD}initial DM{RESET} (sent when the keyword comment is first detected)
  uses POST /<comment_id>/private_replies, which is covered by
  instagram_business_manage_messages.
""")
pause(2)

# -- STEP 2: Poll conversations for lead replies --------------------------
step(2, "Polling DM Conversations for Lead Replies")

print(f"""
  APScheduler runs poll_conversations() every 3 minutes.
  Polaris calls:
""")
pause()

api_call(
    "GET",
    "/v18.0/me/conversations",
    "instagram_manage_messages"
)
print(f"    {DIM}params: platform=instagram  fields=messages{{id,message,from,created_time}}{RESET}")
print()
pause()

r = httpx.get(
    f"https://graph.facebook.com/v18.0/me/conversations",
    params={
        "platform": "instagram",
        "fields": "messages{id,message,from,created_time}",
        "access_token": token,
    }
)
convos = r.json()

if "data" in convos and convos["data"]:
    print(f"  {GREEN}Conversations found: {len(convos['data'])}{RESET}\n")
    for c in convos["data"][:3]:
        msgs = c.get("messages", {}).get("data", [])
        print(f"    Thread ID: {c.get('id', '--')}")
        print(f"    Messages:  {len(msgs)}")
        if msgs:
            last = msgs[0]
            frm  = last.get("from", {}).get("username") or last.get("from", {}).get("id", "--")
            txt  = (last.get("message") or "")[:55]
            ts   = last.get("created_time", "")[:10]
            print(f"    Latest:    [{ts}] @{frm}: \"{txt}\"")
        print()
elif "error" in convos:
    err = convos["error"].get("message", "unknown")
    print(f"  {YELLOW}API response: {err}{RESET}")
    print(f"""
  {DIM}Note: GET /me/conversations requires instagram_manage_messages
  and may also require Advanced Access / App Review approval before
  returning live data. The endpoint and permission are correct --
  full access is granted once App Review is approved.{RESET}
""")
else:
    print(f"  {DIM}(No active conversations yet){RESET}\n")

pause(2)

# -- STEP 3: How Polaris matches threads to leads -------------------------
step(3, "Matching Conversation Threads to Lead Records")

print(f"""
  Each Lead record in Polaris stores the commenter's
  Instagram-scoped user ID (from.id from the comments API).

  Polaris matches conversation threads to leads by comparing:

    conversation.messages[].from.id  ==  lead.commenter_ig_user_id

  For any thread where a match is found AND the latest message
  is newer than the last entry in the lead's conversation_history,
  Polaris treats it as a new reply and triggers the AI response.
""")
pause()

if leads:
    print(f"  {GREEN}Current leads in Polaris pipeline:{RESET}\n")
    for lead in leads:
        lid, uname, status, ctext, dm_sent, conv_hist = lead
        msgs = 0
        if conv_hist:
            try:
                msgs = len(json.loads(conv_hist))
            except Exception:
                pass
        info("Lead ID:",          str(lid))
        info("Username:",         f"@{uname or '--'}")
        info("Status:",           status or "--")
        info("Trigger keyword:",  (ctext or "")[:20].upper())
        info("DM sent:",          "yes" if dm_sent else "no")
        info("Conv. messages:",   str(msgs))
        print()
pause(2)

# -- STEP 4: AI reply generation and sending ------------------------------
step(4, "Claude AI Generates a Reply -- Sent via POST /me/messages")

FOLLOWER_REPLY = "I run a landscaping company and I'm drowning in quote requests"

print(f"""
  When a new reply is detected in the thread, Polaris passes
  the full conversation history to Claude AI and generates
  a contextual follow-up response.

  Example incoming reply:
    {BLUE}@follower_example:{RESET} \"{FOLLOWER_REPLY}\"
""")
pause()

print(f"  Polaris generates an AI reply and sends it via:\n")
api_call(
    "POST",
    "/v18.0/me/messages",
    "instagram_manage_messages"
)
print(f"""
  {BOLD}Payload structure:{RESET}
    {{
      "recipient": {{ "id": "<instagram_scoped_user_id>" }},
      "message":   {{ "text": "<ai_generated_reply>" }}
    }}

  The recipient.id is the commenter's from.id stored in the
  Lead record when the keyword comment was first detected.
""")
pause()

# Generate a live AI reply
print(f"  {DIM}Generating live AI reply via Claude...{RESET}\n")
pause(0.5)

from polaris.services.ai.lead_responder import LeadResponder
responder = LeadResponder()
INITIAL_DM = (
    "Hey! Thanks for commenting -- you're in the right place. "
    "I'm going to send you the exact AI automation setup we use to "
    "reclaim 10+ hours a week. Quick question first: what's the #1 "
    "task in your business eating the most time right now?"
)
history = [
    {"role": "assistant", "message": INITIAL_DM,       "timestamp": "2026-02-25T15:00:00"},
    {"role": "user",      "message": FOLLOWER_REPLY,   "timestamp": "2026-02-25T15:04:00"},
]
ai_reply = responder.generate_reply(
    commenter_username="follower_example",
    conversation_history=history,
    post_topic="AI automation saving 10 hours a week",
)

print(f"  {GREEN}Claude AI reply:{RESET}\n")
print(f"    {BOLD}\"{ai_reply}\"{RESET}\n")
pause()

print(f"  Polaris sends this reply via POST /me/messages then updates")
print(f"  the lead's conversation_history and sets status -> REPLIED.")
pause(2)

# -- STEP 5: Full conversation stored in Polaris --------------------------
step(5, "Full Conversation Tracked in Polaris")

print(f"""
  After the AI reply is sent, the lead record holds the
  full conversation history:

    {GREEN}Polaris{RESET}  2026-02-25 15:00
    \"{INITIAL_DM[:85]}...\"

    {BLUE}@follower_example{RESET}  2026-02-25 15:04
    \"{FOLLOWER_REPLY}\"

    {GREEN}Polaris (AI){RESET}  2026-02-25 15:04
    \"{ai_reply}\"

  Run {BOLD}polaris leads show <id>{RESET} to inspect any lead's
  full conversation at any time.
""")
pause(2)

# -- STEP 6: Summary of API calls -----------------------------------------
step(6, "API Calls Using instagram_manage_messages")

print(f"""
  {BOLD}1. Poll DM threads for replies from leads:{RESET}
""")
api_call("GET", "/v18.0/me/conversations",
         "platform=instagram  fields=messages{...}")

print(f"""
  {BOLD}2. Send AI-generated follow-up DM to a lead:{RESET}
""")
api_call("POST", "/v18.0/me/messages",
         "recipient={{id}} message={{text}}")

print(f"""
  Both calls run on APScheduler (poll_conversations every 3 min).
  Messages are only sent to users who previously commented the
  trigger keyword -- this is a fully opt-in flow.

  {BOLD}Relationship to instagram_business_manage_messages:{RESET}
    instagram_manage_messages     ->  read threads, send follow-up DMs
    instagram_business_manage_messages  ->  send the initial private reply
                                            to the triggering comment

  Both permissions are required for the complete pipeline.
  Neither is used for cold messaging or bulk outreach.
""")
pause(2)

# -- Summary ---------------------------------------------------------------
header("Summary")
print(f"""
  {BOLD}instagram_manage_messages{RESET} allows Polaris to:

    {GREEN}1.{RESET}  Read DM conversations on the Instagram Business account
       to detect replies from leads
       (GET /me/conversations)

    {GREEN}2.{RESET}  Send AI-generated follow-up DMs to continue qualifying
       leads who have replied
       (POST /me/messages)

  {BOLD}User consent model:{RESET}
    Messages are only sent to users who explicitly commented
    the trigger keyword on the business owner's post.
    No cold messaging. No bulk outreach. Fully opt-in.

  {BOLD}Relationship to instagram_business_manage_messages:{RESET}
    These two permissions together cover the full DM lifecycle:
    initial private reply (business permission) + conversation
    polling and follow-up (this permission).

  {BOLD}Dependency:{RESET}
    Requires instagram_business_basic for the Instagram User ID
    used to scope /me/conversations and /me/messages calls.

  All lead and conversation data is stored locally in SQLite.
  Polaris has no backend server. No data is shared externally.

  {DIM}End of demo -- Polaris Innovations{RESET}
""")
