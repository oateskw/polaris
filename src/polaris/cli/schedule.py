"""CLI commands for post scheduling."""

from datetime import datetime, timezone
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from polaris.config import get_settings
from polaris.models.schedule import ScheduleStatus
from polaris.repositories import AccountRepository, ContentRepository, ScheduleRepository

schedule_app = typer.Typer(help="Schedule posts")
console = Console()


def get_session():
    """Create a database session."""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    return Session()


def parse_datetime(time_str: str) -> datetime:
    """Parse datetime string in various formats."""
    formats = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%d/%m/%Y %H:%M",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(time_str, fmt)
            # Assume UTC if no timezone
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    raise ValueError(
        f"Invalid datetime format: {time_str}. "
        "Use format like '2024-01-15 10:00' or '2024-01-15T10:00'"
    )


@schedule_app.command("create")
def create_schedule(
    content_id: int = typer.Option(..., "--content-id", "-c", help="Content ID to schedule"),
    time: str = typer.Option(..., "--time", "-t", help="Scheduled time (YYYY-MM-DD HH:MM)"),
    account_id: Optional[int] = typer.Option(None, "--account", "-a", help="Account ID (uses content's account if not specified)"),
):
    """Schedule a post for publishing."""
    session = get_session()
    content_repo = ContentRepository(session)
    schedule_repo = ScheduleRepository(session)
    account_repo = AccountRepository(session)

    # Get content
    content = content_repo.get(content_id)
    if not content:
        console.print(f"[red]Error:[/red] Content {content_id} not found.")
        session.close()
        raise typer.Exit(1)

    # Determine account
    if account_id is None:
        account_id = content.account_id

    account = account_repo.get(account_id)
    if not account:
        console.print(f"[red]Error:[/red] Account {account_id} not found.")
        session.close()
        raise typer.Exit(1)

    if not account.is_active:
        console.print(f"[red]Error:[/red] Account @{account.username} is not active.")
        session.close()
        raise typer.Exit(1)

    # Parse scheduled time
    try:
        scheduled_time = parse_datetime(time)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        session.close()
        raise typer.Exit(1)

    # Validate time is in the future
    now = datetime.now(timezone.utc)
    if scheduled_time <= now:
        console.print("[red]Error:[/red] Scheduled time must be in the future.")
        session.close()
        raise typer.Exit(1)

    # Create scheduled post
    scheduled_post = schedule_repo.create_scheduled_post(
        account_id=account_id,
        content_id=content_id,
        scheduled_time=scheduled_time,
    )
    schedule_repo.commit()

    # Schedule with APScheduler
    from polaris.services.scheduler_service import SchedulerService

    settings = get_settings()
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    scheduler = SchedulerService(session_factory=Session, settings=settings)

    job_id = scheduler.schedule_post(scheduled_post.id, scheduled_time)
    schedule_repo.update_job_id(scheduled_post.id, job_id)
    schedule_repo.commit()

    console.print(f"[green]Post scheduled successfully![/green]")
    console.print(f"  Schedule ID: {scheduled_post.id}")
    console.print(f"  Content ID: {content_id}")
    console.print(f"  Account: @{account.username}")
    console.print(f"  Scheduled for: {scheduled_time.strftime('%Y-%m-%d %H:%M UTC')}")

    session.close()


