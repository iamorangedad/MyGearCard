"""Image sniffing, vision payloads, and the print-file renderer."""

from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .config import DATA

CARD_W = 744
CARD_H = 1040
RESAMPLE_BILINEAR = getattr(getattr(Image, "Resampling", Image), "BILINEAR")
RESAMPLE_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")

SANS = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
SANS_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
SERIF_BOLD = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"
SERIF = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"
FONT_INDEX = 2

THEMES = {
    "core": {
        "inner": (62, 24, 30),
        "ink": (255, 246, 232),
        "muted": (232, 196, 160),
        "accent": (214, 78, 52),
        "gold": (196, 142, 58),
    },
    "peripheral": {
        "inner": (12, 42, 48),
        "ink": (236, 252, 250),
        "muted": (168, 214, 210),
        "accent": (46, 168, 156),
        "gold": (118, 176, 168),
    },
    "av": {
        "inner": (40, 22, 58),
        "ink": (248, 240, 255),
        "muted": (214, 190, 232),
        "accent": (168, 112, 214),
        "gold": (176, 142, 206),
    },
    "ride": {
        "inner": (48, 30, 14),
        "ink": (255, 246, 230),
        "muted": (230, 196, 150),
        "accent": (214, 112, 42),
        "gold": (206, 150, 64),
    },
    "terminal": {
        "inner": (16, 46, 34),
        "ink": (236, 252, 242),
        "muted": (176, 214, 186),
        "accent": (64, 168, 112),
        "gold": (132, 184, 146),
    },
    "other": {
        "inner": (32, 34, 42),
        "ink": (245, 245, 248),
        "muted": (196, 198, 208),
        "accent": (150, 154, 170),
        "gold": (176, 178, 188),
    },
}

PAPER = (247, 241, 228)
INK = (42, 32, 28)
MUTED = (112, 92, 76)
DAMAGE = (168, 42, 36)


def sniff(raw: bytes) -> str | None:
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(raw) > 12 and raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    return None


def extension_for(mime: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(mime, ".img")


def safe_path(relpath: str) -> Path:
    path = (DATA / relpath).resolve()
    root = DATA.resolve()
    if path != root and root not in path.parents:
        raise ValueError("路径越界")
    return path


def vision_data_url(path: Path, mime: str) -> str:
    """Shrink the photo before it is posted to a vision model."""
    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((1024, 1024))
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=85)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"
    except Exception:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size, index=FONT_INDEX)


