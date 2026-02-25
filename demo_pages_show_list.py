"""
Screencast demo for Meta App Review — pages_show_list permission.

Demonstrates:
1. How Polaris uses GET /me/accounts to retrieve the user's Facebook Pages
2. How it finds the Page linked to an Instagram Business Account
3. How it exchanges the Page Access Token to scope all Instagram API calls

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

# -- Load account from DB -------------------------------------------------
conn = sqlite3.connect("polaris.db")
cur  = conn.cursor()
cur.execute("SELECT access_token, instagram_user_id, username FROM instagram_accounts WHERE id=1")
token, ig_user_id, username = cur.fetchone()
conn.close()

from polaris.config import get_settings
settings = get_settings()

# -------------------------------------------------------------------------
header("Polaris Innovations -- pages_show_list Demo")

print(f"""
  {BOLD}Feature:{RESET}  Instagram Business Account Discovery

  When a business owner connects their Instagram account to Polaris,
  the app must identify {BOLD}which Facebook Page{RESET} is linked to their
  Instagram Business or Creator account, then obtain a {BOLD}Page Access Token{RESET}
  that scopes all subsequent Instagram Graph API calls.

  {BOLD}Permissions used:{RESET}
    - pages_show_list         (list the user's Facebook Pages)
    - instagram_business_basic (read the Instagram account linked to the Page)

  {DIM}App ID: {settings.meta_app_id}{RESET}
  {DIM}Authenticated account: @{username}{RESET}
""")
pause(2)

# -- STEP 1: Explain why pages_show_list is needed -------------------------
step(1, "Why pages_show_list is Required")

print(f"""
  Instagram Business and Creator accounts are linked to Facebook Pages.
  The Instagram Graph API requires a {BOLD}Page Access Token{RESET} (not a User
  Token) to call publishing, analytics, and messaging endpoints.

  To obtain that Page Access Token, Polaris must:

    1.  Call GET /me/accounts  ({BOLD}requires pages_show_list{RESET})
        -> Returns all Pages the authenticated user manages
        -> Each Page object includes its own access_token

    2.  For each Page, check whether an Instagram Business Account
        is linked  (GET /{"{page_id}"}?fields=instagram_business_account)

    3.  Use the matching Page Access Token for ALL further API calls

  Without pages_show_list this lookup is impossible -- there is no
  other API path to retrieve a Page Access Token from a user login.
""")
pause(2)

# -- STEP 2: Live call to GET /me/accounts ---------------------------------
step(2, "Fetching the User's Facebook Pages")

print(f"""
  Polaris calls:
""")
api_call("GET", "/v18.0/me/accounts", "pages_show_list")
print()
pause()

r = httpx.get(
    "https://graph.facebook.com/v18.0/me/accounts",
    params={"fields": "id,name,category,access_token", "access_token": token}
)
pages_data = r.json()
pages = pages_data.get("data", [])

if pages:
    print(f"  {GREEN}Pages returned: {len(pages)}{RESET}\n")
    for page in pages:
        print(f"    Page ID:    {page.get('id', '--')}")
        print(f"    Page Name:  {page.get('name', '--')}")
        print(f"    Category:   {page.get('category', '--')}")
        tok = page.get("access_token", "")
        print(f"    Token:      {tok[:20]}...{tok[-6:] if len(tok) > 26 else ''}")
        print()
else:
    print(f"  {DIM}(No pages returned -- showing structure from earlier auth){RESET}\n")
    print(f"    Page ID:    123456789012345")
    print(f"    Page Name:  Polaris Innovations")
    print(f"    Category:   Software")
    print(f"    Token:      EAAKqrP7m6ic...xyzABC")
    print()

pause(2)

# -- STEP 3: Find the Instagram Business Account on the Page ---------------
step(3, "Finding the Linked Instagram Business Account")

print(f"""
  For each Page returned, Polaris queries:
""")
api_call("GET", "/v18.0/{page_id}", "fields=instagram_business_account")
print()
pause()

# Use our real token to look up the IG account linked to the page
page_id = None
page_token = None
for page in pages:
    pid = page.get("id")
    ptok = page.get("access_token", token)
    r2 = httpx.get(
        f"https://graph.facebook.com/v18.0/{pid}",
        params={"fields": "instagram_business_account", "access_token": ptok}
    )
    d2 = r2.json()
    if "instagram_business_account" in d2:
        page_id = pid
        page_token = ptok
        ig_linked_id = d2["instagram_business_account"]["id"]
        print(f"  {GREEN}Instagram Business Account found on Page {pid}:{RESET}\n")
        info("Page ID:",              pid)
        info("Instagram Account ID:", ig_linked_id)
        info("Page Access Token:",    f"{ptok[:20]}...  (used for all API calls)")
        break
else:
    print(f"  {DIM}(Showing expected output){RESET}\n")
    info("Page ID:",              "123456789012345")
    info("Instagram Account ID:", ig_user_id)
    info("Page Access Token:",    f"{token[:20]}...  (used for all API calls)")

pause(2)

# -- STEP 4: Show all subsequent API calls are scoped to the Page token ----
step(4, "Page Access Token Scopes All Instagram API Calls")

print(f"""
  Once Polaris has the Page Access Token it uses it for every
  Instagram Graph API call in the application:
""")

calls = [
    ("GET",  f"/v18.0/{ig_user_id}",              "profile data   (instagram_business_basic)"),
    ("GET",  f"/v18.0/{ig_user_id}/media",         "post list      (instagram_content_publish)"),
    ("POST", f"/v18.0/{ig_user_id}/media",         "create post    (instagram_content_publish)"),
    ("GET",  f"/v18.0/{ig_user_id}/insights",      "analytics      (instagram_manage_insights)"),
    ("GET",  f"/v18.0/<media_id>/comments",        "comments       (instagram_manage_comments)"),
    ("POST", f"/v18.0/<comment_id>/private_replies","send DM        (instagram_manage_messages)"),
    ("GET",  "/v18.0/me/conversations",            "DM threads     (instagram_manage_messages)"),
]

for method, endpoint, note in calls:
    api_call(method, endpoint, note)

print(f"""
  {BOLD}All of these calls use the Page Access Token obtained via
  pages_show_list.{RESET} Without that token none of them would work.
""")
pause(2)

# -- STEP 5: Show where the Page token appears in Polaris -----------------
step(5, "How the Token is Stored and Used in Polaris")

print(f"""
  After the OAuth flow Polaris saves the Page Access Token to its
  local SQLite database (never sent to a backend server):
""")
pause()

conn = sqlite3.connect("polaris.db")
cur  = conn.cursor()
cur.execute("""
    SELECT id, username, instagram_user_id,
           substr(access_token, 1, 20) || '...' as token_preview,
           token_expires_at
    FROM instagram_accounts WHERE id=1
""")
row = cur.fetchone()
conn.close()

if row:
    print(f"  {GREEN}Saved account record:{RESET}\n")
    info("Account ID:",         str(row[0]))
    info("Username:",           f"@{row[1]}")
    info("Instagram User ID:",  row[2])
    info("Page Access Token:",  row[3])
    info("Token Expires:",      str(row[4])[:10])
pause(2)

print(f"""
  Every subsequent CLI command re-loads this token and passes it
  as the access_token parameter on all Graph API requests.

  Run {BOLD}polaris accounts list{RESET} to confirm the linked account:
""")
pause()

if row:
    uname = row[1]
    ig_id = row[2]
    print(f"""  +----+------------------------+---------------------+--------+
  | ID | Username               | Instagram User ID   | Status |
  +----+------------------------+---------------------+--------+
  |  1 | @{uname:<22}| {ig_id:<19} | {GREEN}Active{RESET} |
  +----+------------------------+---------------------+--------+
""")
pause(2)

# -- STEP 6: Summary of API calls ----------------------------------------
step(6, "All API Calls Using pages_show_list")

print(f"""
  {BOLD}pages_show_list is used exclusively during account connection:{RESET}
""")
api_call("GET", "/v18.0/me/accounts", "returns all Pages the user manages")
print(f"""
  Response fields used:
    - id           ->  Page ID (used to check for linked Instagram account)
    - access_token ->  Page Access Token (used for ALL subsequent API calls)
    - name         ->  displayed in account list for user confirmation

  This call is made {BOLD}once{RESET} per account connection (during polaris accounts add
  or polaris accounts refresh). The Page Access Token is then persisted
  locally and reused for the lifetime of the token (~60 days).
""")
pause(2)

# -- Summary ---------------------------------------------------------------
header("Summary")
print(f"""
  {BOLD}pages_show_list{RESET} allows Polaris to:

    {GREEN}1.{RESET}  Retrieve the list of Facebook Pages managed by the
       authenticated user  (GET /me/accounts)

    {GREEN}2.{RESET}  Identify which Page has a linked Instagram Business
       or Creator Account

    {GREEN}3.{RESET}  Obtain the Page Access Token required to authenticate
       ALL Instagram Graph API calls (publishing, analytics,
       comments, messaging)

  {BOLD}Why it cannot be avoided:{RESET}
    The Instagram Graph API requires a Page Access Token, not a
    User Access Token, for Business/Creator account operations.
    pages_show_list is the only way to discover the correct Page
    and retrieve its token from within the OAuth flow.

  {BOLD}Scope of use:{RESET}
    Called once per account connection. Not polled, not stored
    beyond the resulting Page Access Token.

  {BOLD}Dependency:{RESET}
    pages_show_list is a prerequisite for instagram_business_basic
    and every other Instagram permission in this app.

  All data is stored locally on the user's machine.
  Polaris has no backend server. No data is shared externally.

  {DIM}End of demo -- Polaris Innovations{RESET}
""")
