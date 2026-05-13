"""AI-powered video generation using image slideshows."""

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from moviepy import (
    AudioFileClip,
    ImageClip,
    VideoClip,
    CompositeVideoClip,
    concatenate_videoclips,
    concatenate_audioclips,
)
from moviepy.video.fx import CrossFadeIn, CrossFadeOut, FadeIn, FadeOut
from moviepy.audio.fx import AudioFadeIn, AudioFadeOut
from PIL import Image, ImageDraw, ImageFont
import io

from polaris.services.ai.image_generator import (
    ImageGenerator,
    extract_hook,
    BRAND,
    GRAPHIC_STYLE_DEFAULT,
    _get_font,
    wrap_text,
    create_reel_slide,
)


@dataclass
class GeneratedVideo:
    """Generated video with metadata."""

    local_path: str
    url: Optional[str]
    prompt: str
    duration: float
    num_slides: int
    cover_path: Optional[str] = None
    slide_paths: list = None  # all composited slide image paths


# ---------------------------------------------------------------------------
# Story arc prompt generation
# ---------------------------------------------------------------------------

_STORY_ARC_PROMPT = """You are an art director creating a visual narrative for a short Instagram video about:

Topic: {topic}
Hook: {hook}

Generate {num_slides} image scene descriptions that form a cohesive visual story arc.
The scenes should progress emotionally from PROBLEM → TENSION → TURNING POINT → SOLUTION/RELIEF (use as many stages as you have slides).

For each scene write ONE sentence describing:
- Specific subject (real person, specific age/look)
- Their emotion and body language
- The exact environment and props
- Lighting and mood

Rules:
- Each scene must be visually DISTINCT (different angle, location, or moment in time)
- No text, logos, or watermarks in images
- Real small business settings — offices, storefronts, phones, laptops
- No robots, sci-fi, or abstract concepts
- Each scene must feel like a different frame in a documentary
- Show people doing the work they are passionate about, not buried in admin work
- Avoid paperwork, forms, invoices, filing, and stressed "doing desk work" moments
- Keep the mood upbeat and cheerful with positive body language

Return ONLY {num_slides} lines, one scene per line, numbered 1. 2. 3. etc."""


def _generate_story_arc_prompts(
    topic: str,
    hook: str,
    num_slides: int,
    claude_client,
) -> list[str]:
    """Ask Claude to generate story-arc scene descriptions."""
    prompt = _STORY_ARC_PROMPT.format(
        topic=topic,
        hook=hook,
        num_slides=num_slides,
    )
    response = claude_client.generate(prompt=prompt, temperature=0.75, max_tokens=600)

    scenes = []
    for line in response.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # Strip leading "1. " / "1) " etc.
        cleaned = re.sub(r"^\d+[.)]\s*", "", line).strip()
        if cleaned:
            scenes.append(cleaned)

    # Ensure we always return exactly num_slides items
    while len(scenes) < num_slides:
        scenes.append(f"A small business owner working confidently at a modern desk, scene {len(scenes) + 1}")
    return scenes[:num_slides]


