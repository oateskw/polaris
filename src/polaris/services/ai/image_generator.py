"""AI-powered image generation using Replicate Flux 1.1 Pro."""

import io
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
- Keep under 120 words

Return ONLY the image prompt, nothing else."""


IMAGE_STYLE_DEFAULT = """Style: Authentic editorial photography. Real small business owners in genuine environments — warm, sunlit offices, modern co-working spaces, and real storefronts. People who look confident and successful but approachable. Documentary-style warmth. No stock photo stiffness, no forced smiles. Cinematic color grading: warm highlights, slightly desaturated shadows. Professional yet deeply human."""


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
    accent_bar = 5  # orange bar height on top

    if position == "top":
        y_start = 48 + accent_bar + pad_v
    elif position == "bottom":
        y_start = height - total_text_h - pad_v - 60
    else:
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
) -> bytes:
    """Add a branded title + subtitle overlay to a carousel slide.

    Uses a gradient card with Poppins Bold title, Poppins Regular subtitle,
    and an orange left-edge accent bar.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    width, height = img.size

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Auto-scale fonts to image size
    title_size = max(36, int(width * 0.052))
    subtitle_size = max(22, int(width * 0.030))

    title_font = _get_font("bold", title_size)
    subtitle_font = _get_font("regular", subtitle_size)

    max_width = int(width * 0.82)

    title_lines = wrap_text(title, title_font, max_width, draw)
    subtitle_lines = wrap_text(subtitle, subtitle_font, max_width, draw)

    def measure(lines, font):
        hs, ws = [], []
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            ws.append(bbox[2] - bbox[0])
            hs.append(bbox[3] - bbox[1])
        return hs, ws

    t_hs, t_ws = measure(title_lines, title_font)
    s_hs, s_ws = measure(subtitle_lines, subtitle_font)

    t_line_h = max(t_hs) if t_hs else title_size
    s_line_h = max(s_hs) if s_hs else subtitle_size
    t_spacing = int(t_line_h * 0.22)
    s_spacing = int(s_line_h * 0.22)
    title_subtitle_gap = int(title_size * 0.45)
    accent_bar_w = 6

    total_title_h = len(title_lines) * t_line_h + max(0, len(title_lines) - 1) * t_spacing
    total_subtitle_h = len(subtitle_lines) * s_line_h + max(0, len(subtitle_lines) - 1) * s_spacing
    total_text_h = total_title_h + title_subtitle_gap + total_subtitle_h

    pad_v, pad_h = 30, 36
    y_start = 52

    all_ws = t_ws + s_ws
    max_line_w = max(all_ws) if all_ws else 0

    box_x1 = (width - max_line_w) // 2 - pad_h
    box_x2 = (width + max_line_w) // 2 + pad_h
    box_y1 = y_start - pad_v
    box_y2 = y_start + total_text_h + pad_v

    # Gradient background card
    _draw_gradient_rect(
        draw,
        (box_x1, box_y1, box_x2, box_y2),
        BRAND["bg_dark"],
        BRAND["bg_mid"],
        radius=16,
    )

    # Left-edge orange accent bar
    draw.rounded_rectangle(
        [box_x1, box_y1, box_x1 + accent_bar_w, box_y2],
        radius=8,
        fill=BRAND["accent"],
    )

    # Title lines
    y = y_start
    for line in title_lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        lw = bbox[2] - bbox[0]
        x = (width - lw) // 2
        draw.text((x + 2, y + 2), line, font=title_font, fill=BRAND["shadow"])
        draw.text((x, y), line, font=title_font, fill=BRAND["text_white"])
        y += t_line_h + t_spacing

    y += title_subtitle_gap - t_spacing

    # Subtitle lines
    for line in subtitle_lines:
        bbox = draw.textbbox((0, 0), line, font=subtitle_font)
        lw = bbox[2] - bbox[0]
        x = (width - lw) // 2
        draw.text((x + 1, y + 1), line, font=subtitle_font, fill=BRAND["shadow"])
        draw.text((x, y), line, font=subtitle_font, fill=BRAND["text_muted"])
        y += s_line_h + s_spacing

    img = Image.alpha_composite(img, overlay).convert("RGB")
    output = io.BytesIO()
    img.save(output, format="PNG", quality=95)
    return output.getvalue()


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

    def generate_image(
        self,
        topic: str,
        caption_summary: Optional[str] = None,
        output_dir: Optional[Path] = None,
        text_overlay: Optional[str] = None,
        text_position: str = "top",
        style_instructions: Optional[str] = None,
    ) -> GeneratedImage:
        """Generate a high-quality image for the given topic."""
        image_prompt = self.generate_image_prompt(topic, caption_summary, style_instructions)
        image_bytes = self._call_replicate(image_prompt)

        if text_overlay:
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

    def generate_carousel_slide_image(
        self,
        title: str,
        subtitle: str,
        image_prompt: str,
        output_dir: Optional[Path] = None,
        slide_index: int = 0,
    ) -> "GeneratedImage":
        """Generate a carousel slide image with branded title + subtitle overlay."""
        image_bytes = self._call_replicate(image_prompt)
        image_bytes = add_carousel_text_overlay(image_bytes, title, subtitle)

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

    def _call_replicate(self, prompt: str) -> bytes:
        """Call Replicate Flux 1.1 Pro to generate an image."""
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
            "Prefer": "wait",
        }

        payload = {
            "input": {
                "prompt": prompt,
                "aspect_ratio": "1:1",
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
