"""
Screencast demo for Meta App Review -- instagram_content_publish permission.

Demonstrates:
1. How Polaris generates AI-written captions and uploads media
2. The three-step container -> status-check -> publish flow
3. All five content types: image, reel, carousel, story image, story video
4. Scheduled publishing via APScheduler

Run this while screen recording.
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, "src")

import sqlite3
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

cur.execute("""
    SELECT id, caption, media_type, media_url, status, instagram_media_id, created_at
    FROM contents
    ORDER BY id DESC LIMIT 5
""")
recent_content = cur.fetchall()
conn.close()

from polaris.config import get_settings
settings = get_settings()

# --------------------------------------------------------------------------
header("Polaris Innovations -- instagram_content_publish Demo")

print(f"""
  {BOLD}Feature:{RESET}  AI-Powered Content Generation and Publishing

  Polaris generates Instagram content with Claude AI -- captions,
  hashtags, and AI-generated images or videos -- then publishes it
  directly to Instagram using the Graph API.

  All five Instagram content types are supported:
    - Single image post
    - Reel (video)
    - Carousel (multi-image, up to 10 slides)
    - Instagram Story (image)
    - Instagram Story (video)

  Publishing can be triggered immediately or scheduled to run
  automatically via APScheduler.

  {BOLD}Permission used:{RESET}
    - instagram_content_publish  (create containers, publish media)

  {DIM}App ID: {settings.meta_app_id}{RESET}
  {DIM}Account: @{username}{RESET}
""")
pause(2)

# -- STEP 1: AI content generation ----------------------------------------
step(1, "Generate Content with Claude AI")

print(f"""
  The business owner runs:

    {BOLD}polaris content generate --topic "One AI tool that saved us 10 hours a week" --video{RESET}

  Polaris calls Claude API to produce:
    - An attention-grabbing caption with a strong hook
    - 20-30 relevant hashtags
    - A story-arc image prompt sequence (Problem -> Solution -> CTA)

  Then it generates images or video frames using AI image synthesis,
  assembles them into a slideshow video with Ken Burns motion effects
  and per-slide text overlays, and uploads the file to Cloudinary
  to obtain a publicly accessible HTTPS URL for the Instagram API.
""")
pause()

if recent_content:
    latest = recent_content[0]
    lid, caption, mtype, murl, status, ig_mid, sched = latest
    print(f"  {GREEN}Most recently generated content (ID {lid}):{RESET}\n")
    info("Content ID:",    str(lid))
    info("Media type:",    mtype or "REEL")
    info("Status:",        status or "--")
    info("IG Media ID:",   ig_mid or "(not yet published)")
    if caption:
        snippet = caption[:70].replace("\n", " ")
        info("Caption:",   f"\"{snippet}...\"")
    if murl:
        info("Media URL:", murl[:55] + "..." if len(murl) > 55 else murl)
pause(2)

# -- STEP 2: The three-step publishing flow --------------------------------
step(2, "Three-Step Publishing Flow")

print(f"""
  The Instagram Content Publish API uses a {BOLD}container model{RESET}:

    1.  Create a media container  (Polaris uploads the media URL)
    2.  Poll the container status (wait for Instagram to process)
    3.  Publish the container     (makes it live on Instagram)

  All three steps use {BOLD}instagram_content_publish{RESET}.
""")
pause(2)

# -- STEP 3: Show all five content-type flows ------------------------------
step(3, "API Calls for All Five Content Types")

print(f"\n  {BOLD}A) Single Image Post{RESET}\n")
api_call("POST", f"/v18.0/{ig_user_id}/media",
         "image_url=<cdn_url>  caption=<text>")
api_call("GET",  "/v18.0/{container_id}",
         "fields=status_code,status")
api_call("POST", f"/v18.0/{ig_user_id}/media_publish",
         "creation_id={container_id}")
pause()

print(f"\n  {BOLD}B) Reel (Video){RESET}\n")
api_call("POST", f"/v18.0/{ig_user_id}/media",
         "video_url=<cdn_url>  caption=<text>  media_type=REELS")
api_call("GET",  "/v18.0/{container_id}",
         "fields=status_code,status  (poll until FINISHED, up to 10 min)")
api_call("POST", f"/v18.0/{ig_user_id}/media_publish",
         "creation_id={container_id}")
pause()

print(f"\n  {BOLD}C) Carousel (Multi-Image, 2-10 slides){RESET}\n")
api_call("POST", f"/v18.0/{ig_user_id}/media",
         "image_url=<url_1>  is_carousel_item=true  (x N slides)")
api_call("GET",  "/v18.0/{item_container_id}",
         "fields=status_code,status  (one check per item)")
api_call("POST", f"/v18.0/{ig_user_id}/media",
         "media_type=CAROUSEL  children=<id1,id2,...>  caption=<text>")
api_call("POST", f"/v18.0/{ig_user_id}/media_publish",
         "creation_id={carousel_container_id}")
pause()

print(f"\n  {BOLD}D) Instagram Story (Image){RESET}\n")
api_call("POST", f"/v18.0/{ig_user_id}/media",
         "image_url=<cdn_url>  media_type=STORIES")
api_call("GET",  "/v18.0/{container_id}",
         "fields=status_code,status")
api_call("POST", f"/v18.0/{ig_user_id}/media_publish",
         "creation_id={container_id}")
pause()

print(f"\n  {BOLD}E) Instagram Story (Video){RESET}\n")
api_call("POST", f"/v18.0/{ig_user_id}/media",
         "video_url=<cdn_url>  media_type=STORIES")
api_call("GET",  "/v18.0/{container_id}",
         "fields=status_code,status  (poll until FINISHED)")
api_call("POST", f"/v18.0/{ig_user_id}/media_publish",
         "creation_id={container_id}")
pause(2)

# -- STEP 4: Container status polling ------------------------------------
step(4, "Container Status Polling")

print(f"""
  After creating a container, Polaris polls its status every 5 seconds:

    GET /v18.0/{{container_id}}?fields=status_code,status

  Possible status_code values:

    {GREEN}FINISHED{RESET}    -> ready to publish
    {DIM}IN_PROGRESS{RESET} -> still processing (wait and retry)
    {YELLOW}EXPIRED{RESET}     -> took too long; retry the whole flow
    {YELLOW}ERROR{RESET}       -> failed; Polaris surfaces the error message

  Images time out after {BOLD}5 minutes{RESET}. Videos time out after {BOLD}10 minutes{RESET}.

  Polaris uses tenacity (exponential back-off with 3 retries) on
  the container creation and publish steps, so transient API errors
  are automatically recovered without user intervention.
