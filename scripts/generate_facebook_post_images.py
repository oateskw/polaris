"""
Generate 3 Facebook post images for photographer group marketing.

Post 1: Ghosting Agent - "They said 'I'll get back to you.'"
Post 2: Anniversary Agent - "Your past clients are your best untapped lead source."
Post 3: Speed-to-Lead - "She commented on your reel. Then booked a photo session with someone else 20 minutes later."

Run from project root: python scripts/generate_facebook_post_images.py
"""

import argparse
import io
import sys
import time
from pathlib import Path

# Add src to path so we can import polaris modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PIL import Image, ImageDraw, ImageFilter

from polaris.config import get_settings
from polaris.services.ai.image_generator import ImageGenerator, _get_font, add_carousel_text_overlay


POSTS = [
    {
        "title": "They said 'I'll get back to you.'",
        "subtitle": "Most won't. Until the right follow-up finds them.",
        "image_prompt": (
            "Moody wedding reception interior, dark ambient lighting, bokeh candlelight and fairy lights, "
            "empty decorated chairs with bride silhouette visible in soft focus distance, luxury wedding venue, "
            "cinematic photography, ultra-realistic, warm amber tones, no text, no logos, no visible faces"
        ),
        "index": 0,
    },
    {
        "title": "Your past clients are your best untapped lead source.",
        "subtitle": "Most photographers forget them. The smart ones automate.",
        "image_prompt": (
            "Romantic couple anniversary portrait, golden hour backlight, bride and groom embracing with "
            "soft bokeh background, shallow depth of field, warm amber and golden tones, film-grain aesthetic, "
            "cinematic wedding photography, no text, no logos, faces not clearly visible"
        ),
        "index": 1,
    },
    {
        "title": "She commented on your reel.",
        "subtitle": "Then booked a photo session with someone else 20 minutes later.",
        "image_prompt": (
            "Close-up of iPhone or Android smartphone displaying Instagram feed with visible comment section, "
            "multiple comments visible below a post, social media interface clear, dark moody background behind phone, "
            "shallow depth of field bokeh, soft cinematic lighting, warm amber accent lights, professional editorial photography, "
            "no logos or watermarks, phone screen content realistic and legible"
        ),
        "index": 2,
    },
]


def _draw_rounded_shadow(canvas: Image.Image, box: tuple[int, int, int, int], radius: int, alpha: int) -> None:
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(box, radius=radius, fill=(0, 0, 0, alpha))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(radius=18)))


def _render_instagram_comment_notification(width: int = 700, height: int = 300) -> Image.Image:
    card = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(card)

    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=34, fill=(255, 255, 255, 228))
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=34, outline=(226, 232, 240, 255), width=1)

    icon_box = (26, 28, 96, 98)
    gradient = Image.new("RGBA", (70, 70), (0, 0, 0, 0))
    gradient_draw = ImageDraw.Draw(gradient)
    for y in range(70):
        ratio = y / 69
        color = (
            int(245 + (131 - 245) * ratio),
            int(90 + (58 - 90) * ratio),
            int(94 + (180 - 94) * ratio),
            255,
        )
        gradient_draw.line((0, y, 69, y), fill=color)
    mask = Image.new("L", (70, 70), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 69, 69), radius=18, fill=255)
    card.paste(gradient, (icon_box[0], icon_box[1]), mask)

    draw.rounded_rectangle((46, 48, 76, 78), radius=8, outline=(255, 255, 255, 255), width=3)
    draw.ellipse((56, 58, 66, 68), outline=(255, 255, 255, 255), width=3)
    draw.ellipse((69, 51, 73, 55), fill=(255, 255, 255, 255))

    label_font = _get_font("semibold", 20)
    heading_font = _get_font("semibold", 32)
    body_font = _get_font("regular", 24)
    meta_font = _get_font("regular", 18)

    draw.text((118, 34), "Instagram Comment", font=label_font, fill=(107, 114, 128, 255))
    draw.text((118, 72), "brooklynbride", font=heading_font, fill=(17, 24, 39, 255))
    draw.text((118, 118), '"Are October weekends still open?"', font=body_font, fill=(55, 65, 81, 255))

    draw.line((26, 184, width - 26, 184), fill=(229, 231, 235, 255), width=1)
    draw.text((30, 206), "No reply for 20 minutes", font=meta_font, fill=(107, 114, 128, 255))

    status_w = 260
    status_x = width - status_w - 30
    status_y = 198
    draw.rounded_rectangle((status_x, status_y, status_x + status_w, status_y + 56), radius=18, fill=(254, 242, 242, 255), outline=(254, 202, 202, 255), width=1)
    draw.text((status_x + 18, status_y + 16), "Lead went elsewhere", font=label_font, fill=(185, 28, 28, 255))
    return card


