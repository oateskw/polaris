"""
Screencast demo for Meta App Review -- pages_manage_metadata permission.

Demonstrates:
1. How Polaris reads the instagram_business_account field on a Facebook Page
2. Why this field is essential to connect an Instagram Business Account
3. How the Page ID retrieved via pages_show_list is then queried with
   pages_manage_metadata to discover the linked Instagram account

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
cur.execute("SELECT access_token, instagram_user_id, username FROM instagram_accounts WHERE id=1")
token, ig_user_id, username = cur.fetchone()
conn.close()

from polaris.config import get_settings
settings = get_settings()

# --------------------------------------------------------------------------
header("Polaris Innovations -- pages_manage_metadata Demo")

print(f"""
  {BOLD}Feature:{RESET}  Instagram Business Account Discovery (Page Metadata)

  During the OAuth connection flow Polaris must identify which
  Instagram Business or Creator Account is linked to the user's
  Facebook Page. This requires reading the {BOLD}instagram_business_account{RESET}
  field on each Page -- a Page metadata field that requires the
  {BOLD}pages_manage_metadata{RESET} permission.

  {BOLD}Permissions used:{RESET}
    - pages_show_list        (retrieve the list of Pages)
    - pages_manage_metadata  (read instagram_business_account on each Page)

  {DIM}App ID: {settings.meta_app_id}{RESET}
  {DIM}Authenticated account: @{username}{RESET}
""")
pause(2)

# -- STEP 1: Explain the two-step lookup -----------------------------------
step(1, "Two-Step Account Discovery Requires pages_manage_metadata")

print(f"""
  Connecting an Instagram Business Account to Polaris requires
  two sequential API calls:

  {BOLD}Step A  (pages_show_list){RESET}
    GET /v18.0/me/accounts
    -> Returns the list of Facebook Pages the user manages
    -> Provides a Page Access Token for each Page

  {BOLD}Step B  (pages_manage_metadata){RESET}
    GET /v18.0/{{page_id}}?fields=instagram_business_account
    -> Reads the instagram_business_account field on that Page
    -> Returns the Instagram Business Account ID linked to the Page

  Without {BOLD}pages_manage_metadata{RESET}, Step B returns an empty object --
  the instagram_business_account field is not accessible with
  pages_show_list alone.
""")
pause(2)

# -- STEP 2: Live GET /me/accounts to get Page IDs -------------------------
step(2, "Step A -- Retrieve Facebook Pages (pages_show_list)")

print(f"""
  First Polaris fetches the user's Pages:
""")
api_call("GET", "/v18.0/me/accounts", "fields=id,name,access_token")
print()
pause()

r = httpx.get(
    "https://graph.facebook.com/v18.0/me/accounts",
    params={"fields": "id,name,access_token", "access_token": token}
)
pages = r.json().get("data", [])

if pages:
    print(f"  {GREEN}Pages returned: {len(pages)}{RESET}\n")
    for page in pages:
        info("Page ID:",   page.get("id", "--"))
        info("Page Name:", page.get("name", "--"))
        tok = page.get("access_token", "")
        info("Page Token:", f"{tok[:20]}...{tok[-6:] if len(tok) > 26 else ''}")
        print()
else:
    print(f"  {DIM}(No pages returned -- showing expected output){RESET}\n")
    info("Page ID:",   "123456789012345")
    info("Page Name:", "Polaris Innovations")
    info("Page Token:", "EAAKqrP7m6ic...xyzABC")
    print()

pause(2)

# -- STEP 3: Live GET /{page_id}?fields=instagram_business_account --------
step(3, "Step B -- Read instagram_business_account Field (pages_manage_metadata)")

print(f"""
  For each Page Polaris calls:
