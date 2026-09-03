# -*- coding: utf-8 -*-
"""APP设备管理视图"""
import base64
import os
import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
import logging

from .test_case_views import AppPagination
from ..models import AppDevice
from ..serializers import AppDeviceSerializer
from ..managers.device_manager import DeviceManager
from ..utils.android_source_inspector import enrich_candidate_from_source

logger = logging.getLogger(__name__)

TOUCH_X_PATTERNS = ('ABS_MT_POSITION_X', 'ABS_X')
TOUCH_Y_PATTERNS = ('ABS_MT_POSITION_Y', 'ABS_Y')


def run_adb_command(adb_path: str, device_id: str, args: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    """Run adb command for a specific device."""
    return subprocess.run(
        [adb_path, '-s', device_id, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        timeout=timeout,
    )


def extract_valid_xml(raw_text: str) -> str:
    start = raw_text.find('<?xml')
    end = raw_text.rfind('</hierarchy>')
    if start < 0 or end < 0:
        return ''
    return raw_text[start:end + len('</hierarchy>')]


def dump_ui_xml(adb_path: str, device_id: str, timeout: int = 15) -> str:
    commands = [
        "rm -f /data/local/tmp/uidump.xml /sdcard/uidump.xml >/dev/null 2>&1; uiautomator dump --compressed /data/local/tmp/uidump.xml >/dev/null 2>&1 && cat /data/local/tmp/uidump.xml",
        "rm -f /data/local/tmp/uidump.xml /sdcard/uidump.xml >/dev/null 2>&1; uiautomator dump /data/local/tmp/uidump.xml >/dev/null 2>&1 && cat /data/local/tmp/uidump.xml",
        "rm -f /data/local/tmp/uidump.xml /sdcard/uidump.xml >/dev/null 2>&1; uiautomator dump --compressed /sdcard/uidump.xml >/dev/null 2>&1 && cat /sdcard/uidump.xml",
        "rm -f /data/local/tmp/uidump.xml /sdcard/uidump.xml >/dev/null 2>&1; uiautomator dump /sdcard/uidump.xml >/dev/null 2>&1 && cat /sdcard/uidump.xml",
    ]
    last_error = ''

    for command in commands:
        try:
            result = run_adb_command(
                adb_path,
                device_id,
                ['shell', 'sh', '-c', command],
                timeout=timeout,
            )
            stdout = result.stdout.decode('utf-8', errors='ignore')
            xml_text = extract_valid_xml(stdout)
            if xml_text:
                return xml_text
            last_error = stdout[:200]
        except subprocess.CalledProcessError as exc:  # pragma: no cover - device-specific fallback
            stdout = exc.stdout.decode('utf-8', errors='ignore') if isinstance(exc.stdout, bytes) else str(exc.stdout or '')
            stderr = exc.stderr.decode('utf-8', errors='ignore') if isinstance(exc.stderr, bytes) else str(exc.stderr or '')
            last_error = f'exit={exc.returncode} stdout={stdout[:120]} stderr={stderr[:120]}'
            time.sleep(0.15)
        except Exception as exc:  # pragma: no cover - best effort fallback
            last_error = str(exc)
            time.sleep(0.15)

    raise RuntimeError(f'UI 树抓取失败: {last_error or "未返回有效 XML"}')


def capture_screenshot_bytes(adb_path: str, device_id: str, timeout: int = 12) -> bytes:
    result = run_adb_command(
        adb_path,
        device_id,
        ['exec-out', 'screencap', '-p'],
        timeout=timeout,
    )
    if not result.stdout:
        raise RuntimeError('鎴浘缁撴灉涓虹┖')
    return result.stdout


def capture_screenshot_bytes_safe(adb_path: str, device_id: str, timeout: int = 12) -> bytes:
    strategies = [
        ('exec-out', lambda: run_adb_command(
            adb_path,
            device_id,
            ['exec-out', 'screencap', '-p'],
            timeout=timeout,
        ).stdout),
        ('pull-from-device', lambda: capture_screenshot_via_pull(adb_path, device_id, timeout=timeout + 8)),
    ]
    last_error = 'unknown screenshot error'

    for strategy_name, strategy in strategies:
        try:
            screenshot_bytes = strategy()
            if screenshot_bytes:
                if strategy_name != 'exec-out':
                    logger.warning("设备 %s 截图已回退到备用方案: %s", device_id, strategy_name)
                return screenshot_bytes
            last_error = f'{strategy_name} returned empty bytes'
        except subprocess.CalledProcessError as exc:
            stderr_text = (exc.stderr or b'').decode('utf-8', errors='ignore').strip()
            last_error = f'{strategy_name} failed: {stderr_text or exc}'
            logger.warning("设备 %s 截图方案 %s 失败: %s", device_id, strategy_name, last_error)
        except Exception as exc:  # pragma: no cover - defensive fallback
            last_error = f'{strategy_name} failed: {exc}'
            logger.warning("设备 %s 截图方案 %s 异常: %s", device_id, strategy_name, exc)

    raise RuntimeError(f'截图失败: {last_error}')


def capture_screenshot_via_pull(adb_path: str, device_id: str, timeout: int = 20) -> bytes:
    remote_path = f"/sdcard/testhub_capture_{int(time.time() * 1000)}.png"
    with tempfile.TemporaryDirectory(prefix='testhub_capture_') as temp_dir:
        local_path = os.path.join(temp_dir, 'device_capture.png')
        try:
            run_adb_command(
                adb_path,
                device_id,
                ['shell', 'screencap', '-p', remote_path],
                timeout=timeout,
            )
            run_adb_command(
                adb_path,
                device_id,
                ['pull', remote_path, local_path],
                timeout=timeout,
            )
            with open(local_path, 'rb') as image_file:
                return image_file.read()
        finally:
            try:
                run_adb_command(
                    adb_path,
                    device_id,
                    ['shell', 'rm', '-f', remote_path],
                    timeout=max(5, min(timeout, 10)),
                )
            except Exception:
                logger.debug("设备 %s 远端截图清理失败: %s", device_id, remote_path)


capture_screenshot_bytes = capture_screenshot_bytes_safe


def get_current_focus_info(adb_path: str, device_id: str, timeout: int = 10) -> dict:
    try:
        result = run_adb_command(
            adb_path,
            device_id,
            ['shell', 'dumpsys', 'window', 'windows'],
            timeout=timeout,
        )
        output = result.stdout.decode('utf-8', errors='ignore')
    except Exception:
        output = ''

    patterns = [
        r'mCurrentFocus.+?\s([A-Za-z0-9._$]+)/([A-Za-z0-9._$/]+)',
        r'mFocusedApp.+?\s([A-Za-z0-9._$]+)/([A-Za-z0-9._$/]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, output)
        if match:
            return {
                'package_name': match.group(1),
                'activity': match.group(2),
            }

    return {
        'package_name': '',
        'activity': '',
    }


def get_screen_size(adb_path: str, device_id: str, timeout: int = 8) -> tuple[int, int]:
    result = run_adb_command(
        adb_path,
        device_id,
        ['shell', 'wm', 'size'],
        timeout=timeout,
    )
    output = result.stdout.decode('utf-8', errors='ignore')
    match = re.search(r'Physical size:\s*(\d+)x(\d+)', output)
    if not match:
        raise RuntimeError('鏃犳硶璇嗗埆灞忓箷鍒嗚鲸鐜?')
    return int(match.group(1)), int(match.group(2))


def get_touch_axis_limits(adb_path: str, device_id: str, timeout: int = 10) -> dict:
    try:
        result = run_adb_command(
            adb_path,
            device_id,
            ['shell', 'getevent', '-lp'],
            timeout=timeout,
        )
    except Exception:
        return {}

    output = result.stdout.decode('utf-8', errors='ignore')
    x_limit = None
    y_limit = None

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if 'ABS_MT_POSITION_X' in line or re.search(r'\bABS_X\b', line):
            match = re.search(r'max\s+(\d+)', line)
            if match:
                x_limit = int(match.group(1))
        elif 'ABS_MT_POSITION_Y' in line or re.search(r'\bABS_Y\b', line):
            match = re.search(r'max\s+(\d+)', line)
            if match:
                y_limit = int(match.group(1))
        if x_limit is not None and y_limit is not None:
            return {'max_x': x_limit, 'max_y': y_limit}

    return {}


def parse_touch_input_devices(getevent_output: str) -> list[dict]:
    devices: list[dict] = []
    current: dict | None = None

    for raw_line in str(getevent_output or '').splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        match = re.match(r'add device \d+: (\S+)', stripped)
        if match:
            if current:
                devices.append(current)
            current = {
                'path': match.group(1),
                'name': '',
                'has_mt_x': False,
                'has_mt_y': False,
                'has_abs_x': False,
                'has_abs_y': False,
                'has_tracking_id': False,
                'has_btn_touch': False,
                'has_btn_tool_finger': False,
                'is_direct': False,
            }
            continue

        if current is None:
            continue

        name_match = re.match(r'name:\s+"(.+)"', stripped)
        if name_match:
            current['name'] = name_match.group(1)
            continue

        if 'ABS_MT_POSITION_X' in stripped:
            current['has_mt_x'] = True
        if 'ABS_MT_POSITION_Y' in stripped:
            current['has_mt_y'] = True
        if re.search(r'\bABS_X\b', stripped):
            current['has_abs_x'] = True
        if re.search(r'\bABS_Y\b', stripped):
            current['has_abs_y'] = True
        if 'ABS_MT_TRACKING_ID' in stripped:
            current['has_tracking_id'] = True
        if 'BTN_TOUCH' in stripped:
            current['has_btn_touch'] = True
        if 'BTN_TOOL_FINGER' in stripped:
            current['has_btn_tool_finger'] = True
        if 'INPUT_PROP_DIRECT' in stripped:
            current['is_direct'] = True

    if current:
        devices.append(current)

    return devices


def choose_primary_touch_device(devices: list[dict]) -> str | None:
    if not devices:
        return None

    def score(device: dict) -> tuple[int, int, int, int, int]:
        has_mt_axes = int(bool(device.get('has_mt_x') and device.get('has_mt_y')))
        has_abs_axes = int(bool(device.get('has_abs_x') and device.get('has_abs_y')))
        has_tracking = int(bool(device.get('has_tracking_id')))
        has_touch_key = int(bool(device.get('has_btn_touch') or device.get('has_btn_tool_finger')))
        is_direct = int(bool(device.get('is_direct')))
        return (has_mt_axes, has_tracking, has_touch_key, is_direct, has_abs_axes)

    best = max(devices, key=score)
    if max(score(best)) <= 0:
        return None
    return best.get('path') or None


def get_primary_touch_device_path(adb_path: str, device_id: str, timeout: int = 10) -> str | None:
    try:
        result = run_adb_command(
            adb_path,
            device_id,
            ['shell', 'getevent', '-pl'],
            timeout=timeout,
        )
    except Exception:
        return None

    output = result.stdout.decode('utf-8', errors='ignore')
    devices = parse_touch_input_devices(output)
    return choose_primary_touch_device(devices)


def parse_bounds(bounds_text: str) -> dict:
    match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds_text or '')
    if not match:
        return {'x1': 0, 'y1': 0, 'x2': 0, 'y2': 0, 'width': 0, 'height': 0}

    x1, y1, x2, y2 = map(int, match.groups())
    return {
        'x1': x1,
        'y1': y1,
        'x2': x2,
        'y2': y2,
        'width': max(0, x2 - x1),
        'height': max(0, y2 - y1),
    }


def normalize_selector_text(value: str) -> str:
    return str(value or '').strip()


def selector_text_matches(actual: str, expected: str) -> bool:
    actual_text = normalize_selector_text(actual)
    expected_text = normalize_selector_text(expected)
    if not expected_text:
        return True
    if not actual_text:
        return False
    return actual_text == expected_text or expected_text in actual_text


def rank_candidate_bounds(candidate: dict, selector: dict) -> tuple[int, int, int]:
    selector_bounds = parse_bounds(str(selector.get('bounds') or ''))
    candidate_bounds = parse_bounds(str(candidate.get('raw_bounds') or candidate.get('bounds') or ''))
    if not selector_bounds.get('width') or not candidate_bounds.get('width'):
        return (0, 0, 0)

    sx1, sy1, sx2, sy2 = selector_bounds['x1'], selector_bounds['y1'], selector_bounds['x2'], selector_bounds['y2']
    cx1, cy1, cx2, cy2 = candidate_bounds['x1'], candidate_bounds['y1'], candidate_bounds['x2'], candidate_bounds['y2']

    overlap_width = max(0, min(sx2, cx2) - max(sx1, cx1))
    overlap_height = max(0, min(sy2, cy2) - max(sy1, cy1))
    overlap_area = overlap_width * overlap_height

    selector_center_x = (sx1 + sx2) // 2
    selector_center_y = (sy1 + sy2) // 2
    candidate_center_x = (cx1 + cx2) // 2
    candidate_center_y = (cy1 + cy2) // 2
    center_distance = abs(selector_center_x - candidate_center_x) + abs(selector_center_y - candidate_center_y)

    selector_area = max(1, selector_bounds['width'] * selector_bounds['height'])
    candidate_area = max(1, candidate_bounds['width'] * candidate_bounds['height'])
    area_delta = abs(selector_area - candidate_area)
    return (overlap_area, -center_distance, -area_delta)


def score_selector_candidate(candidate: dict, selector: dict) -> int:
    score = 0
    has_primary_locator = False
    matched_primary_locator = False
    matched_resource_id = False

    resource_id = normalize_selector_text(selector.get('resource_id'))
    if resource_id:
        has_primary_locator = True
        actual = normalize_selector_text(candidate.get('resource_id'))
        tail_actual = actual.split('/')[-1]
        tail_expected = resource_id.split('/')[-1]
        if actual == resource_id or tail_actual == tail_expected:
            score += 12
            matched_primary_locator = True
            matched_resource_id = True
        else:
            return -1

    class_name = normalize_selector_text(selector.get('class'))
    if class_name:
        has_primary_locator = True
        actual = normalize_selector_text(candidate.get('class_name'))
        if actual == class_name or actual.endswith(class_name):
            score += 4
            matched_primary_locator = True
        elif not matched_resource_id:
            return -1

    package_name = normalize_selector_text(selector.get('package'))
    if package_name:
        has_primary_locator = True
        actual = normalize_selector_text(candidate.get('package_name'))
        if actual == package_name:
            score += 2
            matched_primary_locator = True
        elif not matched_resource_id:
            return -1

    text_value = normalize_selector_text(selector.get('text'))
    if text_value:
        if selector_text_matches(candidate.get('text'), text_value) or selector_text_matches(candidate.get('content_desc'), text_value):
            score += 6
            matched_primary_locator = True
        elif not has_primary_locator:
            return -1

    content_desc = normalize_selector_text(selector.get('content_desc'))
    if content_desc:
        if selector_text_matches(candidate.get('content_desc'), content_desc):
            score += 5
            matched_primary_locator = True
        elif not has_primary_locator:
            return -1

    hint_value = normalize_selector_text(selector.get('hint'))
    if hint_value:
        hint_candidates = [candidate.get('hint'), candidate.get('text'), candidate.get('content_desc')]
        if any(selector_text_matches(item, hint_value) for item in hint_candidates):
            score += 3
            matched_primary_locator = True
        elif not has_primary_locator:
            return -1

    enabled = selector.get('enabled')
    if enabled is not None and bool(candidate.get('enabled')) == bool(enabled):
        score += 1

    clickable = selector.get('clickable')
    if clickable is not None and bool(candidate.get('clickable')) == bool(clickable):
        score += 1

    focusable = selector.get('focusable')
    if focusable is not None and bool(candidate.get('focusable')) == bool(focusable):
        score += 1

    if has_primary_locator and not matched_primary_locator:
        return -1

    return score


def find_best_candidate_for_selector(candidates: list[dict], selector: dict) -> tuple[dict | None, int]:
    best_candidate = None
    best_score = -1
    best_bounds_rank = (-1, float('-inf'), float('-inf'))

    for candidate in candidates:
        score = score_selector_candidate(candidate, selector)
        if score < 0:
            continue
        bounds_rank = rank_candidate_bounds(candidate, selector)
        if score > best_score or (score == best_score and bounds_rank > best_bounds_rank):
            best_candidate = candidate
            best_score = score
            best_bounds_rank = bounds_rank

    return best_candidate, best_score


def _parse_getevent_hex_value(line: str) -> int | None:
    match = re.search(r'\b([0-9a-fA-F]{1,8})\s*$', line.strip())
    if not match:
        return None
    return int(match.group(1), 16)


def _normalize_touch_point(raw_x: int, raw_y: int, screen_size: tuple[int, int], axis_limits: dict) -> tuple[int, int]:
    width, height = screen_size
    max_x = axis_limits.get('max_x') or max(width - 1, 1)
    max_y = axis_limits.get('max_y') or max(height - 1, 1)

    if max_x <= 0 or max_y <= 0:
        return raw_x, raw_y

    x = round((raw_x / max_x) * max(width - 1, 1))
    y = round((raw_y / max_y) * max(height - 1, 1))
    return (
        max(0, min(x, max(width - 1, 0))),
        max(0, min(y, max(height - 1, 0))),
    )


def _build_touch_sample(raw_x: int, raw_y: int, screen_size: tuple[int, int], axis_limits: dict) -> dict:
    x, y = _normalize_touch_point(raw_x, raw_y, screen_size, axis_limits)
    return {
        'raw_x': raw_x,
        'raw_y': raw_y,
        'x': x,
        'y': y,
    }


def _append_touch_sample(samples: list[dict], raw_x: int | None, raw_y: int | None, screen_size: tuple[int, int], axis_limits: dict):
    if raw_x is None or raw_y is None:
        return

    sample = _build_touch_sample(raw_x, raw_y, screen_size, axis_limits)
    if samples and samples[-1]['raw_x'] == sample['raw_x'] and samples[-1]['raw_y'] == sample['raw_y']:
        return
    samples.append(sample)


def _build_touch_interaction(samples: list[dict], screen_size: tuple[int, int]) -> dict | None:
    if not samples:
        return None

    start = samples[0]
    end = samples[-1]
    dx = end['x'] - start['x']
    dy = end['y'] - start['y']
    distance = (dx ** 2 + dy ** 2) ** 0.5
    min_dimension = max(1, min(screen_size))
    swipe_threshold = max(24, round(min_dimension * 0.025))
    interaction_type = 'swipe' if distance >= swipe_threshold and len(samples) >= 2 else 'tap'

    return {
        'type': interaction_type,
        'raw_x': end['raw_x'],
        'raw_y': end['raw_y'],
        'x': end['x'],
        'y': end['y'],
        'start_x': start['x'],
        'start_y': start['y'],
        'end_x': end['x'],
        'end_y': end['y'],
        'distance': round(distance, 2),
        'sample_count': len(samples),
        'path': [{'x': point['x'], 'y': point['y']} for point in samples[:20]],
    }


def parse_touch_interaction_from_getevent(output_text: str, screen_size: tuple[int, int], axis_limits: dict) -> dict | None:
    current_x = None
    current_y = None
    touch_started = False
    touch_ended = False
    samples: list[dict] = []

    for raw_line in output_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if any(pattern in line for pattern in TOUCH_X_PATTERNS):
            value = _parse_getevent_hex_value(line)
            if value is not None:
                current_x = value
                if touch_started and current_y is not None:
                    _append_touch_sample(samples, current_x, current_y, screen_size, axis_limits)
            continue

        if any(pattern in line for pattern in TOUCH_Y_PATTERNS):
            value = _parse_getevent_hex_value(line)
            if value is not None:
                current_y = value
                if touch_started and current_x is not None:
                    _append_touch_sample(samples, current_x, current_y, screen_size, axis_limits)
            continue

        if 'BTN_TOUCH' in line or 'BTN_TOOL_FINGER' in line:
            if 'DOWN' in line:
                touch_started = True
                _append_touch_sample(samples, current_x, current_y, screen_size, axis_limits)
            elif 'UP' in line:
                touch_ended = True
        elif 'ABS_MT_TRACKING_ID' in line:
            value = _parse_getevent_hex_value(line)
            if value is not None and value == 0xFFFFFFFF:
                touch_ended = True
            elif value is not None:
                touch_started = True
                _append_touch_sample(samples, current_x, current_y, screen_size, axis_limits)

        if touch_started and current_x is not None and current_y is not None:
            _append_touch_sample(samples, current_x, current_y, screen_size, axis_limits)

        if touch_started and touch_ended and samples:
            return _build_touch_interaction(samples, screen_size)

    return None


def parse_touch_point_from_getevent(output_text: str, screen_size: tuple[int, int], axis_limits: dict) -> dict | None:
    interaction = parse_touch_interaction_from_getevent(output_text, screen_size, axis_limits)
    if not interaction:
        return None
    return {
        'raw_x': interaction['raw_x'],
        'raw_y': interaction['raw_y'],
        'x': interaction['x'],
        'y': interaction['y'],
    }


def parse_accessibility_event_line(line: str) -> dict | None:
    raw = str(line or '').strip()
    if not raw or 'EventType:' not in raw:
        return None

    event_type_match = re.search(r'EventType:\s*([A-Z_]+)', raw)
    if not event_type_match:
        return None

    def extract(pattern: str) -> str:
        match = re.search(pattern, raw)
        if not match:
            return ''
        value = match.group(1).strip()
        return '' if value == 'null' else value

    text_match = re.search(r'Text:\s*\[(.*?)\]', raw)
    text_values = []
    if text_match:
        text_values = [item.strip() for item in text_match.group(1).split(',') if item.strip()]

    return {
        'event_type': event_type_match.group(1),
        'package_name': extract(r'PackageName:\s*([^;]+)'),
        'class_name': extract(r'ClassName:\s*([^;]+)'),
        'content_desc': extract(r'ContentDescription:\s*([^;]+)'),
        'before_text': extract(r'BeforeText:\s*([^;]+)'),
        'scroll_x': extract(r'ScrollX:\s*(-?\d+)'),
        'scroll_y': extract(r'ScrollY:\s*(-?\d+)'),
        'max_scroll_x': extract(r'MaxScrollX:\s*(-?\d+)'),
        'max_scroll_y': extract(r'MaxScrollY:\s*(-?\d+)'),
        'scroll_delta_x': extract(r'ScrollDeltaX:\s*(-?\d+)'),
        'scroll_delta_y': extract(r'ScrollDeltaY:\s*(-?\d+)'),
        'from_index': extract(r'FromIndex:\s*(-?\d+)'),
        'to_index': extract(r'ToIndex:\s*(-?\d+)'),
        'text_values': text_values,
        'text': text_values[0] if text_values else '',
        'raw_line': raw,
    }


def build_interaction_from_accessibility_event(event: dict | None) -> dict | None:
    if not event:
        return None

    event_type = str(event.get('event_type') or '').strip().upper()
    text_value = str(event.get('text') or '').strip()
    before_text = str(event.get('before_text') or '').strip()

    if event_type == 'TYPE_VIEW_TEXT_CHANGED' and text_value and text_value != before_text:
        return {
            'type': 'input',
            'x': 0,
            'y': 0,
            'text': text_value,
            'before_text': before_text,
            'source': 'accessibility',
            'event': event,
        }

    if event_type == 'TYPE_VIEW_SCROLLED':
        return {
            'type': 'swipe',
            'x': 0,
            'y': 0,
            'source': 'accessibility',
            'event': event,
        }

    if event_type in {
        'TYPE_VIEW_CLICKED',
        'TYPE_VIEW_FOCUSED',
        'TYPE_VIEW_SELECTED',
        'TYPE_VIEW_TEXT_SELECTION_CHANGED',
        'TYPE_WINDOW_STATE_CHANGED',
        'TYPE_WINDOW_CONTENT_CHANGED',
    }:
        return {
            'type': 'tap',
            'x': 0,
            'y': 0,
            'source': 'accessibility',
            'event': event,
        }

    return None


def wait_for_next_accessibility_interaction(adb_path: str, device_id: str, timeout: int = 6) -> dict | None:
    deadline = time.monotonic() + timeout
    last_output = ''

    while time.monotonic() < deadline:
        remaining = max(1, int(deadline - time.monotonic()))
        try:
            result = run_adb_command(
                adb_path,
                device_id,
                ['shell', 'uiautomator', 'events'],
                timeout=min(remaining, 2),
            )
            output_text = result.stdout.decode('utf-8', errors='ignore')
        except subprocess.TimeoutExpired as exc:
            timeout_output = getattr(exc, 'stdout', b'')
            if isinstance(timeout_output, bytes):
                output_text = timeout_output.decode('utf-8', errors='ignore')
            else:
                output_text = str(timeout_output or '')
        except Exception:
            return None

        if not output_text.strip():
            continue

        last_output = output_text
        events = [
            parse_accessibility_event_line(line)
            for line in output_text.splitlines()
        ]
        events = [item for item in events if item]
        for event in reversed(events):
            interaction = build_interaction_from_accessibility_event(event)
            if interaction:
                interaction['debug_output'] = last_output[:500]
                return interaction

    return None


def wait_for_next_touch(adb_path: str, device_id: str, timeout: int = 30) -> dict:
    deadline = time.monotonic() + timeout
    screen_size = get_screen_size(adb_path, device_id)
    axis_limits = get_touch_axis_limits(adb_path, device_id)
    touch_device_path = get_primary_touch_device_path(adb_path, device_id)
    last_output = ''

    while time.monotonic() < deadline:
        remaining = max(1, int(deadline - time.monotonic()))
        command = ['shell', 'getevent', '-qlt']
        if touch_device_path:
            command.append(touch_device_path)
        try:
            result = run_adb_command(
                adb_path,
                device_id,
                command,
                timeout=min(remaining, 2),
            )
        except subprocess.TimeoutExpired as exc:
            output_text = ''
            timeout_output = getattr(exc, 'stdout', b'')
            if timeout_output:
                if isinstance(timeout_output, bytes):
                    output_text = timeout_output.decode('utf-8', errors='ignore')
                else:
                    output_text = str(timeout_output)
                last_output = output_text
                interaction = parse_touch_interaction_from_getevent(output_text, screen_size, axis_limits)
                if interaction:
                    return interaction
            continue

        output_text = result.stdout.decode('utf-8', errors='ignore')
        if not output_text.strip():
            continue

        last_output = output_text
        interaction = parse_touch_interaction_from_getevent(output_text, screen_size, axis_limits)
        if interaction:
            return interaction

    accessibility_interaction = wait_for_next_accessibility_interaction(
        adb_path,
        device_id,
        timeout=max(2, min(timeout, 6)),
    )
    if accessibility_interaction:
        return accessibility_interaction

    raise TimeoutError(f'绛夊緟鎵嬪姩鐐瑰嚮瓒呮椂: {last_output[:200]}')


def extract_element_candidates(xml_text: str) -> tuple[int, list[dict]]:
    root = ET.fromstring(xml_text)
    candidates: list[dict] = []
    seen: set[tuple] = set()
    node_count = 0

    ignored_classes = {
        'android.widget.FrameLayout',
        'android.widget.LinearLayout',
        'android.widget.RelativeLayout',
        'android.widget.ScrollView',
        'android.view.ViewGroup',
    }

    for node in root.iter('node'):
        node_count += 1
        attrs = node.attrib
        resource_id = (attrs.get('resource-id') or '').strip()
        text = (attrs.get('text') or '').strip()
        content_desc = (attrs.get('content-desc') or '').strip()
        hint = (attrs.get('hint') or '').strip()
        class_name = (attrs.get('class') or '').strip()
        package_name = (attrs.get('package') or '').strip()
        clickable = attrs.get('clickable') == 'true'
        focusable = attrs.get('focusable') == 'true'
        focused = attrs.get('focused') == 'true'
        checkable = attrs.get('checkable') == 'true'
        checked = attrs.get('checked') == 'true'
        long_clickable = attrs.get('long-clickable') == 'true'
        scrollable = attrs.get('scrollable') == 'true'
        selected = attrs.get('selected') == 'true'
        enabled = attrs.get('enabled') == 'true'

        if not enabled:
            continue

        has_locator_signal = any([resource_id, text, content_desc, hint])
        has_interaction_signal = any([clickable, focusable, checkable, long_clickable, scrollable])
        if not has_locator_signal and not has_interaction_signal:
            continue

        if class_name in ignored_classes and not has_locator_signal:
            continue

        bounds = parse_bounds(attrs.get('bounds', ''))
        dedupe_key = (
            resource_id,
            text,
            content_desc,
            hint,
            class_name,
            bounds['x1'],
            bounds['y1'],
            bounds['x2'],
            bounds['y2'],
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        short_class = class_name.split('.')[-1] if class_name else ''
        locator_name = resource_id.split('/')[-1] if '/' in resource_id else resource_id
        display_text = text or content_desc or hint or locator_name or short_class or '未命名元素'

        candidates.append({
            'name': display_text[:80],
            'description': f'{short_class or "Node"} | {locator_name or "-"}',
            'package_name': package_name,
            'class_name': class_name,
            'resource_id': resource_id,
            'text': text,
            'content_desc': content_desc,
            'hint': hint,
            'clickable': clickable,
            'focusable': focusable,
            'focused': focused,
            'checkable': checkable,
            'checked': checked,
            'long_clickable': long_clickable,
            'scrollable': scrollable,
            'selected': selected,
            'bounds': bounds,
            'raw_bounds': attrs.get('bounds', ''),
        })

    candidates.sort(
        key=lambda item: (
            not bool(item['resource_id']),
            not bool(item['text'] or item['content_desc'] or item['hint']),
            item['bounds']['y1'],
            item['bounds']['x1'],
        )
    )
    return node_count, candidates[:150]


def enrich_candidates_with_source(candidates: list[dict], activity_name: str) -> list[dict]:
    enriched: list[dict] = []
    for candidate in candidates:
        source_info = enrich_candidate_from_source(candidate, activity_name=activity_name)
        enriched.append({
            **candidate,
            **source_info,
        })
    return enriched


def capture_page_state_payload(
    adb_path: str,
    device_id: str,
    timestamp: int | None = None,
    include_screenshot: bool = True,
) -> dict:
    screenshot_bytes = b''
    if include_screenshot:
        screenshot_bytes = capture_screenshot_bytes(adb_path, device_id, timeout=12)
    xml_text = dump_ui_xml(adb_path, device_id, timeout=18)
    page_info = get_current_focus_info(adb_path, device_id, timeout=8)
    node_count, candidates = extract_element_candidates(xml_text)
    candidates = enrich_candidates_with_source(candidates, page_info.get('activity', ''))
    event_timestamp = timestamp or int(timezone.now().timestamp())
    image_base64 = base64.b64encode(screenshot_bytes).decode('utf-8') if screenshot_bytes else ''
    hotzone_count = sum(1 for item in candidates if item.get('is_hotzone'))
    return {
        'filename': f"page_state_{device_id}_{event_timestamp}.png",
        'content': f"data:image/png;base64,{image_base64}" if image_base64 else '',
        'device_id': device_id,
        'timestamp': event_timestamp,
        'package_name': page_info.get('package_name', ''),
        'activity': page_info.get('activity', ''),
        'ui_xml': xml_text,
        'node_count': node_count,
        'candidate_count': len(candidates),
        'hotzone_count': hotzone_count,
        'candidates': candidates,
    }


def find_candidate_by_point(candidates: list[dict], x: int, y: int) -> dict | None:
    matched: list[dict] = []
    nearest: list[dict] = []
    for candidate in candidates:
        bounds = candidate.get('bounds') or {}
        x1 = int(bounds.get('x1') or 0)
        y1 = int(bounds.get('y1') or 0)
        x2 = int(bounds.get('x2') or 0)
        y2 = int(bounds.get('y2') or 0)
        area = max(1, (x2 - x1) * (y2 - y1))
        if x1 <= x <= x2 and y1 <= y <= y2:
            matched.append({
                **candidate,
                '_area': area,
            })
        else:
            dx = max(x1 - x, 0, x - x2)
            dy = max(y1 - y, 0, y - y2)
            nearest.append({
                **candidate,
                '_distance': dx + dy,
                '_area': area,
            })

    priority = find_text_or_resource_candidate_by_point(matched, nearest, x, y)
    if priority:
        return priority

    if matched:
        matched.sort(key=lambda item: score_point_candidate(item, x, y), reverse=True)
        best = dict(matched[0])
        if is_generic_container_candidate(best):
            nearby = [
                item
                for item in nearest
                if item['_distance'] <= 96 and not is_generic_container_candidate(item)
            ]
            if nearby:
                nearby.sort(key=lambda item: score_point_candidate(item, x, y, prefer_distance=True), reverse=True)
                best = dict(nearby[0])
                best.pop('_distance', None)
        best.pop('_area', None)
        return best

    nearest = [item for item in nearest if item['_distance'] <= 48]
    if not nearest:
        return None

    nearest.sort(key=lambda item: score_point_candidate(item, x, y, prefer_distance=True), reverse=True)
    best = dict(nearest[0])
    best.pop('_distance', None)
    best.pop('_area', None)
    return best


def find_text_or_resource_candidate_by_point(matched: list[dict], nearest: list[dict], x: int, y: int) -> dict | None:
    text_matched = [
        item for item in matched
        if candidate_has_visible_text(item) and not is_generic_container_candidate(item)
    ]
    if text_matched:
        text_matched.sort(key=lambda item: score_text_priority_candidate(item, x, y), reverse=True)
        return clean_scored_candidate(text_matched[0])

    resource_matched = [
        item for item in matched
        if str(item.get('resource_id') or '').strip()
        and not is_generic_container_candidate(item)
    ]
    if resource_matched:
        resource_matched.sort(key=lambda item: score_point_candidate(item, x, y), reverse=True)
        return clean_scored_candidate(resource_matched[0])

    nearby_text = [
        item for item in nearest
        if item.get('_distance', 9999) <= 96
        and candidate_has_visible_text(item)
        and not is_generic_container_candidate(item)
    ]
    if nearby_text:
        nearby_text.sort(key=lambda item: score_text_priority_candidate(item, x, y, prefer_distance=True), reverse=True)
        return clean_scored_candidate(nearby_text[0])

    return None


def candidate_has_visible_text(candidate: dict | None) -> bool:
    if not candidate:
        return False
    return bool(
        str(candidate.get('text') or '').strip()
        or str(candidate.get('content_desc') or '').strip()
        or str(candidate.get('hint') or '').strip()
    )


def score_text_priority_candidate(candidate: dict, x: int, y: int, prefer_distance: bool = False) -> tuple:
    bounds = candidate.get('bounds') or {}
    x1 = int(bounds.get('x1') or 0)
    y1 = int(bounds.get('y1') or 0)
    x2 = int(bounds.get('x2') or 0)
    y2 = int(bounds.get('y2') or 0)
    width = max(0, x2 - x1)
    height = max(0, y2 - y1)
    area = int(candidate.get('_area') or max(1, width * height))
    center_distance = abs(((x1 + x2) // 2) - x) + abs(((y1 + y2) // 2) - y)
    role = str(candidate.get('interaction_role') or '').strip().lower()
    class_name = str(candidate.get('class_name') or '').strip().lower()
    resource_id = str(candidate.get('resource_id') or '').strip().lower()
    button_words = ('cancel', 'confirm', 'ok', 'logout', 'exit', '退出', '取消', '确认', '確定')
    role_score = {
        'button': 5,
        'option': 4,
        'entry': 4,
        'tab': 4,
        'checkbox': 4,
        'switch': 4,
        'input': 3,
        'clickable': 3,
        'focusable': 2,
    }.get(role, 0)

    return (
        role_score,
        1 if any(word in resource_id for word in button_words) else 0,
        1 if any(word in str(candidate.get('text') or candidate.get('content_desc') or candidate.get('hint') or '') for word in button_words) else 0,
        1 if 'textview' in class_name or 'button' in class_name else 0,
        1 if candidate.get('resource_id') else 0,
        -int(candidate.get('_distance') or 0) if prefer_distance else 0,
        -center_distance,
        -abs(width - 120),
        -abs(height - 56),
        -area,
    )


def clean_scored_candidate(candidate: dict) -> dict:
    cleaned = dict(candidate)
    cleaned.pop('_distance', None)
    cleaned.pop('_area', None)
    return cleaned


def is_generic_container_candidate(candidate: dict | None) -> bool:
    if not candidate:
        return False

    interaction_role = str(candidate.get('interaction_role') or '').strip().lower()
    if interaction_role in {'input', 'button', 'checkbox', 'switch', 'slider', 'tab', 'option', 'entry', 'search', 'rich_text'}:
        return False

    class_name = str(candidate.get('class_name') or '').strip().lower()
    resource_id = str(candidate.get('resource_id') or '').strip().lower()
    has_content = bool(candidate.get('text') or candidate.get('content_desc') or candidate.get('hint'))
    generic_markers = (
        'drawerlayout',
        'recyclerview',
        'listview',
        'gridview',
        'scrollview',
        'nestedscrollview',
        'viewpager',
        'viewgroup',
        'framelayout',
        'linearlayout',
        'relativelayout',
        'constraintlayout',
    )

    decorative_markers = (
        'background',
        'bg',
        'mask',
        'cover',
        'banner',
        'placeholder',
        'divider',
        'shadow',
        'overlay',
        'ivbackground',
        'backgroundimage',
    )

    if resource_id in {'android:id/content', 'android:id/decor_content_parent'}:
        return True
    if resource_id.endswith(':id/content') or resource_id.endswith('/content'):
        return True
    if 'decorview' in class_name:
        return True
    if any(marker in resource_id for marker in decorative_markers) and interaction_role not in {'button', 'checkbox', 'switch', 'tab', 'option', 'entry'}:
        return True
    if 'drawerlayout' in class_name or resource_id.endswith('/drawerlayout') or resource_id.endswith(':id/drawerlayout'):
        return True
    if candidate.get('scrollable'):
        return True
    if not has_content and any(marker in class_name for marker in generic_markers):
        return True
    return False


def score_point_candidate(candidate: dict, x: int, y: int, prefer_distance: bool = False) -> tuple:
    bounds = candidate.get('bounds') or {}
    x1 = int(bounds.get('x1') or 0)
    y1 = int(bounds.get('y1') or 0)
    x2 = int(bounds.get('x2') or 0)
    y2 = int(bounds.get('y2') or 0)
    center_x = (x1 + x2) // 2
    center_y = (y1 + y2) // 2
    center_distance = abs(center_x - x) + abs(center_y - y)
    area = int(candidate.get('_area') or max(1, (x2 - x1) * (y2 - y1)))
    width = max(0, x2 - x1)
    height = max(0, y2 - y1)

    interaction_role = str(candidate.get('interaction_role') or '').strip().lower()
    source_confidence = str(candidate.get('source_confidence') or '').strip().lower()
    class_name = str(candidate.get('class_name') or '').strip().lower()
    resource_id = str(candidate.get('resource_id') or '').strip().lower()
    has_label = bool(candidate.get('text') or candidate.get('content_desc') or candidate.get('hint') or candidate.get('name'))
    is_generic = is_generic_container_candidate(candidate)
    is_drawer = 'drawerlayout' in class_name or resource_id.endswith('/drawerlayout') or resource_id.endswith(':id/drawerlayout')
    is_system_root = resource_id in {'android:id/content', 'android:id/decor_content_parent'}
    is_system_root = is_system_root or resource_id.endswith(':id/content') or resource_id.endswith('/content')
    is_system_root = is_system_root or 'decorview' in class_name
    decorative_markers = (
        'background',
        'bg',
        'mask',
        'cover',
        'banner',
        'placeholder',
        'divider',
        'shadow',
        'overlay',
        'ivbackground',
        'backgroundimage',
    )
    is_decorative = any(marker in resource_id for marker in decorative_markers) and interaction_role not in {'button', 'checkbox', 'switch', 'tab', 'option', 'entry'}
    is_large_unlabeled = area >= 800000 and not has_label
    role_score = {
        'input': 5,
        'button': 4,
        'checkbox': 4,
        'switch': 4,
        'tab': 4,
        'option': 4,
        'entry': 4,
        'search': 4,
        'slider': 3,
        'rich_text': 3,
        'clickable': 3,
        'focusable': 2,
        'unknown': 1,
    }.get(interaction_role, 0)
    confidence_score = {
        'high': 2,
        'medium': 1,
    }.get(source_confidence, 0)

    return (
        0 if is_system_root else 1,
        0 if is_drawer else 1,
        0 if is_decorative else 1,
        0 if is_generic else 1,
        0 if is_large_unlabeled else 1,
        1 if is_input_like_candidate(candidate) else 0,
        role_score,
        1 if has_label else 0,
        1 if candidate.get('is_hotzone') else 0,
        confidence_score,
        1 if candidate.get('resource_id') and not is_generic else 0,
        -int(candidate.get('_distance') or 0) if prefer_distance else 0,
        -center_distance,
        -abs(width - 160) if has_label else -width,
        -abs(height - 80) if has_label else -height,
        -area,
    )


def find_candidate_by_accessibility_event(candidates: list[dict], event: dict | None) -> dict | None:
    if not candidates or not event:
        return None

    event_class = str(event.get('class_name') or '').strip().lower()
    event_package = str(event.get('package_name') or '').strip()
    event_text = str(event.get('text') or '').strip()
    event_desc = str(event.get('content_desc') or '').strip()
    event_type = str(event.get('event_type') or '').strip().upper()

    ranked: list[tuple[int, dict]] = []
    for candidate in candidates:
        score = 0
        candidate_class = str(candidate.get('class_name') or '').strip().lower()
        candidate_package = str(candidate.get('package_name') or '').strip()
        candidate_text = str(candidate.get('text') or '').strip()
        candidate_desc = str(candidate.get('content_desc') or '').strip()
        candidate_hint = str(candidate.get('hint') or '').strip()

        if event_package and candidate_package == event_package:
            score += 2
        if event_class and (candidate_class == event_class or candidate_class.endswith(event_class.split('.')[-1])):
            score += 6
        if event_text:
            if selector_text_matches(candidate_text, event_text):
                score += 8
            elif selector_text_matches(candidate_hint, event_text):
                score += 6
            elif selector_text_matches(candidate_desc, event_text):
                score += 5
        if event_desc and selector_text_matches(candidate_desc, event_desc):
            score += 6
        if event_type == 'TYPE_VIEW_TEXT_CHANGED' and is_input_like_candidate(candidate):
            score += 10
        if candidate.get('resource_id'):
            score += 1
        if candidate.get('is_hotzone'):
            score += 1

        if score > 0:
            ranked.append((score, candidate))

    if not ranked:
        return None

    ranked.sort(
        key=lambda item: (
            item[0],
            0 if is_generic_container_candidate(item[1]) else 1,
            1 if item[1].get('resource_id') else 0,
        ),
        reverse=True,
    )
    return ranked[0][1]


def candidate_identity_key(candidate: dict | None) -> tuple[str, str, str]:
    if not candidate:
        return ('', '', '')
    return (
        str(candidate.get('resource_id') or '').strip(),
        str(candidate.get('class_name') or '').strip(),
        str(candidate.get('raw_bounds') or '').strip(),
    )


def candidate_center(candidate: dict | None) -> tuple[int, int]:
    bounds = (candidate or {}).get('bounds') or {}
    x1 = int(bounds.get('x1') or 0)
    y1 = int(bounds.get('y1') or 0)
    x2 = int(bounds.get('x2') or 0)
    y2 = int(bounds.get('y2') or 0)
    if x2 <= x1 or y2 <= y1:
        return (0, 0)
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def build_touch_point_from_candidate(candidate: dict | None, interaction_type: str = 'tap') -> dict:
    x, y = candidate_center(candidate)
    return {
        'type': interaction_type,
        'x': x,
        'y': y,
        'start_x': x,
        'start_y': y,
        'end_x': x,
        'end_y': y,
        'distance': 0,
        'sample_count': 1,
        'path': [{'x': x, 'y': y}] if x or y else [],
        'source': 'ui_state_diff',
    }


def build_page_state_signature(payload: dict | None) -> tuple:
    payload = payload or {}
    candidates = payload.get('candidates') or []
    snapshot = tuple(
        (
            candidate_identity_key(candidate),
            str(candidate.get('text') or '').strip(),
            str(candidate.get('content_desc') or '').strip(),
            str(candidate.get('hint') or '').strip(),
            bool(candidate.get('focused')),
            bool(candidate.get('selected')),
            bool(candidate.get('checked')),
        )
        for candidate in candidates[:150]
    )
    return (
        str(payload.get('package_name') or '').strip(),
        str(payload.get('activity') or '').strip(),
        snapshot,
    )


def page_state_changed(before_payload: dict | None, after_payload: dict | None) -> bool:
    return build_page_state_signature(before_payload) != build_page_state_signature(after_payload)


def _newly_true_candidate(before_candidates: list[dict], after_candidates: list[dict], field: str) -> dict | None:
    before_map = {
        candidate_identity_key(candidate): candidate
        for candidate in before_candidates
    }
    matches: list[dict] = []
    for candidate in after_candidates:
        if not candidate.get(field):
            continue
        before_candidate = before_map.get(candidate_identity_key(candidate))
        if before_candidate and before_candidate.get(field):
            continue
        matches.append(candidate)

    if not matches:
        return None

    matches.sort(
        key=lambda item: (
            1 if is_input_like_candidate(item) else 0,
            0 if is_generic_container_candidate(item) else 1,
            1 if item.get('resource_id') else 0,
            1 if item.get('text') or item.get('content_desc') or item.get('hint') else 0,
        ),
        reverse=True,
    )
    return matches[0]


def infer_transition_tap_candidate(before_payload: dict, after_payload: dict) -> dict | None:
    before_candidates = before_payload.get('candidates') or []
    after_candidates = after_payload.get('candidates') or []
    prominent_after_texts = [
        str(candidate.get('text') or candidate.get('content_desc') or candidate.get('hint') or '').strip()
        for candidate in sorted(
            after_candidates,
            key=lambda item: (
                int((item.get('bounds') or {}).get('y1') or 0),
                int((item.get('bounds') or {}).get('x1') or 0),
            )
        )[:12]
        if str(candidate.get('text') or candidate.get('content_desc') or candidate.get('hint') or '').strip()
    ]
    if not prominent_after_texts:
        return None

    ranked: list[tuple[int, dict]] = []
    for candidate in before_candidates:
        label = str(candidate.get('text') or candidate.get('content_desc') or candidate.get('hint') or '').strip()
        if not label:
            continue
        score = 0
        for target_text in prominent_after_texts:
            if label == target_text:
                score = max(score, 12)
            elif label in target_text or target_text in label:
                score = max(score, 8)
        if score <= 0:
            continue
        if candidate.get('is_hotzone'):
            score += 2
        if candidate.get('resource_id'):
            score += 1
        ranked.append((score, candidate))

    if not ranked:
        return None

    ranked.sort(
        key=lambda item: (
            item[0],
            0 if is_generic_container_candidate(item[1]) else 1,
            1 if item[1].get('resource_id') else 0,
        ),
        reverse=True,
    )
    return ranked[0][1]


def infer_interaction_from_page_diff(before_payload: dict, after_payload: dict) -> dict | None:
    before_candidates = before_payload.get('candidates') or []
    after_candidates = after_payload.get('candidates') or []

    inferred_input = infer_text_input_change(
        None,
        before_candidates,
        after_candidates,
    )
    if inferred_input:
        candidate = inferred_input.get('candidate')
        touch_point = build_touch_point_from_candidate(candidate, interaction_type='input')
        touch_point['text'] = inferred_input.get('text', '')
        touch_point['before_text'] = inferred_input.get('before_text', '')
        return {
            'interaction_type': 'input',
            'touch_point': touch_point,
            'matched_candidate': candidate,
            'inferred_input': inferred_input,
        }

    for field in ('focused', 'selected', 'checked'):
        candidate = _newly_true_candidate(before_candidates, after_candidates, field)
        if candidate:
            return {
                'interaction_type': 'tap',
                'touch_point': build_touch_point_from_candidate(candidate, interaction_type='tap'),
                'matched_candidate': candidate,
                'inferred_input': None,
            }

    if (
        str(before_payload.get('activity') or '').strip() != str(after_payload.get('activity') or '').strip() or
        str(before_payload.get('package_name') or '').strip() != str(after_payload.get('package_name') or '').strip()
    ):
        candidate = infer_transition_tap_candidate(before_payload, after_payload)
        if candidate:
            return {
                'interaction_type': 'tap',
                'touch_point': build_touch_point_from_candidate(candidate, interaction_type='tap'),
                'matched_candidate': candidate,
                'inferred_input': None,
            }

    return None


def is_input_like_candidate(candidate: dict | None) -> bool:
    if not candidate:
        return False

    signature = ' '.join(
        str(candidate.get(field) or '')
        for field in ('class_name', 'resource_id', 'text', 'hint', 'content_desc', 'name')
    ).lower()

    keywords = (
        'edittext',
        'textfield',
        'input',
        'search',
        'keyword',
        'phone',
        'mobile',
        'password',
        'pwd',
        'verify',
        'code',
        'email',
        'account',
        'username',
        'name',
        'title',
        'content',
        'desc',
        'description',
        'remark',
        'nickname',
        'communityname',
        'manifesto',
        '名称',
        '标题',
        '内容',
        '简介',
        '描述',
        '备注',
        '昵称',
        '账号',
        '用户名',
        '手机号',
        '验证码',
    )
    return any(keyword in signature for keyword in keywords)


def match_candidate_by_identity(candidates: list[dict], target: dict | None) -> dict | None:
    if not candidates or not target:
        return None

    target_resource = str(target.get('resource_id') or '').strip()
    target_class = str(target.get('class_name') or '').strip()
    target_bounds = str(target.get('raw_bounds') or '').strip()
    target_hint = str(target.get('hint') or '').strip()
    target_desc = str(target.get('content_desc') or '').strip()

    for candidate in candidates:
        if (
            str(candidate.get('resource_id') or '').strip() == target_resource and
            str(candidate.get('class_name') or '').strip() == target_class and
            str(candidate.get('raw_bounds') or '').strip() == target_bounds
        ):
            return candidate

    for candidate in candidates:
        if (
            target_resource and
            str(candidate.get('resource_id') or '').strip() == target_resource and
            str(candidate.get('class_name') or '').strip() == target_class
        ):
            return candidate

    for candidate in candidates:
        if (
            target_class and
            str(candidate.get('class_name') or '').strip() == target_class and
            str(candidate.get('hint') or '').strip() == target_hint and
            str(candidate.get('content_desc') or '').strip() == target_desc
        ):
            return candidate

    return None


def infer_text_input_change(
    before_candidate: dict | None,
    before_candidates: list[dict],
    after_candidates: list[dict],
) -> dict | None:
    candidates_to_check: list[dict] = []
    seen_keys: set[tuple[str, str, str]] = set()

    def push_candidate(candidate: dict | None):
        if not candidate:
            return
        key = (
            str(candidate.get('resource_id') or '').strip(),
            str(candidate.get('class_name') or '').strip(),
            str(candidate.get('raw_bounds') or '').strip(),
        )
        if key in seen_keys:
            return
        seen_keys.add(key)
        candidates_to_check.append(candidate)

    push_candidate(before_candidate)
    for candidate in before_candidates:
        push_candidate(candidate)

    ranked_matches: list[tuple[int, dict]] = []

    for candidate in candidates_to_check:
        after_candidate = match_candidate_by_identity(after_candidates, candidate)
        if not after_candidate:
            continue

        before_text = str(candidate.get('text') or '').strip()
        after_text = str(after_candidate.get('text') or '').strip()

        if after_text and after_text != before_text:
            score = 0
            if candidate is before_candidate:
                score += 40
            if is_input_like_candidate(candidate) or is_input_like_candidate(after_candidate):
                score += 120
            if len(after_text) > len(before_text):
                score += 20
            score += min(len(after_text), 60)
            ranked_matches.append((score, {
                'text': after_text,
                'before_text': before_text,
                'after_text': after_text,
                'candidate': after_candidate,
            }))

    if not ranked_matches:
        return None

    ranked_matches.sort(key=lambda item: item[0], reverse=True)
    return ranked_matches[0][1]


def get_adb_path() -> str:
    """
    获取 ADB 路径：优先使用数据库配置，否则使用默认值 'adb'
    """
    try:
        from ..models import AppTestConfig
        config = AppTestConfig.objects.first()
        return config.adb_path if config else 'adb'
    except Exception as e:
        logger.warning(f"获取 ADB 配置失败，使用默认路径: {e}")
        return 'adb'


class AppDeviceViewSet(viewsets.ModelViewSet):
    """APP设备管理 ViewSet"""
    queryset = AppDevice.objects.all()
    serializer_class = AppDeviceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = AppPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'connection_type']
    search_fields = ['device_id', 'name']

    def get_queryset(self):
        """Hide stale/offline devices by default so the list reflects adb reality."""
        queryset = AppDevice.objects.all().order_by('-updated_at')
        include_offline = str(self.request.query_params.get('include_offline') or '').lower() in {
            '1',
            'true',
            'yes',
        }
        if include_offline:
            return queryset
        return queryset.exclude(status='offline')

    @action(detail=True, methods=['post'], url_path='health-check')
    def health_check(self, request, pk=None):
        """Run a best-effort executable health check for one Android device."""
        device = self.get_object()
        adb_path = get_adb_path()
        checks = []

        def add_check(key, name, passed, message='', detail=None, suggestion=''):
            checks.append({
                'key': key,
                'name': name,
                'passed': bool(passed),
                'message': message,
                'detail': detail or {},
                'suggestion': suggestion,
            })

        def run_check(key, name, func, suggestion=''):
            start_time = time.time()
            try:
                detail = func() or {}
                elapsed_ms = int((time.time() - start_time) * 1000)
                add_check(key, name, True, f'正常，耗时 {elapsed_ms}ms', detail, '')
                return detail
            except subprocess.TimeoutExpired:
                add_check(key, name, False, '检查超时', {}, suggestion or '请检查 USB 调试、设备授权和连接稳定性。')
            except subprocess.CalledProcessError as exc:
                stderr = (exc.stderr or b'').decode('utf-8', errors='ignore').strip()
                stdout = (exc.stdout or b'').decode('utf-8', errors='ignore').strip()
                add_check(
                    key,
                    name,
                    False,
                    stderr or stdout or str(exc),
                    {'returncode': exc.returncode},
                    suggestion or '请重新插拔设备、确认 adb devices 显示为 device 状态。',
                )
            except Exception as exc:
                add_check(key, name, False, str(exc), {}, suggestion)
            return {}

        if device.status == 'offline':
            add_check(
                'adb_state',
                'ADB 连通',
                False,
                '设备在平台中标记为离线',
                {'device_status': device.status},
                '请先点击“刷新设备”，确认 adb devices 能发现该设备。',
            )
            passed_count = 0
            verdict = 'unavailable'
        else:
            run_check(
                'adb_state',
                'ADB 连通',
                lambda: {
                    'state': run_adb_command(adb_path, device.device_id, ['get-state'], timeout=6)
                    .stdout.decode('utf-8', errors='ignore').strip()
                },
                '请确认 USB 调试授权弹窗已允许，或重新插拔数据线。',
            )
            run_check(
                'screen_size',
                '屏幕尺寸',
                lambda: {'size': '%sx%s' % get_screen_size(adb_path, device.device_id, timeout=6)},
                '无法获取屏幕尺寸时，通常是设备连接不稳定或系统服务未响应。',
            )
            run_check(
                'screenshot',
                '截图能力',
                lambda: {'bytes': len(capture_screenshot_bytes(adb_path, device.device_id, timeout=10))},
                '截图失败会影响元素录入、报告截图和探索测试，请优先处理。',
            )
            run_check(
                'ui_xml',
                'UI 树获取',
                lambda: {'xml_length': len(dump_ui_xml(adb_path, device.device_id, timeout=15))},
                'UI 树失败会影响语义元素定位，请确认手机未锁屏且页面可被 uiautomator 读取。',
            )
            focus_info = run_check(
                'foreground_app',
                '前台应用',
                lambda: get_current_focus_info(adb_path, device.device_id, timeout=8),
                '如果前台包名为空，请点亮屏幕并停留在待测 APP 页面。',
            )
            run_check(
                'battery',
                '电量信息',
                lambda: {
                    'battery': run_adb_command(adb_path, device.device_id, ['shell', 'dumpsys', 'battery'], timeout=6)
                    .stdout.decode('utf-8', errors='ignore')[:800]
                },
                '电量信息失败不阻塞执行，但建议确认设备未处于异常省电或断连状态。',
            )

            passed_count = sum(1 for item in checks if item['passed'])
            failed_count = len(checks) - passed_count
            if failed_count == 0:
                verdict = 'executable'
            elif passed_count >= 3:
                verdict = 'needs_attention'
            else:
                verdict = 'unavailable'

        score = int((passed_count / max(len(checks), 1)) * 100)
        verdict_text = {
            'executable': '可执行',
            'needs_attention': '需处理',
            'unavailable': '不可用',
        }.get(verdict, '需处理')
        suggestions = [
            item['suggestion']
            for item in checks
            if not item['passed'] and item.get('suggestion')
        ]

        return Response({
            'code': 0,
            'success': True,
            'msg': '设备健康检查完成',
            'data': {
                'device_id': device.device_id,
                'device_name': device.name or device.device_id,
                'score': score,
                'verdict': verdict,
                'verdict_text': verdict_text,
                'checks': checks,
                'suggestions': suggestions,
                'checked_at': timezone.now().isoformat(),
            }
        })
    
    @action(detail=False, methods=['get'])
    def discover(self, request):
        """发现ADB设备"""
        try:
            adb_path = get_adb_path()
            logger.info(f"使用 ADB 路径: {adb_path}")
            
            manager = DeviceManager(adb_path=adb_path)
            devices_info = manager.list_devices()
            connected_device_ids = {item.get('device_id') for item in devices_info if item.get('device_id')}
            
            # 更新或创建设备记录
            db_devices = []
            for device_info in devices_info:
                # 判断连接类型和 IP 地址
                device_id = device_info['device_id']
                if ':' in device_id:
                    # 远程设备（IP:端口格式）
                    connection_type = 'remote_emulator'
                    ip_address = device_info.get('ip_address') or ''
                elif device_id.startswith('emulator-'):
                    # 本地模拟器 - 使用 localhost
                    connection_type = 'emulator'
                    ip_address = '127.0.0.1'
                else:
                    # USB 连接的真机
                    connection_type = 'usb'
                    ip_address = device_info.get('ip_address') or ''
                
                device, created = AppDevice.objects.update_or_create(
                    device_id=device_info['device_id'],
                    defaults={
                        'name': device_info.get('name') or '',
                        'status': device_info.get('status') or 'offline',
                        'android_version': device_info.get('android_version') or '',
                        'ip_address': ip_address,
                        'port': device_info.get('port') or 5555,
                        'connection_type': connection_type,
                    }
                )
                db_devices.append(device)

            # ADB 当前不可见的本地/真机历史设备不能继续展示为“可用”。
            stale_queryset = (
                AppDevice.objects
                .filter(connection_type__in=['usb', 'emulator', 'real_device'])
                .exclude(device_id__in=connected_device_ids)
                .exclude(status='offline')
            )
            stale_count = stale_queryset.update(status='offline', locked_by=None, locked_at=None)
            
            # 返回序列化后的数据库对象
            return Response({
                'success': True,
                'message': f'发现 {len(db_devices)} 个设备，已隐藏 {stale_count} 个历史离线设备',
                'devices': AppDeviceSerializer(db_devices, many=True).data
            })
        except Exception as e:
            logger.error(f"发现设备失败: {str(e)}")
            return Response({
                'success': False,
                'message': f'发现设备失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'], url_path='page-state')
    def page_state(self, request, pk=None):
        """Capture the current page screenshot and UI hierarchy together."""
        device = self.get_object()

        if device.status == 'offline':
            return Response({
                'code': 400,
                'msg': '设备离线，无法采集当前页',
                'success': False
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            adb_path = get_adb_path()
            payload = capture_page_state_payload(adb_path, device.device_id)
            logger.info(
                "设备 %s 当前页采集成功 package=%s activity=%s candidates=%s",
                device.device_id,
                payload.get('package_name') or '-',
                payload.get('activity') or '-',
                payload.get('candidate_count', 0),
            )
            return Response({
                'code': 0,
                'msg': '当前页面采集成功',
                'success': True,
                'data': payload,
            })
            screenshot_result = run_adb_command(
                adb_path,
                device.device_id,
                ['exec-out', 'screencap', '-p'],
                timeout=12,
            )
            if not screenshot_result.stdout:
                raise RuntimeError('截图结果为空')

            xml_text = dump_ui_xml(adb_path, device.device_id, timeout=18)
            page_info = get_current_focus_info(adb_path, device.device_id, timeout=8)
            node_count, candidates = extract_element_candidates(xml_text)
            candidates = enrich_candidates_with_source(candidates, page_info.get('activity', ''))
            timestamp = int(timezone.now().timestamp())
            image_base64 = base64.b64encode(screenshot_result.stdout).decode('utf-8')
            hotzone_count = sum(1 for item in candidates if item.get('is_hotzone'))

            logger.info(
                "设备 %s 当前页采集成功: package=%s activity=%s candidates=%s",
                device.device_id,
                page_info.get('package_name') or '-',
                page_info.get('activity') or '-',
                len(candidates),
            )

            return Response({
                'code': 0,
                'msg': '当前页采集成功',
                'success': True,
                'data': {
                    'filename': f"page_state_{device.id}_{timestamp}.png",
                    'content': f"data:image/png;base64,{image_base64}",
                    'device_id': device.device_id,
                    'timestamp': timestamp,
                    'package_name': page_info.get('package_name', ''),
                    'activity': page_info.get('activity', ''),
                    'ui_xml': xml_text,
                    'node_count': node_count,
                    'candidate_count': len(candidates),
                    'hotzone_count': hotzone_count,
                    'candidates': candidates,
                }
            })
        except subprocess.TimeoutExpired:
            logger.error("设备 %s 当前页采集超时", device.device_id)
            return Response({
                'code': 500,
                'msg': '当前页采集超时，请检查设备连接状态',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except ET.ParseError as exc:
            logger.error("设备 %s UI 树解析失败: %s", device.device_id, exc)
            return Response({
                'code': 500,
                'msg': f'UI 树解析失败: {exc}',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"设备 {device.device_id} 当前页采集失败: {str(e)}")
            return Response({
                'code': 500,
                'msg': f'当前页采集失败: {str(e)}',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'], url_path='record-next-interaction')
    def record_next_interaction(self, request, pk=None):
        """Wait for the next manual touch and capture before/after page states."""
        device = self.get_object()

        if device.status == 'offline':
            return Response({
                'code': 400,
                'msg': '设备离线，无法记录交互',
                'success': False
            }, status=status.HTTP_400_BAD_REQUEST)

        timeout = int(request.data.get('timeout', 30) or 30)
        post_capture_delay_ms = int(request.data.get('post_capture_delay_ms', 400) or 400)

        try:
            adb_path = get_adb_path()
            before_payload = capture_page_state_payload(adb_path, device.device_id, include_screenshot=False)
            timeout_error = None
            try:
                touch_point = wait_for_next_touch(adb_path, device.device_id, timeout=timeout)
            except TimeoutError as exc:
                timeout_error = exc
                touch_point = None

            if post_capture_delay_ms > 0:
                time.sleep(min(post_capture_delay_ms, 3000) / 1000)

            after_payload = capture_page_state_payload(adb_path, device.device_id, include_screenshot=True)

            if touch_point is None:
                if timeout_error and page_state_changed(before_payload, after_payload):
                    inferred = infer_interaction_from_page_diff(before_payload, after_payload)
                    if inferred:
                        logger.info(
                            "设备 %s 通过页面 diff 补录交互 type=%s candidate=%s",
                            device.device_id,
                            inferred.get('interaction_type') or '-',
                            (inferred.get('matched_candidate') or {}).get('resource_id')
                            or (inferred.get('matched_candidate') or {}).get('name')
                            or '-',
                        )
                        return Response({
                            'code': 0,
                            'msg': '交互记录成功',
                            'success': True,
                            'data': {
                                'device_id': device.device_id,
                                'interaction_type': inferred.get('interaction_type') or 'tap',
                                'touch_point': inferred.get('touch_point') or {},
                                'matched_candidate': inferred.get('matched_candidate'),
                                'inferred_input': inferred.get('inferred_input'),
                                'before': before_payload,
                                'after': after_payload,
                            }
                        })
                raise timeout_error

            event_payload = touch_point.get('event') or {}
            has_coordinates = any(
                touch_point.get(field) not in (None, 0)
                for field in ('x', 'y', 'start_x', 'start_y')
            )

            if has_coordinates:
                match_x = touch_point.get('start_x', touch_point['x'])
                match_y = touch_point.get('start_y', touch_point['y'])
                matched_candidate = find_candidate_by_point(
                    before_payload.get('candidates', []),
                    match_x,
                    match_y,
                )
            else:
                matched_candidate = (
                    find_candidate_by_accessibility_event(before_payload.get('candidates', []), event_payload)
                    or find_candidate_by_accessibility_event(after_payload.get('candidates', []), event_payload)
                )
            inferred_input = infer_text_input_change(
                matched_candidate,
                before_payload.get('candidates', []),
                after_payload.get('candidates', []),
            )
            if not inferred_input and touch_point.get('type') == 'input' and touch_point.get('text'):
                inferred_input = {
                    'text': touch_point.get('text'),
                    'before_text': touch_point.get('before_text', ''),
                    'after_text': touch_point.get('text'),
                    'candidate': matched_candidate,
                }

            logger.info(
                "设备 %s 手动交互已记录 x=%s y=%s before=%s after=%s candidate=%s",
                device.device_id,
                touch_point.get('type') or 'tap',
                touch_point.get('start_x', touch_point['x']),
                touch_point.get('start_y', touch_point['y']),
                touch_point['x'],
                touch_point['y'],
                before_payload.get('activity') or '-',
                after_payload.get('activity') or '-',
                (matched_candidate or {}).get('resource_id') or (matched_candidate or {}).get('name') or '-',
            )

            return Response({
                'code': 0,
                'msg': '交互记录成功',
                'success': True,
                'data': {
                    'device_id': device.device_id,
                    'interaction_type': touch_point.get('type') or 'tap',
                    'touch_point': touch_point,
                    'matched_candidate': matched_candidate,
                    'inferred_input': inferred_input,
                    'before': before_payload,
                    'after': after_payload,
                }
            })
        except TimeoutError as exc:
            return Response({
                'code': 408,
                'msg': str(exc),
                'success': False
            }, status=status.HTTP_408_REQUEST_TIMEOUT)
        except subprocess.TimeoutExpired:
            return Response({
                'code': 500,
                'msg': '交互记录超时，请检查设备连接状态',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except ET.ParseError as exc:
            return Response({
                'code': 500,
                'msg': f'UI 树解析失败: {exc}',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as exc:
            logger.error("设备 %s 交互记录失败: %s", device.device_id, exc)
            return Response({
                'code': 500,
                'msg': f'交互记录失败: {exc}',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def lock(self, request, pk=None):
        """锁定设备"""
        device = self.get_object()
        
        if device.status == 'locked':
            return Response({
                'success': False,
                'message': '设备已被锁定'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        device.lock(request.user)
        
        return Response({
            'success': True,
            'message': '设备锁定成功',
            'device': AppDeviceSerializer(device).data
        })
    
    @action(detail=True, methods=['post'])
    def unlock(self, request, pk=None):
        """释放设备"""
        device = self.get_object()
        
        if device.locked_by and device.locked_by != request.user:
            return Response({
                'success': False,
                'message': '无权释放他人锁定的设备'
            }, status=status.HTTP_403_FORBIDDEN)
        
        device.unlock()
        
        return Response({
            'success': True,
            'message': '设备释放成功',
            'device': AppDeviceSerializer(device).data
        })
    
    @action(detail=True, methods=['post'])
    def disconnect(self, request, pk=None):
        """断开远程设备连接"""
        device = self.get_object()
        
        # 只有远程设备可以断开
        if device.connection_type not in ['remote', 'remote_emulator']:
            return Response({
                'success': False,
                'message': '只能断开远程设备的连接'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            adb_path = get_adb_path()
            manager = DeviceManager(adb_path=adb_path)
            success = manager.disconnect_device(f'{device.ip_address}:{device.port}')
            
            if not success:
                return Response({
                    'success': False,
                    'message': '断开设备失败'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # 更新设备状态为离线
            device.status = 'offline'
            device.save()
            
            return Response({
                'success': True,
                'message': f'设备 {device.name or device.device_id} 已断开连接',
                'device': AppDeviceSerializer(device).data
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'message': f'断开设备失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def connect(self, request):
        """连接远程设备"""
        try:
            ip_address = request.data.get('ip_address')
            port = request.data.get('port', 5555)
            
            if not ip_address:
                return Response({
                    'success': False,
                    'message': '请提供设备IP地址'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            adb_path = get_adb_path()
            manager = DeviceManager(adb_path=adb_path)
            device_info = manager.connect_device(ip_address, port)
            
            # 创建或更新设备记录
            device, created = AppDevice.objects.update_or_create(
                device_id=device_info['device_id'],
                defaults={
                    'name': device_info.get('name') or '',
                    'status': 'online',
                    'android_version': device_info.get('android_version', ''),
                    'ip_address': ip_address,
                    'port': port,
                    'connection_type': 'remote_emulator',
                }
            )
            
            return Response({
                'success': True,
                'message': '设备连接成功',
                'device': AppDeviceSerializer(device).data
            })
        except Exception as e:
            logger.error(f"连接设备失败: {str(e)}")
            return Response({
                'success': False,
                'message': f'连接设备失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'], url_path='validate-selector')
    def validate_selector(self, request, pk=None):
        """Validate whether a selector can still hit the intended element on the live page."""
        device = self.get_object()

        if device.status == 'offline':
            return Response({
                'code': 400,
                'msg': '设备离线，无法验证当前定位',
                'success': False
            }, status=status.HTTP_400_BAD_REQUEST)

        selector = request.data.get('selector') or {}
        if not any(selector.get(key) for key in ('resource_id', 'text', 'content_desc', 'class', 'hint')):
            return Response({
                'code': 400,
                'msg': '缺少可用于验证的定位字段',
                'success': False
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            adb_path = get_adb_path()
            page_payload = capture_page_state_payload(adb_path, device.device_id)
            matched_candidate, score = find_best_candidate_for_selector(page_payload.get('candidates', []), selector)
            matched = matched_candidate is not None

            return Response({
                'code': 0,
                'msg': '定位验证完成',
                'success': True,
                'data': {
                    'matched': matched,
                    'score': score,
                    'matched_candidate': matched_candidate,
                    'page_state': page_payload,
                }
            })
        except subprocess.TimeoutExpired:
            return Response({
                'code': 500,
                'msg': '定位验证超时，请检查设备连接状态',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as exc:
            logger.error("设备 %s 定位验证失败: %s", device.device_id, exc)
            return Response({
                'code': 500,
                'msg': f'定位验证失败: {exc}',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'], url_path='screenshot')
    def screenshot(self, request, pk=None):
        """
        获取设备实时截图
        
        功能：
        1. 使用 adb screencap 获取设备截图
        2. 转换为 Base64
        3. 返回 data URL 格式
        """
        device = self.get_object()
        
        if device.status == 'offline':
            return Response({
                'code': 400,
                'msg': '设备离线，无法截图',
                'success': False
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            adb_path = get_adb_path()
            
            # 使用 adb screencap 命令截图
            screenshot_bytes = capture_screenshot_bytes(adb_path, device.device_id, timeout=10)
            
            if not screenshot_bytes:
                return Response({
                    'code': 500,
                    'msg': '截图失败：无返回数据',
                    'success': False
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # 转换为 Base64
            image_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            logger.info(f"设备 {device.device_id} 截图成功")
            
            return Response({
                'code': 0,
                'msg': '截图成功',
                'success': True,
                'data': {
                    'filename': f"device_{device.id}_{int(timezone.now().timestamp())}.png",
                    'content': f"data:image/png;base64,{image_base64}",
                    'device_id': device.device_id,
                    'timestamp': int(timezone.now().timestamp())
                }
            })
            
        except subprocess.TimeoutExpired:
            logger.error(f"设备 {device.device_id} 截图超时")
            return Response({
                'code': 500,
                'msg': '截图超时，请检查设备连接',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"设备 {device.device_id} 截图失败: {str(e)}")
            return Response({
                'code': 500,
                'msg': f'截图失败: {str(e)}',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
