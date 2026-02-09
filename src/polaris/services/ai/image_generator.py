"""AI-powered image generation using Replicate."""

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


IMAGE_PROMPT_TEMPLATE = """Create a concise image generation prompt for an Instagram post about the following topic.

Topic: {topic}
Caption summary: {caption_summary}

Requirements:
- The image should be visually striking and professional
- Suitable for a tech/software brand called "Polaris Innovations"
- Modern, clean aesthetic with blues, purples, or tech-inspired colors
- No text in the image (text will be added separately)
- High-quality digital art or 3D render style
- Good for Instagram square format (1:1 aspect ratio)
- Leave some space at the top or center for text overlay

Return ONLY the image prompt, nothing else. Keep it under 100 words."""


def extract_hook(caption: str) -> str:
    """Extract the first sentence/hook from a caption."""
    # Remove any leading whitespace or newlines
    caption = caption.strip()

    # Try to find the first sentence ending with ? ! or .
    match = re.match(r'^([^.!?]+[.!?])', caption)
    if match:
        hook = match.group(1).strip()
        # If hook is too long, truncate at a reasonable point
        if len(hook) > 80:
            # Try to break at a natural point
            words = hook.split()
            truncated = []
            length = 0
            for word in words:
                if length + len(word) + 1 > 75:
                    break
                truncated.append(word)
                length += len(word) + 1
            hook = ' '.join(truncated) + '...'
        return hook

    # Fallback: take first 60 chars
    if len(caption) > 60:
        return caption[:57] + '...'
    return caption


def add_text_overlay(
    image_bytes: bytes,
    text: str,
    position: str = "top",
    font_size: int = 48,
) -> bytes:
    """Add text overlay to an image.

    Args:
        image_bytes: Raw image bytes
        text: Text to overlay
        position: Where to place text ("top", "center", "bottom")
        font_size: Base font size (will auto-adjust)

    Returns:
        Modified image as bytes
    """
    # Open image
    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert("RGBA")
    width, height = img.size

    # Create overlay layer for semi-transparent background
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Try to load a nice font, fall back to default
    font = None
    font_paths = [
        "C:/Windows/Fonts/arialbd.ttf",  # Windows Arial Bold
        "C:/Windows/Fonts/segoeui.ttf",  # Windows Segoe UI
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
        "/System/Library/Fonts/Helvetica.ttc",  # macOS
    ]

    for font_path in font_paths:
        try:
            font = ImageFont.truetype(font_path, font_size)
            break
        except (OSError, IOError):
            continue

    if font is None:
        font = ImageFont.load_default()
        font_size = 20  # Default font is smaller

    # Word wrap the text
    max_width = int(width * 0.85)  # 85% of image width
    lines = wrap_text(text, font, max_width, draw)

    # Calculate text block dimensions
    line_heights = []
    line_widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])

    line_height = max(line_heights) if line_heights else font_size
    line_spacing = int(line_height * 0.3)
    total_text_height = len(lines) * line_height + (len(lines) - 1) * line_spacing

    # Determine Y position based on position parameter
    padding = 40
    if position == "top":
        y_start = padding + 20
    elif position == "bottom":
        y_start = height - total_text_height - padding - 40
    else:  # center
        y_start = (height - total_text_height) // 2

    # Draw semi-transparent background box
    box_padding = 25
    box_top = y_start - box_padding
    box_bottom = y_start + total_text_height + box_padding
    max_line_width = max(line_widths) if line_widths else 0
    box_left = (width - max_line_width) // 2 - box_padding
    box_right = (width + max_line_width) // 2 + box_padding

    # Draw rounded rectangle background
    draw.rounded_rectangle(
        [box_left, box_top, box_right, box_bottom],
        radius=15,
        fill=(0, 0, 0, 180),  # Semi-transparent black
    )

    # Draw text lines (centered)
    y = y_start
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        x = (width - line_width) // 2

        # Draw text with slight shadow for depth
        draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, 150))  # Shadow
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))  # White text

        y += line_height + line_spacing

    # Composite overlay onto image
    img = Image.alpha_composite(img, overlay)
    img = img.convert("RGB")

    # Save to bytes
    output = io.BytesIO()
    img.save(output, format="PNG", quality=95)
    return output.getvalue()


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.Draw) -> list[str]:
    """Wrap text to fit within max_width."""
    words = text.split()
    lines = []
    current_line = []

    for word in words:
        test_line = ' '.join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        test_width = bbox[2] - bbox[0]

        if test_width <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]

    if current_line:
        lines.append(' '.join(current_line))

    return lines


