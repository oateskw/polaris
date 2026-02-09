"""AI-powered image generation using Replicate."""

import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

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

Return ONLY the image prompt, nothing else. Keep it under 100 words."""


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
    ) -> GeneratedImage:
        """Generate an image for the given topic.

        Args:
            topic: The topic for the image
            caption_summary: Optional summary of the caption for context
            output_dir: Directory to save the image (defaults to polaris/images/)

        Returns:
            GeneratedImage with local path and metadata
        """
        # Generate optimized prompt using Claude
        image_prompt = self.generate_image_prompt(topic, caption_summary)

        # Call Replicate API
        image_bytes = self._call_replicate(image_prompt)

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
