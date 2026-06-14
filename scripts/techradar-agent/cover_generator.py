"""Generate podcast cover images (Style A: Tech Dark) using Pillow.

Channel cover: static 1400x1400 PNG per topic, generated once.
Episode cover: per-episode 1400x1400 JPEG with tagline, date, duration.

Run directly to regenerate static channel covers:
    uv run cover_generator.py
"""

from datetime import datetime
from pathlib import Path

import numpy as np

SIZE = 1400
_BAR_H = 145  # bottom bar height (episode covers)

_ACCENT = {
    "AI":       (96, 165, 250),   # #60a5fa
    "Robotics": (52, 211, 153),   # #34d399
}
_ACCENT_LIGHT = {
    "AI":       (147, 197, 253),  # #93c5fd
    "Robotics": (110, 231, 183),  # #6ee7b7
}
_BG_TOP = {
    "AI":       (15, 23, 42),     # #0f172a
    "Robotics": (13, 31, 20),     # #0d1f14
}
_BG_MID = {
    "AI":       (30, 58, 95),     # #1e3a5f
    "Robotics": (26, 61, 43),     # #1a3d2b
}


def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    import matplotlib
    fonts_dir = Path(matplotlib.__file__).parent / "mpl-data" / "fonts" / "ttf"
    path = fonts_dir / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
    try:
        return ImageFont.truetype(str(path), size)
    except Exception:
        return ImageFont.load_default()


def _make_base_image(topic: str):
    from PIL import Image

    c_top = np.array(_BG_TOP[topic], dtype=float)
    c_mid = np.array(_BG_MID[topic], dtype=float)

    pixels = np.zeros((SIZE, SIZE, 3), dtype=np.uint8)
    for y in range(SIZE):
        t = y / SIZE
        if t < 0.55:
            t2 = t / 0.55
            row = c_top * (1 - t2) + c_mid * t2
        else:
            t2 = (t - 0.55) / 0.45
            row = c_mid * (1 - t2) + c_top * t2
        pixels[y] = row.astype(np.uint8)

    # Radial glow at upper-right
    accent = np.array(_ACCENT[topic], dtype=float)
    cx, cy = int(SIZE * 0.72), int(SIZE * 0.22)
    radius = SIZE * 0.52

    y_g, x_g = np.mgrid[0:SIZE, 0:SIZE]
    dist = np.sqrt((x_g - cx) ** 2 + (y_g - cy) ** 2)
    alpha = np.clip(1.0 - dist / radius, 0, 1) ** 2.8 * 0.22
    for c in range(3):
        pixels[:, :, c] = np.clip(
            pixels[:, :, c] * (1 - alpha) + accent[c] * alpha, 0, 255
        ).astype(np.uint8)

    return Image.fromarray(pixels, "RGB")


def _center_text(draw, y: int, text: str, font, fill) -> int:
    """Draw text centered horizontally; return bottom y."""
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    draw.text(((SIZE - w) // 2, y), text, font=font, fill=fill)
    return y + (bbox[3] - bbox[1])


def _wrap_lines(draw, text: str, font, max_w: int) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for word in words:
        trial = (cur + " " + word).strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def generate_channel_cover(topic: str, out_path: Path) -> None:
    """Static channel cover for podcast app listing (PNG)."""
    from PIL import Image, ImageDraw

    img = _make_base_image(topic)
    draw = ImageDraw.Draw(img)
    accent = _ACCENT[topic]
    light = _ACCENT_LIGHT[topic]

    label = "AI DAILY RADAR" if topic == "AI" else "ROBOTICS DAILY RADAR"
    title_lines = ("AI", "Daily", "Radar") if topic == "AI" else ("Robotics", "Daily", "Radar")

    # Eyebrow label
    f_eye = _font(30, bold=True)
    _center_text(draw, 255, label, f_eye, accent)

    # Accent rule
    rx = SIZE // 2 - 44
    draw.rectangle([(rx, 303), (rx + 88, 308)], fill=accent)

    # Main title
    f_title = _font(118, bold=True)
    y = 340
    for line in title_lines:
        bbox = draw.textbbox((0, 0), line, font=f_title)
        w = bbox[2] - bbox[0]
        draw.text(((SIZE - w) // 2, y), line, font=f_title, fill=(248, 250, 252))
        y += bbox[3] - bbox[1] + 8

    # Subtitle
    f_sub = _font(30)
    _center_text(draw, y + 28, "Daily news digest in audio form", f_sub, (148, 163, 184))

    # Author
    f_auth = _font(28, bold=True)
    _center_text(draw, SIZE - 100, "Keith Fry", f_auth, light)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out_path), "PNG", optimize=True)


def generate_episode_cover(
    topic: str,
    tagline: str,
    date: datetime,
    duration_sec: int,
    out_path: Path,
) -> None:
    """Per-episode cover with tagline, date, and duration (JPEG)."""
    from PIL import Image, ImageDraw

    img = _make_base_image(topic)
    draw = ImageDraw.Draw(img)
    accent = _ACCENT[topic]
    light = _ACCENT_LIGHT[topic]

    label = "AI DAILY RADAR" if topic == "AI" else "ROBOTICS DAILY RADAR"

    # Eyebrow
    f_eye = _font(28, bold=True)
    _center_text(draw, 195, label, f_eye, accent)

    # Accent rule
    rx = SIZE // 2 - 44
    draw.rectangle([(rx, 240), (rx + 88, 245)], fill=accent)

    # Tagline (wrapped, vertically centered in upper zone)
    f_tag = _font(74, bold=True)
    pad = 110
    lines = _wrap_lines(draw, tagline, f_tag, SIZE - pad * 2)
    line_h = draw.textbbox((0, 0), "Ag", font=f_tag)[3] + 14
    zone_top, zone_bot = 280, SIZE - _BAR_H - 40
    total_h = len(lines) * line_h - 14
    y = zone_top + (zone_bot - zone_top - total_h) // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=f_tag)
        w = bbox[2] - bbox[0]
        draw.text(((SIZE - w) // 2, y), line, font=f_tag, fill=(248, 250, 252))
        y += line_h

    # Bottom bar overlay
    bar_top = SIZE - _BAR_H
    overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([(0, bar_top), (SIZE, SIZE)], fill=(*accent, 52))
    od.line([(0, bar_top), (SIZE, bar_top)], fill=(*accent, 80), width=2)
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Date (centered)
    f_date = _font(34, bold=True)
    date_str = date.strftime("%B %-d, %Y")
    _center_text(draw, bar_top + 22, date_str, f_date, light)

    # Duration (centered)
    f_dur = _font(28)
    mins = duration_sec // 60
    dur_str = f"{mins} minute{'s' if mins != 1 else ''}"
    _center_text(draw, bar_top + 72, dur_str, f_dur, light)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out_path), "JPEG", quality=92, optimize=True)


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[2]
    for topic, subdir in [("AI", "AI"), ("Robotics", "Robotics")]:
        out = repo_root / "techradar" / subdir / "podcast-cover.png"
        print(f"Generating {topic} channel cover → {out}")
        generate_channel_cover(topic, out)
        print(f"  Done: {out.stat().st_size // 1024} KB")