class ImageGenerator:
    """Generate images using Replicate API."""

    # Replicate model - SDXL
    REPLICATE_MODEL = "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b"

    def __init__(
        self,
        claude_client: Optional[ClaudeClient] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        self.claude_client = claude_client or ClaudeClient()
        self._http_client = httpx.Client(timeout=180.0)

        if not self.settings.is_replicate_configured:
            raise ValueError(
                "Replicate API key not configured. "
                "Set REPLICATE_API_KEY in your .env file.\n"
                "Get a key at: https://replicate.com/account/api-tokens"
            )
        self.api_key = self.settings.replicate_api_key

    def generate_image_prompt(self, topic: str, caption_summary: Optional[str] = None) -> str:
        """Use Claude to generate an optimized image prompt."""
        prompt = IMAGE_PROMPT_TEMPLATE.format(
            topic=topic,
            caption_summary=caption_summary or topic,
        )

        return self.claude_client.generate(
            prompt=prompt,
            temperature=0.7,
            max_tokens=200,
        ).strip()

    def generate_image(
        self,
        topic: str,
        caption_summary: Optional[str] = None,
        output_dir: Optional[Path] = None,
        text_overlay: Optional[str] = None,
        text_position: str = "top",
    ) -> GeneratedImage:
        """Generate an image for the given topic.

        Args:
            topic: The topic for the image
            caption_summary: Optional summary of the caption for context
            output_dir: Directory to save the image (defaults to polaris/images/)
            text_overlay: Optional text to overlay on the image
            text_position: Position for text ("top", "center", "bottom")

        Returns:
            GeneratedImage with local path and metadata
        """
        # Generate optimized prompt using Claude
        image_prompt = self.generate_image_prompt(topic, caption_summary)

        # Call Replicate API
        image_bytes = self._call_replicate(image_prompt)

        # Add text overlay if provided
        if text_overlay:
            image_bytes = add_text_overlay(
                image_bytes,
                text_overlay,
                position=text_position,
            )

        # Save the image
        if output_dir is None:
            output_dir = Path.cwd() / "images"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename from topic
        safe_topic = re.sub(r'[^\w\s-]', '', topic)[:30].strip().replace(' ', '_')
        timestamp = int(time.time())
        filename = f"{safe_topic}_{timestamp}.png"
        local_path = output_dir / filename

        # Write image bytes
        local_path.write_bytes(image_bytes)

        return GeneratedImage(
            local_path=str(local_path),
            url=None,
            prompt=image_prompt,
            model=self.REPLICATE_MODEL,
        )

    def _call_replicate(self, prompt: str) -> bytes:
        """Call Replicate API to generate image."""
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
        }

        # Start prediction
        response = self._http_client.post(
            "https://api.replicate.com/v1/predictions",
            headers=headers,
            json={
                "version": self.REPLICATE_MODEL.split(":")[1],
                "input": {
                    "prompt": prompt,
                    "width": 1024,
                    "height": 1024,
                    "num_outputs": 1,
                    "scheduler": "K_EULER",
                    "num_inference_steps": 30,
                    "guidance_scale": 7.5,
                    "negative_prompt": "blurry, low quality, distorted, ugly, text, watermark, logo",
                },
            },
        )

        if response.status_code == 402:
            raise Exception(
                "Replicate requires billing setup for image generation.\n"
                "Please add a payment method at: https://replicate.com/account/billing\n"
                "Replicate offers $5 free credit for new accounts."
            )

        response.raise_for_status()
        prediction = response.json()

        # Poll for completion
        prediction_url = prediction["urls"]["get"]
        while True:
            response = self._http_client.get(prediction_url, headers=headers)
            response.raise_for_status()
            result = response.json()

            status = result["status"]
            if status == "succeeded":
                output = result["output"]
                image_url = output[0] if isinstance(output, list) else output
                # Download the image
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
    """Upload a file to GitHub and return the raw URL.

    Args:
        local_path: Local path to the file
        repo: GitHub repo in format 'username/repo'
        branch: Branch name
        remote_path: Path in repo (defaults to images/<filename>)

    Returns:
        Raw GitHub URL for the uploaded file
    """
    filename = Path(local_path).name
    if remote_path is None:
        remote_path = f"images/{filename}"

    repo_root = Path.cwd()

    # Ensure target directory exists
    target_path = repo_root / remote_path
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Copy file to correct location if needed
    if str(local_path) != str(target_path):
        import shutil
        shutil.copy2(local_path, target_path)

    # Git add, commit, push
    subprocess.run(["git", "add", remote_path], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"Add generated image: {filename}"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "push"], cwd=repo_root, check=True, capture_output=True)

    # Return raw URL
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{remote_path}"
