#!/usr/bin/env python3
"""Generate a branded lead-flow workflow diagram for Instagram."""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PIL import Image, ImageDraw
from polaris.services.ai.image_generator import _get_font, BRAND

W, H = 1080, 1080

# ── Palette ──────────────────────────────────────────────────────────────────
BG_TOP      = (6,  12,  30)
BG_BOT      = (14, 28,  58)
ORANGE      = (249, 115,  22)
BLUE_ACC    = ( 59, 130, 246)
PURPLE_ACC  = (168,  85, 247)
GREEN_ACC   = ( 34, 197,  94)
WHITE       = (255, 255, 255)
MUTED       = (148, 163, 184)
DARK_CARD   = ( 16,  32,  68)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _centered_text(draw, text, font, cx, y, color):
    bb = draw.textbbox((0, 0), text, font=font)
    draw.text((cx - (bb[2] - bb[0]) // 2, y), text, font=font, fill=color)


def _gradient_bg(img: Image.Image):
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        r = int(BG_TOP[0] + (BG_BOT[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOT[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOT[2] - BG_TOP[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b, 255))


def _glow_rect(img: Image.Image, box, color, radius=18, strength=12, alpha_max=70):
    """Composite a soft radial glow around a box onto img."""
    x1, y1, x2, y2 = box
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d  = ImageDraw.Draw(ov)
    for i in range(strength, 0, -1):
        a = int(alpha_max * (i / strength) ** 1.5)
        d.rounded_rectangle(
            (x1 - i * 2, y1 - i * 2, x2 + i * 2, y2 + i * 2),
            radius=radius + i * 2,
            fill=(*color[:3], a),
        )
    img.alpha_composite(ov)


def _node(img: Image.Image, box, fill, border, radius=18, border_w=2,
          glow=None, glow_strength=10):
    if glow:
        _glow_rect(img, box, glow, radius=radius, strength=glow_strength)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d  = ImageDraw.Draw(ov)
    d.rounded_rectangle(box, radius=radius, fill=(*fill, 215))
    d.rounded_rectangle(box, radius=radius, outline=(*border, 255), width=border_w)
    img.alpha_composite(ov)


def _arrow(draw, x1, y, x2, color=ORANGE, width=3):
    """Straight horizontal arrow."""
    draw.line([(x1, y), (x2, y)], fill=color, width=width)
    ah, aw = 12, 7
    draw.polygon([(x2, y), (x2 - ah, y - aw), (x2 - ah, y + aw)], fill=color)


def _branch_arrow(draw, x1, mid_y, x2, y_top, y_bot, color=ORANGE, width=2):
    """One stem forking to two destinations."""
    mid_x = (x1 + x2) // 2
    draw.line([(x1, mid_y), (mid_x, mid_y)], fill=color, width=width)
    for y_dest in (y_top, y_bot):
        draw.line([(mid_x, mid_y), (mid_x, y_dest)], fill=color, width=width)
        draw.line([(mid_x, y_dest), (x2, y_dest)],   fill=color, width=width)
        ah, aw = 12, 6
        draw.polygon([(x2, y_dest), (x2-ah, y_dest-aw), (x2-ah, y_dest+aw)], fill=color)


def _merge_arrow(draw, x1, y_top, y_bot, x2, mid_y, color, width=2):
    """Two sources merging into one stem."""
    mid_x = (x1 + x2) // 2
    for y_src in (y_top, y_bot):
        draw.line([(x1, y_src), (mid_x, y_src)], fill=color, width=width)
        draw.line([(mid_x, y_src), (mid_x, mid_y)], fill=color, width=width)
    draw.line([(mid_x, mid_y), (x2, mid_y)], fill=color, width=width)
    ah, aw = 12, 6
    draw.polygon([(x2, mid_y), (x2-ah, mid_y-aw), (x2-ah, mid_y+aw)], fill=color)


# ── Icons ─────────────────────────────────────────────────────────────────────

def _icon_spreadsheet(draw, cx, cy, color):
    cw, ch = 52, 44
    x1, y1 = cx - cw // 2, cy - ch // 2
    draw.rectangle([x1, y1, x1+cw, y1+ch], outline=(*color, 255), width=2)
    draw.rectangle([x1, y1, x1+cw, y1+12], fill=(*color, 160))
    col_w = cw // 3
    for i in (1, 2):
        xv = x1 + col_w * i
        draw.line([(xv, y1), (xv, y1+ch)], fill=(*color, 120), width=1)
    row_h = (ch - 12) // 3
    for i in (1, 2):
        yh = y1 + 12 + row_h * i
        draw.line([(x1, yh), (x1+cw, yh)], fill=(*color, 80), width=1)
    for row in range(3):
        for col in range(3):
            rx = x1 + 6 + col * col_w
            ry = y1 + 17 + row * row_h
            draw.rounded_rectangle([rx, ry, rx + col_w - 10, ry + 5], radius=2, fill=(*color, 140))


def _icon_ai(draw, cx, cy, color):
    r = 30
    pts = [(cx + r * math.cos(math.pi/6 + i * math.pi/3),
            cy + r * math.sin(math.pi/6 + i * math.pi/3)) for i in range(6)]
    draw.polygon(pts, fill=(*color, 40), outline=(*color, 255), width=2)
    font = _get_font("bold", 28)
    bb = draw.textbbox((0, 0), "AI", font=font)
    draw.text((cx - (bb[2]-bb[0])//2, cy - (bb[3]-bb[1])//2 - 2),
              "AI", font=font, fill=(*color, 255))
    for i in range(6):
        angle = math.pi/6 + i * math.pi/3
        px = cx + (r + 10) * math.cos(angle)
        py = cy + (r + 10) * math.sin(angle)
        draw.ellipse([px-3, py-3, px+3, py+3], fill=(*color, 200))


def _icon_sms(draw, cx, cy, color):
    bw, bh = 46, 34
    x1, y1 = cx - bw//2, cy - bh//2
    draw.rounded_rectangle([x1, y1, x1+bw, y1+bh],
                            radius=8, fill=(*color, 40), outline=(*color, 220), width=2)
    draw.polygon([(x1+10, y1+bh), (x1+4, y1+bh+10), (x1+22, y1+bh)], fill=(*color, 220))
    draw.rounded_rectangle([x1+7, y1+8,  x1+bw-7,  y1+14], radius=3, fill=(*color, 160))
    draw.rounded_rectangle([x1+7, y1+18, x1+bw-14, y1+24], radius=3, fill=(*color, 110))


def _icon_email(draw, cx, cy, color):
    ew, eh = 48, 34
    x1, y1 = cx - ew//2, cy - eh//2
    draw.rectangle([x1, y1, x1+ew, y1+eh], fill=(*color, 40), outline=(*color, 220), width=2)
    draw.line([(x1, y1), (cx, cy-2), (x1+ew, y1)], fill=(*color, 200), width=2)


def _icon_calendar_check(draw, cx, cy, color):
    cw, ch = 46, 44
    x1, y1 = cx - cw//2, cy - ch//2
    draw.rounded_rectangle([x1, y1, x1+cw, y1+ch],
                            radius=8, fill=(*color, 40), outline=(*color, 220), width=2)
    draw.rounded_rectangle([x1, y1, x1+cw, y1+12], radius=8, fill=(*color, 170))
    for rx in (x1+12, x1+cw-12):
        draw.rectangle([rx-2, y1-4, rx+2, y1+6], fill=WHITE)
    ck_pts = [
        (cx - 13, cy + 8),
        (cx -  4, cy + 17),
        (cx + 14, cy -  3),
    ]
    draw.line(ck_pts, fill=(*color, 240), width=4)


# ── Badge ─────────────────────────────────────────────────────────────────────

def _badge(img: Image.Image, draw, cx, cy, label):
    r = 16
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    od.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(*ORANGE, 35), outline=(*ORANGE, 200), width=2)
    img.alpha_composite(ov)
    draw = ImageDraw.Draw(img)
    font = _get_font("bold", 16)
    bb = draw.textbbox((0, 0), label, font=font)
    draw.text((cx-(bb[2]-bb[0])//2, cy-(bb[3]-bb[1])//2+1),
              label, font=font, fill=(*ORANGE, 230))


# ── Main generator ────────────────────────────────────────────────────────────

def generate(output_path: str = "images/lead_flow_diagram.png") -> str:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    _gradient_bg(img)

    # Subtle dot-grid texture
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(ov)
    for gx in range(0, W, 54):
        for gy in range(0, H, 54):
            gd.ellipse([gx-1, gy-1, gx+1, gy+1], fill=(255, 255, 255, 10))
    img.alpha_composite(ov)

    # ── Top accent bar ──────────────────────────────────────────────────────
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    od.rectangle([(0, 0), (W, 7)], fill=(*ORANGE, 255))
    img.alpha_composite(ov)

    draw = ImageDraw.Draw(img)

    # ── Header ─────────────────────────────────────────────────────────────
    title_font = _get_font("bold", 50)
    sub_font   = _get_font("regular", 26)

    # Draw title in two parts with a custom arrow between them (Poppins lacks →)
    part1 = "COLD LEAD"
    part2 = "BOOKED CLIENT"
    p1_bb = draw.textbbox((0, 0), part1, font=title_font)
    p2_bb = draw.textbbox((0, 0), part2, font=title_font)
    p1_w  = p1_bb[2] - p1_bb[0]
    p2_w  = p2_bb[2] - p2_bb[0]
    arrow_gap = 24   # space each side of the arrow
    arrow_w   = 38
    total_w   = p1_w + arrow_gap + arrow_w + arrow_gap + p2_w
    tx        = (W - total_w) // 2
    ty        = 28
    title_h   = p1_bb[3] - p1_bb[1]

    draw.text((tx, ty), part1, font=title_font, fill=WHITE)
    # Arrow line + head
    ax1 = tx + p1_w + arrow_gap
    ax2 = ax1 + arrow_w
    ay  = ty + title_h // 2 + 2
    draw.line([(ax1, ay), (ax2, ay)], fill=ORANGE, width=4)
    draw.polygon([(ax2, ay), (ax2-12, ay-7), (ax2-12, ay+7)], fill=ORANGE)
    draw.text((ax2 + arrow_gap, ty), part2, font=title_font, fill=WHITE)

    _centered_text(draw, "How the Polaris AI Lead Agent works",
                   sub_font, W//2, 96, (*MUTED, 210))

    draw.line([(70, 148), (W-70, 148)], fill=(*ORANGE, 60), width=1)

    # ── Flow positions ──────────────────────────────────────────────────────
    CY   = 510   # main vertical center
    Y_SMS   = 435
    Y_EMAIL = 590

    NW, NH    = 165, 175   # main node size
    SW, SH    =  140, 108  # small node (SMS / Email)

    X_LEADS  = 130
    X_AI     = 360
    X_CH     = 625   # SMS/Email column
    X_RESULT = 875

    # ── Node 1 — Cold Leads ──────────────────────────────────────────────────
    b1 = (X_LEADS-NW//2, CY-NH//2, X_LEADS+NW//2, CY+NH//2)
    _node(img, b1, DARK_CARD, BLUE_ACC, glow=BLUE_ACC, glow_strength=8)
    draw = ImageDraw.Draw(img)
    _icon_spreadsheet(draw, X_LEADS, CY - 30, BLUE_ACC)
    _centered_text(draw, "COLD LEADS",  _get_font("bold",    20), X_LEADS, CY + 50, WHITE)
    _centered_text(draw, "Spreadsheet", _get_font("regular", 15), X_LEADS, CY + 74, MUTED)

    # ── Node 2 — AI Agent (hero) ─────────────────────────────────────────────
    b2 = (X_AI-NW//2, CY-NH//2, X_AI+NW//2, CY+NH//2)
    _node(img, b2, (35, 14, 4), ORANGE, border_w=3, glow=ORANGE, glow_strength=20)
    draw = ImageDraw.Draw(img)
    _icon_ai(draw, X_AI, CY - 30, ORANGE)
    _centered_text(draw, "AI AGENT",        _get_font("bold",    22), X_AI, CY + 50, ORANGE)
    _centered_text(draw, "Qualifies & Books", _get_font("regular", 14), X_AI, CY + 76, MUTED)

    # ── Node 3a — SMS ────────────────────────────────────────────────────────
    b3a = (X_CH-SW//2, Y_SMS-SH//2, X_CH+SW//2, Y_SMS+SH//2)
    _node(img, b3a, DARK_CARD, BLUE_ACC, radius=14, glow=BLUE_ACC, glow_strength=7)
    draw = ImageDraw.Draw(img)
    _icon_sms(draw, X_CH, Y_SMS - 16, BLUE_ACC)
    _centered_text(draw, "SMS",           _get_font("bold",    20), X_CH, Y_SMS + 20, WHITE)
    _centered_text(draw, "Text Outreach", _get_font("regular", 13), X_CH, Y_SMS + 42, MUTED)

    # ── Node 3b — Email ──────────────────────────────────────────────────────
    b3b = (X_CH-SW//2, Y_EMAIL-SH//2, X_CH+SW//2, Y_EMAIL+SH//2)
    _node(img, b3b, DARK_CARD, PURPLE_ACC, radius=14, glow=PURPLE_ACC, glow_strength=7)
    draw = ImageDraw.Draw(img)
    _icon_email(draw, X_CH, Y_EMAIL - 16, PURPLE_ACC)
    _centered_text(draw, "EMAIL",          _get_font("bold",    20), X_CH, Y_EMAIL + 20, WHITE)
    _centered_text(draw, "Email Outreach", _get_font("regular", 13), X_CH, Y_EMAIL + 42, MUTED)

    # ── Node 4 — New Business ────────────────────────────────────────────────
    b4 = (X_RESULT-NW//2, CY-NH//2, X_RESULT+NW//2, CY+NH//2)
    _node(img, b4, (8, 28, 18), GREEN_ACC, glow=GREEN_ACC, glow_strength=14)
    draw = ImageDraw.Draw(img)
    _icon_calendar_check(draw, X_RESULT, CY - 30, GREEN_ACC)
    _centered_text(draw, "NEW BUSINESS",  _get_font("bold",    19), X_RESULT, CY + 50, GREEN_ACC)
    _centered_text(draw, "Booked Clients", _get_font("regular", 14), X_RESULT, CY + 74, MUTED)

    # ── Arrows ───────────────────────────────────────────────────────────────
    draw = ImageDraw.Draw(img)
    # 1 → 2
    _arrow(draw, X_LEADS + NW//2 + 2, CY, X_AI - NW//2 - 2, color=ORANGE, width=3)
    # 2 → SMS + Email
    _branch_arrow(draw, X_AI + NW//2 + 2, CY,
                  X_CH - SW//2 - 2, Y_SMS, Y_EMAIL, color=ORANGE, width=2)
    # SMS + Email → 4
    _merge_arrow(draw, X_CH + SW//2 + 2, Y_SMS, Y_EMAIL,
                 X_RESULT - NW//2 - 2, CY, color=GREEN_ACC, width=2)

    # ── Step badges ───────────────────────────────────────────────────────────
    badge_y = CY - NH//2 - 26
    for cx, label in ((X_LEADS, "01"), (X_AI, "02"), (X_CH, "03"), (X_RESULT, "04")):
        _badge(img, draw, cx, badge_y, label)
        draw = ImageDraw.Draw(img)

    # ── Divider ──────────────────────────────────────────────────────────────
    draw.line([(70, 730), (W-70, 730)], fill=(*ORANGE, 50), width=1)

    # ── Stats row ─────────────────────────────────────────────────────────────
    stats = [
        ("< 2 MIN",  "Response Time"),
        ("24 / 7",   "Always On"),
        ("100%",     "Leads Followed Up"),
    ]
    big_f = _get_font("bold",    32)
    sm_f  = _get_font("regular", 16)
    for (val, lbl), sx in zip(stats, (200, 540, 880)):
        _centered_text(draw, val, big_f, sx, 750, ORANGE)
        _centered_text(draw, lbl, sm_f,  sx, 793, MUTED)

    # ── Brand divider ────────────────────────────────────────────────────────
    draw.line([(70, 850), (W-70, 850)], fill=(*ORANGE, 35), width=1)

    # Orange dot + brand name
    dot_cx = W//2
    brand_font  = _get_font("bold",    36)
    tag_font    = _get_font("regular", 20)
    handle_font = _get_font("regular", 16)

    bb = draw.textbbox((0, 0), "POLARIS INNOVATIONS", font=brand_font)
    bw = bb[2] - bb[0]
    dot_r = 10
    total_w = dot_r * 2 + 14 + bw
    dot_x = W//2 - total_w//2
    text_x = dot_x + dot_r * 2 + 14

    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    od.ellipse([dot_x, 878, dot_x + dot_r*2, 878 + dot_r*2], fill=(*ORANGE, 255))
    img.alpha_composite(ov)

    draw = ImageDraw.Draw(img)
    draw.text((text_x, 871), "POLARIS INNOVATIONS", font=brand_font, fill=WHITE)
    _centered_text(draw, "AI Agents for Small Business", tag_font,    W//2, 920, MUTED)
    _centered_text(draw, "@polarisinnovationsai",        handle_font, W//2, 952, (*ORANGE, 190))

    # ── Bottom bar ────────────────────────────────────────────────────────────
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    od.rectangle([(0, H-7), (W, H)], fill=(*ORANGE, 255))
    img.alpha_composite(ov)

    # ── Save ─────────────────────────────────────────────────────────────────
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(str(out), format="PNG", quality=95)
    print(f"Saved: {out}")
    return str(out)


if __name__ == "__main__":
    generate()
