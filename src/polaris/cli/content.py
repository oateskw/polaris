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
    carousel: bool = typer.Option(False, "--carousel", "-C", help="Generate a multi-image carousel post"),
    story: bool = typer.Option(False, "--story", "-s", help="Generate a 9:16 image and post as an Instagram Story"),
    reel: bool = typer.Option(False, "--reel", "-r", help="Generate a 9:16 portrait video optimised for Instagram Reels"),
    audio_track: str = typer.Option("none", "--audio", "-A", help="Music track for reels: none, cinematic, calm, motivational, urgent"),
    with_carousel: bool = typer.Option(True, "--with-carousel/--no-carousel", help="Also save reel slides as a paired carousel post"),
    github_repo: Optional[str] = typer.Option(None, "--github-repo", help="GitHub repo for media upload (e.g., 'user/repo')"),
):
    """Generate AI-powered caption, hashtags, and optionally an image for a post."""
    settings = get_settings()

    if not settings.is_anthropic_configured:
        console.print("[red]Error:[/red] Anthropic API key not configured.")
        console.print("Please set ANTHROPIC_API_KEY in your .env file.")
        raise typer.Exit(1)

    if (image or video or carousel or reel) and not settings.is_replicate_configured:
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
    media_type = None
    cover_url = None

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

        # Generate carousel if requested
        if carousel:
            console.print(f"\n[bold blue]Generating carousel ({slides} slides)...[/bold blue]")
            from polaris.services.ai.content_generator import CarouselSlide
            from polaris.services.ai import ImageGenerator, upload_to_github
            from pathlib import Path

            carousel_slides = generator.generate_carousel_slides(topic, context or "", slides)
            console.print(f"[green]Generated {len(carousel_slides)} slides[/green]\n")

            img_generator = ImageGenerator()
            slide_urls = []
            repo = github_repo or settings.github_repo or "oateskw/polaris"

            try:
                for i, slide in enumerate(carousel_slides, 1):
                    console.print(f"[bold cyan][{i}/{len(carousel_slides)}] Generating slide:[/bold cyan] \"{slide.title}\"")
                    console.print(f"      Subtitle: {slide.subtitle}")
                    if slide.bullets:
                        for b in slide.bullets:
                            console.print(f"        - {b}")

                    generated_image = img_generator.generate_carousel_slide_image(
                        title=slide.title,
                        subtitle=slide.subtitle,
                        image_prompt=slide.image_prompt,
                        slide_index=i,
                        bullets=slide.bullets,
                    )
                    console.print(f"      Image saved: {generated_image.local_path}")

                    if repo:
                        try:
                            slide_url = upload_to_github(
                                local_path=Path(generated_image.local_path),
                                repo=repo,
                                branch=settings.github_branch,
                            )
                            slide_urls.append(slide_url)
                            console.print(f"      Uploaded: {slide_url}\n")
                        except Exception as e:
                            console.print(f"      [yellow]Warning:[/yellow] Upload failed: {e}")
                            console.print(f"      Image saved locally: {generated_image.local_path}\n")

                    # Small pause between slides to avoid Replicate rate limiting
                    if i < len(carousel_slides):
                        import time as _time
                        _time.sleep(3)
            finally:
                img_generator.close()

            if slide_urls:
                media_url = "|".join(slide_urls)
                media_type = ContentType.CAROUSEL
                console.print(f"[green]Carousel ready with {len(slide_urls)} slides.[/green]")

        # Generate video if requested
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

        # Generate reel (9:16 portrait video) if requested
        if reel:
            reel_slides = slides if slides != 3 else 4
            console.print(f"\n[bold blue]Generating Reel ({reel_slides} slides, 9:16)...[/bold blue]")
            console.print("[dim]This may take a few minutes...[/dim]")
            from polaris.services.ai.video_generator import VideoGenerator
            from polaris.services.ai import upload_to_cloudinary
            from pathlib import Path

            reel_generator = VideoGenerator()
            generated_reel = None
            try:
                generated_reel = reel_generator.generate_video(
                    topic=topic,
                    caption=result.caption,
                    num_slides=reel_slides,
                    slide_duration=6.0,
                    include_text=not no_text,
                    style_instructions=context,
                    output_size=(1080, 1920),
                    brand_name="Polaris Innovations",
                    brand_tagline="AI Agents for Small Business",
                    audio_track=audio_track,
                )
                console.print(f"[green]Reel generated:[/green] {generated_reel.local_path}")
                console.print(f"[dim]Duration: {generated_reel.duration:.1f}s, Slides: {generated_reel.num_slides}[/dim]")

                media_type = ContentType.REEL

                if settings.is_cloudinary_configured:
                    console.print(f"\n[bold blue]Uploading Reel to Cloudinary...[/bold blue]")
                    try:
                        media_url = upload_to_cloudinary(Path(generated_reel.local_path))
                        console.print(f"[green]Uploaded to Cloudinary:[/green] {media_url}")

                        # Upload first slide as reel cover image
                        if generated_reel.cover_path and Path(generated_reel.cover_path).exists():
                            try:
                                cover_url = upload_to_cloudinary(Path(generated_reel.cover_path), resource_type="image")
                                console.print(f"[green]Cover uploaded:[/green] {cover_url}")
                            except Exception as ce:
                                console.print(f"[yellow]Warning:[/yellow] Cover upload failed: {ce}")
                    except Exception as e:
                        console.print(f"[yellow]Warning:[/yellow] Cloudinary upload failed: {e}")
                        console.print(f"Reel saved locally at: {generated_reel.local_path}")
                else:
                    console.print(f"\n[yellow]Note:[/yellow] Reel saved locally. Set CLOUDINARY_* in .env to auto-upload for Instagram.")
            except Exception as e:
                console.print(f"[red]Reel generation error:[/red] {e}")
            finally:
                reel_generator.close()

        # Generate paired carousel from reel slides if requested
        if reel and with_carousel and generated_reel is not None and getattr(generated_reel, "slide_paths", None):
            console.print(f"\n[bold blue]Creating paired carousel from reel slides...[/bold blue]")
            from polaris.services.ai.image_generator import upload_to_github

            repo = github_repo or settings.github_repo or "oateskw/polaris"
            slide_urls = []
            try:
                for i, slide_path in enumerate(generated_reel.slide_paths, 1):
                    console.print(f"  [{i}/{len(generated_reel.slide_paths)}] Uploading slide...")
                    slide_url = upload_to_github(
                        local_path=Path(slide_path),
                        repo=repo,
                        branch=settings.github_branch,
                    )
                    slide_urls.append(slide_url)

                if slide_urls and save:
                    carousel_session = get_session()
                    try:
                        c_repo = ContentRepository(carousel_session)
                        account_repo = AccountRepository(carousel_session)
                        accounts = account_repo.get_active_accounts()
                        c_account_id = accounts[0].id if accounts else None

                        carousel_content = c_repo.create_content(
                            account_id=c_account_id,
                            caption=result.caption,
                            hashtags=result.hashtags,
                            media_url="|".join(slide_urls),
                            media_type=ContentType.CAROUSEL,
                            topic=topic,
                            ai_generated=True,
                        )
                        carousel_session.commit()
                        console.print(f"[green]Paired carousel saved:[/green] ID {carousel_content.id} ({len(slide_urls)} slides)")
                    finally:
                        carousel_session.close()
            except Exception as e:
                console.print(f"[yellow]Warning:[/yellow] Carousel pairing failed: {e}")

        # Generate and post story if requested
        if story:
            console.print("\n[bold blue]Generating 9:16 story image...[/bold blue]")
            from polaris.services.ai.image_generator import ImageGenerator, extract_hook, upload_to_github, create_story_slide, GRAPHIC_STYLE_DEFAULT
            from polaris.services.instagram.client import InstagramClient
            from polaris.services.instagram.publisher import InstagramPublisher
            from pathlib import Path

            hook_text = extract_hook(result.caption)

            img_generator = ImageGenerator()
            try:
                raw_story = img_generator.generate_image(
                    topic=topic,
                    caption_summary=result.caption[:200],
                    style_instructions=GRAPHIC_STYLE_DEFAULT,
                    aspect_ratio="9:16",
                    output_dir=Path("images"),
                )
                composited_path = raw_story.local_path.replace(".png", "_story.png")
                create_story_slide(
                    image_path=raw_story.local_path,
                    headline=hook_text,
                    body="",
                    output_path=composited_path,
                )

                class _StoryGenerated:
                    local_path = composited_path

                generated_story = _StoryGenerated()
                console.print(f"[green]Story image saved:[/green] {generated_story.local_path}")

                # Upload to GitHub to get a public URL
                repo = github_repo or settings.github_repo or "oateskw/polaris"
                story_url = None
                if repo:
                    console.print(f"[bold blue]Uploading story image to GitHub ({repo})...[/bold blue]")
                    try:
                        story_url = upload_to_github(
                            local_path=Path(generated_story.local_path),
                            repo=repo,
                            branch=settings.github_branch,
                        )
                        console.print(f"[green]Uploaded:[/green] {story_url}")
                    except Exception as e:
                        console.print(f"[yellow]Warning:[/yellow] GitHub upload failed: {e}")

                # Post to Instagram Story
                if story_url:
                    console.print("\n[bold blue]Publishing to Instagram Story...[/bold blue]")
                    session = get_session()
                    try:
                        account_repo = AccountRepository(session)
                        accounts = account_repo.get_active_accounts()
                        if not accounts:
                            console.print("[yellow]No Instagram accounts connected. Run 'polaris accounts add'.[/yellow]")
                        else:
                            acct = accounts[0] if account_id is None else next(
                                (a for a in accounts if a.id == account_id), accounts[0]
                            )
                            client = InstagramClient(
                                access_token=acct.access_token,
                                instagram_user_id=acct.instagram_user_id,
                            )
                            publisher = InstagramPublisher(client)
                            story_media_id = publisher.publish_story(story_url)
                            console.print(f"[bold green]Story published![/bold green] Media ID: {story_media_id}")
                    except Exception as e:
                        console.print(f"[red]Story publish error:[/red] {e}")
                    finally:
                        session.close()
                else:
                    console.print("[yellow]No public URL — story not published. Set --github-repo to auto-upload.[/yellow]")
            finally:
                img_generator.close()

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
                if cover_url is not None:
                    create_kwargs["cover_url"] = cover_url
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