def _gradient(width: int, height: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    column = Image.new("RGB", (1, height))
    pixels = column.load()
    for y in range(height):
        blend = y / max(height - 1, 1)
        pixels[0, y] = tuple(int(top[i] * (1 - blend) + bottom[i] * blend) for i in range(3))
    return column.resize((width, height), RESAMPLE_BILINEAR)


def _cover(image: Image.Image, width: int, height: int) -> Image.Image:
    image = ImageOps.exif_transpose(image).convert("RGB")
    scale = max(width / image.width, height / image.height)
    resized = image.resize(
        (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
        RESAMPLE_LANCZOS,
    )
    left = max(0, (resized.width - width) // 2)
    top = max(0, (resized.height - height) // 2)
    return resized.crop((left, top, left + width, top + height))


def _rounded(image: Image.Image, radius: int) -> Image.Image:
    image = image.convert("RGBA")
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, image.width - 1, image.height - 1), radius=radius, fill=255)
    image.putalpha(mask)
    return image


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text or "":
        trial = current + char
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def _fit(draw: ImageDraw.ImageDraw, text: str, path: str, max_width: int, start: int, minimum: int):
    size = start
    while size >= minimum:
        face = _font(path, size)
        if draw.textlength(text, font=face) <= max_width:
            return face, text
        size -= 2
    face = _font(path, minimum)
    trimmed = text
    while trimmed and draw.textlength(trimmed + "…", font=face) > max_width:
        trimmed = trimmed[:-1]
    return face, (trimmed + "…") if trimmed else text[:1]


def _disc(draw: ImageDraw.ImageDraw, xy: tuple[int, int], radius: int, fill: tuple[int, int, int]) -> None:
    x, y = xy
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)


def render_card(art_path: Path, meta: dict) -> bytes:
    theme = THEMES.get(meta.get("type_key"), THEMES["other"])
    canvas = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    frame = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(frame)

    draw.rounded_rectangle((0, 0, CARD_W - 1, CARD_H - 1), radius=46, fill=(88, 56, 24, 255))
    draw.rounded_rectangle((6, 6, CARD_W - 7, CARD_H - 7), radius=42, fill=(255, 232, 186, 255))
    draw.rounded_rectangle((12, 12, CARD_W - 13, CARD_H - 13), radius=38, fill=theme["gold"] + (255,))
    draw.rounded_rectangle((22, 22, CARD_W - 23, CARD_H - 23), radius=32, fill=theme["inner"] + (255,))
    canvas.alpha_composite(frame)

    pen = ImageDraw.Draw(canvas)
    name_font, name = _fit(pen, meta.get("name") or "未命名装备", SERIF_BOLD, 470, 52, 28)
    pen.text((48, 42), name, font=name_font, fill=theme["ink"])

    hp_font = _font(SERIF_BOLD, 64)
    hp_label = _font(SANS_BOLD, 18)
    pen.text((696, 40), "HP", font=hp_label, fill=theme["muted"], anchor="rt")
    pen.text((696, 118), str(meta.get("hp") or 100), font=hp_font, fill=theme["ink"], anchor="rb")

    sub_font = _font(SANS, 22)
    pen.text((50, 108), f"{meta.get('type_name', '装备')}  ·  {meta.get('category_label', '')}", font=sub_font, fill=theme["muted"])

    art_box = (48, 148, 696, 548)
    art_w = art_box[2] - art_box[0]
    art_h = art_box[3] - art_box[1]
    try:
        with Image.open(art_path) as source:
            art = _cover(source, art_w, art_h)
    except Exception:
        art = Image.new("RGB", (art_w, art_h), (24, 24, 28))
    art = _rounded(art, 18)
    canvas.alpha_composite(art, (art_box[0], art_box[1]))

    badge_font = _font(SANS_BOLD, 20)
    rarity = str(meta.get("rarity") or "普通")
    badge = f" {meta.get('type_name', '装备')} "
    rarity_label = f" {rarity} "
    badge_w = int(pen.textlength(badge, font=badge_font)) + 18
    rarity_w = int(pen.textlength(rarity_label, font=badge_font)) + 18
    pen.rounded_rectangle((62, 164, 62 + badge_w, 198), radius=8, fill=(20, 16, 14, 210))
    pen.text((71, 168), badge.strip(), font=badge_font, fill=(255, 248, 236))
    pen.rounded_rectangle((682 - rarity_w, 164, 682, 198), radius=8, fill=(20, 16, 14, 210))
    pen.text((690 - rarity_w, 168), rarity_label.strip(), font=badge_font, fill=theme["muted"])

    paper = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    paper_draw = ImageDraw.Draw(paper)
    paper_draw.rounded_rectangle((40, 566, CARD_W - 41, 1002), radius=22, fill=PAPER + (255,))
    canvas.alpha_composite(paper)
    pen = ImageDraw.Draw(canvas)

    name_font_atk = _font(SANS_BOLD, 32)
    body_font = _font(SANS, 24)
    y = 590
    footer_top = 900
    for attack in (meta.get("attacks") or [])[:2]:
        if y > footer_top - 80:
            break
        cost = int(attack.get("cost") or 1)
        pip_x = 64
        for _ in range(min(3, max(1, cost))):
            _disc(pen, (pip_x, y + 16), 11, theme["accent"])
            _disc(pen, (pip_x, y + 16), 5, (255, 248, 236))
            pip_x += 28
        pen.text((pip_x + 8, y), str(attack.get("name") or "招式"), font=name_font_atk, fill=INK)
        damage = str(attack.get("damage") or "")
        if damage:
            pen.text((684, y - 4), damage, font=_font(SERIF_BOLD, 40), fill=DAMAGE, anchor="rt")
        y += 46
        lines = _wrap(pen, str(attack.get("text") or ""), body_font, 560)[:2]
        if len(_wrap(pen, str(attack.get("text") or ""), body_font, 560)) > 2 and lines:
            lines[-1] = lines[-1][:-1] + "…" if len(lines[-1]) > 1 else "…"
        for line in lines:
            pen.text((64, y), line, font=body_font, fill=MUTED)
            y += 32
        y += 14

    flavor_font = _font(SERIF, 22)
    flavor_lines = _wrap(pen, str(meta.get("flavor") or ""), flavor_font, 600)[:2]
    flavor_y = min(y + 6, 828)
    for line in flavor_lines:
        if flavor_y > footer_top - 28:
            break
        pen.text((64, flavor_y), line, font=flavor_font, fill=(92, 72, 58))
        flavor_y += 30

    pen.line((64, 908, 680, 908), fill=(214, 196, 170), width=2)
    foot = _font(SANS, 22)
    tiny = _font(SANS, 18)
    pen.text((64, 924), f"弱点  {meta.get('weakness', '磨损')} ×2", font=foot, fill=INK)
    retreat = int(meta.get("retreat") or 1)
    pen.text((430, 924), "撤退", font=foot, fill=INK)
    rx = 500
    for _ in range(min(4, max(0, retreat))):
        _disc(pen, (rx, 936), 8, theme["accent"])
        rx += 22
    stars = "★" * int(meta.get("rarity_stars") or 1)
    pen.text((684, 924), stars, font=foot, fill=theme["accent"], anchor="rt")
    pen.text((64, 966), f"绘制 · {meta.get('illustrator', '工坊')}", font=tiny, fill=MUTED)
    pen.text((684, 966), f"MG-{meta.get('number', '001')}/150", font=tiny, fill=MUTED, anchor="rt")

    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG", compress_level=4)
    return buffer.getvalue()


def sample_art(kind: str) -> Image.Image:
    """Built-in stand-in photos so the workshop can be tried without a camera."""
    width, height = 960, 640
    scenes = {
        "laptop": ((18, 28, 48), (8, 10, 18), "轻薄笔记本"),
        "keyboard": ((28, 24, 22), (10, 9, 12), "机械键盘"),
        "car": ((18, 16, 28), (6, 6, 12), "夜色跑车"),
    }
    top, bottom, title = scenes.get(kind, scenes["laptop"])
    image = _gradient(width, height, top, bottom).convert("RGBA")
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((180, 40, 820, 520), fill=(255, 196, 120, 80))
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(36)))
    draw = ImageDraw.Draw(image)

    if kind == "keyboard":
        draw.rounded_rectangle((140, 150, 820, 500), radius=28, fill=(42, 36, 34))
        for row in range(5):
            for col in range(14):
                x = 170 + col * 44
                y = 186 + row * 58
                draw.rounded_rectangle((x, y, x + 34, y + 40), radius=5, fill=(232, 214, 190))
        draw.rounded_rectangle((360, 470, 620, 492), radius=6, fill=(232, 214, 190))
    elif kind == "car":
        draw.rectangle((0, 430, width, height), fill=(18, 18, 22))
        draw.polygon([(150, 390), (250, 300), (620, 280), (820, 360), (800, 420), (160, 430)], fill=(176, 36, 42))
        draw.polygon([(280, 308), (400, 250), (600, 246), (640, 300)], fill=(186, 220, 230))
        draw.ellipse((230, 390, 340, 500), fill=(16, 16, 18))
        draw.ellipse((250, 410, 320, 480), fill=(210, 210, 214))
        draw.ellipse((640, 380, 760, 500), fill=(16, 16, 18))
        draw.ellipse((662, 402, 738, 478), fill=(210, 210, 214))
        draw.ellipse((700, 330, 748, 360), fill=(255, 220, 140))
    else:
        draw.rounded_rectangle((250, 390, 760, 470), radius=16, fill=(186, 190, 198))
        draw.rounded_rectangle((230, 120, 730, 400), radius=16, fill=(24, 28, 36))
        draw.rounded_rectangle((250, 140, 710, 378), radius=8, fill=(64, 140, 170))
        draw.rectangle((250, 300, 710, 378), fill=(20, 36, 48))
        for col in range(12):
            draw.rectangle((280 + col * 34, 408, 304 + col * 34, 422), fill=(70, 74, 82))

    draw.text((56, 560), title, font=_font(SERIF_BOLD, 36), fill=(255, 244, 226))
    return image.convert("RGB")