""")
pause(2)

# -- STEP 5: Scheduled publishing -----------------------------------------
step(5, "Scheduled Publishing via APScheduler")

print(f"""
  Content saved with a future scheduled_for timestamp is published
  automatically when 'polaris run' is active:

    {BOLD}polaris run --foreground{RESET}

  APScheduler runs a check every minute. When the scheduled time
  arrives it calls InstagramPublisher.publish_content(content) which
  routes to the correct publish method based on media_type (IMAGE,
  REEL, CAROUSEL), then updates the content record:

    status           ->  PUBLISHED
    instagram_media_id  ->  <id returned by media_publish>
    published_at     ->  now()
""")
pause()

print(f"  Run {BOLD}polaris content list{RESET} to see the content queue:\n")
pause()

print(f"  +----+---------+------+------------+----------------------+")
print(f"  | ID | Type    | St.  | Created    | Caption              |")
print(f"  +----+---------+------+------------+----------------------+")
for row in recent_content:
    lid, cap, mtype, murl, status, ig_mid, created = row
    mt    = (mtype  or "REEL")[:7]
    st    = (status or "DRAFT")[:5]
    sc    = str(created)[:10] if created else "--"
    cap_s = ((cap or "")[:20]).replace("\n", " ")
    color = GREEN if status == "PUBLISHED" else (YELLOW if status == "SCHEDULED" else DIM)
    print(f"  |{lid:>3} | {mt:<7} | {color}{st}{RESET}  | {sc:<10} | {cap_s:<20} |")
print(f"  +----+---------+------+------------+----------------------+")
pause(2)

# -- STEP 6: Immediate publish from CLI -----------------------------------
step(6, "Immediate Publishing from the CLI")

print(f"""
  The business owner can publish immediately with:

    {BOLD}polaris content publish <id>{RESET}

  Or generate and publish in one command:

    {BOLD}polaris content generate --topic "..." --video --publish{RESET}

  Polaris prints each stage as it happens:

    {DIM}Creating media container...{RESET}
    {DIM}Container ID: 17846368219941196{RESET}
    {DIM}Waiting for container to be ready... (status: IN_PROGRESS){RESET}
    {DIM}Waiting for container to be ready... (status: IN_PROGRESS){RESET}
    {DIM}Container ready. Publishing...{RESET}
    {GREEN}Published! Instagram Media ID: 17846368219941197{RESET}
""")
pause(2)

# -- Summary ---------------------------------------------------------------
header("Summary")
print(f"""
  {BOLD}instagram_content_publish{RESET} allows Polaris to:

    {GREEN}1.{RESET}  Create media containers for all content types:
       - Single images  (POST /{{ig_user_id}}/media  image_url)
       - Reels          (POST /{{ig_user_id}}/media  video_url  media_type=REELS)
       - Carousels      (POST /{{ig_user_id}}/media  media_type=CAROUSEL)
       - Stories        (POST /{{ig_user_id}}/media  media_type=STORIES)

    {GREEN}2.{RESET}  Poll container status until the media is processed
       (GET /{{container_id}}?fields=status_code,status)

    {GREEN}3.{RESET}  Publish the processed container to Instagram
       (POST /{{ig_user_id}}/media_publish  creation_id)

  {BOLD}When publishing happens:{RESET}
    - Immediately via  polaris content publish <id>
    - Automatically when a scheduled time is reached (polaris run)
    - Inline during  polaris content generate --publish

  {BOLD}Media hosting:{RESET}
    Images and videos are hosted on Cloudinary (images) or
    Cloudinary/GitHub (images) before being submitted to the
    Instagram API. Instagram fetches from those public URLs during
    container processing.

  All content metadata is stored locally in SQLite.
  Polaris has no backend server. No data is shared externally.

  {DIM}End of demo -- Polaris Innovations{RESET}
""")
