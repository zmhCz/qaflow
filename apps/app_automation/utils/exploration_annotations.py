# -*- coding: utf-8 -*-
"""Screenshot annotation helpers for AI exploratory testing reports."""

from __future__ import annotations

import math
import os
import re
from typing import Iterable

from django.conf import settings


BOUNDS_RE = re.compile(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]')


def build_annotated_screenshot(step) -> str:
    """Return a media-relative screenshot path with the step operation highlighted."""
    source = step.before_screenshot or step.after_screenshot
    if not source:
        return ''

    source_abs = _media_abs_path(source)
    if not os.path.exists(source_abs):
        return ''

    output_rel = f'app-automation/explorations/task_{step.task_id}/annotated_step_{step.step_index}.png'
    output_abs = os.path.join(settings.MEDIA_ROOT, output_rel)

    try:
        if os.path.exists(output_abs) and os.path.getmtime(output_abs) >= os.path.getmtime(source_abs):
            return output_rel.replace('\\', '/')

        from PIL import Image, ImageDraw, ImageFont

        with Image.open(source_abs) as raw_image:
            image = raw_image.convert('RGBA')

        overlay = Image.new('RGBA', image.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)
        font = _safe_font()

        if step.action_type == 'swipe':
            _draw_swipe(draw, image.size, step, font)
        else:
            _draw_tap(draw, image.size, step, font)

        annotated = Image.alpha_composite(image, overlay).convert('RGB')
        os.makedirs(os.path.dirname(output_abs), exist_ok=True)
        annotated.save(output_abs, 'PNG')
        return output_rel.replace('\\', '/')
    except Exception:
        return ''


def parse_bounds(bounds: str) -> tuple[int, int, int, int] | None:
    match = BOUNDS_RE.match(str(bounds or '').strip())
    if not match:
        return None
    return tuple(int(item) for item in match.groups())


def _media_abs_path(path: str) -> str:
    normalized = str(path or '').replace('\\', '/').lstrip('/')
    if os.path.isabs(str(path)):
        return str(path)
    if normalized.startswith('media/'):
        normalized = normalized[len('media/'):]
    return os.path.join(settings.MEDIA_ROOT, normalized)


def _draw_tap(draw, image_size: tuple[int, int], step, font) -> None:
    width, height = image_size
    bounds = parse_bounds(step.bounds)
    if bounds:
        x1, y1, x2, y2 = _clamp_box(bounds, width, height)
    else:
        x = _safe_int(step.x, width // 2)
        y = _safe_int(step.y, height // 2)
        radius = max(32, min(width, height) // 28)
        x1, y1, x2, y2 = _clamp_box((x - radius, y - radius, x + radius, y + radius), width, height)

    stroke = max(4, min(width, height) // 120)
    draw.rounded_rectangle(
        (x1, y1, x2, y2),
        radius=10,
        outline=(239, 68, 68, 245),
        width=stroke,
        fill=(239, 68, 68, 42),
    )
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    cross = max(10, stroke * 3)
    draw.line((cx - cross, cy, cx + cross, cy), fill=(239, 68, 68, 245), width=max(2, stroke // 2))
    draw.line((cx, cy - cross, cx, cy + cross), fill=(239, 68, 68, 245), width=max(2, stroke // 2))
    _draw_label(draw, (x1, max(0, y1 - 34)), '点击位置', font)


def _draw_swipe(draw, image_size: tuple[int, int], step, font) -> None:
    width, height = image_size
    raw = step.raw or {}
    start = _point(raw.get('start')) or (_safe_int(step.x, width // 2), _safe_int(step.y, int(height * 0.75)))
    end = _point(raw.get('end')) or (start[0], max(24, start[1] - int(height * 0.42)))
    start = _clamp_point(start, width, height)
    end = _clamp_point(end, width, height)

    stroke = max(6, min(width, height) // 90)
    draw.line((*start, *end), fill=(37, 99, 235, 245), width=stroke)
    _draw_arrow_head(draw, start, end, stroke)
    _draw_label(draw, (min(start[0], end[0]), max(0, min(start[1], end[1]) - 38)), '滑动方向', font, color=(37, 99, 235, 245))


def _draw_arrow_head(draw, start: tuple[int, int], end: tuple[int, int], stroke: int) -> None:
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    size = max(20, stroke * 4)
    points = [end]
    for delta in (math.pi * 0.82, -math.pi * 0.82):
        points.append((
            int(end[0] + size * math.cos(angle + delta)),
            int(end[1] + size * math.sin(angle + delta)),
        ))
    draw.polygon(points, fill=(37, 99, 235, 245))


def _draw_label(draw, xy: tuple[int, int], text: str, font, color=(239, 68, 68, 245)) -> None:
    x, y = xy
    padding_x = 10
    padding_y = 6
    box = draw.textbbox((x, y), text, font=font)
    draw.rounded_rectangle(
        (x, y, box[2] + padding_x * 2, box[3] + padding_y * 2),
        radius=8,
        fill=(255, 255, 255, 230),
        outline=color,
        width=2,
    )
    draw.text((x + padding_x, y + padding_y), text, font=font, fill=color)


def _safe_font():
    from PIL import ImageFont

    candidates = [
        'C:/Windows/Fonts/msyh.ttc',
        'C:/Windows/Fonts/simhei.ttf',
        'C:/Windows/Fonts/arial.ttf',
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, 22)
            except Exception:
                continue
    return ImageFont.load_default()


def _point(value: object) -> tuple[int, int] | None:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        return None
    items = list(value)
    if len(items) < 2:
        return None
    return _safe_int(items[0], 0), _safe_int(items[1], 0)


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _clamp_point(point: tuple[int, int], width: int, height: int) -> tuple[int, int]:
    return max(0, min(point[0], width - 1)), max(0, min(point[1], height - 1))


def _clamp_box(box: tuple[int, int, int, int], width: int, height: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    x1 = max(0, min(x1, width - 1))
    y1 = max(0, min(y1, height - 1))
    x2 = max(x1 + 1, min(x2, width))
    y2 = max(y1 + 1, min(y2, height))
    return x1, y1, x2, y2