@schedule_app.command("list")
def list_schedules(
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
    account_id: Optional[int] = typer.Option(None, "--account", "-a", help="Filter by account"),
    upcoming: bool = typer.Option(False, "--upcoming", "-u", help="Show only next 24 hours"),
):
    """List scheduled posts."""
    session = get_session()
    schedule_repo = ScheduleRepository(session)

    # Get scheduled posts based on filters
    if upcoming:
        schedules = schedule_repo.get_upcoming(account_id, hours=24)
    elif status:
        try:
            status_filter = ScheduleStatus(status.lower())
        except ValueError:
            console.print(f"[red]Error:[/red] Invalid status '{status}'")
            console.print("Valid options: pending, processing, published, failed, cancelled")
            session.close()
            raise typer.Exit(1)

        if account_id:
            schedules = schedule_repo.get_by_account(account_id, status=status_filter)
        elif status_filter == ScheduleStatus.PENDING:
            schedules = schedule_repo.get_pending()
        elif status_filter == ScheduleStatus.FAILED:
            schedules = schedule_repo.get_failed()
        else:
            schedules = [s for s in schedule_repo.get_all() if s.status == status_filter]
    elif account_id:
        schedules = schedule_repo.get_by_account(account_id)
    else:
        schedules = schedule_repo.get_pending()

    if not schedules:
        console.print("[yellow]No scheduled posts found.[/yellow]")
        session.close()
        return

    table = Table(title="Scheduled Posts")
    table.add_column("ID", style="dim")
    table.add_column("Content ID")
    table.add_column("Account")
    table.add_column("Scheduled Time")
    table.add_column("Status")
    table.add_column("Retries")

    for schedule in schedules:
        status_color = {
            ScheduleStatus.PENDING: "yellow",
            ScheduleStatus.PROCESSING: "blue",
            ScheduleStatus.PUBLISHED: "green",
            ScheduleStatus.FAILED: "red",
            ScheduleStatus.CANCELLED: "dim",
        }.get(schedule.status, "white")

        table.add_row(
            str(schedule.id),
            str(schedule.content_id),
            f"@{schedule.account.username}",
            schedule.scheduled_time.strftime("%Y-%m-%d %H:%M UTC"),
            f"[{status_color}]{schedule.status.value}[/{status_color}]",
            str(schedule.retry_count),
        )

    console.print(table)
    session.close()


@schedule_app.command("cancel")
def cancel_schedule(
    schedule_id: int = typer.Argument(..., help="Schedule ID to cancel"),
):
    """Cancel a scheduled post."""
    session = get_session()
    schedule_repo = ScheduleRepository(session)

    schedule = schedule_repo.get(schedule_id)
    if not schedule:
        console.print(f"[red]Error:[/red] Schedule {schedule_id} not found.")
        session.close()
        raise typer.Exit(1)

    if schedule.status != ScheduleStatus.PENDING:
        console.print(f"[red]Error:[/red] Can only cancel pending schedules.")
        session.close()
        raise typer.Exit(1)

    # Cancel APScheduler job
    if schedule.job_id:
        from polaris.services.scheduler_service import SchedulerService

        settings = get_settings()
        engine = create_engine(settings.database_url)
        Session = sessionmaker(bind=engine)
        scheduler = SchedulerService(session_factory=Session, settings=settings)
        scheduler.cancel_scheduled_post(schedule.job_id)

    schedule_repo.mark_cancelled(schedule_id)
    schedule_repo.commit()

    console.print(f"[green]Schedule {schedule_id} cancelled.[/green]")
    session.close()


@schedule_app.command("reschedule")
def reschedule(
    schedule_id: int = typer.Argument(..., help="Schedule ID to reschedule"),
    time: str = typer.Option(..., "--time", "-t", help="New scheduled time"),
):
    """Reschedule a post to a new time."""
    session = get_session()
    schedule_repo = ScheduleRepository(session)

    schedule = schedule_repo.get(schedule_id)
    if not schedule:
        console.print(f"[red]Error:[/red] Schedule {schedule_id} not found.")
        session.close()
        raise typer.Exit(1)

    if schedule.status not in (ScheduleStatus.PENDING, ScheduleStatus.FAILED):
        console.print(f"[red]Error:[/red] Can only reschedule pending or failed schedules.")
        session.close()
        raise typer.Exit(1)

    # Parse new time
    try:
        new_time = parse_datetime(time)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        session.close()
        raise typer.Exit(1)

    now = datetime.now(timezone.utc)
    if new_time <= now:
        console.print("[red]Error:[/red] New time must be in the future.")
        session.close()
        raise typer.Exit(1)

    # Update APScheduler job
    from polaris.services.scheduler_service import SchedulerService

    settings = get_settings()
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    scheduler = SchedulerService(session_factory=Session, settings=settings)

    if schedule.job_id:
        scheduler.reschedule_post(schedule.job_id, new_time)
    else:
        job_id = scheduler.schedule_post(schedule.id, new_time)
        schedule_repo.update_job_id(schedule.id, job_id)

    schedule_repo.reschedule(schedule_id, new_time)
    schedule_repo.commit()

    console.print(f"[green]Schedule {schedule_id} rescheduled to {new_time.strftime('%Y-%m-%d %H:%M UTC')}.[/green]")
    session.close()


