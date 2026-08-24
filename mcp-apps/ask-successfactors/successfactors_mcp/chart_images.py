"""Short-lived aggregate chart images for Teams Adaptive Card fallbacks."""
from __future__ import annotations

import hashlib
import io
import json
import threading
import time
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    Image = ImageDraw = ImageFont = None


_LOCK = threading.Lock()
_TTL_SECONDS = 900
_MAX_IMAGES = 64
_IMAGES: dict[str, tuple[float, bytes]] = {}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _render_headcount(rows: list[dict[str, Any]], total: int) -> bytes:
    if not HAS_PIL:
        return b""
    rows = rows[:10]
    width, row_height = 900, 58
    height = 120 + row_height * max(1, len(rows)) + 42
    image = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    draw.text((34, 24), "Workforce headcount by department", fill="#242424", font=_font(28, True))
    draw.text((34, 66), f"Total headcount: {total:,}", fill="#616161", font=_font(18))
    maximum = max((int(row.get("headcount", 0)) for row in rows), default=1)
    label_width, bar_width = 280, 450
    colors = ["#6264A7", "#0078D4", "#008272", "#8E562E", "#8764B8", "#038387"]
    for index, row in enumerate(rows):
        y = 116 + index * row_height
        label = str(row.get("department") or "Unassigned")
        if len(label) > 29:
            label = label[:28] + "…"
        count = int(row.get("headcount", 0))
        pct = float(row.get("percentage", 0))
        draw.text((34, y + 8), label, fill="#242424", font=_font(17))
        x = 34 + label_width
        draw.rounded_rectangle((x, y + 8, x + bar_width, y + 34), radius=7, fill="#EDEBE9")
        filled = max(3, round((count / maximum) * bar_width)) if count else 0
        if filled:
            draw.rounded_rectangle((x, y + 8, x + filled, y + 34), radius=7, fill=colors[index % len(colors)])
        draw.text((x + bar_width + 16, y + 8), f"{count:,}  ({pct:g}%)", fill="#242424", font=_font(16, True))
    draw.text((34, height - 30), "Source: SAP SuccessFactors", fill="#616161", font=_font(14))
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def store_headcount_chart(rows: list[dict[str, Any]], total: int) -> str:
    """Render and retain an opaque chart image identifier for fifteen minutes."""
    payload = json.dumps({"rows": rows[:10], "total": total}, sort_keys=True, separators=(",", ":"), default=str)
    chart_id = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    now = time.monotonic()
    with _LOCK:
        existing = _IMAGES.get(chart_id)
        if existing and now - existing[0] < _TTL_SECONDS:
            return chart_id
    image = _render_headcount(rows, total)
    with _LOCK:
        expired = [key for key, (stored, _) in _IMAGES.items() if now - stored >= _TTL_SECONDS]
        for key in expired:
            _IMAGES.pop(key, None)
        if len(_IMAGES) >= _MAX_IMAGES:
            oldest = min(_IMAGES, key=lambda key: _IMAGES[key][0])
            _IMAGES.pop(oldest, None)
        _IMAGES[chart_id] = (now, image)
    return chart_id


def _render_joiners(rows: list[dict[str, Any]], total: int, label_key: str, title: str) -> bytes:
    if not HAS_PIL:
        return b""
    rows = rows[:12]
    width, row_height = 900, 58
    height = 120 + row_height * max(1, len(rows)) + 42
    image = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    draw.text((34, 24), title, fill="#242424", font=_font(28, True))
    draw.text((34, 66), f"Total joiners: {total:,}", fill="#616161", font=_font(18))
    maximum = max((int(row.get("joiners", 0)) for row in rows), default=1)
    label_width, bar_width = 280, 450
    colors = ["#0078D4", "#008272", "#6264A7", "#D83B01", "#8764B8", "#038387"]
    for index, row in enumerate(rows):
        y = 116 + index * row_height
        label = str(row.get(label_key) or "Unknown")
        if len(label) > 29:
            label = label[:28] + "…"
        count = int(row.get("joiners", 0))
        draw.text((34, y + 8), label, fill="#242424", font=_font(17))
        x = 34 + label_width
        draw.rounded_rectangle((x, y + 8, x + bar_width, y + 34), radius=7, fill="#EDEBE9")
        filled = max(3, round((count / maximum) * bar_width)) if count else 0
        if filled:
            draw.rounded_rectangle((x, y + 8, x + filled, y + 34), radius=7, fill=colors[index % len(colors)])
        draw.text((x + bar_width + 16, y + 8), f"{count:,}", fill="#242424", font=_font(16, True))
    if not rows:
        draw.text((34, 126), "No joiners found for this period", fill="#616161", font=_font(18))
    draw.text((34, height - 30), "Source: SAP SuccessFactors", fill="#616161", font=_font(14))
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def store_joiners_chart(rows: list[dict[str, Any]], total: int, label_key: str, title: str) -> str:
    """Render and retain a joiner chart using the same short-lived image store."""
    payload_data = {"kind": "joiners", "rows": rows[:12], "total": total, "label_key": label_key, "title": title}
    payload = json.dumps(payload_data, sort_keys=True, separators=(",", ":"), default=str)
    chart_id = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    now = time.monotonic()
    with _LOCK:
        existing = _IMAGES.get(chart_id)
        if existing and now - existing[0] < _TTL_SECONDS:
            return chart_id
    image = _render_joiners(rows, total, label_key, title)
    with _LOCK:
        expired = [key for key, (stored, _) in _IMAGES.items() if now - stored >= _TTL_SECONDS]
        for key in expired:
            _IMAGES.pop(key, None)
        if len(_IMAGES) >= _MAX_IMAGES:
            oldest = min(_IMAGES, key=lambda key: _IMAGES[key][0])
            _IMAGES.pop(oldest, None)
        _IMAGES[chart_id] = (now, image)
    return chart_id


def get_chart(chart_id: str) -> bytes | None:
    if len(chart_id) != 32 or any(char not in "0123456789abcdef" for char in chart_id):
        return None
    now = time.monotonic()
    with _LOCK:
        item = _IMAGES.get(chart_id)
        if not item or now - item[0] >= _TTL_SECONDS:
            _IMAGES.pop(chart_id, None)
            return None
        return item[1]
