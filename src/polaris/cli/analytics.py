"""CLI commands for analytics and reporting."""

from datetime import datetime, timedelta, timezone
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from polaris.config import get_settings
from polaris.repositories import AccountRepository, AnalyticsRepository, ContentRepository

analytics_app = typer.Typer(help="View analytics and reports")
console = Console()


def get_session():
    """Create a database session."""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    return Session()


@analytics_app.command("report")
def generate_report(
    account_id: Optional[int] = typer.Option(None, "--account", "-a", help="Account ID"),
    days: int = typer.Option(30, "--days", "-d", help="Report period in days"),
):
    """Generate an engagement analytics report."""
    session = get_session()
    account_repo = AccountRepository(session)
    analytics_repo = AnalyticsRepository(session)
    content_repo = ContentRepository(session)

    # Get account
    if account_id:
        account = account_repo.get(account_id)
        if not account:
            console.print(f"[red]Error:[/red] Account {account_id} not found.")
            session.close()
            raise typer.Exit(1)
        accounts = [account]
    else:
        accounts = account_repo.get_active_accounts()
        if not accounts:
            console.print("[yellow]No active accounts found.[/yellow]")
            session.close()
            return

    # Date range
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    for account in accounts:
        console.print(Panel(
            f"Analytics Report for @{account.username}",
            title=f"[bold blue]Polaris Analytics[/bold blue]",
            subtitle=f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
        ))

        # Account overview
        console.print("\n[bold]Account Overview[/bold]")
        console.print(f"  Followers: {account.followers_count or 'N/A'}")
        console.print(f"  Following: {account.following_count or 'N/A'}")
        console.print(f"  Total Posts: {account.media_count or 'N/A'}")

        # Engagement totals
        totals = analytics_repo.get_account_totals(account.id, start_date, end_date)
        console.print(f"\n[bold]Engagement Summary ({days} days)[/bold]")
        console.print(f"  Total Impressions: {totals['total_impressions']:,}")
        console.print(f"  Total Reach: {totals['total_reach']:,}")
        console.print(f"  Total Likes: {totals['total_likes']:,}")
        console.print(f"  Total Comments: {totals['total_comments']:,}")
        console.print(f"  Total Shares: {totals['total_shares']:,}")
        console.print(f"  Total Saves: {totals['total_saves']:,}")
        console.print(f"  Posts Analyzed: {totals['post_count']}")

        # Averages
        averages = analytics_repo.get_average_engagement(account.id, start_date, end_date)
        console.print(f"\n[bold]Average Per Post[/bold]")
        console.print(f"  Avg Impressions: {averages['avg_impressions']:.0f}")
        console.print(f"  Avg Reach: {averages['avg_reach']:.0f}")
        console.print(f"  Avg Likes: {averages['avg_likes']:.1f}")
        console.print(f"  Avg Comments: {averages['avg_comments']:.1f}")

        # Top performing posts
        top_posts = analytics_repo.get_top_performing_posts(account.id, metric="likes", limit=5)
        if top_posts:
            console.print(f"\n[bold]Top Performing Posts (by likes)[/bold]")
            table = Table(show_header=True)
            table.add_column("Media ID", style="dim")
            table.add_column("Likes", justify="right")
            table.add_column("Comments", justify="right")
            table.add_column("Reach", justify="right")
            table.add_column("Engagement Rate")

            for metric in top_posts:
                eng_rate = f"{metric.engagement_rate:.2f}%" if metric.engagement_rate else "N/A"
                table.add_row(
                    metric.instagram_media_id[:15] + "...",
                    str(metric.likes or 0),
                    str(metric.comments or 0),
                    str(metric.reach or 0),
                    eng_rate,
                )

            console.print(table)

        # Content stats
        published = content_repo.get_published(account.id, limit=100)
        ai_generated = sum(1 for c in published if c.ai_generated)
        console.print(f"\n[bold]Content Stats[/bold]")
        console.print(f"  Published Posts: {len(published)}")
        console.print(f"  AI-Generated: {ai_generated} ({ai_generated/len(published)*100:.0f}%)" if published else "  AI-Generated: 0")

        console.print()

    session.close()