def create_speed_to_lead_image(generator: ImageGenerator, post: dict, output_dir: Path) -> str:
    base_prompt = (
        "Photorealistic wedding photographer workspace, editing desk with camera body, lens, laptop, and smartphone nearby, "
        "warm tungsten studio light, amber bokeh in the background, premium editorial photography, shallow depth of field, "
        "clean composition with open space for graphic overlays, realistic, no text, no logos, no watermark"
    )
    image_bytes = generator._call_replicate(base_prompt, aspect_ratio="1:1")
    canvas = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    canvas = canvas.filter(ImageFilter.GaussianBlur(radius=2.2))

    shade = Image.new("RGBA", canvas.size, (8, 12, 20, 104))
    canvas.alpha_composite(shade)

    comment_card = _render_instagram_comment_notification()
    card_x = (canvas.size[0] - comment_card.size[0]) // 2
    card_y = 138
    _draw_rounded_shadow(
        canvas,
        (card_x + 8, card_y + 12, card_x + comment_card.size[0] + 8, card_y + comment_card.size[1] + 12),
        radius=34,
        alpha=78,
    )
    canvas.alpha_composite(comment_card, dest=(card_x, card_y))

    small_card = Image.new("RGBA", (388, 102), (255, 255, 255, 0))
    small_draw = ImageDraw.Draw(small_card)
    small_draw.rounded_rectangle((0, 0, 387, 101), radius=24, fill=(248, 250, 252, 235), outline=(226, 232, 240, 255), width=1)
    small_font = _get_font("semibold", 18)
    meta_font = _get_font("regular", 16)
    small_draw.text((20, 18), "No immediate reply detected", font=small_font, fill=(17, 24, 39, 255))
    small_draw.text((20, 50), "Client booked with a different photographer", font=meta_font, fill=(71, 85, 105, 255))
    small_x = 64
    small_y = 68
    _draw_rounded_shadow(
        canvas,
        (small_x + 6, small_y + 10, small_x + 394, small_y + 112),
        radius=26,
        alpha=62,
    )
    canvas.alpha_composite(small_card, dest=(small_x, small_y))

    output = io.BytesIO()
    canvas.convert("RGB").save(output, format="PNG", quality=95)
    composed = add_carousel_text_overlay(output.getvalue(), post["title"], post["subtitle"], bullets=None)

    timestamp = int(time.time())
    filename = f"carousel_slide{post['index']}_{post['title'][:24].replace(' ', '_').replace('.', '')}_{timestamp}.png"
    local_path = output_dir / filename
    local_path.write_bytes(composed)
    return str(local_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--post", type=int, choices=[1, 2, 3], help="Generate only a single post image")
    args = parser.parse_args()

    print("Generating 3 Facebook post images for photographer group...")
    print(f"{'='*70}\n")

    settings = get_settings()
    generator = ImageGenerator(settings=settings)

    output_dir = Path.cwd() / "images" / "facebook_posts"
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    posts = POSTS if args.post is None else [POSTS[args.post - 1]]

    for post in posts:
        print(f"Generating Post {post['index'] + 1}/3...")
        print(f"  Title: {post['title']}")
        print(f"  Subtitle: {post['subtitle']}\n")

        try:
            if post["index"] == 2:
                image_path = create_speed_to_lead_image(generator, post, output_dir)
            else:
                image = generator.generate_carousel_slide_image(
                    title=post["title"],
                    subtitle=post["subtitle"],
                    image_prompt=post["image_prompt"],
                    output_dir=output_dir,
                    slide_index=post["index"],
                    bullets=None,
                )
                image_path = image.local_path

            results.append({
                "index": post["index"] + 1,
                "title": post["title"],
                "path": image_path,
                "success": True,
            })

            print(f"  ✓ Saved to: {image_path}\n")

        except Exception as e:
            results.append({
                "index": post["index"] + 1,
                "title": post["title"],
                "error": str(e),
                "success": False,
            })

            print(f"  ✗ Error: {e}\n")

    # Summary
    print(f"{'='*70}")
    print("GENERATION COMPLETE")
    print(f"{'='*70}\n")

    for r in results:
        if r["success"]:
            print(f"Post {r['index']}: ✓ {r['title'][:50]}...")
            print(f"  → {r['path']}\n")
        else:
            print(f"Post {r['index']}: ✗ {r['title'][:50]}...")
            print(f"  Error: {r['error']}\n")

    success_count = sum(1 for r in results if r["success"])
    print(f"Total: {success_count}/{len(results)} images generated successfully")
    print(f"Output directory: {output_dir}\n")


if __name__ == "__main__":
    main()
