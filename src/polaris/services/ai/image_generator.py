"""AI-powered image generation using Replicate Flux 1.1 Pro."""

import io
import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
from PIL import Image, ImageDraw, ImageFont

from polaris.config import Settings, get_settings
from polaris.services.ai.claude_client import ClaudeClient


@dataclass
class GeneratedImage:
    """Generated image with metadata."""

    local_path: str
    url: Optional[str]
    prompt: str
    model: str


# ---------------------------------------------------------------------------
# Brand palette
# ---------------------------------------------------------------------------
BRAND = {
    "bg_dark":     (10,  20,  40,  210),   # deep navy, semi-transparent
    "bg_mid":      (20,  40,  80,  180),   # lighter navy for gradient feel
    "accent":      (249, 115, 22,  255),   # vivid orange  #F97316
    "accent_soft": (251, 146, 60,  200),   # softer orange for accents
    "text_white":  (255, 255, 255, 255),
    "text_muted":  (203, 213, 225, 230),   # slate-300
    "shadow":      (0,   0,   0,   160),
}

# ---------------------------------------------------------------------------
# Font management — downloads Poppins Bold/Regular from Google Fonts on demand
# ---------------------------------------------------------------------------
_FONT_DIR = Path(__file__).parent.parent.parent.parent.parent / "fonts"
_FONTS = {
    "bold":    ("Poppins-Bold.ttf",    "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf"),
    "semibold": ("Poppins-SemiBold.ttf", "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-SemiBold.ttf"),
    "regular": ("Poppins-Regular.ttf", "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Regular.ttf"),
}
_WINDOWS_FALLBACKS = [
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
]


def _get_font(variant: str = "bold", size: int = 48) -> ImageFont.FreeTypeFont:
    """Return a Poppins font at the requested size, downloading if needed."""
    _FONT_DIR.mkdir(parents=True, exist_ok=True)
    filename, url = _FONTS.get(variant, _FONTS["bold"])
    font_path = _FONT_DIR / filename

    if not font_path.exists():
        try:
            resp = httpx.get(url, follow_redirects=True, timeout=30)
            resp.raise_for_status()
            font_path.write_bytes(resp.content)
        except Exception:
            # Fall back to Windows system fonts
            for fallback in _WINDOWS_FALLBACKS:
                if Path(fallback).exists():
                    try:
                        return ImageFont.truetype(fallback, size)
                    except (OSError, IOError):
                        continue
            return ImageFont.load_default()

    try:
        return ImageFont.truetype(str(font_path), size)
    except (OSError, IOError):
        return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Image prompt generation
# ---------------------------------------------------------------------------

IMAGE_PROMPT_TEMPLATE = """You are an expert photographer and art director creating prompts for a professional AI image generator.

Create a single, highly detailed image generation prompt for an Instagram post.

Topic: {topic}
Caption summary: {caption_summary}
{style_instructions}

Your prompt must include ALL of these elements:
1. SUBJECT: Who/what is in the scene (specific, not generic — e.g. "a woman in her late 30s at a modern desk" not "a person")
2. ACTION/EMOTION: What they are doing and what emotion is conveyed
3. ENVIRONMENT: The specific setting (e.g. "a warm modern home office with a MacBook, plants, natural light from a large window")
4. LIGHTING: Specific lighting setup (e.g. "soft golden afternoon light from the left, creating gentle shadows")
5. CAMERA: Lens and framing (e.g. "shot on a Sony A7IV with 85mm f/1.8 lens, shallow depth of field, slight bokeh background")
6. MOOD: Overall cinematic tone (e.g. "warm, aspirational, documentary-style")
7. QUALITY TAGS: photorealistic, 8K, ultra-detailed, professional color grading, sharp focus

Critical rules:
- No text, logos, or watermarks in the image
- No robots, holograms, or sci-fi elements
- Real people in real settings that small business owners can instantly relate to
- Authentic, not staged — think editorial magazine photography
- Show the person actively doing the work they love (their craft), not doing admin tasks
- Avoid paperwork, clipboards, spreadsheets, invoices, filing, or stressed "office admin" visuals
- Prioritize positive, cheerful expressions and pride in their work
- Keep under 120 words

Return ONLY the image prompt, nothing else."""


IMAGE_STYLE_DEFAULT = """Style: Authentic editorial photography. Real small business owners in genuine environments — warm, sunlit offices, modern co-working spaces, and real storefronts. People who look confident and successful but approachable. Documentary-style warmth. No stock photo stiffness, no forced smiles. Cinematic color grading: warm highlights, slightly desaturated shadows. Professional yet deeply human."""

PROOFREAD_PROMPT = """Fix any spelling or typo errors in the following text values. Preserve the exact capitalization style, punctuation, line breaks, and tone of each entry. Return ONLY a JSON array of corrected strings in the same order — no explanations, no extra text.

Input:
{json_input}"""