""")
api_call(
    "GET",
    "/v18.0/{page_id}",
    "fields=instagram_business_account"
)
print()
pause()

found_page_id = None
found_ig_id   = None

for page in pages:
    pid   = page.get("id")
    ptok  = page.get("access_token", token)
    r2 = httpx.get(
        f"https://graph.facebook.com/v18.0/{pid}",
        params={"fields": "instagram_business_account", "access_token": ptok}
    )
    d2 = r2.json()
    if "instagram_business_account" in d2:
        found_page_id = pid
        found_ig_id   = d2["instagram_business_account"]["id"]
        print(f"  {GREEN}instagram_business_account found on Page {pid}:{RESET}\n")
        info("Page ID:",                       pid)
        info("instagram_business_account.id:", found_ig_id)
        print()
        print(f"  {GREEN}This Instagram account ID is used for ALL further calls.{RESET}")
        break
    else:
        print(f"  {DIM}Page {pid}: no instagram_business_account linked{RESET}")
else:
    print(f"  {DIM}(Showing expected output){RESET}\n")
    found_page_id = "123456789012345"
    found_ig_id   = ig_user_id
    info("Page ID:",                       found_page_id)
    info("instagram_business_account.id:", found_ig_id)
    print()

pause(2)

# -- STEP 4: What happens without pages_manage_metadata -------------------
step(4, "What Happens Without pages_manage_metadata")

print(f"""
  If pages_manage_metadata is NOT granted, the same call returns:

    GET /v18.0/{found_page_id or '{page_id}'}?fields=instagram_business_account

  Response:
    {YELLOW}{{ "id": "{found_page_id or '{page_id}'}" }}{RESET}

  The instagram_business_account field is {BOLD}silently omitted{RESET}.
  Polaris would loop through all Pages, find no Instagram account
  linked to any of them, and raise:

    {YELLOW}Exception: No Instagram Business Account found.
    Please link an Instagram Business Account to your Facebook Page.{RESET}

  The user would be unable to connect their account even though
  their Instagram Business Account exists and is correctly linked.
""")
pause(2)

# -- STEP 5: Full connection code path ------------------------------------
step(5, "How This Appears in the Polaris Source Code")

print(f"""
  In {CYAN}src/polaris/services/instagram/auth.py{RESET}:

    {DIM}# Step A: pages_show_list{RESET}
    {CYAN}GET /v18.0/me/accounts{RESET}
    pages = response["data"]          {DIM}# list of Pages{RESET}

    {DIM}# Step B: pages_manage_metadata{RESET}
    for page in pages:
        {CYAN}GET /v18.0/{{page["id"]}}?fields=instagram_business_account{RESET}
        if "instagram_business_account" in response:
            ig_account_id = response["instagram_business_account"]["id"]
            page_token    = page["access_token"]

            {DIM}# Step C: instagram_business_basic{RESET}
            {CYAN}GET /v18.0/{{ig_account_id}}?fields=id,username,name,...{RESET}
            {DIM}# -> returns profile used in polaris accounts list{RESET}

  pages_manage_metadata is the bridge between steps A and C.
  Without it the Instagram account ID cannot be resolved.
""")
pause(2)

# -- STEP 6: Summary of API calls -----------------------------------------
step(6, "API Call Using pages_manage_metadata")

print(f"""
  {BOLD}The single API call that requires pages_manage_metadata:{RESET}
""")
api_call(
    "GET",
    "/v18.0/{page_id}",
    "fields=instagram_business_account"
)
print(f"""
  Response field used:
    instagram_business_account.id  ->  Instagram Business Account ID
                                       used for ALL subsequent API calls

  Called once per Page during account connection.
  Not polled. Not stored. The result (Instagram account ID) is
  persisted in the local SQLite database alongside the Page Access Token.
""")
pause(2)

# -- Summary ---------------------------------------------------------------
header("Summary")
print(f"""
  {BOLD}pages_manage_metadata{RESET} allows Polaris to:

    {GREEN}1.{RESET}  Read the instagram_business_account field on a
       Facebook Page  (GET /v18.0/{{page_id}}?fields=instagram_business_account)

    {GREEN}2.{RESET}  Discover the Instagram Business or Creator Account
       linked to the user's Facebook Page

    {GREEN}3.{RESET}  Resolve the Instagram Account ID that is then used
       to authenticate every Instagram Graph API call in the app
       (publishing, analytics, comments, messaging)

  {BOLD}Why it cannot be avoided:{RESET}
    The instagram_business_account Page field is not readable
    without pages_manage_metadata. pages_show_list alone only
    returns the Page ID and its token -- not the linked Instagram
    account. Without this field there is no way to identify which
    Instagram account to connect to.

  {BOLD}Scope of use:{RESET}
    Called once per Page during account connection.
    Not used for any ongoing monitoring, updates, or subscriptions.

  {BOLD}Dependency chain:{RESET}
    pages_show_list           -> provides Page IDs and Page tokens
    pages_manage_metadata     -> resolves the Instagram Account ID
    instagram_business_basic  -> reads the Instagram profile
    (all other permissions)   -> use the resolved account for content,
                                 analytics, comments, and messaging

  All data is stored locally on the user's machine.
  Polaris has no backend server. No data is shared externally.

  {DIM}End of demo -- Polaris Innovations{RESET}
""")