@analytics_app.command("fetch")
def fetch_metrics(
    account_id: int = typer.Option(..., "--account", "-a", help="Account ID"),
    limit: int = typer.Option(25, "--limit", "-l", help="Number of recent posts to fetch"),
):
    """Fetch and store engagement metrics from Instagram."""
    settings = get_settings()

    if not settings.is_instagram_configured:
        console.print("[red]Error:[/red] Instagram API not configured.")
        raise typer.Exit(1)

    session = get_session()
    account_repo = AccountRepository(session)
    analytics_repo = AnalyticsRepository(session)

    account = account_repo.get(account_id)
    if not account:
        console.print(f"[red]Error:[/red] Account {account_id} not found.")
        session.close()
        raise typer.Exit(1)

    if not account.is_active:
        console.print(f"[red]Error:[/red] Account @{account.username} is not active.")
        session.close()
        raise typer.Exit(1)

    console.print(f"[bold blue]Fetching metrics for @{account.username}...[/bold blue]")

    try:
        from polaris.services.instagram.client import InstagramClient

        client = InstagramClient(
            access_token=account.access_token,
            instagram_user_id=account.instagram_user_id,
        )

        # Fetch recent media
        media_list = client.get_media(limit=limit)
        console.print(f"Found {len(media_list)} posts")

        recorded_at = datetime.now(timezone.utc)
        fetched_count = 0

        for media in media_list:
            media_id = media.get("id")
            if not media_id:
                continue

            # Get insights for this media
            try:
                insights = client.get_media_insights(media_id)
                insights_data = {d["name"]: d["values"][0]["value"] for d in insights.get("data", [])}
            except Exception:
                # Some media types don't support insights
                insights_data = {}

            # Record metric
            analytics_repo.record_metric(
                account_id=account.id,
                instagram_media_id=media_id,
                recorded_at=recorded_at,
                impressions=insights_data.get("impressions"),
                reach=insights_data.get("reach"),
                likes=media.get("like_count"),
                comments=media.get("comments_count"),
                saves=insights_data.get("saved"),
                shares=insights_data.get("shares"),
            )
            fetched_count += 1

        analytics_repo.commit()
        client.close()

        console.print(f"[green]Successfully fetched metrics for {fetched_count} posts.[/green]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        session.close()


@analytics_app.command("top")
def top_posts(
    account_id: Optional[int] = typer.Option(None, "--account", "-a", help="Account ID"),
    metric: str = typer.Option("likes", "--metric", "-m", help="Metric to sort by"),
    limit: int = typer.Option(10, "--limit", "-l", help="Number of posts to show"),
):
    """Show top performing posts by a specific metric."""
    session = get_session()
    account_repo = AccountRepository(session)
    analytics_repo = AnalyticsRepository(session)

    valid_metrics = ["likes", "comments", "shares", "saves", "reach", "impressions"]
    if metric not in valid_metrics:
        console.print(f"[red]Error:[/red] Invalid metric '{metric}'")
        console.print(f"Valid options: {', '.join(valid_metrics)}")
        session.close()
        raise typer.Exit(1)

    if account_id:
        accounts = [account_repo.get(account_id)]
        if not accounts[0]:
            console.print(f"[red]Error:[/red] Account {account_id} not found.")
            session.close()
            raise typer.Exit(1)
    else:
        accounts = account_repo.get_active_accounts()

    for account in accounts:
        if not account:
            continue

        console.print(f"\n[bold]Top Posts for @{account.username} (by {metric})[/bold]")

        top = analytics_repo.get_top_performing_posts(account.id, metric=metric, limit=limit)

        if not top:
            console.print("[yellow]No metrics found.[/yellow]")
            continue

        table = Table()
        table.add_column("#", style="dim")
        table.add_column("Media ID")
        table.add_column(metric.capitalize(), justify="right", style="cyan")
        table.add_column("Likes", justify="right")
        table.add_column("Comments", justify="right")
        table.add_column("Recorded")

        for i, m in enumerate(top, 1):
            metric_value = getattr(m, metric, 0) or 0
            table.add_row(
                str(i),
                m.instagram_media_id[:20],
                str(metric_value),
                str(m.likes or 0),
                str(m.comments or 0),
                m.recorded_at.strftime("%Y-%m-%d"),
            )

        console.print(table)

    session.close()


@analytics_app.command("history")
def metric_history(
    media_id: str = typer.Argument(..., help="Instagram media ID"),
):
    """Show metric history for a specific post."""
    session = get_session()
    analytics_repo = AnalyticsRepository(session)

    metrics = analytics_repo.get_by_media_id(media_id, latest_only=False)

    if not metrics:
        console.print(f"[yellow]No metrics found for media ID {media_id}[/yellow]")
        session.close()
        return

    console.print(f"[bold]Metric History for {media_id}[/bold]\n")

    table = Table()
    table.add_column("Recorded At")
    table.add_column("Impressions", justify="right")
    table.add_column("Reach", justify="right")
    table.add_column("Likes", justify="right")
    table.add_column("Comments", justify="right")
    table.add_column("Saves", justify="right")

    for m in metrics:
        table.add_row(
            m.recorded_at.strftime("%Y-%m-%d %H:%M"),
            str(m.impressions or "-"),
            str(m.reach or "-"),
            str(m.likes or "-"),
            str(m.comments or "-"),
            str(m.saves or "-"),
        )

    console.print(table)
    session.close()