GRAPHIC_STYLE_DEFAULT = """Style: Bright, photorealistic editorial business scene for Instagram Reels.
Visual language: Real workspace environments (pastry kitchen, bakery studio, decorated cake table) with natural daylight and soft depth of field. Keep the scene premium, clean, and believable.
Color palette: Warm neutrals, soft cream highlights, gentle pastels, and subtle orange accents (#F97316). Avoid dark-heavy navy or charcoal dominance.
Aesthetic: Cheerful, optimistic, and polished. Crisp subject detail, clean background separation, bright natural lighting, balanced exposure, and fresh color grading.
Composition: Keep the center and lower-middle simple and uncluttered so UI cards and short text overlays are easy to read. Leave at least top 18% and bottom 22% as cleaner negative space.
Subject direction: show the owner/chef actively creating, decorating, or presenting a beautiful cake with pride. Focus on passion and craft moments.
Do not depict paperwork, inbox stress, filing, or overwhelmed admin scenes.
No text burned into the generated image. No logos. No watermarks. No cartoons or clip art."""


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def _draw_gradient_rect(draw: ImageDraw.Draw, box: tuple[int, int, int, int], color_top: tuple, color_bottom: tuple, radius: int = 16) -> None:
    """Draw a vertical gradient rounded rectangle onto an RGBA draw context.

    Renders the gradient into a temporary surface, masks it with a rounded
    rectangle, then composites it onto the draw target.
    """
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    if w <= 0 or h <= 0:
        return

    # Build gradient on a small RGBA surface the size of the card
    grad = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(grad)
    for row in range(h):
        t = row / max(h - 1, 1)
        r = int(color_top[0] + (color_bottom[0] - color_top[0]) * t)
        g = int(color_top[1] + (color_bottom[1] - color_top[1]) * t)
        b = int(color_top[2] + (color_bottom[2] - color_top[2]) * t)
        a = int(color_top[3] + (color_bottom[3] - color_top[3]) * t)
        grad_draw.line([(0, row), (w, row)], fill=(r, g, b, a))

    # Create a rounded-rect mask (white = keep, black = discard)
    mask = Image.new("L", (w, h), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)

    # Apply mask so corners are transparent
    grad.putalpha(mask)

    # Paste onto the draw target's image — retrieve it via the draw context
    target_img = draw._image  # type: ignore[attr-defined]
    target_img.alpha_composite(grad, dest=(x1, y1))


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.Draw) -> list[str]:
    """Wrap text to fit within max_width."""
    words = text.split()
    lines = []
    current_line: list[str] = []

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

    return lines


def extract_hook(caption: str, max_chars: int = 60) -> str:
    """Extract the first sentence/hook from a caption, capped for text overlays."""
    caption = caption.strip()
    match = re.match(r'^([^.!?]+[.!?])', caption)
    if match:
        hook = match.group(1).strip()
    else:
        hook = caption.split('\n')[0].strip()

    if len(hook) > max_chars:
        truncated = hook[:max_chars].rsplit(' ', 1)[0]
        hook = truncated.rstrip('.,;:') + '...'

    return hook