@content_app.command("reel-from-images")
def reel_from_images(
    images: list[str] = typer.Argument(..., help="Image file paths to use as slides"),
    topic: str = typer.Option(..., "--topic", "-t", help="Topic label for the output filename"),
    slide_duration: float = typer.Option(5.0, "--duration", "-d", help="Seconds each slide is shown"),
    fade_duration: float = typer.Option(0.6, "--fade", help="Fade-in/fade-out duration in seconds"),
    brand_name: str = typer.Option("Polaris Innovations", "--brand", help="Brand name for watermark"),
    brand_tagline: str = typer.Option("AI Agents for Small Business", "--tagline", help="Brand tagline"),
    audio_file: Optional[str] = typer.Option(None, "--audio-file", "-a", help="Path to an MP3 file to embed (or filename from the music/ folder)"),
    ai_label: bool = typer.Option(False, "--ai-label", help="Apply the 'Made with AI' label on Instagram"),
    caption: Optional[str] = typer.Option(None, "--caption", "-c", help="Caption to save with the content"),
    hashtags: Optional[str] = typer.Option(None, "--hashtags", help="Hashtags to save with the content"),
    save: bool = typer.Option(False, "--save", help="Save content to database after assembling"),
):
    """Assemble a 9:16 Reel from pre-existing approved images.

    Images are letterboxed (full image always visible) and connected with
    clean fade-to-black transitions.
    """
    from pathlib import Path

    settings = get_settings()

    missing = [p for p in images if not Path(p).exists()]
    if missing:
        console.print(f"[red]Error:[/red] Image files not found: {', '.join(missing)}")
        raise typer.Exit(1)

    if len(images) < 2:
        console.print("[red]Error:[/red] Need at least 2 images to create a reel.")
        raise typer.Exit(1)

    # Resolve audio file — accept full path or filename relative to music/ folder
    resolved_audio = None
    if audio_file:
        audio_candidate = Path(audio_file)
        if not audio_candidate.exists():
            audio_candidate = Path(__file__).parents[3] / "music" / audio_file
            if not audio_candidate.suffix:
                audio_candidate = audio_candidate.with_suffix(".mp3")
        if audio_candidate.exists():
            resolved_audio = str(audio_candidate)
        else:
            console.print(f"[yellow]Warning:[/yellow] Audio file not found: {audio_file}")
            console.print(f"[dim]Drop MP3 files into the music/ folder and use the filename.[/dim]")

    console.print(f"[bold blue]Assembling Reel from {len(images)} images...[/bold blue]")
    for i, img in enumerate(images, 1):
        console.print(f"  [{i}] {img}")
    if resolved_audio:
        console.print(f"[dim]Audio: {Path(resolved_audio).name}[/dim]")
    elif audio_file:
        console.print(f"[yellow]Audio file not found — reel will be silent.[/yellow]")
    if ai_label:
        console.print(f"[dim]AI label: enabled[/dim]")

    from polaris.services.ai.video_generator import VideoGenerator
    from polaris.services.ai import upload_to_cloudinary

    reel_gen = VideoGenerator()
    media_url = None
    try:
        generated_reel = reel_gen.generate_video_from_images(
            image_paths=images,
            topic=topic,
            slide_duration=slide_duration,
            output_size=(1080, 1920),
            brand_name=brand_name,
            brand_tagline=brand_tagline,
            fade_duration=fade_duration,
            audio_path=resolved_audio,
        )
        console.print(f"[green]Reel generated:[/green] {generated_reel.local_path}")
        console.print(f"[dim]Duration: {generated_reel.duration:.1f}s, Slides: {generated_reel.num_slides}[/dim]")

        reel_cover_url = None
        if settings.is_cloudinary_configured:
            console.print(f"\n[bold blue]Uploading Reel to Cloudinary...[/bold blue]")
            try:
                media_url = upload_to_cloudinary(Path(generated_reel.local_path))
                console.print(f"[green]Uploaded to Cloudinary:[/green] {media_url}")
                # Upload first slide as cover
                try:
                    reel_cover_url = upload_to_cloudinary(Path(images[0]), resource_type="image")
                    console.print(f"[green]Cover uploaded:[/green] {reel_cover_url}")
                except Exception as ce:
                    console.print(f"[yellow]Warning:[/yellow] Cover upload failed: {ce}")
            except Exception as e:
                console.print(f"[yellow]Warning:[/yellow] Cloudinary upload failed: {e}")
        else:
            console.print(f"\n[yellow]Note:[/yellow] Reel saved locally. Set CLOUDINARY_* in .env to auto-upload.")

        # Save to database if requested
        if save and caption:
            session = get_session()
            try:
                from polaris.repositories import AccountRepository, ContentRepository
                from polaris.models.content import ContentType
                account_repo = AccountRepository(session)
                accounts = account_repo.get_active_accounts()
                if accounts:
                    content_repo = ContentRepository(session)
                    content = content_repo.create_content(
                        account_id=accounts[0].id,
                        caption=caption,
                        hashtags=hashtags or "",
                        media_url=media_url,
                        topic=topic,
                        ai_generated=True,
                        ai_model="flux-1.1-pro",
                        media_type=ContentType.VIDEO,
                    )
                    # Set publishing options directly
                    content.audio_name = Path(resolved_audio).name if resolved_audio else None
                    content.is_ai_generated_content = ai_label
                    content.media_type = ContentType.REEL
                    content.cover_url = reel_cover_url
                    content_repo.commit()
                    console.print(f"\n[green]Content saved with ID:[/green] {content.id}")
            finally:
                session.close()

    except Exception as e:
        console.print(f"[red]Reel assembly error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        reel_gen.close()


@content_app.command("post-story")
def post_story(
    story_type: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help="Story type: tip, fact, poll, quote (auto-rotates daily if not set)",
    ),
    topic: str = typer.Option(
        "AI automation for small businesses",
        "--topic",
        help="Topic context for the story",
    ),
    account_id: Optional[int] = typer.Option(None, "--account", "-a", help="Account ID"),
    github_repo: Optional[str] = typer.Option(None, "--github-repo", envvar="GITHUB_REPO", help="GitHub repo (owner/repo) for image hosting"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Generate image only, do not publish"),
    audio: str = typer.Option("cinematic", "--audio", help="Music track: cinematic/motivational/calm/urgent/none"),
):
    """Generate and publish a daily Instagram Story (auto-rotates tip/fact/poll/quote).

    Run at 8:00 AM daily via Task Scheduler for hands-off story posting.
    Logs to logs/stories.log.
    """
    import logging
    from datetime import date, datetime, timezone
    from pathlib import Path

    log_path = Path(__file__).parents[4] / "logs" / "stories.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    from logging.handlers import RotatingFileHandler
    handler = RotatingFileHandler(str(log_path), maxBytes=5_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])

    from polaris.services.ai.prompts import (
        BRAND_CONTEXT,
        STORY_CONTENT_PROMPT,
        STORY_TYPE_INSTRUCTIONS,
    )
    from polaris.services.ai.claude_client import ClaudeClient
    from polaris.services.ai.image_generator import ImageGenerator, upload_to_github, create_story_slide, GRAPHIC_STYLE_DEFAULT
    from polaris.services.ai.video_generator import create_story_video_with_audio
    from polaris.services.instagram.client import InstagramClient
    from polaris.services.instagram.publisher import InstagramPublisher

    settings = get_settings()
    if not settings.is_anthropic_configured:
        console.print("[red]Error:[/red] Anthropic API key not configured.")
        raise typer.Exit(1)
    if not settings.is_replicate_configured:
        console.print("[red]Error:[/red] Replicate API key not configured.")
        raise typer.Exit(1)

    # Auto-rotate story type by day of year (cycles: tip, fact, poll, quote)
    types = ["tip", "fact", "poll", "quote"]
    if story_type is None:
        story_type = types[date.today().toordinal() % 4]
    elif story_type not in types:
        console.print(f"[red]Unknown type '{story_type}'. Choose from: {', '.join(types)}[/red]")
        raise typer.Exit(1)

    type_label = {"tip": "Tip of the Day", "fact": "Did You Know?", "poll": "Poll", "quote": "Quote"}[story_type]
    console.print(f"\n[bold blue]Generating {type_label} story...[/bold blue]\n")

    # 1. Generate story content with Claude
    claude = ClaudeClient()
    prompt = STORY_CONTENT_PROMPT.format(
        brand_context=BRAND_CONTEXT,
        story_type=type_label,
        topic=topic,
        type_instructions=STORY_TYPE_INSTRUCTIONS[story_type],
    )
    try:
        raw = claude.generate(prompt=prompt, temperature=0.8, max_tokens=300).strip()
    except Exception as e:
        console.print(f"[red]Content generation failed:[/red] {e}")
        logging.error(f"post-story content generation failed: {e}")
        raise typer.Exit(1)

    # Parse HEADLINE / BODY / IMAGE_TOPIC
    def _parse_field(text: str, field: str) -> str:
        for line in text.splitlines():
            if line.upper().startswith(f"{field.upper()}:"):
                return line[len(field) + 1:].strip()
        return ""

    headline = _parse_field(raw, "HEADLINE")
    body = _parse_field(raw, "BODY")
    image_topic = _parse_field(raw, "IMAGE_TOPIC")

    if not headline or not image_topic:
        console.print(f"[red]Failed to parse Claude response:[/red]\n{raw}")
        logging.error(f"post-story parse failed. Raw: {raw}")
        raise typer.Exit(1)

    console.print(f"[bold]{type_label}[/bold]")
    console.print(f"Headline:  {headline}")
    console.print(f"Body:      {body}")
    console.print(f"Image:     {image_topic}\n")

    # 2. Generate 9:16 story image using graphic style + integrated slide layout
    console.print("[dim]Generating story image...[/dim]")
    img_gen = ImageGenerator()
    try:
        raw_image = img_gen.generate_image(
            topic=image_topic,
            caption_summary=headline,
            style_instructions=GRAPHIC_STYLE_DEFAULT,
            aspect_ratio="9:16",
            output_dir=Path("images"),
        )

        composited_path = raw_image.local_path.replace(".png", "_story.png")
        create_story_slide(
            image_path=raw_image.local_path,
            headline=headline,
            body=body,
            output_path=composited_path,
        )

        # Optionally wrap in a short video with audio
        use_audio = audio.lower() not in ("none", "")
        music_path = Path(__file__).parents[3] / "music" / f"{audio.lower()}.mp3"
        if use_audio and music_path.exists():
            console.print(f"[dim]Adding audio ({audio})...[/dim]")
            video_path = composited_path.replace(".png", ".mp4")
            create_story_video_with_audio(composited_path, str(music_path), video_path)
            final_output = video_path
            is_video = True
        else:
            if use_audio:
                console.print(f"[yellow]Audio file not found: {music_path} — publishing as image.[/yellow]")
            final_output = composited_path
            is_video = False

        # Wrap in a simple namespace so downstream code can reference .local_path
        class _Generated:
            local_path = final_output

        generated = _Generated()

    except Exception as e:
        console.print(f"[red]Image generation failed:[/red] {e}")
        logging.error(f"post-story image generation failed: {e}")
        img_gen.close()
        raise typer.Exit(1)
    finally:
        img_gen.close()

    label = "Video saved" if is_video else "Image saved"
    console.print(f"[green]{label}:[/green] {generated.local_path}")

    if dry_run:
        console.print("[yellow]Dry run — skipping publish.[/yellow]")
        return

    # 3. Upload for a public URL — videos go to Cloudinary, images try GitHub first
    media_url = None
    if is_video:
        if settings.is_cloudinary_configured:
            from polaris.services.ai import upload_to_cloudinary
            console.print("[dim]Uploading video to Cloudinary...[/dim]")
            try:
                media_url = upload_to_cloudinary(Path(generated.local_path), resource_type="video")
                console.print(f"[green]Uploaded:[/green] {media_url}")
            except Exception as e:
                console.print(f"[red]Cloudinary upload failed:[/red] {e}")
                logging.error(f"post-story cloudinary video upload failed: {e}")
                raise typer.Exit(1)
        else:
            console.print("[red]Cloudinary not configured — required for video stories.[/red]")
            raise typer.Exit(1)
    else:
        repo = github_repo or (settings.github_repo if hasattr(settings, "github_repo") else None)
        if repo:
            console.print("[dim]Uploading image to GitHub...[/dim]")
            try:
                media_url = upload_to_github(Path(generated.local_path), repo=repo)
                console.print(f"[green]Uploaded:[/green] {media_url}")
            except Exception as e:
                console.print(f"[yellow]GitHub upload failed, trying Cloudinary:[/yellow] {e}")
                logging.warning(f"post-story github upload failed: {e}")

        if not media_url and settings.is_cloudinary_configured:
            from polaris.services.ai import upload_to_cloudinary
            console.print("[dim]Uploading image to Cloudinary...[/dim]")
            try:
                media_url = upload_to_cloudinary(Path(generated.local_path), resource_type="image")
                console.print(f"[green]Uploaded:[/green] {media_url}")
            except Exception as e:
                console.print(f"[red]Cloudinary upload failed:[/red] {e}")
                logging.error(f"post-story cloudinary upload failed: {e}")
                raise typer.Exit(1)

    if not media_url:
        console.print("[red]No upload destination configured.[/red] Set GITHUB_REPO or CLOUDINARY_* in .env.")
        raise typer.Exit(1)

    # 4. Publish to Instagram Story
    session = get_session()
    try:
        account_repo = AccountRepository(session)
        accounts = account_repo.get_active_accounts()
        if not accounts:
            console.print("[red]No active Instagram account found.[/red]")
            raise typer.Exit(1)
        acct = accounts[0] if account_id is None else next(
            (a for a in accounts if a.id == account_id), accounts[0]
        )
        client = InstagramClient(
            access_token=acct.access_token,
            instagram_user_id=acct.instagram_user_id,
        )
        publisher = InstagramPublisher(client)
        console.print("[dim]Publishing to Instagram Story...[/dim]")
        if is_video:
            media_id = publisher.publish_story_video(media_url)
        else:
            media_id = publisher.publish_story(media_url)
        console.print(f"[bold green]Story published![/bold green] Media ID: {media_id}")
        logging.info(f"Story published: type={story_type} media_id={media_id} headline={headline!r}")
    except Exception as e:
        console.print(f"[red]Publish failed:[/red] {e}")
        logging.error(f"post-story publish failed: {e}")
        raise typer.Exit(1)
    finally:
        session.close()


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


