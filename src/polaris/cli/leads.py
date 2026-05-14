"""CLI commands for lead management (comment-to-DM automation)."""

import re

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from polaris.config import get_settings

leads_app = typer.Typer(help="Manage comment-to-DM lead automation")
outreach_app = typer.Typer(help="Track manual DM outreach in Google Sheets")
leads_app.add_typer(outreach_app, name="outreach")
console = Console()


def _get_session():
    settings = get_settings()
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    return Session()


def _get_active_account(session, account_id=None):
    from polaris.repositories import AccountRepository

    repo = AccountRepository(session)
    if account_id:
        return repo.get(account_id)
    accounts = repo.get_active_accounts()
    return accounts[0] if accounts else None


@leads_app.command("setup")
def setup(
    account_id: int = typer.Option(
        None, "--account", "-a", help="Account ID (uses first active if not specified)"
    ),
):
    """Set up a new comment trigger on an Instagram post."""
    session = _get_session()

    account = _get_active_account(session, account_id)
    if not account:
        console.print("[red]Error:[/red] No active Instagram account found.")
        console.print("Run 'polaris accounts add' to connect an account.")
        session.close()
        raise typer.Exit(1)

    console.print(
        f"\n[bold blue]Setting up comment trigger for @{account.username}[/bold blue]\n"
    )

    post_id = typer.prompt("Enter the Instagram media ID of the post to watch")
    keyword = typer.prompt("Trigger keyword (e.g. INFO)")
    initial_message = typer.prompt(
        "Initial DM message to send when keyword is detected (make it niche-specific and end with one clear question)",
    )
    follow_up = typer.confirm("Enable AI follow-up replies?", default=True)

    from polaris.repositories.lead_repository import CommentTriggerRepository

    repo = CommentTriggerRepository(session)
    trigger = repo.create_trigger(
        account_id=account.id,
        post_instagram_media_id=post_id.strip(),
        keyword=keyword.strip(),
        initial_message=initial_message.strip(),
        follow_up_enabled=follow_up,
    )
    session.commit()

    console.print(f"\n[bold green]Trigger #{trigger.id} created![/bold green]")
    console.print(f"  Post:    {post_id}")
    console.print(f"  Keyword: {keyword}")
    console.print(f"  AI follow-up: {'enabled' if follow_up else 'disabled'}")
    console.print("\nPolling starts automatically when 'polaris run' is active.")
    session.close()


@leads_app.command("triggers")
def triggers(
    account_id: int = typer.Option(None, "--account", "-a", help="Account ID"),
):
    """List all configured comment triggers."""
    session = _get_session()
    account = _get_active_account(session, account_id)
    if not account:
        console.print("[red]No active account found.[/red]")
        session.close()
        raise typer.Exit(1)
    active_account_id = account.id

    from sqlalchemy import select
    from polaris.models.lead import CommentTrigger

    stmt = select(CommentTrigger).where(CommentTrigger.account_id == account.id)
    account_triggers = list(session.execute(stmt).scalars().all())

    if not account_triggers:
        console.print(
            "No triggers configured. Run 'polaris leads setup' to create one."
        )
        session.close()
        return

    table = Table(title=f"Comment Triggers — @{account.username}")
    table.add_column("ID", style="dim")
    table.add_column("Post ID")
    table.add_column("Keyword")
    table.add_column("Follow-up")
    table.add_column("Active")
    table.add_column("Last Polled")

    for t in account_triggers:
        last_polled = (
            t.last_polled_at.strftime("%Y-%m-%d %H:%M") if t.last_polled_at else "never"
        )
        table.add_row(
            str(t.id),
            t.post_instagram_media_id,
            t.keyword,
            "[green]yes[/green]" if t.follow_up_enabled else "[dim]no[/dim]",
            "[green]yes[/green]" if t.is_active else "[red]no[/red]",
            last_polled,
        )

    console.print(table)
    session.close()


@leads_app.command("pause")
def pause(
    trigger_id: int = typer.Argument(..., help="Trigger ID to pause"),
):
    """Pause a comment trigger (stops polling)."""
    session = _get_session()
    from polaris.repositories.lead_repository import CommentTriggerRepository

    repo = CommentTriggerRepository(session)
    trigger = repo.deactivate(trigger_id)
    if not trigger:
        console.print(f"[red]Trigger #{trigger_id} not found.[/red]")
        session.close()
        raise typer.Exit(1)

    session.commit()
    console.print(f"[yellow]Trigger #{trigger_id} paused.[/yellow]")
    session.close()


@leads_app.command("resume")
def resume(
    trigger_id: int = typer.Argument(..., help="Trigger ID to resume"),
):
    """Resume a paused comment trigger."""
    session = _get_session()
    from polaris.repositories.lead_repository import CommentTriggerRepository

    repo = CommentTriggerRepository(session)
    trigger = repo.activate(trigger_id)
    if not trigger:
        console.print(f"[red]Trigger #{trigger_id} not found.[/red]")
        session.close()
        raise typer.Exit(1)

    session.commit()
    console.print(f"[green]Trigger #{trigger_id} resumed.[/green]")
    session.close()


