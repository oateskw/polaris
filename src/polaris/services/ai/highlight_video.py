"""Create highlight videos from a single image with zoom effects and callouts."""

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from moviepy import VideoClip, CompositeVideoClip, concatenate_videoclips, ImageClip
from PIL import Image, ImageDraw, ImageFont


@dataclass
class Highlight:
    """A highlight area with text callout."""
    text: str
    x: float  # 0-1, relative position
    y: float  # 0-1, relative position
    zoom: float = 1.5  # zoom level


def create_highlight_clip(
    image_path: str,
    highlight: Highlight,
    duration: float = 3.0,
    output_size: tuple = (1080, 1080),
) -> VideoClip:
    """Create a clip that zooms into a highlight area.

    Args:
        image_path: Path to the source image
        highlight: Highlight with position and text
        duration: Duration in seconds
        output_size: Output dimensions

    Returns:
        VideoClip with zoom effect
    """
    # Load image
    img = Image.open(image_path).convert("RGB")

    # Scale up for zoom headroom
    scale = 2.0
    img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    img_array = np.array(img)

    img_h, img_w = img_array.shape[:2]
    out_w, out_h = output_size

    # Calculate target center based on highlight position
    target_x = int(highlight.x * img_w)
    target_y = int(highlight.y * img_h)

    # Start centered, end at highlight
    start_x = img_w // 2
    start_y = img_h // 2
    start_zoom = 1.0
    end_zoom = highlight.zoom

    def make_frame(t):
        progress = t / duration
        # Ease in-out
        progress = 3 * progress**2 - 2 * progress**3

        # Interpolate position and zoom
        current_x = int(start_x + (target_x - start_x) * progress)
        current_y = int(start_y + (target_y - start_y) * progress)
        current_zoom = start_zoom + (end_zoom - start_zoom) * progress

        # Calculate crop size
        crop_w = int(out_w / current_zoom)
        crop_h = int(out_h / current_zoom)

        # Calculate crop bounds
        x1 = max(0, current_x - crop_w // 2)
        y1 = max(0, current_y - crop_h // 2)
        x2 = min(img_w, x1 + crop_w)
        y2 = min(img_h, y1 + crop_h)

        # Adjust if at edges
        if x2 - x1 < crop_w:
            x1 = max(0, x2 - crop_w)
        if y2 - y1 < crop_h:
            y1 = max(0, y2 - crop_h)

        # Crop and resize
        cropped = img_array[y1:y2, x1:x2]
        pil_cropped = Image.fromarray(cropped)
        pil_resized = pil_cropped.resize(output_size, Image.LANCZOS)

        return np.array(pil_resized)

    return VideoClip(make_frame, duration=duration)


def create_text_callout(
    text: str,
    size: tuple = (1080, 1080),
    position: str = "bottom",
    font_size: int = 50,
) -> np.ndarray:
    """Create a text callout overlay."""
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Load font
    font = None
    font_paths = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]

    for font_path in font_paths:
        try:
            font = ImageFont.truetype(font_path, font_size)
            break
        except:
            continue

    if font is None:
        font = ImageFont.load_default()

    # Word wrap
    max_width = int(size[0] * 0.9)
    words = text.split()
    lines = []
    current_line = []

    for word in words:
        test_line = ' '.join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
    if current_line:
        lines.append(' '.join(current_line))

    # Calculate dimensions
    line_height = font_size + 8
    total_height = len(lines) * line_height

    # Position
    padding = 50
    if position == "top":
        y_start = padding
    elif position == "bottom":
        y_start = size[1] - total_height - padding - 30
    else:
        y_start = (size[1] - total_height) // 2

    # Draw background
    max_line_width = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        max_line_width = max(max_line_width, bbox[2] - bbox[0])

    box_padding = 25
    box_left = (size[0] - max_line_width) // 2 - box_padding
    box_right = (size[0] + max_line_width) // 2 + box_padding
    box_top = y_start - box_padding
    box_bottom = y_start + total_height + box_padding

    # Pink/rose gold background for beauty salon theme
    draw.rounded_rectangle(
        [box_left, box_top, box_right, box_bottom],
        radius=15,
        fill=(219, 112, 147, 230),  # Rose pink
    )

    # Draw text
    y = y_start
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        x = (size[0] - line_width) // 2

        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_height

    return np.array(img)


def create_highlight_video(
    image_path: str,
    highlights: list[Highlight],
    output_path: str,
    duration_per_highlight: float = 2.5,
    hold_duration: float = 1.5,
) -> str:
    """Create a video highlighting different areas of an image.

    Args:
        image_path: Path to source image
        highlights: List of highlights to show
        output_path: Where to save the video
        duration_per_highlight: Zoom animation duration
        hold_duration: How long to hold on each highlight

    Returns:
        Path to created video
    """
    clips = []

    for i, highlight in enumerate(highlights):
        # Create zoom clip
        zoom_clip = create_highlight_clip(
            image_path,
            highlight,
            duration=duration_per_highlight,
        )

        # Create text callout
        text_overlay = create_text_callout(
            highlight.text,
            position="bottom",
        )
        text_clip = ImageClip(text_overlay).with_duration(duration_per_highlight + hold_duration)

        # Add a hold at the end of each highlight
        if hold_duration > 0:
            # Get the last frame and hold it
            last_frame = zoom_clip.get_frame(duration_per_highlight - 0.01)
            hold_clip = ImageClip(last_frame).with_duration(hold_duration)
            zoom_clip = concatenate_videoclips([zoom_clip, hold_clip])

        # Composite zoom with text
        final_clip = CompositeVideoClip([zoom_clip, text_clip])
        clips.append(final_clip)

    # Concatenate all clips
    final_video = concatenate_videoclips(clips, method="compose")

    # Write video
    final_video.write_videofile(
        output_path,
        fps=30,
        codec='libx264',
        audio=False,
        preset='medium',
        logger=None,
    )

    # Cleanup
    final_video.close()
    for clip in clips:
        clip.close()

    return output_path
