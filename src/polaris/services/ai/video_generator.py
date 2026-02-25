"""AI-powered video generation using image slideshows."""

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from moviepy import (
    ImageClip,
    VideoClip,
    CompositeVideoClip,
    concatenate_videoclips,
)
from moviepy.video.fx import CrossFadeIn, CrossFadeOut, FadeIn, FadeOut
from PIL import Image, ImageDraw, ImageFont
import io

from polaris.services.ai.image_generator import (
    ImageGenerator,
    extract_hook,
    BRAND,
    _get_font,
    wrap_text,
)


@dataclass
class GeneratedVideo:
    """Generated video with metadata."""

    local_path: str
    url: Optional[str]
    prompt: str
    duration: float
    num_slides: int


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


def _generate_slide_texts(
    topic: str,
    caption: str,
    num_slides: int,
    claude_client,
) -> list[str]:
    """Generate one short on-screen text line per slide, forming a story arc.

    The lines are designed to be read as a connected narrative across the video:
    Hook → Problem → Turning Point → Solution/CTA.
    """
    prompt = f"""Write exactly {num_slides} short on-screen text captions for an Instagram Reel.

Topic: "{topic}"

These lines appear one per slide as the video plays — like chapter titles that tell a story together.

Story arc to follow across {num_slides} slides:
- Slide 1: Grab attention / relatable hook
- Middle slides: Build the problem, then the turning point
- Last slide: The payoff / clear call to action

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

        Returns:
            GeneratedVideo with path and metadata
        """
        if output_dir is None:
            output_dir = Path.cwd() / "videos"
        output_dir.mkdir(parents=True, exist_ok=True)

        temp_dir = output_dir / "temp_frames"
        temp_dir.mkdir(parents=True, exist_ok=True)

        hook = extract_hook(caption)

        # Generate story-arc scene descriptions via Claude
        scene_descriptions = _generate_story_arc_prompts(
            topic=topic,
            hook=hook,
            num_slides=num_slides,
            claude_client=self.image_generator.claude_client,
        )

        # Generate per-slide text lines
        slide_texts = _generate_slide_texts(
            topic=topic,
            caption=caption,
            num_slides=num_slides,
            claude_client=self.image_generator.claude_client,
        )

        # Generate images for each scene
        image_paths = []
        prompts = []

        for i, scene in enumerate(scene_descriptions):
            # Combine topic context with the specific scene description
            image_topic = f"{topic}. Scene: {scene}"
            generated = self.image_generator.generate_image(
                topic=image_topic,
                caption_summary=caption[:200],
                output_dir=temp_dir,
                style_instructions=style_instructions,
            )
            image_paths.append(generated.local_path)
            prompts.append(generated.prompt)

        # Build Ken Burns clips
        clips = []
        for i, img_path in enumerate(image_paths):
            clip = create_ken_burns_clip(
                img_path,
                duration=slide_duration,
                zoom_direction=self.ZOOM_DIRECTIONS[i % len(self.ZOOM_DIRECTIONS)],
                pan_direction=self.PAN_DIRECTIONS[i % len(self.PAN_DIRECTIONS)],
            )
            clips.append(clip)

        # Apply crossfade transitions between slides
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

        # Per-slide text overlays — each line is timed to its corresponding slide
        if include_text:
            text_clips = []
            fade = self.CROSSFADE_DURATION
            for i, text_line in enumerate(slide_texts):
                # Slide i starts at this timestamp in the final video
                slide_start = i * (slide_duration - fade)
                # Show text for most of the slide, leaving a gap before crossfade
                text_dur = slide_duration - fade - 0.3
                if text_dur <= 0:
                    text_dur = slide_duration * 0.7

                text_array = create_text_overlay_image(
                    text_line, size=(1080, 1080), position="top"
                )
                text_clip = (
                    ImageClip(text_array)
                    .with_start(slide_start + 0.15)
                    .with_duration(text_dur)
                    .with_effects([FadeIn(0.25), FadeOut(0.35)])
                )
                text_clips.append(text_clip)

            final_clip = CompositeVideoClip([final_clip] + text_clips)

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

    def close(self):
        """Clean up resources."""
        self.image_generator.close()