@content_app.command("trending-audio")
def trending_audio(
    topic: str = typer.Option(
        "AI automation for small businesses",
        "--topic",
        "-t",
        help="Topic of your Reel content",
    ),
    content_type: str = typer.Option(
        "Reel",
        "--type",
        help="Content type (Reel, Carousel, Story)",
    ),
):
    """Get AI-curated trending Instagram audio recommendations for your Reel."""
    from datetime import date

    settings = get_settings()
    if not settings.is_anthropic_configured:
        console.print("[red]Error:[/red] Anthropic API key not configured.")
        raise typer.Exit(1)

    from polaris.services.ai.claude_client import ClaudeClient
    from polaris.services.ai.prompts import BRAND_CONTEXT, TRENDING_AUDIO_PROMPT

    console.print(f"\n[bold blue]Finding trending audio for:[/bold blue] {topic}\n")

    prompt = TRENDING_AUDIO_PROMPT.format(
        today=date.today().strftime("%B %d, %Y"),
        brand_context=BRAND_CONTEXT,
        topic=topic,
        content_type=content_type,
    )

    try:
        from rich.markup import escape

        claude = ClaudeClient()
        result = claude.generate(prompt=prompt, temperature=0.7, max_tokens=800)

        console.print(Panel(
            escape(result.strip()),
            title="[bold green]Trending Audio Recommendations[/bold green]",
            border_style="green",
            padding=(1, 2),
        ))

        console.print(
            "\n[dim]Tip: Use the track name with[/dim] [bold]polaris content reel-from-images --audio-name \"<track>\"[/bold]"
        )

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


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