@leads_app.command("list")
def list_leads(
    account_id: int = typer.Option(None, "--account", "-a", help="Account ID"),
    status: str = typer.Option(
        None,
        "--status",
        "-s",
        help="Filter by status (NEW, CONTACTED, REPLIED, QUALIFIED, CLOSED)",
    ),
    limit: int = typer.Option(50, "--limit", "-n", help="Max leads to show"),
):
    """List leads with their status and last message snippet."""
    session = _get_session()
    account = _get_active_account(session, account_id)
    if not account:
        console.print("[red]No active account found.[/red]")
        session.close()
        raise typer.Exit(1)

    from polaris.models.lead import LeadStatus
    from polaris.repositories.lead_repository import LeadRepository

    repo = LeadRepository(session)

    lead_status = None
    if status:
        try:
            lead_status = LeadStatus(status.upper())
        except ValueError:
            console.print(
                f"[red]Invalid status '{status}'. Choose from: NEW, CONTACTED, REPLIED, QUALIFIED, CLOSED[/red]"
            )
            session.close()
            raise typer.Exit(1)

    leads = repo.get_by_account(account.id, status=lead_status, limit=limit)

    if not leads:
        console.print("No leads found.")
        session.close()
        return

    table = Table(title=f"Leads — @{account.username}")
    table.add_column("ID", style="dim")
    table.add_column("Username")
    table.add_column("Status")
    table.add_column("Keyword")
    table.add_column("Last Message")
    table.add_column("Created")

    status_colors = {
        "NEW": "white",
        "CONTACTED": "cyan",
        "REPLIED": "blue",
        "QUALIFIED": "green",
        "CLOSED": "dim",
    }

    for lead in leads:
        history = lead.conversation_history or []
        last_msg = ""
        if history:
            last_entry = history[-1]
            snippet = last_entry.get("message", "")[:50]
            last_msg = f"[{last_entry.get('role', '?')}] {snippet}{'...' if len(last_entry.get('message', '')) > 50 else ''}"

        color = status_colors.get(lead.status.value, "white")
        created = lead.created_at.strftime("%m-%d %H:%M") if lead.created_at else ""

        table.add_row(
            str(lead.id),
            f"@{lead.commenter_username}",
            f"[{color}]{lead.status.value}[/{color}]",
            lead.trigger.keyword if lead.trigger else "",
            last_msg,
            created,
        )

    console.print(table)
    session.close()


