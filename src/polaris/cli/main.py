"""Main CLI entry point for Polaris."""

import typer
from rich.console import Console
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from polaris import __version__
from polaris.cli.accounts import accounts_app
from polaris.cli.analytics import analytics_app
from polaris.cli.content import content_app
from polaris.cli.schedule import schedule_app
from polaris.config import get_settings
from polaris.models.base import Base

app = typer.Typer(
    name="polaris",
    help="Polaris Instagram Management Suite - AI-powered content management for Instagram",
    no_args_is_help=True,
)

console = Console()

# Register sub-commands
app.add_typer(accounts_app, name="accounts", help="Manage Instagram accounts")
app.add_typer(content_app, name="content", help="Create and manage content")
app.add_typer(schedule_app, name="schedule", help="Schedule posts")
app.add_typer(analytics_app, name="analytics", help="View analytics and reports")


def get_session():
    """Create a database session."""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    return Session()


@app.command()
def init():
    """Initialize the Polaris database and configuration."""
    settings = get_settings()

    console.print("[bold blue]Initializing Polaris...[/bold blue]")

    # Create data directory if needed
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"  Data directory: {settings.data_dir}")

    # Initialize database
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    console.print(f"  Database initialized: {settings.database_url}")

    # Check configuration
    console.print("\n[bold]Configuration Status:[/bold]")

    if settings.is_anthropic_configured:
        console.print("  [green][+][/green] Anthropic API configured")
    else:
        console.print("  [yellow][!][/yellow] Anthropic API key not set (AI features disabled)")

    if settings.is_instagram_configured:
        console.print("  [green][+][/green] Meta/Instagram API configured")
    else:
        console.print("  [yellow][!][/yellow] Meta API credentials not set (Instagram features disabled)")

    console.print("\n[bold green]Polaris initialized successfully![/bold green]")
    console.print("\nNext steps:")
    console.print("  1. Copy .env.example to .env and configure your API keys")
    console.print("  2. Run 'polaris accounts add' to connect an Instagram account")
    console.print("  3. Run 'polaris content generate --topic \"your topic\"' to create content")


@app.command()
def version():
    """Show the Polaris version."""
    console.print(f"Polaris v{__version__}")


@app.command()
def run(
    foreground: bool = typer.Option(
        False, "--foreground", "-f", help="Run in foreground mode"
    ),
):
    """Start the scheduler daemon to publish scheduled posts."""
    from polaris.services.scheduler_service import SchedulerService

    settings = get_settings()

    console.print("[bold blue]Starting Polaris scheduler...[/bold blue]")

    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)

    scheduler = SchedulerService(session_factory=Session, settings=settings)
    scheduler.start()

    console.print("[green]Scheduler started successfully![/green]")
    console.print("Press Ctrl+C to stop")

    if foreground:
        import signal
        import time

        def signal_handler(signum, frame):
            console.print("\n[yellow]Stopping scheduler...[/yellow]")
            scheduler.stop()
            raise SystemExit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            pass
    else:
        console.print("[yellow]Running in background mode[/yellow]")


@app.command()
def publish(
    content_id: int = typer.Argument(..., help="Content ID to publish"),
    account_id: int = typer.Option(None, "--account", "-a", help="Account ID (uses first active if not specified)"),
):
    """Publish content to Instagram immediately."""
    settings = get_settings()
    session = get_session()

    from polaris.repositories import AccountRepository, ContentRepository
    from polaris.services.instagram.client import InstagramClient
    from polaris.services.instagram.publisher import InstagramPublisher, PublishError
    from polaris.models.content import ContentStatus

    content_repo = ContentRepository(session)
    account_repo = AccountRepository(session)

    # Get the content
    content = content_repo.get(content_id)
    if not content:
        console.print(f"[red]Error:[/red] Content {content_id} not found.")
        session.close()
        raise typer.Exit(1)

    if not content.media_url:
        console.print(f"[red]Error:[/red] Content has no media URL set.")
        console.print("Use 'polaris content edit --media-url <url>' to set one.")
        session.close()
        raise typer.Exit(1)

    # Get the account
    if account_id:
        account = account_repo.get(account_id)
    else:
        accounts = account_repo.get_active_accounts()
        account = accounts[0] if accounts else None

    if not account:
        console.print("[red]Error:[/red] No Instagram account found.")
        console.print("Run 'polaris accounts add' to connect an account.")
        session.close()
        raise typer.Exit(1)

    console.print(f"[bold blue]Publishing content #{content_id} to @{account.username}...[/bold blue]")
    console.print(f"Media URL: {content.media_url}")

    try:
        client = InstagramClient(
            access_token=account.access_token,
            instagram_user_id=account.instagram_user_id,
        )
        publisher = InstagramPublisher(client)

        # Publish
        media_id = publisher.publish_content(content)

        # Update content status
        content_repo.mark_published(content_id, instagram_media_id=media_id)
        content_repo.commit()

        console.print(f"\n[bold green]Published successfully![/bold green]")
        console.print(f"Instagram Media ID: {media_id}")

    except PublishError as e:
        console.print(f"[red]Publish error:[/red] {e}")
        content_repo.mark_failed(content_id)
        content_repo.commit()
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        session.close()


@app.command()
def status():
    """Show the current status of Polaris."""
    settings = get_settings()
    session = get_session()

    from polaris.repositories import AccountRepository, ContentRepository, ScheduleRepository

    account_repo = AccountRepository(session)
    content_repo = ContentRepository(session)
    schedule_repo = ScheduleRepository(session)

    console.print("[bold blue]Polaris Status[/bold blue]\n")

    # Accounts
    accounts = account_repo.get_active_accounts()
    console.print(f"[bold]Connected Accounts:[/bold] {len(accounts)}")
    for account in accounts:
        console.print(f"  - @{account.username}")

    # Content
    drafts = content_repo.get_drafts()
    ready = content_repo.get_ready_for_publish()
    console.print(f"\n[bold]Content:[/bold]")
    console.print(f"  Drafts: {len(drafts)}")
    console.print(f"  Ready to publish: {len(ready)}")

    # Scheduled
    pending = schedule_repo.get_pending()
    upcoming = schedule_repo.get_upcoming(hours=24)
    console.print(f"\n[bold]Scheduled Posts:[/bold]")
    console.print(f"  Total pending: {len(pending)}")
    console.print(f"  Next 24 hours: {len(upcoming)}")

    # Configuration
    console.print(f"\n[bold]Configuration:[/bold]")
    console.print(f"  Anthropic API: {'[green][+][/green]' if settings.is_anthropic_configured else '[red][x][/red]'}")
    console.print(f"  Instagram API: {'[green][+][/green]' if settings.is_instagram_configured else '[red][x][/red]'}")

    session.close()


if __name__ == "__main__":
    app()