def add_text_overlay(
    image_bytes: bytes,
    text: str,
    position: str = "top",
    font_size: int = 48,
) -> bytes:
    """Add a branded text overlay to an image.

    Renders a gradient-backed text card with Poppins Bold and an orange accent bar.

    position: "top" | "center" | "bottom" | "lower_third"
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    width, height = img.size

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font = _get_font("bold", font_size)
    max_width = int(width * 0.82)
    lines = wrap_text(text, font, max_width, draw)

    line_heights, line_widths = [], []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])

    line_h = max(line_heights) if line_heights else font_size
    line_spacing = int(line_h * 0.25)
    total_text_h = len(lines) * line_h + (len(lines) - 1) * line_spacing

    pad_v, pad_h = 28, 32
    accent_bar = 5

    if position == "top":
        y_start = 48 + accent_bar + pad_v
    elif position == "bottom":
        y_start = height - total_text_h - pad_v - 60
    elif position == "lower_third":
        y_start = int(height * 0.65) + accent_bar + pad_v
    else:  # center
        y_start = (height - total_text_h) // 2

    max_line_w = max(line_widths) if line_widths else 0
    box_x1 = (width - max_line_w) // 2 - pad_h
    box_x2 = (width + max_line_w) // 2 + pad_h
    box_y1 = y_start - pad_v - accent_bar
    box_y2 = y_start + total_text_h + pad_v

    # Gradient background
    _draw_gradient_rect(
        draw,
        (box_x1, box_y1, box_x2, box_y2),
        BRAND["bg_dark"],
        BRAND["bg_mid"],
        radius=14,
    )

    # Orange accent bar at top of box
    draw.rounded_rectangle(
        [box_x1, box_y1, box_x2, box_y1 + accent_bar + 4],
        radius=6,
        fill=BRAND["accent"],
    )

    # Draw text lines
    y = y_start
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        x = (width - lw) // 2
        draw.text((x + 2, y + 2), line, font=font, fill=BRAND["shadow"])
        draw.text((x, y), line, font=font, fill=BRAND["text_white"])
        y += line_h + line_spacing

    img = Image.alpha_composite(img, overlay).convert("RGB")
    output = io.BytesIO()
    img.save(output, format="PNG", quality=95)
    return output.getvalue()


def add_carousel_text_overlay(
    image_bytes: bytes,
    title: str,
    subtitle: str,
    bullets: Optional[list] = None,
) -> bytes:
    """Add a branded title + subtitle + bullet overlay to a carousel slide.

    Positioned in the lower portion of the image with a very transparent (10%)
    dark navy background so the photo shows through. Smaller fonts and an
    orange left-edge accent bar. Bullet points use an orange dot prefix.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    width, height = img.size

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    bullets = bullets or []

    # Smaller fonts — title ~3.5% of width, subtitle/bullets ~2.2%
    title_size   = max(26, int(width * 0.035))
    subtitle_size = max(18, int(width * 0.022))
    bullet_size  = max(17, int(width * 0.021))

    title_font   = _get_font("bold",    title_size)
    subtitle_font = _get_font("semibold", subtitle_size)
    bullet_font  = _get_font("regular", bullet_size)

    max_text_w = int(width * 0.84)

    title_lines    = wrap_text(title,    title_font,    max_text_w, draw)
    subtitle_lines = wrap_text(subtitle, subtitle_font, max_text_w, draw)

    def line_height(font, size):
        bbox = draw.textbbox((0, 0), "Ag", font=font)
        return bbox[3] - bbox[1]

    t_lh = line_height(title_font,    title_size)
    s_lh = line_height(subtitle_font, subtitle_size)
    b_lh = line_height(bullet_font,   bullet_size)

    t_spacing = int(t_lh * 0.20)
    s_spacing = int(s_lh * 0.18)
    b_spacing = int(b_lh * 0.22)

    gap_ts = int(title_size * 0.35)   # gap between title block and subtitle
    gap_sb = int(title_size * 0.30)   # gap between subtitle and bullets

    total_title_h    = len(title_lines)    * t_lh + max(0, len(title_lines)    - 1) * t_spacing
    total_subtitle_h = len(subtitle_lines) * s_lh + max(0, len(subtitle_lines) - 1) * s_spacing
    total_bullets_h  = len(bullets)        * b_lh + max(0, len(bullets)        - 1) * b_spacing

    total_h = total_title_h
    if subtitle_lines:
        total_h += gap_ts + total_subtitle_h
    if bullets:
        total_h += gap_sb + total_bullets_h

    pad_v, pad_h = 28, 40
    accent_bar_w = 5
    dot_r = max(4, int(bullet_size * 0.28))

    # Position the card in the lower portion of the image
    card_bottom = height - int(height * 0.04)
    card_top    = card_bottom - total_h - pad_v * 2
    box_x1 = int(width * 0.05)
    box_x2 = int(width * 0.95)
    box_y1 = card_top
    box_y2 = card_bottom

    # 10% opacity dark navy background (alpha = 26 out of 255)
    card_img = Image.new("RGBA", (box_x2 - box_x1, box_y2 - box_y1), (0, 0, 0, 0))
    card_draw = ImageDraw.Draw(card_img)
    card_draw.rounded_rectangle(
        [0, 0, box_x2 - box_x1 - 1, box_y2 - box_y1 - 1],
        radius=14,
        fill=(10, 20, 40, 160),  # ~63% opacity
    )
    overlay.alpha_composite(card_img, dest=(box_x1, box_y1))

    draw = ImageDraw.Draw(overlay)

    # Orange left-edge accent bar
    draw.rounded_rectangle(
        [box_x1, box_y1, box_x1 + accent_bar_w, box_y2],
        radius=6,
        fill=BRAND["accent"],
    )

    # Helper: draw text with a soft shadow for readability against bright images
    def draw_shadowed(txt, x, y, font, color):
        for dx, dy in ((2, 2), (1, 1)):
            draw.text((x + dx, y + dy), txt, font=font, fill=(0, 0, 0, 180))
        draw.text((x, y), txt, font=font, fill=color)

    text_x = box_x1 + accent_bar_w + pad_h
    y = box_y1 + pad_v

    # Title
    for line in title_lines:
        draw_shadowed(line, text_x, y, title_font, BRAND["text_white"])
        y += t_lh + t_spacing

    # Subtitle
    if subtitle_lines:
        y += gap_ts - t_spacing
        for line in subtitle_lines:
            draw_shadowed(line, text_x, y, subtitle_font, BRAND["text_muted"])
            y += s_lh + s_spacing

    # Bullet points
    if bullets:
        y += gap_sb - s_spacing
        for bullet in bullets[:5]:
            # Orange dot
            dot_x = text_x
            dot_y = y + (b_lh - dot_r * 2) // 2
            draw.ellipse(
                [dot_x, dot_y, dot_x + dot_r * 2, dot_y + dot_r * 2],
                fill=BRAND["accent"],
            )
            # Bullet text
            bullet_x = dot_x + dot_r * 2 + int(dot_r * 1.6)
            draw_shadowed(bullet, bullet_x, y, bullet_font, BRAND["text_white"])
            y += b_lh + b_spacing

    img = Image.alpha_composite(img, overlay).convert("RGB")
    output = io.BytesIO()
    img.save(output, format="PNG", quality=95)
    return output.getvalue()


# ---------------------------------------------------------------------------
# Integrated reel slide compositor
# ---------------------------------------------------------------------------