@leads_app.command("reply-comments")
def reply_comments(
    account_id: int = typer.Option(
        None, "--account", "-a", help="Account ID (uses first active if not specified)"
    ),
):
    """Reply publicly to all new comments on recent posts using Claude.

    Run every 5 minutes via Task Scheduler for continuous engagement.
    Logs to logs/comment_replies.log.
    """
    import logging
    from logging.handlers import RotatingFileHandler
    from pathlib import Path

    log_path = Path(__file__).parents[4] / "logs" / "comment_replies.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(str(log_path), maxBytes=5_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])

    session = _get_session()
    account = _get_active_account(session, account_id)
    if not account:
        console.print("[red]No active account found.[/red]")
        session.close()
        raise typer.Exit(1)

    from polaris.services.comment_reply_service import CommentReplyService

    try:
        service = CommentReplyService(session, account)
        replied = service.run()
        if replied:
            console.print(f"[green]Posted {replied} public reply/replies.[/green]")
        else:
            console.print("[dim]No new comments to reply to.[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        logging.error(f"reply-comments failed: {e}")
        session.close()
        raise typer.Exit(1)

    session.close()


@leads_app.command("poll")
def poll(
    account_id: int = typer.Option(
        None, "--account", "-a", help="Account ID (uses first active if not specified)"
    ),
):
    """Run one pass of comment trigger polling and AI conversation follow-ups.

    Designed to be called every 2 minutes via Task Scheduler — no persistent
    process needed.
    """
    import logging
    from logging.handlers import RotatingFileHandler
    from pathlib import Path

    # Log to file so silent Task Scheduler runs leave a trail
    log_path = Path(__file__).parents[4] / "logs" / "leads.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(str(log_path), maxBytes=5_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])

    session = _get_session()
    account = _get_active_account(session, account_id)
    if not account:
        console.print("[red]No active account found.[/red]")
        session.close()
        raise typer.Exit(1)

    from polaris.services.lead_service import LeadService

    active_account_id = account.id

    try:
        service = LeadService(session, account)

        new_leads = service.poll_triggers()
        if new_leads:
            console.print(f"[green]{new_leads} new lead(s) detected and DM'd.[/green]")
        else:
            console.print("[dim]No new trigger matches.[/dim]")

        replies = service.poll_conversations()
        if replies:
            console.print(f"[green]{replies} AI reply/replies sent.[/green]")
        else:
            console.print("[dim]No pending conversations.[/dim]")

    except Exception as e:
        console.print(f"[red]Poll error:[/red] {e}")
        session.rollback()
        logging.error(f"Poll failed for account {active_account_id}: {e}")
        session.close()
        raise typer.Exit(1)

    session.close()


@leads_app.command("poll_inbound")
def poll_inbound(
    account_id: int = typer.Option(
        None, "--account", "-a", help="Account ID (uses first active if not specified)"
    ),
):
    """Check inbound DMs for trigger keywords and send initial responses.

    This is an alternative to comment trigger polling that doesn't require
    outbound messaging permissions. Users send DMs with your trigger keyword
    (e.g. 'CAKE') and get an automated response.
    """
    import logging
    from logging.handlers import RotatingFileHandler
    from pathlib import Path

    # Log to file so silent Task Scheduler runs leave a trail
    log_path = Path(__file__).parents[4] / "logs" / "leads.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(str(log_path), maxBytes=5_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])

    session = _get_session()
    account = _get_active_account(session, account_id)
    if not account:
        console.print("[red]No active account found.[/red]")
        session.close()
        raise typer.Exit(1)

    from polaris.services.lead_service import LeadService

    try:
        service = LeadService(session, account)

        new_leads = service.poll_inbound_dm_triggers()
        if new_leads:
            console.print(
                f"[green]{new_leads} new inbound DM lead(s) detected and responded to.[/green]"
            )
        else:
            console.print("[dim]No new inbound trigger matches.[/dim]")

        replies = service.poll_conversations()
        if replies:
            console.print(f"[green]{replies} AI reply/replies sent.[/green]")
        else:
            console.print("[dim]No pending conversations.[/dim]")

    except Exception as e:
        console.print(f"[red]Poll error:[/red] {e}")
        session.rollback()
        logging.error(f"Poll failed for account {active_account_id}: {e}")
        session.close()
        raise typer.Exit(1)

    session.close()


@leads_app.command("show")
def show(
    lead_id: int = typer.Argument(..., help="Lead ID to inspect"),
):
    """Show full conversation history for a lead."""
    session = _get_session()
    from polaris.repositories.lead_repository import LeadRepository

    repo = LeadRepository(session)
    lead = repo.get(lead_id)
    if not lead:
        console.print(f"[red]Lead #{lead_id} not found.[/red]")
        session.close()
        raise typer.Exit(1)

    console.print(
        f"\n[bold blue]Lead #{lead.id} — @{lead.commenter_username}[/bold blue]"
    )
    console.print(f"Status:    {lead.status.value}")
    console.print(f"Post ID:   {lead.post_instagram_media_id}")
    console.print(f"Comment:   {lead.comment_text}")
    console.print(f"DM Sent:   {'yes' if lead.dm_sent else 'no'}")
    if lead.dm_sent_at:
        console.print(f"DM Sent At: {lead.dm_sent_at.strftime('%Y-%m-%d %H:%M UTC')}")
    console.print()

    history = lead.conversation_history or []
    if not history:
        console.print("[dim]No conversation history yet.[/dim]")
    else:
        console.print("[bold]Conversation:[/bold]")
        for entry in history:
            role = entry.get("role", "?")
            message = entry.get("message", "")
            timestamp = entry.get("timestamp", "")

            label = (
                "[green]Polaris[/green]"
                if role == "assistant"
                else f"[cyan]@{lead.commenter_username}[/cyan]"
            )
            console.print(f"\n  {label}  [dim]{timestamp[:16]}[/dim]")
            console.print(f"  {message}")

    console.print()
    session.close()


# ---------------------------------------------------------------------------
# Outreach subcommands
# ---------------------------------------------------------------------------


def _get_sheets():
    from polaris.services.sheets_service import SheetsService
    from polaris.config import get_settings

    settings = get_settings()
    if not settings.is_sheets_configured:
        console.print("[red]Google Sheets not configured.[/red]")
        console.print(
            "Set GOOGLE_SHEETS_CLIENT_SECRETS_FILE and GOOGLE_SHEETS_SPREADSHEET_ID in .env"
        )
        raise typer.Exit(1)
    return SheetsService(settings)


@outreach_app.command("prospect")
def outreach_prospect(
    business_type: str = typer.Option(
        ..., "--type", "-t", help="Business type (e.g. roofer, plumber, hair salon)"
    ),
    location: str = typer.Option(
        ..., "--location", "-l", help="City and state (e.g. 'Dallas TX')"
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results to fetch"),
    source: str = typer.Option(
        "google", "--source", "-s", help="Data source: google or yelp"
    ),
):
    """Search for local businesses and find their Instagram handles and emails."""
    import webbrowser
    from polaris.config import get_settings

    settings = get_settings()
    source = source.lower()

    if source == "google":
        if not settings.google_places_api_key:
            console.print("[red]Google Places API key not configured.[/red]")
            console.print("Set GOOGLE_PLACES_API_KEY in .env")
            raise typer.Exit(1)
        from polaris.services.places_service import PlacesService

        console.print(
            f"\nSearching Google Places for [bold]{business_type}[/bold] in [bold]{location}[/bold]..."
        )
        console.print(
            "[dim]Fetching websites to find Instagram handles and emails — this takes a moment...[/dim]\n"
        )
        with PlacesService(settings) as svc:
            results = svc.search_with_instagram(business_type, location, limit=limit)
    else:
        if not settings.yelp_api_key:
            console.print("[red]Yelp API key not configured.[/red]")
            console.print("Set YELP_API_KEY in .env")
            raise typer.Exit(1)
        from polaris.services.yelp_service import YelpService

        console.print(
            f"\nSearching Yelp for [bold]{business_type}[/bold] in [bold]{location}[/bold]..."
        )
        console.print(
            "[dim]Fetching websites to find Instagram handles and emails — this takes a moment...[/dim]\n"
        )
        with YelpService(settings) as svc:
            results = svc.search_with_instagram(business_type, location, limit=limit)

    if not results:
        console.print(
            "[yellow]No results found. Try a different business type or location.[/yellow]"
        )
        return

    # Display results table
    table = Table(
        title=f"{business_type.title()} in {location} — {len(results)} results",
        show_lines=True,
    )
    table.add_column("#", style="dim", width=3)
    table.add_column("Business Name", width=28)
    table.add_column("Rating", justify="center", width=7)
    table.add_column("Reviews", justify="right", width=8)
    table.add_column("Instagram")
    table.add_column("Email")
    table.add_column("Phone", width=15)

    for i, r in enumerate(results, start=1):
        rating = str(r["rating"]) if r["rating"] else "-"
        reviews = str(r["reviews"]) if r["reviews"] else "0"
        if r["instagram"] and r.get("instagram_guessed"):
            instagram = f"[yellow]{r['instagram']}?[/yellow]"
        elif r["instagram"]:
            instagram = f"[green]{r['instagram']}[/green]"
        else:
            instagram = "[dim]not found[/dim]"
        email = f"[cyan]{r['email']}[/cyan]" if r.get("email") else "[dim]-[/dim]"
        table.add_row(
            str(i), r["name"], rating, reviews, instagram, email, r.get("phone", "")
        )

    console.print(table)
    console.print(
        f"\n[dim]Enter numbers to add to outreach (e.g. 1,3,5) or 'all'. Press Enter to skip.[/dim]"
    )

    selection = typer.prompt("Select", default="").strip()
    if not selection:
        console.print("[dim]No prospects selected.[/dim]")
        return

    if selection.lower() == "all":
        selected_indices = list(range(len(results)))
    else:
        try:
            selected_indices = [
                int(x.strip()) - 1 for x in selection.split(",") if x.strip()
            ]
        except ValueError:
            console.print("[red]Invalid selection.[/red]")
            raise typer.Exit(1)

    from polaris.services.ai.claude_client import ClaudeClient, ClaudeClientError

    sheets = _get_sheets()
    sheets.ensure_headers()
    added = 0

    try:
        claude = ClaudeClient()
        claude_available = True
    except ClaudeClientError:
        claude_available = False

    for idx in selected_indices:
        if idx < 0 or idx >= len(results):
            continue
        r = results[idx]

        console.print(f"\n[bold cyan]── {r['name']} ──[/bold cyan]")
        console.print(f"  Address:   {r['address']}")
        console.print(f"  Rating:    {r['rating']} ({r['reviews']} reviews)")
        if r.get("email"):
            console.print(f"  Email:     [cyan]{r['email']}[/cyan]")
        if r["instagram"]:
            ig = (
                f"[yellow]{r['instagram']}?[/yellow]"
                if r.get("instagram_guessed")
                else f"[green]{r['instagram']}[/green]"
            )
            console.print(f"  Instagram: {ig}")

        open_url = r.get("website") or r.get("yelp_url", "")
        if open_url:
            if typer.confirm("  Open website in browser?", default=False):
                webbrowser.open(open_url)

        # Determine preferred outreach channel based on business type
        bt = business_type.lower()
        is_trades = any(
            w in bt
            for w in [
                "hvac",
                "plumber",
                "plumbing",
                "roofer",
                "roofing",
                "electrician",
                "contractor",
                "landscap",
                "lawn",
                "auto repair",
                "mechanic",
            ]
        )
        is_visual = any(
            w in bt
            for w in [
                "photo",
                "salon",
                "medspa",
                "spa",
                "beauty",
                "gym",
                "trainer",
                "florist",
                "wedding",
            ]
        )

        if is_trades:
            primary_channel = "email"
            channel_reason = (
                "trades businesses check email between jobs — DM is a follow-up"
            )
        elif is_visual:
            primary_channel = "instagram"
            channel_reason = (
                "visual businesses live on Instagram — DM first, email as follow-up"
            )
        else:
            primary_channel = "email" if r.get("email") else "instagram"
            channel_reason = (
                "email available" if r.get("email") else "no email found, use Instagram"
            )

        console.print(
            f"\n  [bold]Recommended channel:[/bold] [yellow]{primary_channel.upper()}[/yellow] [dim]({channel_reason})[/dim]"
        )

        # Build niche context for AI
        if any(w in bt for w in ["photo", "photographer", "wedding photo"]):
            niche_context = (
                "Industry research shows wedding photographers' top pain points are: "
                "ghosted inquiries, slow follow-up while on shoots or editing, "
                "spending too much time answering the same email questions, "
                "and inconsistent bookings. 53% of inquiries take 1-4 weeks to convert. "
                "Reference being on a shoot, editing, or the inbox pile-up after a busy weekend."
            )
        elif is_trades:
            niche_context = (
                "Trades businesses miss leads constantly because the owner is on a job and can't answer the phone. "
                "Every missed call or unanswered form is a $200-$2000 job gone to a competitor. "
                "Reference being on a job, in the field, or unable to answer calls."
            )
        elif any(w in bt for w in ["salon", "medspa", "spa", "beauty"]):
            niche_context = (
                "Salons and medspas lose bookings to unanswered DMs and after-hours inquiries. "
                "The owner is usually hands-on with clients and can't monitor messages in real time."
            )
        else:
            niche_context = ""

        polaris_system = (
            "You write cold outreach for Polaris Innovations, a company that builds AI operational "
            "infrastructure for small service businesses. "
            "Polaris helps businesses automatically follow up on inquiries, handle ghosted leads, and book more clients "
            "without the owner spending more time on admin. "
            "No emojis. No fluff. No mentioning AI tools or agents by name. Sound like a real person. "
            "Never use the word 'streamline'. Lead with outcomes the owner actually cares about."
        )

        prospect_info = (
            f"Business name: {r['name']}\nBusiness type: {business_type}\n"
            f"Location: {location}\n\n{niche_context}"
        )

        if claude_available:
            # Generate email sequence for trades / email-first
            if primary_channel == "email" and r.get("email"):
                console.print("\n  [dim]Generating email sequence...[/dim]")
                email_prompt = (
                    f"Write a two-email cold outreach sequence for this prospect:\n\n{prospect_info}\n\n"
                    "Email 1 — the opener: Subject line + 3-4 sentence body. "
                    "Ask one question about a specific pain point. No pitch yet. "
                    "Sign off as 'Alex from Polaris'.\n\n"
                    "Email 2 — follow-up (send 3 days later if no reply): Subject line + 3-4 sentence body. "
                    "Brief intro of what Polaris does in outcomes only, one soft ask for a 15-minute call.\n\n"
                    "Format exactly like this:\n"
                    "EMAIL 1 SUBJECT:\n<subject>\n\nEMAIL 1 BODY:\n<body>\n\n"
                    "EMAIL 2 SUBJECT:\n<subject>\n\nEMAIL 2 BODY:\n<body>"
                )
                try:
                    response = claude.generate(
                        email_prompt,
                        system_prompt=polaris_system,
                        max_tokens=500,
                        temperature=0.8,
                    )

                    # Parse sections
                    def extract_section(text, key):
                        pattern = re.compile(
                            rf"{re.escape(key)}\s*\n(.*?)(?=\nEMAIL \d|$)", re.DOTALL
                        )
                        m = pattern.search(text)
                        return m.group(1).strip() if m else ""

                    e1_subject = extract_section(response, "EMAIL 1 SUBJECT:")
                    e1_body = extract_section(response, "EMAIL 1 BODY:")
                    e2_subject = extract_section(response, "EMAIL 2 SUBJECT:")
                    e2_body = extract_section(response, "EMAIL 2 BODY:")

                    console.print(f"\n  [bold]Email 1 — Send to {r['email']}:[/bold]")
                    console.print(f"  [dim]Subject:[/dim] {e1_subject}")
                    console.print(f"  {e1_body}\n")
                    console.print(
                        f"  [bold]Email 2 — Send 3 days later if no reply:[/bold]"
                    )
                    console.print(f"  [dim]Subject:[/dim] {e2_subject}")
                    console.print(f"  {e2_body}\n")

                    try:
                        import pyperclip

                        pyperclip.copy(f"Subject: {e1_subject}\n\n{e1_body}")
                        console.print("  [dim]Email 1 copied to clipboard.[/dim]")
                    except Exception:
                        pass
                except ClaudeClientError:
                    console.print(
                        "  [yellow]Could not generate email — skipping.[/yellow]"
                    )

            # Generate DM sequence (always for visual, as follow-up for trades)
            handle = r["instagram"] or ""
            handle = typer.prompt("  Instagram handle", default=handle).strip()

            if handle:
                label = (
                    "DM sequence"
                    if primary_channel == "instagram"
                    else "Instagram follow-up DM (use if no email reply)"
                )
                console.print(f"\n  [dim]Generating {label}...[/dim]")
                dm_prompt = (
                    f"Write a two-message cold Instagram DM sequence for this prospect:\n\n{prospect_info}\n"
                    f"Instagram handle: {handle}\n\n"
                    "Message 1 — the opener: One sentence. Ask a genuine question about a specific pain point. "
                    "No pitch, no mention of Polaris. Just a question they'd actually answer.\n\n"
                    "Message 2 — the follow-up (sent after they reply): 2-3 sentences. Acknowledge their pain, "
                    "introduce what Polaris does in terms of outcomes only, end with one low-pressure ask for a 15-minute call.\n\n"
                    "Format exactly like this:\nDM 1:\n<message>\n\nDM 2:\n<message>"
                )
                try:
                    response = claude.generate(
                        dm_prompt,
                        system_prompt=polaris_system,
                        max_tokens=300,
                        temperature=0.8,
                    )
                    parts = response.strip().split("DM 2:")
                    dm1 = parts[0].replace("DM 1:", "").strip() if parts else ""
                    dm2 = parts[1].strip() if len(parts) > 1 else ""

                    dm_label = (
                        "DM 1 — Send this first"
                        if primary_channel == "instagram"
                        else "DM 1 — Send if no email reply after 3 days"
                    )
                    console.print(f"\n  [bold]{dm_label}:[/bold]")
                    console.print(f"  [white]{dm1}[/white]")
                    console.print(f"\n  [bold]DM 2 — Send after they reply:[/bold]")
                    console.print(f"  [white]{dm2}[/white]\n")

                    if primary_channel == "instagram":
                        try:
                            import pyperclip

                            pyperclip.copy(dm1)
                            console.print("  [dim]DM 1 copied to clipboard.[/dim]")
                        except Exception:
                            pass
                except ClaudeClientError:
                    console.print(
                        "  [yellow]Could not generate DM — skipping.[/yellow]"
                    )
        else:
            handle = r["instagram"] or ""
            handle = typer.prompt("  Instagram handle", default=handle).strip()

        # Open the right channel first
        if primary_channel == "email" and r.get("email"):
            console.print(f"\n  [dim]Send email to: [cyan]{r['email']}[/cyan][/dim]")
        elif handle:
            if typer.confirm(f"  Open {handle} on Instagram?", default=True):
                webbrowser.open(f"https://www.instagram.com/{handle.lstrip('@')}/")

        sent = typer.confirm(
            f"  Did you send the {primary_channel} outreach?", default=False
        )
        if not sent:
            console.print("[dim]  Not logged — skipped.[/dim]")
            continue

        email_val = typer.prompt("  Email", default=r.get("email", "")).strip()
        followers = typer.prompt("  Followers (e.g. 1.2k)", default="").strip()
        notes = typer.prompt("  Notes (optional)", default="").strip()

        address_parts = r["address"].split(",")
        loc = (
            ", ".join(address_parts[1:3]).strip()
            if len(address_parts) >= 3
            else location
        )

        sheets.add_prospect(
            handle=handle,
            business_name=r["name"],
            business_type=business_type.title(),
            location=loc,
            followers=followers,
            email=email_val,
            notes=notes,
        )
        console.print(f"  [green]Logged:[/green] {handle} — {r['name']}")
        added += 1

    console.print(
        f"\n[bold green]{added} prospect(s) added to your outreach sheet.[/bold green]"
    )


@outreach_app.command("find")
def outreach_find(
    hashtag: str = typer.Option(
        ..., "--hashtag", "-h", help="Hashtag to search (without #)"
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of posts to fetch"),
    business_type: str = typer.Option(
        "", "--type", "-t", help="Business type to pre-fill (e.g. Roofer)"
    ),
    account_id: int = typer.Option(None, "--account", "-a", help="Account ID"),
):
    """Search a hashtag for prospects, review them, and add to outreach list."""
    import webbrowser
    from datetime import datetime, timezone

    session = _get_session()
    account = _get_active_account(session, account_id)
    if not account:
        console.print("[red]No active account found.[/red]")
        session.close()
        raise typer.Exit(1)

    from polaris.services.instagram.client import InstagramClient, InstagramClientError

    client = InstagramClient(
        access_token=account.access_token,
        instagram_user_id=account.instagram_user_id,
    )

    console.print(f"\nSearching [bold]#{hashtag}[/bold]...")
    try:
        hashtag_id = client.get_hashtag_id(hashtag)
        posts = client.get_hashtag_recent_media(hashtag_id, limit=limit)
    except InstagramClientError as e:
        console.print(f"[red]Error:[/red] {e}")
        session.close()
        raise typer.Exit(1)
    finally:
        client.close()

    if not posts:
        console.print("[yellow]No posts found for that hashtag.[/yellow]")
        session.close()
        return

    # Display posts in a review table
    table = Table(title=f"#{hashtag} — {len(posts)} recent posts", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Caption", width=45)
    table.add_column("Likes", justify="right", width=6)
    table.add_column("Comments", justify="right", width=8)
    table.add_column("Posted", width=12)

    for i, post in enumerate(posts, start=1):
        caption = post.get("caption", "") or ""
        snippet = caption[:80].replace("\n", " ")
        if len(caption) > 80:
            snippet += "..."

        likes = str(post.get("like_count", 0))
        comments = str(post.get("comments_count", 0))

        ts = post.get("timestamp", "")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                days_ago = (datetime.now(timezone.utc) - dt).days
                posted = f"{days_ago}d ago"
            except Exception:
                posted = ts[:10]
        else:
            posted = ""

        table.add_row(str(i), snippet, likes, comments, posted)

    console.print(table)
    console.print(
        "\n[dim]Enter the numbers you want to review (e.g. 1,3,5) or 'all'. Press Enter to skip all.[/dim]"
    )

    selection = typer.prompt("Select", default="").strip()
    if not selection:
        console.print("[dim]No prospects selected.[/dim]")
        session.close()
        return

    if selection.lower() == "all":
        selected_indices = list(range(len(posts)))
    else:
        try:
            selected_indices = [
                int(x.strip()) - 1 for x in selection.split(",") if x.strip()
            ]
        except ValueError:
            console.print("[red]Invalid selection.[/red]")
            session.close()
            raise typer.Exit(1)

    sheets = _get_sheets()
    sheets.ensure_headers()
    added = 0

    for idx in selected_indices:
        if idx < 0 or idx >= len(posts):
            continue
        post = posts[idx]
        permalink = post.get("permalink", "")

        console.print(f"\n[bold]Post #{idx + 1}[/bold]")
        caption = post.get("caption", "") or ""
        console.print(f"[dim]{caption[:200]}[/dim]")
        if permalink:
            console.print(f"Link: [cyan]{permalink}[/cyan]")
            open_it = typer.confirm("Open post in browser?", default=True)
            if open_it:
                webbrowser.open(permalink)

        handle = typer.prompt(
            "Instagram handle (e.g. @joes_roofing), or Enter to skip", default=""
        ).strip()
        if not handle:
            console.print("[dim]Skipped.[/dim]")
            continue

        name = typer.prompt("Business name").strip()
        btype = typer.prompt("Business type", default=business_type or "").strip()
        location = typer.prompt("Location (City ST)").strip()
        followers = typer.prompt("Followers (e.g. 1.2k)", default="").strip()
        notes = typer.prompt("Notes (optional)", default="").strip()

        sheets.add_prospect(
            handle=handle,
            business_name=name,
            business_type=btype,
            location=location,
            followers=followers,
            notes=notes,
        )
        console.print(f"[green]Added:[/green] {handle} — {name}")
        added += 1

    console.print(
        f"\n[bold green]{added} prospect(s) added to your outreach sheet.[/bold green]"
    )
    session.close()


@outreach_app.command("add")
def outreach_add(
    handle: str = typer.Option(
        ..., "--handle", "-H", help="Instagram handle (e.g. @joes_roofing)"
    ),
    name: str = typer.Option(..., "--name", "-n", help="Business name"),
    type_: str = typer.Option(
        ..., "--type", "-t", help="Business type (e.g. Roofer, Salon, Plumber)"
    ),
    location: str = typer.Option(
        ..., "--location", "-l", help="City/state (e.g. 'Dallas TX')"
    ),
    followers: str = typer.Option(
        "", "--followers", "-f", help="Follower count (e.g. 1.2k)"
    ),
    email: str = typer.Option("", "--email", "-e", help="Contact email address"),
    notes: str = typer.Option("", "--notes", help="Optional notes"),
):
    """Log a new outreach prospect and increment today's DM count."""
    sheets = _get_sheets()
    try:
        sheets.ensure_headers()
        sheets.add_prospect(
            handle=handle,
            business_name=name,
            business_type=type_,
            location=location,
            followers=followers,
            email=email,
            notes=notes,
        )
        console.print(f"[green]Logged:[/green] {handle} ({name}) — Stage: Contacted")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@outreach_app.command("replied")
def outreach_replied(
    handle: str = typer.Argument(..., help="Instagram handle that replied"),
):
    """Mark a prospect as replied and increment today's reply count."""
    sheets = _get_sheets()
    try:
        sheets.log_reply(handle)
        console.print(f"[green]Updated:[/green] {handle} marked as Replied")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@outreach_app.command("stats")
def outreach_stats(
    days: int = typer.Option(7, "--days", "-d", help="Number of days to show"),
):
    """Show daily outreach stats for the last N days."""
    sheets = _get_sheets()
    try:
        rows = sheets.get_daily_stats(days=days)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not rows:
        console.print("[yellow]No outreach data yet.[/yellow]")
        return

    table = Table(title=f"Outreach — Last {days} Days")
    table.add_column("Date")
    table.add_column("DMs Sent", justify="right")
    table.add_column("Replies", justify="right")
    table.add_column("Calls Booked", justify="right")
    table.add_column("Notes")

    total_dms = total_replies = total_calls = 0
    for row in rows:
        dms = row.get("DMs Sent", "0") or "0"
        replies = row.get("Replies", "0") or "0"
        calls = row.get("Calls Booked", "0") or "0"
        total_dms += int(dms)
        total_replies += int(replies)
        total_calls += int(calls)
        table.add_row(
            row.get("Date", ""),
            dms,
            replies,
            calls,
            row.get("Notes", ""),
        )

    table.add_section()
    table.add_row(
        "[bold]Total[/bold]",
        f"[bold]{total_dms}[/bold]",
        f"[bold]{total_replies}[/bold]",
        f"[bold]{total_calls}[/bold]",
        "",
    )
    console.print(table)

    if total_dms:
        reply_rate = round(total_replies / total_dms * 100)
        console.print(
            f"\nReply rate: [bold]{reply_rate}%[/bold]  ({total_replies}/{total_dms})"
        )


@outreach_app.command("pipeline")
def outreach_pipeline():
    """Show prospect counts by stage."""
    sheets = _get_sheets()
    try:
        pipeline = sheets.get_pipeline()
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not pipeline:
        console.print("[yellow]No prospects logged yet.[/yellow]")
        return

    stage_order = ["Contacted", "Replied", "Call Booked", "Proposal", "Won", "Lost"]
    stage_colors = {
        "Contacted": "cyan",
        "Replied": "blue",
        "Call Booked": "yellow",
        "Proposal": "magenta",
        "Won": "green",
        "Lost": "dim",
    }

    table = Table(title="Outreach Pipeline")
    table.add_column("Stage")
    table.add_column("Count", justify="right")

    total = 0
    for stage in stage_order:
        count = pipeline.get(stage, 0)
        if count:
            color = stage_colors.get(stage, "white")
            table.add_row(f"[{color}]{stage}[/{color}]", str(count))
            total += count

    for stage, count in pipeline.items():
        if stage not in stage_order:
            table.add_row(stage, str(count))
            total += count

    table.add_section()
    table.add_row("[bold]Total[/bold]", f"[bold]{total}[/bold]")
    console.print(table)


@outreach_app.command("dm")
def outreach_dm(
    name: str = typer.Option(..., "--name", "-n", help="Business name"),
    type_: str = typer.Option(
        ..., "--type", "-t", help="Business type (e.g. Hair Salon, Plumber)"
    ),
    location: str = typer.Option(
        ..., "--location", "-l", help="City/state (e.g. 'Ashburn VA')"
    ),
    handle: str = typer.Option(
        "", "--handle", "-H", help="Instagram handle (optional, for personalization)"
    ),
    notes: str = typer.Option(
        "", "--notes", help="Anything specific you noticed about them"
    ),
):
    """Generate a two-message cold outreach DM sequence using Claude."""
    from polaris.services.ai.claude_client import ClaudeClient, ClaudeClientError

    bt = type_.lower()
    niche_context = ""
    if any(w in bt for w in ["photo", "photographer", "wedding photo"]):
        niche_context = (
            "Industry research shows wedding photographers' top pain points are: "
            "ghosted inquiries, slow follow-up while on shoots or editing, "
            "spending too much time answering the same email questions, "
            "and inconsistent bookings. 53% of inquiries take 1-4 weeks to convert. "
            "The opener should feel like it comes from someone who understands the photographer's world."
        )
    elif any(w in bt for w in ["hvac", "plumber", "roofer", "contractor"]):
        niche_context = (
            "Trades businesses miss leads constantly because the owner is on a job. "
            "Every missed call is a $200–$2000 job gone to a competitor. "
            "The opener should reference being on a job or in the field."
        )
    elif any(w in bt for w in ["salon", "medspa", "spa", "beauty"]):
        niche_context = (
            "Salons and medspas lose bookings to unanswered DMs and after-hours inquiries. "
            "The opener should reference being with a client or after-hours inquiries."
        )

    system_prompt = (
        "You write cold Instagram DM sequences for Polaris Innovations, a company that builds AI operational "
        "infrastructure for small service businesses. "
        "Polaris helps businesses automatically follow up on inquiries, handle ghosted leads, and book more clients "
        "without the owner spending more time on admin. "
        "No emojis. No fluff. No mentioning AI tools or agents by name. Sound like a real person, not a marketing bot. "
        "Never use the word 'streamline'. Lead with outcomes the owner actually cares about."
    )

    details = f"Business name: {name}\nBusiness type: {type_}\nLocation: {location}"
    if handle:
        details += f"\nInstagram handle: {handle}"
    if notes:
        details += f"\nNotes about them: {notes}"

    prompt = (
        f"Write a two-message cold Instagram DM sequence for this prospect:\n\n{details}\n\n"
        f"{niche_context}\n\n"
        "Message 1 — the opener: One sentence. Ask a genuine question about a specific pain point. "
        "No pitch, no mention of Polaris. Just a question they'd actually answer because it resonates.\n\n"
        "Message 2 — the follow-up (sent after they reply): 2-3 sentences. Acknowledge their pain, "
        "introduce what Polaris does in terms of outcomes only (more bookings, fewer ghosted leads, "
        "less time on email), and end with one low-pressure ask for a 15-minute call.\n\n"
        "Format your response exactly like this:\n"
        "DM 1:\n<message>\n\nDM 2:\n<message>"
    )

    try:
        claude = ClaudeClient()
        console.print("\n[dim]Generating...[/dim]\n")
        response = claude.generate(
            prompt, system_prompt=system_prompt, max_tokens=300, temperature=0.8
        )

        # Parse and display
        parts = response.strip().split("DM 2:")
        dm1 = parts[0].replace("DM 1:", "").strip() if parts else ""
        dm2 = parts[1].strip() if len(parts) > 1 else ""

        console.print("[bold]DM 1 — Opener:[/bold]")
        console.print(f"  {dm1}\n")
        console.print("[bold]DM 2 — Follow-up (send after they reply):[/bold]")
        console.print(f"  {dm2}\n")

        try:
            import pyperclip

            pyperclip.copy(f"DM 1:\n{dm1}\n\nDM 2:\n{dm2}")
            console.print("[dim]Both messages copied to clipboard.[/dim]")
        except Exception:
            pass

    except ClaudeClientError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
