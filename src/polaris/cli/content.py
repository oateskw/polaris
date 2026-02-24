"""CLI commands for content management."""

import re
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from polaris.config import get_settings
from polaris.models.content import ContentStatus, ContentType
from polaris.repositories import AccountRepository, ContentRepository

content_app = typer.Typer(help="Create and manage content")
console = Console()


def strip_emojis(text: str) -> str:
    """Remove emojis and special Unicode from text for Windows console compatibility."""
    # Pattern to match emojis and special Unicode characters
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"  # dingbats
        "\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U0001FA00-\U0001FA6F"  # chess symbols
        "\U0001FA70-\U0001FAFF"  # symbols and pictographs extended-a
        "\U00002600-\U000026FF"  # misc symbols
        "\U00002700-\U000027BF"  # dingbats
        "\U00002190-\U000021FF"  # arrows
        "\U00002000-\U0000206F"  # general punctuation
        "\U00002300-\U000023FF"  # misc technical
        "\U000025A0-\U000025FF"  # geometric shapes
        "\U00002B00-\U00002BFF"  # misc symbols and arrows
        "]+",
        flags=re.UNICODE,
    )
    # Replace arrows with simple dashes
    text = text.replace("→", "-").replace("←", "-").replace("•", "-")
    return emoji_pattern.sub("", text)


def safe_print_panel(text: str, title: str, border_style: str) -> None:
    """Print a panel, stripping emojis on Windows."""
    # Always strip emojis on Windows to avoid encoding errors
    if sys.platform == "win32":
        text = strip_emojis(text)
    console.print(Panel(text, title=title, border_style=border_style))


def get_session():
    """Create a database session."""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    return Session()