@schedule_app.command("retry")
def retry_schedule(
    schedule_id: int = typer.Argument(..., help="Schedule ID to retry"),
    time: Optional[str] = typer.Option(None, "--time", "-t", help="New time (uses now + 5 min if not specified)"),
):
    """Retry a failed scheduled post."""
    session = get_session()
    schedule_repo = ScheduleRepository(session)

    schedule = schedule_repo.get(schedule_id)
    if not schedule:
        console.print(f"[red]Error:[/red] Schedule {schedule_id} not found.")
        session.close()
        raise typer.Exit(1)

    if schedule.status != ScheduleStatus.FAILED:
        console.print(f"[red]Error:[/red] Can only retry failed schedules.")
        session.close()
        raise typer.Exit(1)

    if not schedule.can_retry:
        console.print(f"[red]Error:[/red] Maximum retries ({schedule.max_retries}) reached.")
        session.close()
        raise typer.Exit(1)

    # Determine retry time
    from datetime import timedelta

    if time:
        try:
            retry_time = parse_datetime(time)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            session.close()
            raise typer.Exit(1)
    else:
        retry_time = datetime.now(timezone.utc) + timedelta(minutes=5)

    # Schedule retry
    from polaris.services.scheduler_service import SchedulerService

    settings = get_settings()
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    scheduler = SchedulerService(session_factory=Session, settings=settings)

    job_id = scheduler.schedule_post(schedule.id, retry_time)
    schedule_repo.reschedule(schedule_id, retry_time)
    schedule_repo.update_job_id(schedule_id, job_id)
    schedule_repo.commit()

    console.print(f"[green]Schedule {schedule_id} will retry at {retry_time.strftime('%Y-%m-%d %H:%M UTC')}.[/green]")
    session.close()


@schedule_app.command("show")
def show_schedule(
    schedule_id: int = typer.Argument(..., help="Schedule ID to display"),
):
    """Show detailed schedule information."""
    session = get_session()
    schedule_repo = ScheduleRepository(session)

    schedule = schedule_repo.get(schedule_id)
    if not schedule:
        console.print(f"[red]Error:[/red] Schedule {schedule_id} not found.")
        session.close()
        raise typer.Exit(1)

    console.print(f"[bold]Schedule #{schedule.id}[/bold]")
    console.print(f"Status: {schedule.status.value}")
    console.print(f"Account: @{schedule.account.username}")
    console.print(f"Content ID: {schedule.content_id}")
    console.print(f"Scheduled Time: {schedule.scheduled_time.strftime('%Y-%m-%d %H:%M UTC')}")
    console.print(f"Created: {schedule.created_at}")

    if schedule.published_at:
        console.print(f"Published At: {schedule.published_at.strftime('%Y-%m-%d %H:%M UTC')}")

    console.print(f"Retry Count: {schedule.retry_count}/{schedule.max_retries}")

    if schedule.error_message:
        console.print(f"\n[red]Error:[/red] {schedule.error_message}")

    # Show content preview
    console.print(f"\n[bold]Content Preview:[/bold]")
    content = schedule.content
    console.print(f"Topic: {content.topic or 'N/A'}")
    console.print(f"Caption: {content.caption[:100]}..." if len(content.caption) > 100 else f"Caption: {content.caption}")

    session.close()