def create_integrated_slide(
    image_path: str,
    headline: str,
    subtitle: str,
    bullets: list[str],
    output_path: str,
    size: tuple = (1080, 1920),
) -> str:
    """Composite a graphic image with headline + bullets into a single reel slide.

    Layout (strict zones, no text/image overlap):
      [Instagram safe gap 160px]
      [Headline + subtitle — measured precisely including subtitle wrapping]
      [Orange divider]
      [Image window — 640px tall, fills full width]
      [Orange divider]
      [Bullets — font auto-sized to fill available space to bottom]
      [Brand mark]
    """
    W, H = size
    PAD_X       = 72
    DIVIDER_T   = 6
    BRAND_H     = 70   # space reserved at very bottom for brand mark
    IMAGE_H     = 640

    # --- Fonts for measurement ---
    h_font = _get_font("bold", 60)
    s_font = _get_font("regular", 32)

    # Use a full-size canvas for accurate text measurement
    measure_img  = Image.new("RGB", (W, H), (0, 0, 0))
    measure_draw = ImageDraw.Draw(measure_img)

    # Headline: user-specified line breaks via \n
    h_lines  = headline.upper().split("\n")
    h_line_h = max(
        measure_draw.textbbox((0, 0), l, font=h_font)[3] - measure_draw.textbbox((0, 0), l, font=h_font)[1]
        for l in h_lines
    )
    headline_h = len(h_lines) * h_line_h + max(0, len(h_lines) - 1) * 12

    # Subtitle: measure with wrapping so tall subtitles don't bleed into image zone
    sub_lines  = wrap_text(subtitle, s_font, W - PAD_X * 2, measure_draw)
    sub_line_h = measure_draw.textbbox((0, 0), "Ag", font=s_font)[3] - measure_draw.textbbox((0, 0), "Ag", font=s_font)[1]
    subtitle_h = len(sub_lines) * sub_line_h + max(0, len(sub_lines) - 1) * 6

    # --- Zone boundaries ---
    HEADLINE_TOP  = 175                                          # clears Instagram account bar
    ACCENT_Y      = HEADLINE_TOP - 18
    TOP_ZONE_END  = HEADLINE_TOP + headline_h + 14 + subtitle_h + 28
    IMAGE_TOP     = TOP_ZONE_END + DIVIDER_T + 20
    IMAGE_BOT     = IMAGE_TOP + IMAGE_H
    DIVIDER2_Y    = IMAGE_BOT + 20
    BULLETS_TOP   = DIVIDER2_Y + DIVIDER_T + 24
    BULLETS_BOT   = H - BRAND_H                                 # bullets fill down to brand mark

    # --- Auto-size bullet font to fill available space ---
    available_h  = BULLETS_BOT - BULLETS_TOP
    DOT_R        = 8
    bullet_x_max = W - PAD_X * 2 - DOT_R * 2 - 18
    active_bullets = bullets[:2]

    b_size = 34
    while b_size <= 52:
        b_font = _get_font("semibold", b_size)
        b_lh   = measure_draw.textbbox((0, 0), "Ag", font=b_font)[3] - measure_draw.textbbox((0, 0), "Ag", font=b_font)[1]
        total  = 0
        for b in active_bullets:
            n_lines = len(wrap_text(b, b_font, bullet_x_max, measure_draw))
            total  += n_lines * b_lh + (n_lines - 1) * 7 + 22   # line spacing + gap between bullets
        if total > available_h:
            b_size -= 2
            break
        b_size += 2
    b_font = _get_font("semibold", b_size)
    b_lh   = measure_draw.textbbox((0, 0), "Ag", font=b_font)[3] - measure_draw.textbbox((0, 0), "Ag", font=b_font)[1]
    DOT_R  = max(6, int(b_size * 0.22))

    # --- Canvas ---
    canvas = Image.new("RGB", (W, H), (10, 20, 40))

    # Paste graphic into image zone (scale to cover W × IMAGE_H, center-crop)
    graphic = Image.open(image_path).convert("RGB")
    gw, gh  = graphic.size
    scale   = max(W / gw, IMAGE_H / gh)
    new_gw, new_gh = int(gw * scale), int(gh * scale)
    graphic_scaled = graphic.resize((new_gw, new_gh), Image.LANCZOS)
    cx = (new_gw - W) // 2
    cy = (new_gh - IMAGE_H) // 2
    canvas.paste(graphic_scaled.crop((cx, cy, cx + W, cy + IMAGE_H)), (0, IMAGE_TOP))

    draw = ImageDraw.Draw(canvas)

    # Orange accent bar above headline
    draw.rounded_rectangle([PAD_X, ACCENT_Y, PAD_X + 44, ACCENT_Y + 5], radius=2, fill=BRAND["accent"])

    # Headline
    text_y = HEADLINE_TOP
    for line in h_lines:
        draw.text((PAD_X + 2, text_y + 2), line, font=h_font, fill=BRAND["shadow"])
        draw.text((PAD_X, text_y), line, font=h_font, fill=BRAND["text_white"])
        text_y += h_line_h + 12

    # Subtitle (wrapped)
    text_y += 2
    for line in sub_lines:
        draw.text((PAD_X, text_y), line, font=s_font, fill=BRAND["accent"])
        text_y += sub_line_h + 6

    # Dividers
    draw.rounded_rectangle([PAD_X, TOP_ZONE_END, W - PAD_X, TOP_ZONE_END + DIVIDER_T], radius=2, fill=BRAND["accent"])
    draw.rounded_rectangle([PAD_X, DIVIDER2_Y,   W - PAD_X, DIVIDER2_Y   + DIVIDER_T], radius=2, fill=BRAND["accent"])

    # Bullets
    text_y = BULLETS_TOP
    for bullet in active_bullets:
        dot_y_pos = text_y + (b_lh - DOT_R * 2) // 2
        draw.ellipse([PAD_X, dot_y_pos, PAD_X + DOT_R * 2, dot_y_pos + DOT_R * 2], fill=BRAND["accent"])
        b_lines = wrap_text(bullet, b_font, bullet_x_max, draw)
        bx = PAD_X + DOT_R * 2 + 18
        for line in b_lines:
            draw.text((bx + 1, text_y + 1), line, font=b_font, fill=BRAND["shadow"])
            draw.text((bx, text_y), line, font=b_font, fill=BRAND["text_white"])
            text_y += b_lh + 7
        text_y += 22

    # Brand mark
    br_font    = _get_font("bold", 24)
    brand_text = "POLARIS INNOVATIONS"
    bbox       = draw.textbbox((0, 0), brand_text, font=br_font)
    bw         = bbox[2] - bbox[0]
    dot_bx     = (W - bw - 20) // 2
    draw.ellipse([dot_bx, H - 54, dot_bx + 12, H - 42], fill=BRAND["accent"])
    draw.text(((W - bw) // 2 + 2, H - 58), brand_text, font=br_font, fill=BRAND["text_muted"])

    canvas.save(output_path, "PNG")
    return output_path


# ---------------------------------------------------------------------------
# Reel slide compositor
# ---------------------------------------------------------------------------

def create_reel_slide(
    image_path: str,
    headline: str,
    subtitle: str,
    bullets: list[str],
    output_path: str,
    size: tuple = (1080, 1920),
) -> str:
    """Composite a graphic image into a reel slide with flowing text overlays.

    The graphic fills the full canvas. Soft gradients sit behind the top
    (headline + subtitle) and bottom (bullets) text zones — fading to
    transparent in the center so the diagram shows through clearly.
    Text is placed in the natural margins of the image, not over key objects.

    Args:
        image_path: Source graphic image (any aspect ratio).
        headline: Bold headline; use \\n to force line breaks.
        subtitle: One supporting line shown below the headline.
        bullets: 3–4 bullet strings rendered at the bottom.
        output_path: Where to save the composited PNG.
        size: Output (width, height). Default 1080x1920 for Reels.

    Returns:
        The output_path string.
    """
    W, H = size
    PAD_X = 72

    h_font = _get_font("bold", 54)
    s_font = _get_font("semibold", 32)

    measure_img  = Image.new("RGB", (W, H))
    measure_draw = ImageDraw.Draw(measure_img)
    max_text_w   = W - PAD_X * 2

    # Measure headline
    h_lines = headline.upper().split("\n")
    h_lh    = measure_draw.textbbox((0, 0), "Ag", font=h_font)[3] - measure_draw.textbbox((0, 0), "Ag", font=h_font)[1]
    h_total = len(h_lines) * h_lh + max(0, len(h_lines) - 1) * 12

    # Measure subtitle (with wrapping)
    sub_lines = wrap_text(subtitle, s_font, max_text_w, measure_draw) if subtitle else []
    s_lh      = measure_draw.textbbox((0, 0), "Ag", font=s_font)[3] - measure_draw.textbbox((0, 0), "Ag", font=s_font)[1]
    sub_total = len(sub_lines) * s_lh + max(0, len(sub_lines) - 1) * 6

    # Auto-size bullet font to fill bottom zone (y=1320 → y=H-70)
    BULLETS_TOP = 1320
    BRAND_H     = 70
    available_h = H - BRAND_H - BULLETS_TOP
    DOT_R       = 7
    bullet_x_max = max_text_w - DOT_R * 2 - 18
    active_bullets = bullets[:2]

    b_size = 30
    while b_size <= 46:
        b_font = _get_font("semibold", b_size)
        b_lh   = measure_draw.textbbox((0, 0), "Ag", font=b_font)[3] - measure_draw.textbbox((0, 0), "Ag", font=b_font)[1]
        total  = sum(
            len(wrap_text(b, b_font, bullet_x_max, measure_draw)) * b_lh + 20
            for b in active_bullets
        )
        if total > available_h:
            b_size -= 2
            break
        b_size += 2
    b_font = _get_font("semibold", b_size)
    b_lh   = measure_draw.textbbox((0, 0), "Ag", font=b_font)[3] - measure_draw.textbbox((0, 0), "Ag", font=b_font)[1]
    DOT_R  = max(5, int(b_size * 0.22))

    # --- Canvas: fill with graphic ---
    canvas  = Image.new("RGB", (W, H), (10, 20, 40))
    graphic = Image.open(image_path).convert("RGB")
    gw, gh  = graphic.size
    scale   = max(W / gw, H / gh)
    new_gw, new_gh = int(gw * scale), int(gh * scale)
    graphic_scaled = graphic.resize((new_gw, new_gh), Image.LANCZOS)
    cx = (new_gw - W) // 2
    cy = (new_gh - H) // 2
    canvas.paste(graphic_scaled.crop((cx, cy, cx + W, cy + H)), (0, 0))

    # Soft gradient overlay — keep readability while preserving brighter imagery
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov_draw  = ImageDraw.Draw(overlay)

    TOP_DARK_END   = 175 + h_total + (16 + sub_total if sub_lines else 0) + 52
    TOP_FADE_END   = TOP_DARK_END + 160   # gradient fades out over 160px
    BOT_FADE_START = BULLETS_TOP - 160    # gradient fades in 160px before bullets
    BOT_DARK_START = BULLETS_TOP - 20

    for y in range(H):
        if y <= TOP_DARK_END:
            alpha = 95
        elif y <= TOP_FADE_END:
            t     = (y - TOP_DARK_END) / 160
            smooth = t * t * (3 - 2 * t)
            alpha = int(95 * (1 - smooth))
        elif y < BOT_FADE_START:
            alpha = 0
        elif y < BOT_DARK_START:
            t     = (y - BOT_FADE_START) / (BOT_DARK_START - BOT_FADE_START)
            smooth = t * t * (3 - 2 * t)
            alpha = int(95 * smooth)
        else:
            alpha = 95
        if alpha > 0:
            ov_draw.line([(0, y), (W, y)], fill=(10, 20, 40, alpha))

    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    draw   = ImageDraw.Draw(canvas)

    # --- Top: orange accent bar + headline + subtitle ---
    HEADLINE_TOP = 175
    draw.rounded_rectangle([PAD_X, HEADLINE_TOP - 16, PAD_X + 44, HEADLINE_TOP - 11], radius=2, fill=BRAND["accent"])

    y = HEADLINE_TOP
    for line in h_lines:
        draw.text((PAD_X + 2, y + 2), line, font=h_font, fill=BRAND["shadow"])
        draw.text((PAD_X, y), line, font=h_font, fill=BRAND["text_white"])
        y += h_lh + 12

    if sub_lines:
        y += 4
        for line in sub_lines:
            # Keep orange subtitle readable over bright backgrounds.
            draw.text((PAD_X, y), line, font=s_font, fill=BRAND["accent"], stroke_width=2, stroke_fill=BRAND["shadow"])
            y += s_lh + 6

    # --- Bottom: bullets ---
    y = BULLETS_TOP
    for bullet in active_bullets:
        is_cta = bool(re.match(r"^DM\s+us\s+the\s+word\s+\w+\s+right\s+now\.?$", bullet.strip(), flags=re.IGNORECASE))
        dot_y = y + (b_lh - DOT_R * 2) // 2
        draw.ellipse([PAD_X, dot_y, PAD_X + DOT_R * 2, dot_y + DOT_R * 2], fill=BRAND["accent"])
        bx      = PAD_X + DOT_R * 2 + 18
        line_font = _get_font("bold", min(b_size + 10, 56)) if is_cta else b_font
        line_h = draw.textbbox((0, 0), "Ag", font=line_font)[3] - draw.textbbox((0, 0), "Ag", font=line_font)[1]
        b_lines = wrap_text(bullet, line_font, bullet_x_max, draw)
        for line in b_lines:
            draw.text((bx + 1, y + 1), line, font=line_font, fill=BRAND["shadow"])
            if is_cta:
                draw.text((bx, y), line, font=line_font, fill=BRAND["accent"], stroke_width=2, stroke_fill=BRAND["shadow"])
            else:
                draw.text((bx, y), line, font=line_font, fill=BRAND["text_white"])
            y += line_h + 7
        y += 22 if is_cta else 20

    # --- Brand mark ---
    br_font    = _get_font("bold", 24)
    brand_text = "POLARIS INNOVATIONS"
    bbox       = draw.textbbox((0, 0), brand_text, font=br_font)
    bw         = bbox[2] - bbox[0]
    dot_bx     = (W - bw - 20) // 2
    draw.ellipse([dot_bx, H - 56, dot_bx + 12, H - 44], fill=BRAND["accent"])
    draw.text(((W - bw) // 2 + 2, H - 60), brand_text, font=br_font, fill=BRAND["text_muted"])

    canvas.save(output_path, "PNG")
    return output_path


# ---------------------------------------------------------------------------
# Story slide compositor
# ---------------------------------------------------------------------------

def create_story_slide(
    image_path: str,
    headline: str,
    body: str,
    output_path: str,
    size: tuple = (1080, 1920),
) -> str:
    """Composite a graphic image with headline + body for an Instagram Story.

    The graphic fills the full canvas. Text flows naturally from the top of the
    image downward — headline then body — with a dark gradient behind the text
    block for readability. The rest of the image shows through unobstructed.

    Args:
        image_path: Source graphic image (any aspect ratio).
        headline: Short bold headline. Long headlines are wrapped automatically.
        body: Body text — 1-3 sentences. Wrapped automatically to fit.
        output_path: Where to save the composited PNG.
        size: Output (width, height). Default 1080x1920 for Stories.

    Returns:
        The output_path string.
    """
    W, H = size
    PAD_X = 80

    h_font = _get_font("bold", 54)
    b_font = _get_font("regular", 36)

    # Measure text using a full-size canvas
    measure_img  = Image.new("RGB", (W, H))
    measure_draw = ImageDraw.Draw(measure_img)

    max_text_w = W - PAD_X * 2

    h_lines  = wrap_text(headline, h_font, max_text_w, measure_draw)
    h_lh     = measure_draw.textbbox((0, 0), "Ag", font=h_font)[3] - measure_draw.textbbox((0, 0), "Ag", font=h_font)[1]
    h_total  = len(h_lines) * h_lh + max(0, len(h_lines) - 1) * 10

    b_lines  = wrap_text(body, b_font, max_text_w, measure_draw) if body else []
    b_lh     = measure_draw.textbbox((0, 0), "Ag", font=b_font)[3] - measure_draw.textbbox((0, 0), "Ag", font=b_font)[1]
    b_total  = len(b_lines) * b_lh + max(0, len(b_lines) - 1) * 8

    # Layout: bottom-anchored — text sits above the brand mark, graphic fully visible above
    BRAND_H      = 70
    GAP_HB       = 22   # gap between headline and body
    ACCENT_H     = 5
    text_block_h = h_total + (GAP_HB + b_total if b_lines else 0)
    TEXT_BOT     = H - BRAND_H - 28          # bottom of text block (28px pad above brand)
    TEXT_TOP     = TEXT_BOT - text_block_h   # top of headline
    ACCENT_Y     = TEXT_TOP - ACCENT_H - 10  # accent bar just above headline
    OVERLAY_TOP  = ACCENT_Y - 28             # where gradient starts to darken

    # --- Canvas: fill with graphic ---
    canvas = Image.new("RGB", (W, H), (10, 20, 40))
    graphic = Image.open(image_path).convert("RGB")
    gw, gh  = graphic.size
    scale   = max(W / gw, H / gh)
    new_gw, new_gh = int(gw * scale), int(gh * scale)
    graphic_scaled = graphic.resize((new_gw, new_gh), Image.LANCZOS)
    cx = (new_gw - W) // 2
    cy = (new_gh - H) // 2
    canvas.paste(graphic_scaled.crop((cx, cy, cx + W, cy + H)), (0, 0))

    # Dark gradient covering only the bottom text zone, fading in from above
    overlay  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov_draw  = ImageDraw.Draw(overlay)
    FADE_START = max(0, OVERLAY_TOP - 160)
    for y in range(FADE_START, H):
        if y < OVERLAY_TOP:
            t      = (y - FADE_START) / (OVERLAY_TOP - FADE_START)
            smooth = t * t * (3 - 2 * t)
            alpha  = int(190 * smooth)
        else:
            alpha = 190
        if alpha > 0:
            ov_draw.line([(0, y), (W, y)], fill=(10, 20, 40, alpha))

    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    draw   = ImageDraw.Draw(canvas)

    # Orange accent bar above headline
    draw.rounded_rectangle([PAD_X, ACCENT_Y, PAD_X + 44, ACCENT_Y + ACCENT_H], radius=2, fill=BRAND["accent"])

    # Headline
    y = TEXT_TOP
    for line in h_lines:
        draw.text((PAD_X + 2, y + 2), line, font=h_font, fill=BRAND["shadow"])
        draw.text((PAD_X, y), line, font=h_font, fill=BRAND["text_white"])
        y += h_lh + 10

    # Body
    if b_lines:
        y += GAP_HB - 10
        for line in b_lines:
            draw.text((PAD_X, y), line, font=b_font, fill=BRAND["text_muted"])
            y += b_lh + 8

    # Brand mark — bottom of canvas
    br_font    = _get_font("bold", 24)
    brand_text = "POLARIS INNOVATIONS"
    bbox       = draw.textbbox((0, 0), brand_text, font=br_font)
    bw         = bbox[2] - bbox[0]
    dot_bx     = (W - bw - 20) // 2
    draw.ellipse([dot_bx, H - 56, dot_bx + 12, H - 44], fill=BRAND["accent"])
    draw.text(((W - bw) // 2 + 2, H - 60), brand_text, font=br_font, fill=BRAND["text_muted"])

    canvas.save(output_path, "PNG")
    return output_path


# ---------------------------------------------------------------------------
# Image generator
# ---------------------------------------------------------------------------

class ImageGenerator:
    """Generate images using Replicate Flux 1.1 Pro."""

    # Flux 1.1 Pro — best-in-class photorealism on Replicate
    REPLICATE_MODEL = "black-forest-labs/flux-1.1-pro"

    def __init__(
        self,
        claude_client: Optional[ClaudeClient] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        self.claude_client = claude_client or ClaudeClient()
        self._http_client = httpx.Client(timeout=300.0)

        if not self.settings.is_replicate_configured:
            raise ValueError(
                "Replicate API key not configured. "
                "Set REPLICATE_API_KEY in your .env file.\n"
                "Get a key at: https://replicate.com/account/api-tokens"
            )
        self.api_key = self.settings.replicate_api_key

    def generate_image_prompt(
        self,
        topic: str,
        caption_summary: Optional[str] = None,
        style_instructions: Optional[str] = None,
    ) -> str:
        """Use Claude to generate a rich cinematic image prompt."""
        style = style_instructions or IMAGE_STYLE_DEFAULT
        prompt = IMAGE_PROMPT_TEMPLATE.format(
            topic=topic,
            caption_summary=caption_summary or topic,
            style_instructions=f"Style guidance: {style}",
        )

        return self.claude_client.generate(
            prompt=prompt,
            temperature=0.75,
            max_tokens=300,
        ).strip()

    def proofread(self, *texts: str) -> list[str]:
        """Use Claude to fix spelling/typos in one or more text strings.

        Returns the corrected strings in the same order. Falls back to the
        originals unchanged if parsing fails.
        """
        non_empty = [t for t in texts if t and t.strip()]
        if not non_empty:
            return list(texts)

        prompt = PROOFREAD_PROMPT.format(
            json_input=json.dumps(list(texts), ensure_ascii=False)
        )
        result = self.claude_client.generate(prompt=prompt, temperature=0, max_tokens=800)

        match = re.search(r'\[.*\]', result, re.DOTALL)
        if match:
            try:
                corrected = json.loads(match.group(0))
                if isinstance(corrected, list) and len(corrected) == len(texts):
                    return [str(c) for c in corrected]
            except json.JSONDecodeError:
                pass

        return list(texts)  # fallback: originals unchanged

    def generate_image(
        self,
        topic: str,
        caption_summary: Optional[str] = None,
        output_dir: Optional[Path] = None,
        text_overlay: Optional[str] = None,
        text_position: str = "top",
        style_instructions: Optional[str] = None,
        aspect_ratio: str = "1:1",
    ) -> GeneratedImage:
        """Generate a high-quality image for the given topic."""
        image_prompt = self.generate_image_prompt(topic, caption_summary, style_instructions)
        image_bytes = self._call_replicate(image_prompt, aspect_ratio=aspect_ratio)

        if text_overlay:
            text_overlay, = self.proofread(text_overlay)
            image_bytes = add_text_overlay(image_bytes, text_overlay, position=text_position)

        if output_dir is None:
            output_dir = Path.cwd() / "images"
        output_dir.mkdir(parents=True, exist_ok=True)

        safe_topic = re.sub(r'[^\w\s-]', '', topic)[:30].strip().replace(' ', '_')
        timestamp = int(time.time())
        filename = f"{safe_topic}_{timestamp}.png"
        local_path = output_dir / filename
        local_path.write_bytes(image_bytes)

        return GeneratedImage(
            local_path=str(local_path),
            url=None,
            prompt=image_prompt,
            model=self.REPLICATE_MODEL,
        )

    def generate_story_image(
        self,
        topic: str,
        caption_summary: Optional[str] = None,
        output_dir: Optional[Path] = None,
        text_overlay: Optional[str] = None,
        style_instructions: Optional[str] = None,
    ) -> GeneratedImage:
        """Generate a 9:16 vertical image optimised for Instagram Stories.

        Uses Flux 1.1 Pro's native 9:16 output and places the text overlay
        in the lower-third of the frame so the subject has visual breathing
        room above it.
        """
        story_style = (style_instructions or "") + (
            " Vertical 9:16 composition. Subject centred in the upper two-thirds "
            "of the frame, leaving clear negative space in the lower third for text. "
            "Portrait orientation, cinematic vertical framing."
        )
        image_prompt = self.generate_image_prompt(topic, caption_summary, story_style)
        image_bytes = self._call_replicate(image_prompt, aspect_ratio="9:16")

        if text_overlay:
            text_overlay, = self.proofread(text_overlay)
            image_bytes = add_text_overlay(
                image_bytes,
                text_overlay,
                position="lower_third",
                font_size=62,
            )

        if output_dir is None:
            output_dir = Path.cwd() / "images"
        output_dir.mkdir(parents=True, exist_ok=True)

        safe_topic = re.sub(r'[^\w\s-]', '', topic)[:30].strip().replace(' ', '_')
        timestamp = int(time.time())
        filename = f"story_{safe_topic}_{timestamp}.png"
        local_path = output_dir / filename
        local_path.write_bytes(image_bytes)

        return GeneratedImage(
            local_path=str(local_path),
            url=None,
            prompt=image_prompt,
            model=self.REPLICATE_MODEL,
        )

    def generate_carousel_slide_image(
        self,
        title: str,
        subtitle: str,
        image_prompt: str,
        output_dir: Optional[Path] = None,
        slide_index: int = 0,
        bullets: Optional[list] = None,
    ) -> "GeneratedImage":
        """Generate a carousel slide image with branded title + subtitle + bullets overlay."""
        bullets = bullets or []
        all_texts = [title, subtitle] + bullets
        proofed = self.proofread(*all_texts)
        title, subtitle = proofed[0], proofed[1]
        bullets = proofed[2:] if len(proofed) > 2 else bullets

        image_bytes = self._call_replicate(image_prompt)
        image_bytes = add_carousel_text_overlay(image_bytes, title, subtitle, bullets=bullets)

        if output_dir is None:
            output_dir = Path.cwd() / "images"
        output_dir.mkdir(parents=True, exist_ok=True)

        safe_title = re.sub(r'[^\w\s-]', '', title)[:25].strip().replace(' ', '_')
        timestamp = int(time.time())
        filename = f"carousel_slide{slide_index}_{safe_title}_{timestamp}.png"
        local_path = output_dir / filename
        local_path.write_bytes(image_bytes)

        return GeneratedImage(
            local_path=str(local_path),
            url=None,
            prompt=image_prompt,
            model=self.REPLICATE_MODEL,
        )

    def _call_replicate(self, prompt: str, aspect_ratio: str = "1:1") -> bytes:
        """Call Replicate Flux 1.1 Pro to generate an image."""
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
            "Prefer": "wait",
        }

        payload = {
            "input": {
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "output_format": "png",
                "output_quality": 100,
                "safety_tolerance": 3,
                "prompt_upsampling": True,
            },
        }

        # Flux 1.1 Pro uses the model-specific predictions endpoint
        url = f"https://api.replicate.com/v1/models/{self.REPLICATE_MODEL}/predictions"

        response = self._http_client.post(url, headers=headers, json=payload)

        if response.status_code == 402:
            raise Exception(
                "Replicate requires billing setup.\n"
                "Add a payment method at: https://replicate.com/account/billing"
            )

        if response.status_code == 429:
            retry_after = int(response.headers.get("retry-after", 60))
            time.sleep(retry_after)
            response = self._http_client.post(url, headers=headers, json=payload)

        response.raise_for_status()
        prediction = response.json()

        # Poll for completion
        prediction_url = prediction["urls"]["get"]
        while True:
            poll = self._http_client.get(prediction_url, headers=headers)
            poll.raise_for_status()
            result = poll.json()

            status = result["status"]
            if status == "succeeded":
                output = result["output"]
                image_url = output[0] if isinstance(output, list) else output
                img_response = self._http_client.get(image_url)
                img_response.raise_for_status()
                return img_response.content
            elif status == "failed":
                raise Exception(f"Image generation failed: {result.get('error', 'Unknown error')}")
            elif status in ("starting", "processing"):
                time.sleep(2)
            else:
                raise Exception(f"Unexpected status: {status}")

    def close(self) -> None:
        """Close HTTP client."""
        self._http_client.close()


def upload_to_github(
    local_path: Path,
    repo: str,
    branch: str = "main",
    remote_path: Optional[str] = None,
) -> str:
    """Upload a file to GitHub and return the raw URL."""
    filename = Path(local_path).name
    if remote_path is None:
        remote_path = f"images/{filename}"

    repo_root = Path.cwd()
    target_path = repo_root / remote_path
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if str(local_path) != str(target_path):
        import shutil
        shutil.copy2(local_path, target_path)

    subprocess.run(["git", "add", remote_path], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"Add generated image: {filename}"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "push"], cwd=repo_root, check=True, capture_output=True)

    return f"https://raw.githubusercontent.com/{repo}/{branch}/{remote_path}"