@content_app.command("generate")
def generate_content(
    topic: str = typer.Option(..., "--topic", "-t", help="Topic for content generation"),
    context: Optional[str] = typer.Option(None, "--context", "-c", help="Additional context"),
    account_id: Optional[int] = typer.Option(None, "--account", "-a", help="Account ID to associate with"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save to database"),
    image: bool = typer.Option(False, "--image", "-i", help="Generate an AI image for the post"),
    video: bool = typer.Option(False, "--video", "-v", help="Generate a slideshow video (3 images)"),
    slides: int = typer.Option(3, "--slides", help="Number of slides for video (2-5)"),
    no_text: bool = typer.Option(False, "--no-text", help="Generate image/video without text overlay"),
    github_repo: Optional[str] = typer.Option(None, "--github-repo", help="GitHub repo for media upload (e.g., 'user/repo')"),
):
    """Generate AI-powered caption, hashtags, and optionally an image for a post."""
    settings = get_settings()

    if not settings.is_anthropic_configured:
        console.print("[red]Error:[/red] Anthropic API key not configured.")
        console.print("Please set ANTHROPIC_API_KEY in your .env file.")
        raise typer.Exit(1)

    if (image or video) and not settings.is_replicate_configured:
        console.print("[red]Error:[/red] Replicate API key not configured.")
        console.print("Please set REPLICATE_API_KEY in your .env file.")
        console.print("Get a key at: https://replicate.com/account/api-tokens")
        console.print("Note: Replicate requires billing setup but offers $5 free credit.")
        raise typer.Exit(1)

    # Validate slides count
    if video and (slides < 2 or slides > 5):
        console.print("[red]Error:[/red] Slides must be between 2 and 5.")
        raise typer.Exit(1)

    from polaris.services.ai import ContentGenerator

    console.print(f"[bold blue]Generating content for:[/bold blue] {topic}\n")

    media_url = None

    try:
        generator = ContentGenerator()
        result = generator.generate_caption(topic, context)

        # Display the generated content
        safe_print_panel(
            result.caption,
            title="[bold green]Caption[/bold green]",
            border_style="green",
        )

        safe_print_panel(
            result.hashtags,
            title="[bold blue]Hashtags[/bold blue]",
            border_style="blue",
        )

        # Generate image if requested
        if image:
            console.print("\n[bold blue]Generating image...[/bold blue]")
            from polaris.services.ai import ImageGenerator, upload_to_github
            from polaris.services.ai.image_generator import extract_hook
            from pathlib import Path

            # Extract hook from caption for text overlay (unless --no-text)
            hook_text = None
            if not no_text:
                hook_text = extract_hook(result.caption)
                console.print(f"[dim]Text overlay: {hook_text}[/dim]")

            img_generator = ImageGenerator()
            try:
                generated_image = img_generator.generate_image(
                    topic=topic,
                    caption_summary=result.caption[:200],
                    text_overlay=hook_text,
                    text_position="top",
                    style_instructions=context,
                )
                console.print(f"[green]Image generated:[/green] {generated_image.local_path}")
                console.print(f"[dim]Prompt used: {generated_image.prompt}[/dim]")

                # Upload to GitHub if repo specified
                repo = github_repo or settings.github_repo or "oateskw/polaris"
                if repo:
                    console.print(f"\n[bold blue]Uploading to GitHub ({repo})...[/bold blue]")
                    try:
                        media_url = upload_to_github(
                            local_path=Path(generated_image.local_path),
                            repo=repo,
                            branch=settings.github_branch,
                        )
                        console.print(f"[green]Uploaded:[/green] {media_url}")
                    except Exception as e:
                        console.print(f"[yellow]Warning:[/yellow] GitHub upload failed: {e}")
                        console.print(f"Image saved locally at: {generated_image.local_path}")
            finally:
                img_generator.close()

        # Generate video if requested
        media_type = None
        if video:
            console.print(f"\n[bold blue]Generating video ({slides} slides)...[/bold blue]")
            console.print("[dim]This may take a few minutes...[/dim]")
            from polaris.services.ai.video_generator import VideoGenerator
            from polaris.services.ai import upload_to_cloudinary
            from pathlib import Path

            vid_generator = VideoGenerator()
            try:
                generated_video = vid_generator.generate_video(
                    topic=topic,
                    caption=result.caption,
                    num_slides=slides,
                    slide_duration=4.0,
                    include_text=not no_text,
                    style_instructions=context,
                )
                console.print(f"[green]Video generated:[/green] {generated_video.local_path}")
                console.print(f"[dim]Duration: {generated_video.duration:.1f}s, Slides: {generated_video.num_slides}[/dim]")

                media_type = ContentType.VIDEO

                # Upload to Cloudinary if configured
                if settings.is_cloudinary_configured:
                    console.print(f"\n[bold blue]Uploading to Cloudinary...[/bold blue]")
                    try:
                        media_url = upload_to_cloudinary(Path(generated_video.local_path))
                        console.print(f"[green]Uploaded to Cloudinary:[/green] {media_url}")
                    except Exception as e:
                        console.print(f"[yellow]Warning:[/yellow] Cloudinary upload failed: {e}")
                        console.print(f"Video saved locally at: {generated_video.local_path}")
                else:
                    console.print(f"\n[yellow]Note:[/yellow] Video saved locally. Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET in .env to auto-upload for Instagram.")
            except Exception as e:
                console.print(f"[red]Video generation error:[/red] {e}")
            finally:
                vid_generator.close()

        # Save to database if requested
        if save:
            session = get_session()

            # Get account ID if not provided
            if account_id is None:
                account_repo = AccountRepository(session)
                accounts = account_repo.get_active_accounts()
                if accounts:
                    account_id = accounts[0].id

            if account_id:
                content_repo = ContentRepository(session)
                create_kwargs = dict(
                    account_id=account_id,
                    caption=result.caption,
                    hashtags=result.hashtags,
                    media_url=media_url,
                    topic=topic,
                    ai_generated=True,
                    ai_model=result.ai_model,
                )
                if media_type is not None:
                    create_kwargs["media_type"] = media_type
                content = content_repo.create_content(**create_kwargs)
                content_repo.commit()
                console.print(f"\n[green]Content saved with ID:[/green] {content.id}")
                if media_url:
                    console.print(f"[green]Media URL set:[/green] {media_url}")
            else:
                console.print("\n[yellow]Warning:[/yellow] No accounts found. Content not saved.")
                console.print("Run 'polaris accounts add' to connect an Instagram account first.")
            session.close()

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@content_app.command("ideas")
def generate_ideas(
    count: int = typer.Option(5, "--count", "-n", help="Number of ideas to generate"),
    focus: Optional[str] = typer.Option(None, "--focus", "-f", help="Focus areas (comma-separated)"),
):
    """Generate post ideas for tech content."""
    settings = get_settings()

    if not settings.is_anthropic_configured:
        console.print("[red]Error:[/red] Anthropic API key not configured.")
        raise typer.Exit(1)

    from polaris.services.ai import ContentGenerator

    console.print(f"[bold blue]Generating {count} content ideas...[/bold blue]\n")

    try:
        generator = ContentGenerator()
        focus_areas = focus.split(",") if focus else None
        ideas = generator.generate_content_ideas(count, focus_areas)

        for i, idea in enumerate(ideas, 1):
            console.print(f"[bold cyan]{i}. {idea.title}[/bold cyan]")
            console.print(f"   {idea.description}")
            console.print(f"   [dim]Media: {idea.media_type} | Key Message: {idea.key_message}[/dim]\n")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@content_app.command("list")
def list_content(
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status (draft, ready, published)"),
    account_id: Optional[int] = typer.Option(None, "--account", "-a", help="Filter by account"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum results"),
):
    """List saved content."""
    session = get_session()
    content_repo = ContentRepository(session)

    # Parse status filter
    status_filter = None
    if status:
        try:
            status_filter = ContentStatus(status.lower())
        except ValueError:
            console.print(f"[red]Error:[/red] Invalid status '{status}'")
            console.print("Valid options: draft, ready, published, failed")
            session.close()
            raise typer.Exit(1)

    if account_id:
        contents = content_repo.get_by_account(account_id, status=status_filter, limit=limit)
    elif status_filter:
        if status_filter == ContentStatus.DRAFT:
            contents = content_repo.get_drafts()[:limit]
        elif status_filter == ContentStatus.READY:
            contents = content_repo.get_ready_for_publish()[:limit]
        elif status_filter == ContentStatus.PUBLISHED:
            contents = content_repo.get_published(limit=limit)
        else:
            contents = content_repo.get_all(limit=limit)
    else:
        contents = content_repo.get_all(limit=limit)

    if not contents:
        console.print("[yellow]No content found.[/yellow]")
        session.close()
        return

    table = Table(title="Content")
    table.add_column("ID", style="dim")
    table.add_column("Topic", max_width=20)
    table.add_column("Caption", max_width=40)
    table.add_column("Status")
    table.add_column("AI", justify="center")
    table.add_column("Created")

    for content in contents:
        status_color = {
            ContentStatus.DRAFT: "yellow",
            ContentStatus.READY: "blue",
            ContentStatus.PUBLISHED: "green",
            ContentStatus.FAILED: "red",
        }.get(content.status, "white")

        # Strip emojis on Windows for console compatibility
        topic = content.topic or "-"
        caption = content.caption[:40] + "..." if len(content.caption) > 40 else content.caption
        if sys.platform == "win32":
            topic = strip_emojis(topic)
            caption = strip_emojis(caption)

        table.add_row(
            str(content.id),
            topic,
            caption,
            f"[{status_color}]{content.status.value}[/{status_color}]",
            "[green][+][/green]" if content.ai_generated else "-",
            content.created_at.strftime("%Y-%m-%d %H:%M"),
        )

    console.print(table)
    session.close()


@content_app.command("show")
def show_content(
    content_id: int = typer.Argument(..., help="Content ID to display"),
):
    """Show detailed content information."""
    session = get_session()
    content_repo = ContentRepository(session)

    content = content_repo.get(content_id)
    if not content:
        console.print(f"[red]Error:[/red] Content {content_id} not found.")
        session.close()
        raise typer.Exit(1)

    console.print(f"[bold]Content #{content.id}[/bold]")
    console.print(f"Status: {content.status.value}")
    console.print(f"Topic: {content.topic or 'N/A'}")
    console.print(f"AI Generated: {'Yes' if content.ai_generated else 'No'}")
    console.print(f"Media Type: {content.media_type.value}")
    console.print(f"Media URL: {content.media_url or 'Not set'}")
    console.print(f"Created: {content.created_at}")
    console.print()

    safe_print_panel(content.caption, title="Caption", border_style="green")

    if content.hashtags:
        safe_print_panel(content.hashtags, title="Hashtags", border_style="blue")

    session.close()


@content_app.command("edit")
def edit_content(
    content_id: int = typer.Argument(..., help="Content ID to edit"),
    caption: Optional[str] = typer.Option(None, "--caption", "-c", help="New caption"),
    hashtags: Optional[str] = typer.Option(None, "--hashtags", help="New hashtags"),
    media_url: Optional[str] = typer.Option(None, "--media-url", "-m", help="Media URL"),
):
    """Edit existing content."""
    session = get_session()
    content_repo = ContentRepository(session)

    content = content_repo.get(content_id)
    if not content:
        console.print(f"[red]Error:[/red] Content {content_id} not found.")
        session.close()
        raise typer.Exit(1)

    updates = {}
    if caption:
        updates["caption"] = caption
    if hashtags:
        updates["hashtags"] = hashtags
    if media_url:
        updates["media_url"] = media_url

    if not updates:
        console.print("[yellow]No changes specified.[/yellow]")
        session.close()
        return

    content_repo.update(content_id, **updates)
    content_repo.commit()
    console.print(f"[green]Content {content_id} updated.[/green]")
    session.close()


@content_app.command("ready")
def mark_ready(
    content_id: int = typer.Argument(..., help="Content ID to mark as ready"),
):
    """Mark content as ready for publishing."""
    session = get_session()
    content_repo = ContentRepository(session)

    content = content_repo.get(content_id)
    if not content:
        console.print(f"[red]Error:[/red] Content {content_id} not found.")
        session.close()
        raise typer.Exit(1)

    if not content.media_url:
        console.print("[yellow]Warning:[/yellow] Content has no media URL set.")
        if not typer.confirm("Mark as ready anyway?"):
            session.close()
            return

    content_repo.mark_ready(content_id)
    content_repo.commit()
    console.print(f"[green]Content {content_id} marked as ready for publishing.[/green]")
    session.close()


@content_app.command("delete")
def delete_content(
    content_id: int = typer.Argument(..., help="Content ID to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete content."""
    session = get_session()
    content_repo = ContentRepository(session)

    content = content_repo.get(content_id)
    if not content:
        console.print(f"[red]Error:[/red] Content {content_id} not found.")
        session.close()
        raise typer.Exit(1)

    if not force:
        if not typer.confirm(f"Delete content #{content_id}?"):
            console.print("Cancelled.")
            session.close()
            return

    content_repo.delete(content_id)
    content_repo.commit()
    console.print(f"[green]Content {content_id} deleted.[/green]")
    session.close()


@content_app.command("improve")
def improve_content(
    content_id: int = typer.Argument(..., help="Content ID to improve"),
    focus: str = typer.Option(
        "engagement and clarity",
        "--focus",
        "-f",
        help="Improvement focus",
    ),
):
    """Improve existing content using AI."""
    settings = get_settings()

    if not settings.is_anthropic_configured:
        console.print("[red]Error:[/red] Anthropic API key not configured.")
        raise typer.Exit(1)

    session = get_session()
    content_repo = ContentRepository(session)

    content = content_repo.get(content_id)
    if not content:
        console.print(f"[red]Error:[/red] Content {content_id} not found.")
        session.close()
        raise typer.Exit(1)

    from polaris.services.ai import ContentGenerator

    console.print(f"[bold blue]Improving content #{content_id}...[/bold blue]\n")

    try:
        generator = ContentGenerator()
        improved_caption = generator.improve_caption(content.caption, focus)

        console.print("[dim]Original:[/dim]")
        safe_print_panel(content.caption, title="Original Caption", border_style="dim")
        console.print()
        safe_print_panel(improved_caption, title="[bold green]Improved Caption[/bold green]", border_style="green")

        if typer.confirm("\nSave improved caption?"):
            content_repo.update_caption(content_id, improved_caption)
            content_repo.commit()
            console.print("[green]Content updated![/green]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        session.close()