def _generate_reel_slide_content(
    topic: str,
    caption: str,
    num_slides: int,
    claude_client,
    cta_word: str = "CAKE",
) -> list[dict]:
    """Generate headline + subtitle + bullets for each reel slide.

    Returns a list of dicts: {headline, subtitle, bullets: [str, ...]}
    Story arc: Hook → Problem escalation → Solution → CTA
    """
    prompt = f"""Write slide content for a {num_slides}-slide Instagram Reel about:
Topic: "{topic}"
Brand: Polaris Innovations — AI operational infrastructure for $2M–$10M companies.
Audience: COOs and ops directors who know their systems are broken.

Generate exactly {num_slides} slides following this story arc:
- Slide 1: Hook — name the failure point operators instantly recognise
- Slides 2 to {num_slides - 1}: Escalate the problem, then introduce the solution
- Slide {num_slides}: CTA — direct, specific ask (DM, discovery call)

For EACH slide return EXACTLY this format:
---
HEADLINE: [2-4 words, ALL CAPS, plain language]
SUBTITLE: [one short sentence, under 8 words]
BULLET1: [max 5 words, simple]
BULLET2: [max 5 words, simple]
---

Rules:
- Headline splits onto 2 lines naturally if over 3 words — write it with a newline: use | as the line break marker
- No emojis, no hashtags, no fluff
- Use plain, non-technical wording anyone can understand
- One idea per slide. Keep it simple.
- Bullets are specific actions or outcomes, not vague claims
- Use role-specific words from the topic/context (example: chef, bakery, wedding cakes) so the viewer feels seen
- Avoid jargon terms like lead generation, qualify leads, operational infrastructure, and pipeline
- Never mention "free 30-minute discovery call" or any discovery call
- Final slide must end with this exact CTA in BULLET2: "DM us the word {cta_word} right now."

Return only the {num_slides} slide blocks, nothing else."""

    response = claude_client.generate(prompt=prompt, temperature=0.7, max_tokens=800)

    slides = []
    current: dict = {}
    for line in response.strip().split("\n"):
        line = line.strip()
        if line == "---":
            if current.get("headline"):
                slides.append(current)
            current = {"headline": "", "subtitle": "", "bullets": []}
        elif line.upper().startswith("HEADLINE:"):
            raw = line.split(":", 1)[1].strip()
            current["headline"] = raw.replace("|", "\n")
        elif line.upper().startswith("SUBTITLE:"):
            current["subtitle"] = line.split(":", 1)[1].strip()
        elif line.upper().startswith("BULLET"):
            val = line.split(":", 1)[1].strip() if ":" in line else ""
            if val:
                current.setdefault("bullets", []).append(val)
    if current.get("headline"):
        slides.append(current)

    # Fallback if parsing is incomplete
    while len(slides) < num_slides:
        slides.append({"headline": topic[:30], "subtitle": "", "bullets": []})

    slides = slides[:num_slides]

    # Enforce final-slide CTA format for consistency.
    if slides:
        cta_line = f"DM us the word {cta_word.upper()} right now."
        final = slides[-1]
        final_bullets = final.get("bullets", [])
        if len(final_bullets) < 2:
            final_bullets = (final_bullets + ["Get more cake orders"])[:1]
            final_bullets.append(cta_line)
        else:
            final_bullets[1] = cta_line
        final["bullets"] = final_bullets

    return slides


