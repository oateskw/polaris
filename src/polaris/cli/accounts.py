"""CLI commands for Instagram account management."""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from polaris.config import get_settings
from polaris.repositories import AccountRepository

accounts_app = typer.Typer(help="Manage Instagram accounts")
console = Console()


def get_session():
    """Create a database session."""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    return Session()


@accounts_app.command("add")
def add_account():
    """Add a new Instagram account via OAuth."""
    settings = get_settings()

    if not settings.is_instagram_configured:
        console.print("[red]Error:[/red] Meta API credentials not configured.")
        console.print("Please set META_APP_ID and META_APP_SECRET in your .env file.")
        raise typer.Exit(1)

    from polaris.services.instagram.auth import InstagramAuth

    auth = InstagramAuth(settings)

    console.print("[bold blue]Starting Instagram authentication...[/bold blue]")
    console.print("This will open your browser to authenticate with Instagram.\n")

    # Generate and display the auth URL first
    auth_url, _ = auth.get_authorization_url()
    console.print("[yellow]If the browser doesn't open automatically, visit this URL:[/yellow]")
    console.print(f"\n{auth_url}\n")

    try:
        # Start OAuth flow
        token_data = auth.start_oauth_flow()

        if not token_data:
            console.print("[red]Authentication failed.[/red]")
            raise typer.Exit(1)

        console.print("[green]Authentication successful![/green]")
        console.print("Fetching Instagram account details...")

        # Get Instagram account info
        ig_account = auth.get_instagram_account(token_data["access_token"])

        # Save to database
        session = get_session()
        account_repo = AccountRepository(session)

        # Check if account already exists
        existing = account_repo.get_by_instagram_id(ig_account["instagram_user_id"])
        if existing:
            # Update existing account
            account_repo.update_token(
                existing.id,
                ig_account["page_access_token"],
                token_data["expires_at"],
            )
            account_repo.commit()
            console.print(f"\n[green]Updated existing account:[/green] @{existing.username}")
        else:
            # Create new account
            account = account_repo.create(
                instagram_user_id=ig_account["instagram_user_id"],
                username=ig_account.get("username", ""),
                name=ig_account.get("name"),
                access_token=ig_account["page_access_token"],
                token_expires_at=token_data["expires_at"],
                profile_picture_url=ig_account.get("profile_picture_url"),
                followers_count=ig_account.get("followers_count"),
                following_count=ig_account.get("follows_count"),
                media_count=ig_account.get("media_count"),
            )
            account_repo.commit()
            console.print(f"\n[green]Account added successfully:[/green] @{account.username}")

        session.close()

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@accounts_app.command("list")
def list_accounts(
    all_accounts: bool = typer.Option(False, "--all", "-a", help="Show all accounts including inactive"),
):
    """List connected Instagram accounts."""
    session = get_session()
    account_repo = AccountRepository(session)

    if all_accounts:
        accounts = account_repo.get_all()
    else:
        accounts = account_repo.get_active_accounts()

    if not accounts:
        console.print("[yellow]No accounts found.[/yellow]")
        console.print("Run 'polaris accounts add' to connect an Instagram account.")
        session.close()
        return

    table = Table(title="Instagram Accounts")
    table.add_column("ID", style="dim")
    table.add_column("Username", style="cyan")
    table.add_column("Name")
    table.add_column("Followers", justify="right")
    table.add_column("Posts", justify="right")
    table.add_column("Status")

    for account in accounts:
        status = "[green]Active[/green]" if account.is_active else "[red]Inactive[/red]"
        if account.is_token_expired:
            status = "[yellow]Token Expired[/yellow]"

        table.add_row(
            str(account.id),
            f"@{account.username}",
            account.name or "-",
            str(account.followers_count or "-"),
            str(account.media_count or "-"),
            status,
        )

    console.print(table)
    session.close()


@accounts_app.command("refresh")
def refresh_account(
    account_id: int = typer.Argument(..., help="Account ID to refresh"),
):
    """Refresh account information and token."""
    settings = get_settings()
    session = get_session()
    account_repo = AccountRepository(session)

    account = account_repo.get(account_id)
    if not account:
        console.print(f"[red]Error:[/red] Account {account_id} not found.")
        session.close()
        raise typer.Exit(1)

    console.print(f"Refreshing account @{account.username}...")

    try:
        from polaris.services.instagram.auth import InstagramAuth
        from polaris.services.instagram.client import InstagramClient

        # Refresh token
        auth = InstagramAuth(settings)
        token_data = auth.refresh_token(account.access_token)

        # Update account info
        client = InstagramClient(
            access_token=token_data["access_token"],
            instagram_user_id=account.instagram_user_id,
        )
        info = client.get_account_info()
        client.close()

        # Save updates
        account_repo.update(
            account_id,
            access_token=token_data["access_token"],
            token_expires_at=token_data["expires_at"],
            followers_count=info.get("followers_count"),
            following_count=info.get("follows_count"),
            media_count=info.get("media_count"),
            profile_picture_url=info.get("profile_picture_url"),
        )
        account_repo.commit()

        console.print(f"[green]Account refreshed successfully![/green]")
        console.print(f"  Followers: {info.get('followers_count', '-')}")
        console.print(f"  Posts: {info.get('media_count', '-')}")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        session.close()


@accounts_app.command("remove")
def remove_account(
    account_id: int = typer.Argument(..., help="Account ID to remove"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Remove an Instagram account."""
    session = get_session()
    account_repo = AccountRepository(session)

    account = account_repo.get(account_id)
    if not account:
        console.print(f"[red]Error:[/red] Account {account_id} not found.")
        session.close()
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(
            f"Are you sure you want to remove @{account.username}? This will delete all associated content and schedules."
        )
        if not confirm:
            console.print("Cancelled.")
            session.close()
            return

    account_repo.delete(account_id)
    account_repo.commit()
    console.print(f"[green]Account @{account.username} removed.[/green]")
    session.close()


@accounts_app.command("deactivate")
def deactivate_account(
    account_id: int = typer.Argument(..., help="Account ID to deactivate"),
):
    """Deactivate an Instagram account (keeps data)."""
    session = get_session()
    account_repo = AccountRepository(session)

    account = account_repo.get(account_id)
    if not account:
        console.print(f"[red]Error:[/red] Account {account_id} not found.")
        session.close()
        raise typer.Exit(1)

    account_repo.deactivate(account_id)
    account_repo.commit()
    console.print(f"[green]Account @{account.username} deactivated.[/green]")
    session.close()


@accounts_app.command("activate")
def activate_account(
    account_id: int = typer.Argument(..., help="Account ID to activate"),
):
    """Activate a deactivated Instagram account."""
    session = get_session()
    account_repo = AccountRepository(session)

    account = account_repo.get(account_id)
    if not account:
        console.print(f"[red]Error:[/red] Account {account_id} not found.")
        session.close()
        raise typer.Exit(1)

    account_repo.activate(account_id)
    account_repo.commit()
    console.print(f"[green]Account @{account.username} activated.[/green]")
    session.close()
