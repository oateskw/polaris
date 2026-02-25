"""CLI commands for lead management (comment-to-DM automation)."""

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from polaris.config import get_settings

leads_app = typer.Typer(help="Manage comment-to-DM lead automation")
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
    account_id: int = typer.Option(None, "--account", "-a", help="Account ID (uses first active if not specified)"),
):
    """Set up a new comment trigger on an Instagram post."""
    session = _get_session()

    account = _get_active_account(session, account_id)
    if not account:
        console.print("[red]Error:[/red] No active Instagram account found.")
        console.print("Run 'polaris accounts add' to connect an account.")
        session.close()
        raise typer.Exit(1)

    console.print(f"\n[bold blue]Setting up comment trigger for @{account.username}[/bold blue]\n")

    post_id = typer.prompt("Enter the Instagram media ID of the post to watch")
    keyword = typer.prompt("Trigger keyword (e.g. INFO)")
    initial_message = typer.prompt("Initial DM message to send when keyword is detected")
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

    from sqlalchemy import select
    from polaris.models.lead import CommentTrigger

    stmt = select(CommentTrigger).where(CommentTrigger.account_id == account.id)
    account_triggers = list(session.execute(stmt).scalars().all())

    if not account_triggers:
        console.print("No triggers configured. Run 'polaris leads setup' to create one.")
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
        last_polled = t.last_polled_at.strftime("%Y-%m-%d %H:%M") if t.last_polled_at else "never"
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
    status: str = typer.Option(None, "--status", "-s", help="Filter by status (NEW, CONTACTED, REPLIED, QUALIFIED, CLOSED)"),
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
            console.print(f"[red]Invalid status '{status}'. Choose from: NEW, CONTACTED, REPLIED, QUALIFIED, CLOSED[/red]")
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

    console.print(f"\n[bold blue]Lead #{lead.id} — @{lead.commenter_username}[/bold blue]")
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

            label = "[green]Polaris[/green]" if role == "assistant" else f"[cyan]@{lead.commenter_username}[/cyan]"
            console.print(f"\n  {label}  [dim]{timestamp[:16]}[/dim]")
            console.print(f"  {message}")

    console.print()
    session.close()