def _extract_cta_word(caption: str, topic: str) -> str:
    """Extract the CTA keyword from caption/topic, defaulting to CAKE."""
    sources = [caption or "", topic or ""]
    for text in sources:
        match = re.search(r"\bDM\s+(?:us\s+)?(?:the\s+word\s+)?['\"]?([A-Za-z]{2,20})['\"]?", text, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return "CAKE"


def _generate_slide_texts(
    topic: str,
    caption: str,
    num_slides: int,
    claude_client,
    brand_name: Optional[str] = None,
) -> list[str]:
    """Generate one short on-screen text line per slide, forming a story arc.

    The lines are designed to be read as a connected narrative across the video:
    Hook → Problem → Turning Point → Solution/CTA.
    """
    brand_line = (
        f"\nBrand: This reel represents \"{brand_name}\". "
        f"Reference the brand's AI agent/solution naturally in the turning point and CTA slides. "
        f"The last slide should feel like a direct offer from {brand_name}.\n"
        if brand_name else ""
    )

    prompt = f"""Write exactly {num_slides} short on-screen text captions for an Instagram Reel.

Topic: "{topic}"
{brand_line}
These lines appear one per slide as the video plays — like chapter titles that tell a story together.

Story arc to follow across {num_slides} slides:
- Slide 1: Grab attention / relatable hook (pure pain point — no brand)
- Slides 2-3: Escalate the problem, then the turning point where the solution appears
- Slide 4: Name the solution / brand benefit specifically
- Last slide: Bold CTA — tell them exactly what to do next

Rules:
- Max 7 words per line — punchy and bold
- Each line must make sense on its own AND build on the previous
- Write like a confident entrepreneur, not a marketer
- No hashtags, no emojis

Return ONLY {num_slides} lines, numbered 1. 2. 3. etc. Nothing else."""

    response = claude_client.generate(prompt=prompt, temperature=0.7, max_tokens=200)

    lines = []
    for line in response.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        cleaned = re.sub(r"^\d+[.)]\s*", "", line).strip()
        if cleaned:
            lines.append(cleaned)

    # Fallback if parsing fails
    while len(lines) < num_slides:
        lines.append(topic[:50])
    return lines[:num_slides]


# ---------------------------------------------------------------------------
# Ken Burns effect
# ---------------------------------------------------------------------------

def create_ken_burns_clip(
    image_path: str,
    duration: float = 5.0,
    zoom_direction: str = "in",
    pan_direction: str = "right",
    output_size: tuple = (1080, 1080),
) -> VideoClip:
    """Create a smooth Ken Burns effect clip from an image."""
    img = Image.open(image_path).convert("RGB")

    scale_factor = 1.35
    base_size = max(output_size)
    new_size = (int(base_size * scale_factor), int(base_size * scale_factor))
    img = img.resize(new_size, Image.LANCZOS)
    img_array = np.array(img)

    img_h, img_w = img_array.shape[:2]
    out_w, out_h = output_size

    start_zoom, end_zoom = (1.0, 1.18) if zoom_direction == "in" else (1.18, 1.0)
    pan_amount = 28

    def make_frame(t):
        progress = t / duration
        # Ease in-out (smoothstep)
        smooth = progress * progress * (3 - 2 * progress)

        current_zoom = start_zoom + (end_zoom - start_zoom) * smooth
        crop_w = int(out_w / current_zoom)
        crop_h = int(out_h / current_zoom)

        center_x = img_w // 2
        center_y = img_h // 2

        pan_progress = (smooth - 0.5) * 2  # -1 to 1
        if pan_direction == "right":
            center_x += int(pan_progress * pan_amount)
        elif pan_direction == "left":
            center_x -= int(pan_progress * pan_amount)
        elif pan_direction == "down":
            center_y += int(pan_progress * pan_amount)
        elif pan_direction == "up":
            center_y -= int(pan_progress * pan_amount)

        x1 = max(0, center_x - crop_w // 2)
        y1 = max(0, center_y - crop_h // 2)
        x2 = min(img_w, x1 + crop_w)
        y2 = min(img_h, y1 + crop_h)

        if x2 - x1 < crop_w:
            x1 = max(0, x2 - crop_w)
        if y2 - y1 < crop_h:
            y1 = max(0, y2 - crop_h)

        cropped = img_array[y1:y2, x1:x2]
        pil_cropped = Image.fromarray(cropped)
        return np.array(pil_cropped.resize(output_size, Image.LANCZOS))

    return VideoClip(make_frame, duration=duration)


# ---------------------------------------------------------------------------
# Text overlay (matches brand style from image_generator)
# ---------------------------------------------------------------------------

def create_text_overlay_image(
    text: str,
    size: tuple = (1080, 1080),
    position: str = "top",
    font_size: int = 42,
) -> np.ndarray:
    """Create a branded text overlay as RGBA numpy array."""
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font = _get_font("bold", font_size)
    max_width = int(size[0] * 0.80)

    # Auto-shrink font so text block stays within 28% of image height
    max_block_h = int(size[1] * 0.28)
    min_size = 24

    def get_wrapped(fnt, fsize):
        words = text.split()
        wrapped, cur = [], []
        for word in words:
            test = ' '.join(cur + [word])
            bbox = draw.textbbox((0, 0), test, font=fnt)
            if bbox[2] - bbox[0] <= max_width:
                cur.append(word)
            else:
                if cur:
                    wrapped.append(' '.join(cur))
                cur = [word]
        if cur:
            wrapped.append(' '.join(cur))
        lh = fsize + int(fsize * 0.22)
        return wrapped, lh

    while font_size > min_size:
        lines, line_h = get_wrapped(font, font_size)
        if len(lines) * line_h <= max_block_h:
            break
        font_size -= 2
        font = _get_font("bold", font_size)

    lines, line_h = get_wrapped(font, font_size)
    total_h = len(lines) * line_h
    accent_bar = 5

    pad_v, pad_h = 26, 30

    if position == "top":
        y_start = 52 + accent_bar + pad_v
    elif position == "bottom":
        y_start = size[1] - total_h - pad_v - 60
    else:
        y_start = (size[1] - total_h) // 2

    max_lw = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        max_lw = max(max_lw, bbox[2] - bbox[0])

    bx1 = max(0, (size[0] - max_lw) // 2 - pad_h)
    bx2 = min(size[0], (size[0] + max_lw) // 2 + pad_h)
    by1 = max(0, y_start - pad_v - accent_bar)
    by2 = min(size[1], y_start + total_h + pad_v)

    # Gradient background card with rounded corners
    card_w, card_h = bx2 - bx1, by2 - by1
    if card_h > 0 and card_w > 0:
        top_c, bot_c = BRAND["bg_dark"], BRAND["bg_mid"]
        grad = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
        grad_draw = ImageDraw.Draw(grad)
        for row in range(card_h):
            t = row / max(card_h - 1, 1)
            r = int(top_c[0] + (bot_c[0] - top_c[0]) * t)
            g = int(top_c[1] + (bot_c[1] - top_c[1]) * t)
            b = int(top_c[2] + (bot_c[2] - top_c[2]) * t)
            a = int(top_c[3] + (bot_c[3] - top_c[3]) * t)
            grad_draw.line([(0, row), (card_w, row)], fill=(r, g, b, a))
        mask = Image.new("L", (card_w, card_h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, card_w - 1, card_h - 1], radius=14, fill=255)
        grad.putalpha(mask)
        img.alpha_composite(grad, dest=(bx1, by1))


    draw = ImageDraw.Draw(img)

    # Orange accent bar
    draw.rounded_rectangle(
        [bx1, by1, bx2, by1 + accent_bar + 4],
        radius=6,
        fill=BRAND["accent"],
    )

    y = y_start
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        x = (size[0] - lw) // 2
        draw.text((x + 2, y + 2), line, font=font, fill=BRAND["shadow"])
        draw.text((x, y), line, font=font, fill=BRAND["text_white"])
        y += line_h

    return np.array(img)


# ---------------------------------------------------------------------------
# Brand watermark overlay
# ---------------------------------------------------------------------------

def create_brand_watermark(
    brand_name: str,
    tagline: str = "",
    size: tuple = (1080, 1080),
) -> np.ndarray:
    """Create a persistent brand strip overlay (bottom-left) as RGBA numpy array.

    Renders the brand name in small-caps Poppins Bold with an orange accent dot,
    plus an optional tagline in muted text beneath it.
    """
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    w, h = size
    name_size = max(22, int(w * 0.026))
    tag_size  = max(16, int(w * 0.018))

    name_font = _get_font("bold",    name_size)
    tag_font  = _get_font("regular", tag_size)

    pad = int(w * 0.038)
    dot_r = max(5, int(w * 0.007))

    # Measure text
    name_bbox = draw.textbbox((0, 0), brand_name.upper(), font=name_font)
    name_w = name_bbox[2] - name_bbox[0]
    name_h = name_bbox[3] - name_bbox[1]

    tag_w, tag_h = 0, 0
    if tagline:
        tag_bbox = draw.textbbox((0, 0), tagline, font=tag_font)
        tag_w = tag_bbox[2] - tag_bbox[0]
        tag_h = tag_bbox[3] - tag_bbox[1]

    # Build the card dimensions
    dot_gap = int(dot_r * 2.5)
    block_w = dot_r * 2 + dot_gap + max(name_w, tag_w)
    block_h = name_h + (int(name_h * 0.3) + tag_h if tagline else 0)

    card_pad_v, card_pad_h = int(h * 0.012), int(w * 0.018)
    card_x1 = pad - card_pad_h
    card_x2 = pad + block_w + card_pad_h
    card_y2 = h - pad + card_pad_v
    card_y1 = card_y2 - block_h - card_pad_v * 2

    # Draw semi-transparent dark card
    card = Image.new("RGBA", (card_x2 - card_x1, card_y2 - card_y1), (0, 0, 0, 0))
    card_draw = ImageDraw.Draw(card)
    card_draw.rounded_rectangle(
        [0, 0, card_x2 - card_x1 - 1, card_y2 - card_y1 - 1],
        radius=10,
        fill=(*BRAND["bg_dark"][:3], 190),
    )
    img.alpha_composite(card, dest=(card_x1, card_y1))

    # Orange accent dot
    text_y = card_y1 + card_pad_v
    dot_x = pad
    dot_y = text_y + (name_h - dot_r * 2) // 2
    draw.ellipse([dot_x, dot_y, dot_x + dot_r * 2, dot_y + dot_r * 2], fill=BRAND["accent"])

    # Brand name
    text_x = dot_x + dot_r * 2 + dot_gap
    draw.text((text_x + 1, text_y + 1), brand_name.upper(), font=name_font, fill=BRAND["shadow"])
    draw.text((text_x, text_y), brand_name.upper(), font=name_font, fill=BRAND["text_white"])

    # Tagline
    if tagline:
        tag_y = text_y + name_h + int(name_h * 0.3)
        draw.text((text_x, tag_y), tagline, font=tag_font, fill=(*BRAND["text_muted"][:3], 200))

    return np.array(img)


# ---------------------------------------------------------------------------
# Story video helper
# ---------------------------------------------------------------------------

def create_story_video_with_audio(
    image_path: str,
    audio_path: str,
    output_path: str,
    duration: float = 7.0,
) -> str:
    """Convert a story image to a short MP4 with a background audio track.

    The image is held for ``duration`` seconds. Audio is trimmed to match.
    Output is suitable for publishing via publish_story_video().

    Args:
        image_path: Path to the composited 9:16 story PNG.
        audio_path: Path to the .mp3 music file.
        output_path: Where to write the output .mp4.
        duration: Clip length in seconds (default 7).

    Returns:
        output_path
    """
    clip  = ImageClip(image_path).with_duration(duration)
    audio = AudioFileClip(audio_path).subclipped(0, duration)
    clip  = clip.with_audio(audio)
    clip.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        logger=None,
    )
    return output_path


# ---------------------------------------------------------------------------
# Video generator
# ---------------------------------------------------------------------------

class VideoGenerator:
    """Generate slideshow videos from AI images with crossfade transitions."""

    CROSSFADE_DURATION = 0.5   # seconds of overlap between slides
    ZOOM_DIRECTIONS = ["in", "out", "in", "out", "in"]
    PAN_DIRECTIONS = ["right", "left", "down", "up", "right"]

    def __init__(self, image_generator: Optional[ImageGenerator] = None):
        self.image_generator = image_generator or ImageGenerator()

    def generate_video(
        self,
        topic: str,
        caption: str,
        num_slides: int = 3,
        slide_duration: float = 4.5,
        output_dir: Optional[Path] = None,
        include_text: bool = True,
        style_instructions: Optional[str] = None,
        output_size: tuple = (1080, 1080),
        brand_name: Optional[str] = None,
        brand_tagline: str = "",
        audio_track: str = "cinematic",
    ) -> GeneratedVideo:
        """Generate a cinematic slideshow video from AI images.

        Uses Claude to build a story-arc across slides (problem → solution)
        and adds smooth crossfade transitions between them.

        Args:
            topic: Topic for image generation
            caption: Caption to extract hook text from
            num_slides: Number of slides/images
            slide_duration: Duration per slide in seconds
            output_dir: Output directory
            include_text: Whether to add text overlay on first slide
            output_size: (width, height) of the output video; use (1080, 1920) for Reels
            brand_name: If set, adds a persistent brand watermark strip on every frame
            brand_tagline: Short tagline shown under the brand name in the watermark

        Returns:
            GeneratedVideo with path and metadata
        """
        if output_dir is None:
            output_dir = Path.cwd() / "videos"
        output_dir.mkdir(parents=True, exist_ok=True)

        temp_dir = output_dir / "temp_frames"
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Derive aspect ratio string for image generation
        w, h = output_size
        if w == h:
            aspect_ratio = "1:1"
        elif h > w:
            aspect_ratio = "9:16"
        else:
            aspect_ratio = "16:9"

        hook = extract_hook(caption)
        is_reel = (aspect_ratio == "9:16")
        effective_style = style_instructions or (GRAPHIC_STYLE_DEFAULT if is_reel else None)

        # Generate story-arc scene descriptions via Claude
        scene_descriptions = _generate_story_arc_prompts(
            topic=topic,
            hook=hook,
            num_slides=num_slides,
            claude_client=self.image_generator.claude_client,
        )

        # For reels: generate per-slide headline + subtitle + bullets via Claude
        # For square posts: use the old single text-line approach
        if is_reel:
            cta_word = _extract_cta_word(caption, topic)
            slide_content = _generate_reel_slide_content(
                topic=topic,
                caption=caption,
                num_slides=num_slides,
                claude_client=self.image_generator.claude_client,
                cta_word=cta_word,
            )
        else:
            slide_texts = _generate_slide_texts(
                topic=topic,
                caption=caption,
                num_slides=num_slides,
                claude_client=self.image_generator.claude_client,
                brand_name=brand_name,
            )

        # Generate images for each scene
        image_paths = []
        prompts = []

        for i, scene in enumerate(scene_descriptions):
            image_topic = f"{topic}. Scene: {scene}"
            generated = self.image_generator.generate_image(
                topic=image_topic,
                caption_summary=caption[:200],
                output_dir=temp_dir,
                style_instructions=effective_style,
                aspect_ratio=aspect_ratio,
            )
            image_paths.append(generated.local_path)
            prompts.append(generated.prompt)

        # For reels: composite each image with integrated slide layout, then fade-assemble
        if is_reel:
            composited_paths = []
            for i, img_path in enumerate(image_paths):
                content = slide_content[i]
                bullets = content["bullets"] or []
                all_texts = [content["headline"], content["subtitle"]] + bullets
                proofed = self.image_generator.proofread(*all_texts)
                headline, subtitle = proofed[0], proofed[1]
                bullets = proofed[2:] if len(proofed) > 2 else bullets

                out_path = str(temp_dir / f"slide_{i}_{int(time.time())}.png")
                create_reel_slide(
                    image_path=img_path,
                    headline=headline,
                    subtitle=subtitle,
                    bullets=bullets,
                    output_path=out_path,
                    size=output_size,
                )
                composited_paths.append(out_path)

            _music_dir = Path(__file__).parents[4] / "music"
            no_audio = audio_track.lower() in {"none", "off", "silent"}
            _audio_file = None
            if not no_audio:
                candidate = _music_dir / f"{audio_track}.mp3"
                if candidate.exists():
                    _audio_file = candidate
                else:
                    fallback = _music_dir / "cinematic.mp3"
                    if fallback.exists():
                        _audio_file = fallback
            result = self.generate_video_from_images(
                image_paths=composited_paths,
                topic=topic,
                caption=caption,
                slide_duration=slide_duration,
                output_dir=output_dir,
                output_size=output_size,
                brand_name=None,  # brand mark already baked in by create_integrated_slide
                audio_path=str(_audio_file) if _audio_file else None,
            )
            result.cover_path = composited_paths[0] if composited_paths else None
            result.slide_paths = composited_paths
            return result

        # Square post: Ken Burns + crossfade (original path)
        clips = []
        for i, img_path in enumerate(image_paths):
            clip = create_ken_burns_clip(
                img_path,
                duration=slide_duration,
                zoom_direction=self.ZOOM_DIRECTIONS[i % len(self.ZOOM_DIRECTIONS)],
                pan_direction=self.PAN_DIRECTIONS[i % len(self.PAN_DIRECTIONS)],
                output_size=output_size,
            )
            clips.append(clip)

        fade = self.CROSSFADE_DURATION
        if len(clips) > 1:
            faded_clips = []
            for i, clip in enumerate(clips):
                effects = []
                if i > 0:
                    effects.append(CrossFadeIn(fade))
                if i < len(clips) - 1:
                    effects.append(CrossFadeOut(fade))
                if effects:
                    clip = clip.with_effects(effects)
                faded_clips.append(clip)
            final_clip = concatenate_videoclips(faded_clips, padding=-fade, method="compose")
        else:
            final_clip = clips[0]

        total_duration = final_clip.duration

        if include_text:
            text_clips = []
            fade = self.CROSSFADE_DURATION
            for i, text_line in enumerate(slide_texts):
                slide_start = i * (slide_duration - fade)
                text_dur = slide_duration - fade - 0.3
                if text_dur <= 0:
                    text_dur = slide_duration * 0.7
                text_array = create_text_overlay_image(
                    text_line, size=output_size, position="top"
                )
                text_clip = (
                    ImageClip(text_array)
                    .with_start(slide_start + 0.15)
                    .with_duration(text_dur)
                    .with_effects([FadeIn(0.25), FadeOut(0.35)])
                )
                text_clips.append(text_clip)
            final_clip = CompositeVideoClip([final_clip] + text_clips)

        if brand_name:
            watermark_array = create_brand_watermark(
                brand_name=brand_name,
                tagline=brand_tagline,
                size=output_size,
            )
            watermark_clip = ImageClip(watermark_array).with_duration(final_clip.duration)
            final_clip = CompositeVideoClip([final_clip, watermark_clip])

        # Output filename
        safe_topic = re.sub(r'[^\w\s-]', '', topic)[:30].strip().replace(' ', '_')
        timestamp = int(time.time())
        output_path = output_dir / f"{safe_topic}_{timestamp}.mp4"

        final_clip.write_videofile(
            str(output_path),
            fps=30,
            codec="libx264",
            audio=False,
            preset="slow",      # Better compression/quality than "medium"
            ffmpeg_params=["-crf", "18"],   # Near-lossless quality
            threads=4,
            logger=None,
        )

        duration = total_duration
        final_clip.close()
        for clip in clips:
            clip.close()

        return GeneratedVideo(
            local_path=str(output_path),
            url=None,
            prompt="; ".join(prompts),
            duration=duration,
            num_slides=num_slides,
        )

    def generate_video_from_images(
        self,
        image_paths: list[str],
        topic: str,
        caption: str = "",
        slide_duration: float = 5.0,
        output_dir: Optional[Path] = None,
        output_size: tuple = (1080, 1920),
        brand_name: Optional[str] = None,
        brand_tagline: str = "",
        fade_duration: float = 0.6,
        audio_path: Optional[str] = None,
    ) -> GeneratedVideo:
        """Assemble a reel from pre-existing images using letterbox + fade transitions.

        Each image is letterboxed into the output frame (full image always
        visible, dark navy bars fill any empty space).  Slides transition via a
        clean fade-to-black then fade-in — no Ken Burns cropping, no extra text
        overlays (the images carry their own text).

        Args:
            image_paths: Ordered list of local image file paths.
            topic: Used for the output filename.
            slide_duration: Total seconds each slide is on screen (including fades).
            output_dir: Where to write the final MP4.
            output_size: (width, height); default 1080×1920 for Reels.
            brand_name: If set, adds a brand watermark on every frame.
            brand_tagline: Shown under the brand name in the watermark.
            fade_duration: Seconds for each fade-in / fade-out.
        """
        if output_dir is None:
            output_dir = Path.cwd() / "videos"
        output_dir.mkdir(parents=True, exist_ok=True)

        out_w, out_h = output_size
        bg_color = (10, 20, 40)   # brand dark navy

        def letterbox(image_path: str) -> np.ndarray:
            """Fit image inside output_size, padding with dark navy."""
            img = Image.open(image_path).convert("RGB")
            img_w, img_h = img.size
            scale = min(out_w / img_w, out_h / img_h)
            new_w = int(img_w * scale)
            new_h = int(img_h * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            bg = Image.new("RGB", output_size, bg_color)
            x = (out_w - new_w) // 2
            y = (out_h - new_h) // 2
            bg.paste(img, (x, y))
            return np.array(bg)

        # Build one clip per image: full duration, fade in + fade out
        clips = []
        for img_path in image_paths:
            frame = letterbox(img_path)
            clip = (
                ImageClip(frame)
                .with_duration(slide_duration)
                .with_effects([FadeIn(fade_duration), FadeOut(fade_duration)])
            )
            clips.append(clip)

        # Concatenate without any overlap so each fade goes cleanly through black
        final_clip = concatenate_videoclips(clips, method="compose")
        total_duration = final_clip.duration

        # Optional brand watermark
        if brand_name:
            watermark_array = create_brand_watermark(
                brand_name=brand_name,
                tagline=brand_tagline,
                size=output_size,
            )
            watermark_clip = ImageClip(watermark_array).with_duration(total_duration)
            final_clip = CompositeVideoClip([final_clip, watermark_clip])

        # Embed audio if provided
        audio_clip = None
        if audio_path and Path(audio_path).exists():
            raw_audio = AudioFileClip(audio_path)
            if raw_audio.duration < total_duration:
                # Loop until long enough, then trim
                copies = int(total_duration / raw_audio.duration) + 2
                audio_clip = concatenate_audioclips([raw_audio] * copies).subclipped(0, total_duration)
            else:
                audio_clip = raw_audio.subclipped(0, total_duration)
            # Fade in (0.4s) and fade out (1.5s) so audio doesn't start or end abruptly
            fade_in = min(0.4, total_duration * 0.1)
            fade_out = min(1.5, total_duration * 0.15)
            audio_clip = audio_clip.with_effects([AudioFadeIn(fade_in), AudioFadeOut(fade_out)])
            final_clip = final_clip.with_audio(audio_clip)

        safe_topic = re.sub(r'[^\w\s-]', '', topic)[:30].strip().replace(' ', '_')
        timestamp = int(time.time())
        output_path = output_dir / f"{safe_topic}_{timestamp}.mp4"

        final_clip.write_videofile(
            str(output_path),
            fps=30,
            codec="libx264",
            audio=audio_clip is not None,
            audio_codec="aac",
            preset="slow",
            ffmpeg_params=["-crf", "18"],
            threads=4,
            logger=None,
        )

        final_clip.close()
        for clip in clips:
            clip.close()
        if audio_clip:
            audio_clip.close()

        return GeneratedVideo(
            local_path=str(output_path),
            url=None,
            prompt=f"Assembled from {len(image_paths)} provided images",
            duration=total_duration,
            num_slides=len(image_paths),
        )

    def close(self):
        """Clean up resources."""
        self.image_generator.close()
