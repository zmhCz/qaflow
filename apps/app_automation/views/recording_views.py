# -*- coding: utf-8 -*-
"""Action recording APIs for APP automation."""

from __future__ import annotations

import base64
import json
import logging
import re
import subprocess
import threading
import time
import uuid
from typing import Any, Dict, Optional

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..managers.recording_manager import get_recording_manager
from ..models import AppDevice, AppTestCase
from ..serializers import AppTestCaseSerializer
from ..views.device_views import (
    capture_page_state_payload,
    capture_screenshot_bytes,
    find_candidate_by_point,
    get_adb_path,
    get_primary_touch_device_path,
    get_screen_size,
    get_touch_axis_limits,
    infer_interaction_from_page_diff,
    is_input_like_candidate,
    page_state_changed,
    build_interaction_from_accessibility_event,
    build_touch_point_from_candidate,
    parse_accessibility_event_line,
    parse_touch_interaction_from_getevent,
)

logger = logging.getLogger(__name__)


COMPONENT_INPUT_RESOURCE_TAILS = {
    "codeinputbox",
    "edittext",
    "editinput",
    "edcodeinput",
    "inputbox",
    "inputcommunityname",
    "et_number",
    "et_pwd",
    "etpassword",
    "etcontent",
    "editmanifesto",
    "manifesto",
    "tvmsgcontent",
    "chatmessageinput",
}

COMPONENT_INPUT_CLASS_MARKERS = (
    "nncommoninputbox",
    "nnphoneinputbox",
    "nnverifycodeinputbox",
    "nnpasswordinputbox",
    "nnlongtexteditview",
    "fakeinputbox",
    "codeinputedittext",
    "mentionedittext",
)


def ok(data: Optional[Dict[str, Any]] = None, msg: str = "success") -> Response:
    return Response({"code": 0, "msg": msg, "success": True, "data": data or {}})


def fail(msg: str, http_status: int = status.HTTP_400_BAD_REQUEST, code: int = 400) -> Response:
    return Response({"code": code, "msg": msg, "success": False}, status=http_status)


def build_page_signature(payload: Optional[dict]) -> str:
    payload = payload or {}
    candidates = payload.get("candidates") or []
    compact = {
        "package_name": payload.get("package_name") or "",
        "activity": payload.get("activity") or "",
        "candidates": [
            {
                "resource_id": item.get("resource_id") or "",
                "class_name": item.get("class_name") or "",
                "text": item.get("text") or "",
                "content_desc": item.get("content_desc") or "",
                "hint": item.get("hint") or "",
                "raw_bounds": item.get("raw_bounds") or "",
                "focused": bool(item.get("focused")),
                "selected": bool(item.get("selected")),
                "checked": bool(item.get("checked")),
            }
            for item in candidates[:180]
        ],
    }
    return json.dumps(compact, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_detected_interaction_key(interaction: Optional[dict], payload: Optional[dict]) -> str:
    interaction = interaction or {}
    payload = payload or {}
    candidate = interaction.get("matched_candidate") or {}
    inferred_input = interaction.get("inferred_input") or {}
    touch_point = interaction.get("touch_point") or {}
    key_payload = {
        "interaction_type": interaction.get("interaction_type") or "",
        "resource_id": candidate.get("resource_id") or "",
        "class_name": candidate.get("class_name") or "",
        "raw_bounds": candidate.get("raw_bounds") or "",
        "text": inferred_input.get("text") or touch_point.get("text") or "",
        "x": touch_point.get("x"),
        "y": touch_point.get("y"),
        "activity": payload.get("activity") or "",
        "package_name": payload.get("package_name") or "",
    }
    return json.dumps(key_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compact_page_state(payload: Optional[dict]) -> Dict[str, Any]:
    payload = payload or {}
    return {
        "device_id": payload.get("device_id") or "",
        "timestamp": payload.get("timestamp"),
        "package_name": payload.get("package_name") or "",
        "activity": payload.get("activity") or "",
        "node_count": payload.get("node_count") or 0,
        "candidate_count": payload.get("candidate_count") or 0,
        "hotzone_count": payload.get("hotzone_count") or 0,
        "content": payload.get("content") or "",
        "candidates": payload.get("candidates") or [],
    }


def get_session_or_404(session_id: str):
    manager = get_recording_manager()
    session = manager.get_session(session_id)
    if not session:
        return manager, None, fail("recording session not found", status.HTTP_404_NOT_FOUND, 404)
    return manager, session, None


def unlock_session_device(session) -> None:
    try:
        device = AppDevice.objects.get(device_id=session.device_id)
        if device.locked_by == session.user:
            device.unlock()
    except AppDevice.DoesNotExist:
        return


class TouchStreamMonitor:
    """Continuously read getevent and push parsed touch interactions to a session."""

    def __init__(self, session_id: str, adb_path: str, device_id: str):
        self.session_id = session_id
        self.adb_path = adb_path
        self.device_id = device_id
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._process: Optional[subprocess.Popen] = None
        self.last_error = ""

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name=f"touch-recorder-{self.session_id[:8]}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        process = self._process
        if process and process.poll() is None:
            try:
                process.terminate()
            except Exception:
                pass

    def _run(self) -> None:
        manager = get_recording_manager()
        try:
            screen_size = get_screen_size(self.adb_path, self.device_id)
            axis_limits = get_touch_axis_limits(self.adb_path, self.device_id)
            touch_device_path = get_primary_touch_device_path(self.adb_path, self.device_id)
            command = [self.adb_path, "-s", self.device_id, "shell", "getevent", "-qlt"]
            if touch_device_path:
                command.append(touch_device_path)

            logger.info("Starting touch stream monitor: session=%s command=%s", self.session_id, command)
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="ignore",
                bufsize=1,
            )

            buffer: list[str] = []
            while not self._stop.is_set():
                process = self._process
                if not process or process.stdout is None:
                    break

                line = process.stdout.readline()
                if not line:
                    if process.poll() is not None:
                        break
                    time.sleep(0.05)
                    continue

                buffer.append(line)
                if len(buffer) > 220:
                    buffer = buffer[-120:]

                interaction = parse_touch_interaction_from_getevent("".join(buffer), screen_size, axis_limits)
                if not interaction:
                    continue

                interaction["source"] = "touch_stream"
                manager.add_touch_event(self.session_id, interaction)
                buffer = []
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning("Touch stream monitor stopped with error: %s", exc, exc_info=True)
        finally:
            process = self._process
            if process and process.poll() is None:
                try:
                    process.terminate()
                except Exception:
                    pass
            logger.info("Touch stream monitor stopped: session=%s", self.session_id)


_touch_monitors: Dict[str, TouchStreamMonitor] = {}
_touch_monitor_lock = threading.RLock()


class AccessibilityStreamMonitor:
    """Continuously read uiautomator accessibility events for semantic recording."""

    ACCEPTED_EVENT_TYPES = {
        "TYPE_VIEW_CLICKED",
        "TYPE_VIEW_FOCUSED",
        "TYPE_VIEW_TEXT_CHANGED",
        "TYPE_VIEW_SELECTED",
        "TYPE_VIEW_SCROLLED",
    }

    def __init__(self, session_id: str, adb_path: str, device_id: str):
        self.session_id = session_id
        self.adb_path = adb_path
        self.device_id = device_id
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._process: Optional[subprocess.Popen] = None
        self.last_error = ""

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name=f"a11y-recorder-{self.session_id[:8]}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        process = self._process
        if process and process.poll() is None:
            try:
                process.terminate()
            except Exception:
                pass

    def _run(self) -> None:
        manager = get_recording_manager()
        command = [self.adb_path, "-s", self.device_id, "shell", "uiautomator", "events"]
        try:
            logger.info("Starting accessibility stream monitor: session=%s command=%s", self.session_id, command)
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="ignore",
                bufsize=1,
            )

            while not self._stop.is_set():
                process = self._process
                if not process or process.stdout is None:
                    break

                line = process.stdout.readline()
                if not line:
                    if process.poll() is not None:
                        break
                    time.sleep(0.05)
                    continue

                event = parse_accessibility_event_line(line)
                event_type = str((event or {}).get("event_type") or "").strip().upper()
                if not event or event_type not in self.ACCEPTED_EVENT_TYPES:
                    continue

                interaction = build_interaction_from_accessibility_event(event)
                if not interaction:
                    continue

                interaction["source"] = "accessibility_stream"
                manager.add_accessibility_event(self.session_id, interaction)
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning("Accessibility stream monitor stopped with error: %s", exc, exc_info=True)
        finally:
            process = self._process
            if process and process.poll() is None:
                try:
                    process.terminate()
                except Exception:
                    pass
            logger.info("Accessibility stream monitor stopped: session=%s", self.session_id)


_accessibility_monitors: Dict[str, AccessibilityStreamMonitor] = {}
_accessibility_monitor_lock = threading.RLock()


def start_touch_monitor(session_id: str, adb_path: str, device_id: str) -> None:
    with _touch_monitor_lock:
        stop_touch_monitor(session_id)
        monitor = TouchStreamMonitor(session_id, adb_path, device_id)
        _touch_monitors[session_id] = monitor
        monitor.start()


def stop_touch_monitor(session_id: str) -> None:
    monitor = _touch_monitors.pop(session_id, None)
    if monitor:
        monitor.stop()


def start_accessibility_monitor(session_id: str, adb_path: str, device_id: str) -> None:
    with _accessibility_monitor_lock:
        stop_accessibility_monitor(session_id)
        monitor = AccessibilityStreamMonitor(session_id, adb_path, device_id)
        _accessibility_monitors[session_id] = monitor
        monitor.start()


def stop_accessibility_monitor(session_id: str) -> None:
    monitor = _accessibility_monitors.pop(session_id, None)
    if monitor:
        monitor.stop()


def stop_recording_monitors(session_id: str) -> None:
    stop_touch_monitor(session_id)
    stop_accessibility_monitor(session_id)


def clear_pending_recording_events(manager, session_id: str) -> None:
    manager.pop_touch_events(session_id)
    manager.pop_accessibility_events(session_id)


def build_detected_from_touch(touch_event: dict, page_payload: dict) -> dict:
    touch_type = touch_event.get("type") or "tap"
    x = int(touch_event.get("x") or 0)
    y = int(touch_event.get("y") or 0)
    candidates = page_payload.get("candidates") or []
    matched_candidate = find_candidate_by_point(candidates, x, y)
    return {
        "interaction_type": "swipe" if touch_type == "swipe" else "tap",
        "touch_point": {
            **touch_event,
            "type": touch_type,
            "x": x,
            "y": y,
            "start_x": int(touch_event.get("start_x") or x),
            "start_y": int(touch_event.get("start_y") or y),
            "end_x": int(touch_event.get("end_x") or x),
            "end_y": int(touch_event.get("end_y") or y),
        },
        "matched_candidate": matched_candidate,
        "inferred_input": None,
        "source": "touch_stream",
        "confidence": 0.92 if matched_candidate else 0.76,
    }


DIALOG_ACTION_MARKERS = (
    "确认",
    "确定",
    "取消",
    "退出",
    "退出登录",
    "登出",
    "删除",
    "移除",
    "保存",
    "提交",
    "同意",
    "允许",
    "拒绝",
    "cancel",
    "confirm",
    "logout",
    "exit",
    "delete",
    "remove",
    "allow",
    "deny",
)


def candidate_label_signature(candidate: Optional[dict]) -> str:
    if not candidate:
        return ""
    return " ".join(
        str(candidate.get(field) or "").strip().lower()
        for field in ("text", "content_desc", "hint", "name", "resource_id")
    )


def is_dialog_action_candidate(candidate: Optional[dict]) -> bool:
    signature = candidate_label_signature(candidate)
    if not signature:
        return False
    return any(marker.lower() in signature for marker in DIALOG_ACTION_MARKERS)


def is_same_candidate(left: Optional[dict], right: Optional[dict]) -> bool:
    if not left or not right:
        return False
    for field in ("resource_id", "raw_bounds", "text", "content_desc", "hint"):
        left_value = str(left.get(field) or "").strip()
        right_value = str(right.get(field) or "").strip()
        if left_value and right_value and left_value == right_value:
            return True
    return False


def candidate_distance_to_point(candidate: Optional[dict], x: int, y: int) -> int:
    bounds = (candidate or {}).get("bounds") or {}
    x1 = int(bounds.get("x1") or 0)
    y1 = int(bounds.get("y1") or 0)
    x2 = int(bounds.get("x2") or 0)
    y2 = int(bounds.get("y2") or 0)
    if x1 <= x <= x2 and y1 <= y <= y2:
        return 0
    dx = max(x1 - x, 0, x - x2)
    dy = max(y1 - y, 0, y - y2)
    return dx + dy


def find_dialog_action_near_touch(page_payload: Optional[dict], touch_event: dict, max_distance: int = 180) -> Optional[dict]:
    if str(touch_event.get("type") or "tap") != "tap":
        return None
    x = int(touch_event.get("x") or touch_event.get("end_x") or 0)
    y = int(touch_event.get("y") or touch_event.get("end_y") or 0)
    candidates = []
    for candidate in (page_payload or {}).get("candidates") or []:
        if not is_dialog_action_candidate(candidate):
            continue
        distance = candidate_distance_to_point(candidate, x, y)
        if distance <= max_distance:
            candidates.append((distance, candidate))
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            item[0],
            -int(((item[1].get("bounds") or {}).get("width") or 0) * ((item[1].get("bounds") or {}).get("height") or 0)),
        )
    )
    return candidates[0][1]


def replace_detected_candidate(detected: dict, candidate: dict, confidence: float = 0.96) -> dict:
    updated = dict(detected)
    updated["matched_candidate"] = candidate
    updated["confidence"] = max(float(updated.get("confidence") or 0), confidence)
    return updated


def build_detected_from_best_touch_snapshot(
    touch_event: dict,
    current_payload: dict,
    previous_payload: Optional[dict] = None,
    *,
    page_changed: bool = False,
) -> tuple[dict, dict]:
    current_detected = build_detected_from_touch(touch_event, current_payload)
    current_action = find_dialog_action_near_touch(current_payload, touch_event)
    if current_action:
        return replace_detected_candidate(current_detected, current_action), current_payload

    if not page_changed or not previous_payload:
        return current_detected, current_payload

    previous_detected = build_detected_from_touch(touch_event, previous_payload)
    previous_candidate = previous_detected.get("matched_candidate")
    current_candidate = current_detected.get("matched_candidate")
    previous_action = find_dialog_action_near_touch(previous_payload, touch_event)
    if previous_action and not is_same_candidate(previous_action, current_candidate):
        return replace_detected_candidate(previous_detected, previous_action), previous_payload

    # Use the before-click snapshot only for transient dialog actions. Applying
    # it to a whole queued touch batch makes later login/logout steps hit stale
    # controls from the old screen.
    if is_dialog_action_candidate(previous_candidate) and not is_same_candidate(previous_candidate, current_candidate):
        return previous_detected, previous_payload

    return current_detected, current_payload


def resource_tail(resource_id: str) -> str:
    text = str(resource_id or "").strip()
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    if ":" in text:
        text = text.rsplit(":", 1)[-1]
    return text.lower()


def input_candidate_key(candidate: dict) -> str:
    return "|".join(
        str(candidate.get(field) or "").strip()
        for field in ("resource_id", "class_name", "raw_bounds")
    )


def parse_ime_focus_candidate(dumpsys_text: str) -> Optional[dict]:
    text = str(dumpsys_text or "")
    served_matches = list(
        re.finditer(
            r"mServedView=([A-Za-z0-9_.$]+)\{[^}\n]*?(?:#[0-9a-fA-F]+ )?app:id/([A-Za-z0-9_]+)",
            text,
        )
    )
    if not served_matches:
        return None

    served_match = served_matches[-1]
    class_name = served_match.group(1)
    resource_tail_value = served_match.group(2)
    package_matches = re.findall(r"packageName=([A-Za-z0-9_.]+)", text)
    package_name = ""
    for package in reversed(package_matches):
        if package and not package.startswith(("com.baidu.", "io.appium.")):
            package_name = package
            break
    if not package_name:
        package_name = package_matches[-1] if package_matches else ""

    resource_id = f"{package_name}:id/{resource_tail_value}" if package_name else resource_tail_value
    return {
        "resource_id": resource_id,
        "class_name": class_name,
        "text": "",
        "hint": "",
        "content_desc": "",
        "name": resource_tail_value,
        "package_name": package_name,
        "interaction_role": "input",
        "source_confidence": "medium",
        "source_declared_tag": "input_method_focus",
        "bounds": {"x1": 0, "y1": 0, "x2": 0, "y2": 0, "width": 0, "height": 0},
        "raw_bounds": "",
    }


def find_existing_focus_candidate(candidates: list[dict], focus_candidate: dict) -> Optional[dict]:
    focus_resource = str(focus_candidate.get("resource_id") or "").strip()
    focus_tail = resource_tail(focus_resource)
    focus_class = str(focus_candidate.get("class_name") or "").strip().lower()
    for candidate in candidates:
        candidate_resource = str(candidate.get("resource_id") or "").strip()
        if focus_resource and candidate_resource == focus_resource:
            return candidate
        if focus_tail and resource_tail(candidate_resource) == focus_tail:
            return candidate
    for candidate in candidates:
        candidate_class = str(candidate.get("class_name") or "").strip().lower()
        if focus_class and (candidate_class == focus_class or candidate_class.endswith(focus_class.rsplit(".", 1)[-1])):
            if is_input_like_candidate(candidate) or is_component_input_focus_candidate(candidate):
                return candidate
    return None


def get_input_method_focus_candidate(adb_path: str, device_id: str, page_payload: dict) -> Optional[dict]:
    try:
        result = subprocess.run(
            [adb_path, "-s", device_id, "shell", "dumpsys", "input_method"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=5,
        )
    except Exception as exc:
        logger.debug("Failed to read input method focus: %s", exc)
        return None

    focus_candidate = parse_ime_focus_candidate(result.stdout.decode("utf-8", errors="ignore"))
    if not focus_candidate:
        return None

    existing = find_existing_focus_candidate(page_payload.get("candidates") or [], focus_candidate)
    if existing:
        return existing
    return focus_candidate


def is_input_method_shown(adb_path: str, device_id: str) -> bool:
    try:
        result = subprocess.run(
            [adb_path, "-s", device_id, "shell", "dumpsys", "input_method"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=5,
        )
    except Exception:
        return False
    text = result.stdout.decode("utf-8", errors="ignore")
    return "mInputShown=true" in text or "isInputViewShown=true" in text


def build_fallback_page_payload(adb_path: str, session) -> dict:
    screen_width = 0
    screen_height = 0
    try:
        screen_width, screen_height = get_screen_size(adb_path, session.device_id)
    except Exception:
        pass
    return {
        "device_id": session.device_id,
        "timestamp": int(timezone.now().timestamp()),
        "package_name": session.package_name or "",
        "activity": "",
        "node_count": 0,
        "candidate_count": 0,
        "hotzone_count": 0,
        "screen_width": screen_width,
        "screen_height": screen_height,
        "input_method_shown": is_input_method_shown(adb_path, session.device_id),
        "candidates": [],
    }


def activate_input_method_focus_if_needed(session, adb_path: str, page_payload: dict) -> None:
    if getattr(session, "active_input_candidate", None):
        return
    focus_candidate = get_input_method_focus_candidate(adb_path, session.device_id, page_payload)
    if focus_candidate and is_component_input_focus_candidate(focus_candidate):
        activate_input_candidate(session, focus_candidate, None)


def collect_input_values(page_payload: dict) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for candidate in page_payload.get("candidates") or []:
        text = str(candidate.get("text") or "").strip()
        if not looks_like_input_value_candidate(candidate):
            continue
        key = input_candidate_key(candidate)
        if not key.strip("|"):
            continue
        values[key] = text
    return values


def looks_like_input_value_candidate(candidate: dict) -> bool:
    text = str(candidate.get("text") or "").strip()
    role = str(candidate.get("interaction_role") or "").strip().lower()
    source_tag = str(candidate.get("source_declared_tag") or "").strip().lower()
    resource_id = str(candidate.get("resource_id") or "").lower()
    tail = resource_tail(resource_id)
    class_name = str(candidate.get("class_name") or "").lower()

    if role == "input" or tail in COMPONENT_INPUT_RESOURCE_TAILS:
        return True
    if any(marker in source_tag for marker in COMPONENT_INPUT_CLASS_MARKERS):
        return True

    if not text:
        return bool(is_input_like_candidate(candidate) or candidate.get("focused"))
    if is_input_like_candidate(candidate) or candidate.get("focused"):
        return True

    bounds = candidate.get("bounds") or {}
    height = int(bounds.get("height") or 0)
    width = int(bounds.get("width") or 0)
    input_name_markers = ("name", "title", "desc", "intro", "content", "remark")

    if len(text) > 80:
        return False
    if any(marker in resource_id for marker in input_name_markers):
        return True
    if "textview" in class_name and width >= 120 and height <= 120:
        return True
    return False


def is_component_input_focus_candidate(candidate: Optional[dict]) -> bool:
    if not candidate:
        return False

    role = str(candidate.get("interaction_role") or "").strip().lower()
    source_tag = str(candidate.get("source_declared_tag") or "").strip().lower()
    tail = resource_tail(str(candidate.get("resource_id") or ""))
    class_name = str(candidate.get("class_name") or "").strip().lower()

    if role == "input" or tail in COMPONENT_INPUT_RESOURCE_TAILS:
        return True
    if any(marker in source_tag for marker in COMPONENT_INPUT_CLASS_MARKERS):
        return True
    if "edittext" in class_name and is_input_like_candidate(candidate):
        return True
    return False


def activate_input_candidate(session, candidate: dict, touch_event: Optional[dict] = None) -> None:
    active = dict(candidate)
    active["_input_key"] = input_candidate_key(candidate)
    active["_activated_at"] = time.time()
    active["_initial_text"] = str(candidate.get("text") or "").strip()
    if touch_event:
        active["_touch_point"] = {
            "x": int(touch_event.get("x") or touch_event.get("start_x") or 0),
            "y": int(touch_event.get("y") or touch_event.get("start_y") or 0),
            "type": touch_event.get("type") or "tap",
        }
    session.active_input_candidate = active


def serialize_pending_input(session) -> Optional[dict]:
    candidate = getattr(session, "active_input_candidate", None)
    if not candidate:
        return None

    touch_point = candidate.get("_touch_point") or {}
    bounds = candidate.get("bounds") or {}
    x = touch_point.get("x")
    y = touch_point.get("y")
    if x is None and bounds:
        x = int((int(bounds.get("x1") or 0) + int(bounds.get("x2") or 0)) / 2)
    if y is None and bounds:
        y = int((int(bounds.get("y1") or 0) + int(bounds.get("y2") or 0)) / 2)

    label = (
        candidate.get("text")
        or candidate.get("hint")
        or candidate.get("content_desc")
        or candidate.get("name")
        or candidate.get("resource_id")
        or "focused field"
    )
    return {
        "key": candidate.get("_input_key") or input_candidate_key(candidate),
        "label": label,
        "x": int(x or 0),
        "y": int(y or 0),
        "bounds": bounds,
        "resource_id": candidate.get("resource_id") or "",
        "class_name": candidate.get("class_name") or "",
        "element_data": {
            key: value
            for key, value in candidate.items()
            if not str(key).startswith("_")
        },
    }


def candidate_matches_active(candidate: dict, active_candidate: Optional[dict]) -> bool:
    if not candidate or not active_candidate:
        return False
    if input_candidate_key(candidate) == str(active_candidate.get("_input_key") or ""):
        return True
    if input_candidate_key(candidate) == input_candidate_key(active_candidate):
        return True
    if str(candidate.get("raw_bounds") or "") and str(candidate.get("raw_bounds") or "") == str(active_candidate.get("raw_bounds") or ""):
        return True
    candidate_tail = resource_tail(str(candidate.get("resource_id") or ""))
    active_tail = resource_tail(str(active_candidate.get("resource_id") or ""))
    return bool(candidate_tail and active_tail and candidate_tail == active_tail)


def find_candidate_by_input_key(candidates: list[dict], key: str) -> Optional[dict]:
    for candidate in candidates:
        if input_candidate_key(candidate) == key:
            return candidate
    return None


def input_value_signature(key: str, value: str) -> str:
    return f"{key}\0{value}"


def find_active_input_candidate(candidates: list[dict], active_candidate: Optional[dict]) -> Optional[dict]:
    if not active_candidate:
        return None
    for candidate in candidates:
        if candidate_matches_active(candidate, active_candidate):
            return candidate
    return None


def clear_stale_active_input_if_needed(session, page_payload: dict) -> None:
    active_candidate = getattr(session, "active_input_candidate", None)
    if not active_candidate:
        return
    candidates = page_payload.get("candidates") or []
    if find_active_input_candidate(candidates, active_candidate):
        return
    if has_focused_input(page_payload):
        return
    session.active_input_candidate = None


def find_changed_input(manager, session, page_payload: dict) -> Optional[dict]:
    current_values = collect_input_values(page_payload)
    previous_values = getattr(session, "last_input_values", {}) or {}
    baseline_values = getattr(session, "input_baseline_values", {}) or {}
    recorded_value_keys = getattr(session, "recorded_input_value_keys", set())
    changed_key = ""
    changed_text = ""
    active_candidate = getattr(session, "active_input_candidate", None)
    candidates = page_payload.get("candidates") or []

    if active_candidate:
        for key, value in current_values.items():
            if not value:
                continue
            candidate = find_candidate_by_input_key(candidates, key)
            if not candidate or not candidate_matches_active(candidate, active_candidate):
                continue
            if previous_values.get(key, "") != value:
                changed_key = key
                changed_text = value
                break

        if not changed_key:
            active_current = find_active_input_candidate(candidates, active_candidate)
            active_text = str((active_current or {}).get("text") or "").strip()
            initial_text = str(active_candidate.get("_initial_text") or "").strip()
            if active_current and active_text and active_text != initial_text:
                changed_key = input_candidate_key(active_current)
                changed_text = active_text

    if not changed_key:
        for key, value in current_values.items():
            if not value:
                continue
            if previous_values.get(key, "") != value:
                changed_key = key
                changed_text = value
                break

    if not changed_key:
        for key, value in current_values.items():
            if not value:
                continue
            if baseline_values.get(key, "") == value:
                continue
            if input_value_signature(key, value) in recorded_value_keys:
                continue
            changed_key = key
            changed_text = value
            break

    session.last_input_values = current_values
    if not changed_key:
        return None

    candidate = find_candidate_by_input_key(candidates, changed_key)
    if not candidate:
        return None
    session.recorded_input_value_keys.add(input_value_signature(changed_key, changed_text))

    bounds = candidate.get("bounds") or {}
    x = int((int(bounds.get("x1") or 0) + int(bounds.get("x2") or 0)) / 2)
    y = int((int(bounds.get("y1") or 0) + int(bounds.get("y2") or 0)) / 2)
    return {
        "interaction_type": "input",
        "touch_point": {
            "type": "input",
            "x": x,
            "y": y,
            "text": changed_text,
            "source": "input_snapshot",
        },
        "matched_candidate": candidate,
        "inferred_input": {
            "text": changed_text,
            "candidate": candidate,
        },
        "source": "input_snapshot",
        "confidence": 0.94,
    }


def has_focused_input(page_payload: dict) -> bool:
    for candidate in page_payload.get("candidates") or []:
        if candidate.get("focused") and (is_input_like_candidate(candidate) or is_component_input_focus_candidate(candidate)):
            return True
    return False


def is_keyboard_noise_after_active_input(touch_event: dict, active_candidate: Optional[dict], page_payload: dict) -> bool:
    if not active_candidate:
        return False

    touch_type = str(touch_event.get("type") or "tap")
    if touch_type not in {"tap", "swipe"}:
        return False

    y_values = [
        int(touch_event.get(field) or 0)
        for field in ("y", "start_y", "end_y")
        if touch_event.get(field) is not None
    ]
    if not y_values:
        return False
    touch_bottom = max(y_values)

    screen_bottom = max(
        [int((item.get("bounds") or {}).get("y2") or 0) for item in page_payload.get("candidates") or []] + [0]
    )
    keyboard_line = int(screen_bottom * 0.55) if screen_bottom > 0 else 0
    if keyboard_line > 0 and touch_bottom >= keyboard_line:
        return True
    return False


def is_likely_keyboard_touch(touch_event: dict, page_payload: dict) -> bool:
    y = int(touch_event.get("y") or touch_event.get("end_y") or 0)
    candidates = page_payload.get("candidates") or []
    screen_bottom = max(
        [int((item.get("bounds") or {}).get("y2") or 0) for item in candidates] + [0]
    )
    if screen_bottom <= 0:
        screen_bottom = int(page_payload.get("screen_height") or 0)
        if screen_bottom <= 0:
            return False
        if bool(page_payload.get("input_method_shown")) and str(touch_event.get("type") or "tap") == "tap":
            return y >= int(screen_bottom * 0.55)
        return False

    # IME windows usually do not appear in the app UI hierarchy. If a touch
    # lands below the bottom of all dumped app nodes, it is almost certainly a
    # system keyboard/system-bar event rather than an app action.
    if y > screen_bottom + 8:
        return True

    if has_focused_input(page_payload) and str(touch_event.get("type") or "tap") == "tap":
        return y >= int(screen_bottom * 0.55)

    return False


def is_weak_container_touch(touch_event: dict, matched_candidate: Optional[dict], page_payload: dict) -> bool:
    if not matched_candidate:
        return False
    if str(touch_event.get("type") or "tap") != "tap":
        return False

    resource_id = str(matched_candidate.get("resource_id") or "").lower()
    class_name = str(matched_candidate.get("class_name") or "").lower()
    weak_markers = (
        "main_content_container",
        "content_container",
        "container",
        "drawerlayout",
        "android:id/content",
    )
    if not any(marker in resource_id for marker in weak_markers) and not any(marker in class_name for marker in ("framelayout", "linearlayout", "relativelayout")):
        return False

    y = int(touch_event.get("y") or touch_event.get("end_y") or 0)
    screen_bottom = max(
        [int((item.get("bounds") or {}).get("y2") or 0) for item in page_payload.get("candidates") or []] + [0]
    )
    if screen_bottom <= 0:
        return False
    return y >= int(screen_bottom * 0.45)


def is_weak_manual_match(candidate: Optional[dict]) -> bool:
    if not candidate:
        return True

    role = str(candidate.get("interaction_role") or "").strip().lower()
    if role in {"input", "button", "checkbox", "switch", "tab", "option", "entry", "search"}:
        return False

    resource_id = str(candidate.get("resource_id") or "").strip().lower()
    class_name = str(candidate.get("class_name") or "").strip().lower()
    has_label = bool(candidate.get("text") or candidate.get("content_desc") or candidate.get("hint"))
    bounds = candidate.get("bounds") or {}
    width = int(bounds.get("width") or 0)
    height = int(bounds.get("height") or 0)
    area = width * height

    weak_resource_markers = (
        "android:id/content",
        "main_content_container",
        "drawerlayout",
        "action_bar_root",
    )
    if any(marker in resource_id for marker in weak_resource_markers):
        return True
    if "drawerlayout" in class_name:
        return True
    if not has_label and any(marker in class_name for marker in ("framelayout", "linearlayout", "relativelayout", "viewgroup")):
        return True
    if area >= 700000 and not has_label:
        return True
    return False


def candidate_text_signature(candidate: dict) -> str:
    return " ".join(
        str(candidate.get(field) or "").strip().lower()
        for field in ("text", "hint", "content_desc", "resource_id", "class_name", "name")
    )


def find_accessibility_candidate(event: dict, page_payload: dict, prefer_input: bool = False) -> Optional[dict]:
    candidates = page_payload.get("candidates") or []
    if not candidates:
        return None

    text = str(event.get("text") or "").strip()
    content_desc = str(event.get("content_desc") or "").strip()
    class_name = str(event.get("class_name") or "").strip().lower()
    before_text = str(event.get("before_text") or "").strip()

    ranked: list[tuple[int, dict]] = []
    for candidate in candidates:
        score = 0
        candidate_class = str(candidate.get("class_name") or "").strip().lower()
        candidate_text = str(candidate.get("text") or "").strip()
        candidate_hint = str(candidate.get("hint") or "").strip()
        candidate_desc = str(candidate.get("content_desc") or "").strip()
        signature = candidate_text_signature(candidate)

        if prefer_input and (candidate.get("focused") or is_input_like_candidate(candidate) or is_component_input_focus_candidate(candidate)):
            score += 12
        if candidate.get("focused"):
            score += 8
        if class_name and (candidate_class == class_name or candidate_class.endswith(class_name.rsplit(".", 1)[-1])):
            score += 5
        if text and text in {candidate_text, candidate_hint, candidate_desc}:
            score += 10
        elif text and text.lower() in signature:
            score += 6
        if before_text and before_text in {candidate_text, candidate_hint, candidate_desc}:
            score += 4
        if content_desc and content_desc in {candidate_text, candidate_hint, candidate_desc}:
            score += 8
        if candidate.get("resource_id"):
            score += 2
        if candidate.get("is_hotzone"):
            score += 1
        if score <= 0:
            continue
        ranked.append((score, candidate))

    if not ranked and prefer_input:
        for candidate in candidates:
            if candidate.get("focused") and (is_input_like_candidate(candidate) or is_component_input_focus_candidate(candidate)):
                return candidate

    if not ranked:
        return None

    ranked.sort(
        key=lambda item: (
            item[0],
            0 if is_generic_container_for_accessibility(item[1]) else 1,
            1 if item[1].get("resource_id") else 0,
        ),
        reverse=True,
    )
    return ranked[0][1]


def build_candidate_from_accessibility_event(event: dict) -> dict:
    text = str(event.get("text") or "").strip()
    content_desc = str(event.get("content_desc") or "").strip()
    class_name = str(event.get("class_name") or "").strip()
    package_name = str(event.get("package_name") or "").strip()
    name = text or content_desc or class_name.rsplit(".", 1)[-1] or "accessibility field"
    return {
        "name": name,
        "description": "Accessibility event fallback",
        "package_name": package_name,
        "class_name": class_name,
        "resource_id": "",
        "text": "",
        "content_desc": content_desc,
        "hint": "",
        "interaction_role": "input",
        "bounds": {},
        "raw_bounds": "",
    }


def is_generic_container_for_accessibility(candidate: dict) -> bool:
    class_name = str(candidate.get("class_name") or "").strip().lower()
    resource_id = str(candidate.get("resource_id") or "").strip().lower()
    if is_input_like_candidate(candidate) or is_component_input_focus_candidate(candidate):
        return False
    return any(marker in resource_id for marker in ("android:id/content", "drawerlayout")) or any(
        marker in class_name for marker in ("framelayout", "linearlayout", "relativelayout")
    )


def find_scroll_candidate(event: dict, page_payload: dict) -> Optional[dict]:
    candidates = page_payload.get("candidates") or []
    scrollable = [candidate for candidate in candidates if candidate.get("scrollable")]
    if scrollable:
        scrollable.sort(
            key=lambda candidate: (
                0 if is_generic_container_for_accessibility(candidate) else 1,
                int((candidate.get("bounds") or {}).get("height") or 0),
                int((candidate.get("bounds") or {}).get("width") or 0),
            ),
            reverse=True,
        )
        return scrollable[0]

    return find_accessibility_candidate(event, page_payload, prefer_input=False)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_swipe_touch_point_from_scroll_event(event: dict, page_payload: dict, candidate: Optional[dict]) -> dict:
    bounds = (candidate or {}).get("bounds") or {}
    screen_bottom = max(
        [int((item.get("bounds") or {}).get("y2") or 0) for item in page_payload.get("candidates") or []] + [2400]
    )
    x1 = _safe_int(bounds.get("x1"), 0)
    y1 = _safe_int(bounds.get("y1"), int(screen_bottom * 0.25))
    x2 = _safe_int(bounds.get("x2"), 1080)
    y2 = _safe_int(bounds.get("y2"), int(screen_bottom * 0.9))
    if x2 <= x1:
        x1, x2 = 0, 1080
    if y2 <= y1:
        y1, y2 = int(screen_bottom * 0.25), int(screen_bottom * 0.9)

    center_x = int((x1 + x2) / 2)
    start_y = int(y1 + (y2 - y1) * 0.72)
    end_y = int(y1 + (y2 - y1) * 0.32)
    start_x = center_x
    end_x = center_x

    delta_x = _safe_int(event.get("scroll_delta_x"), 0)
    delta_y = _safe_int(event.get("scroll_delta_y"), 0)
    if abs(delta_x) > abs(delta_y):
        start_y = end_y = int((y1 + y2) / 2)
        if delta_x > 0:
            start_x = int(x1 + (x2 - x1) * 0.72)
            end_x = int(x1 + (x2 - x1) * 0.32)
        else:
            start_x = int(x1 + (x2 - x1) * 0.32)
            end_x = int(x1 + (x2 - x1) * 0.72)
    elif delta_y < 0:
        start_y, end_y = end_y, start_y

    return {
        "type": "swipe",
        "x": end_x,
        "y": end_y,
        "start_x": start_x,
        "start_y": start_y,
        "end_x": end_x,
        "end_y": end_y,
        "distance": round(((end_x - start_x) ** 2 + (end_y - start_y) ** 2) ** 0.5, 2),
        "sample_count": 2,
        "path": [{"x": start_x, "y": start_y}, {"x": end_x, "y": end_y}],
        "source": "accessibility_scroll",
    }


def apply_pending_accessibility_events(manager, session, page_payload: dict) -> list[dict]:
    recorded: list[dict] = []
    for accessibility_interaction in manager.pop_accessibility_events(session.session_id):
        event = accessibility_interaction.get("event") or {}
        event_type = str(event.get("event_type") or "").strip().upper()

        if event_type == "TYPE_VIEW_TEXT_CHANGED":
            text = str(accessibility_interaction.get("text") or event.get("text") or "").strip()
            if not text:
                continue
            candidate = (
                find_accessibility_candidate(event, page_payload, prefer_input=True)
                or getattr(session, "active_input_candidate", None)
                or build_candidate_from_accessibility_event(event)
            )
            touch_point = build_touch_point_from_candidate(candidate, interaction_type="input")
            touch_point["text"] = text
            detected = {
                "interaction_type": "input",
                "touch_point": touch_point,
                "matched_candidate": candidate,
                "inferred_input": {
                    "text": text,
                    "before_text": event.get("before_text") or "",
                    "candidate": candidate,
                },
                "source": "accessibility_stream",
                "confidence": 0.9 if candidate else 0.72,
            }
            atom = manager.record_detected_interaction(session.session_id, detected, page_data=page_payload)
            if atom:
                recorded.append(atom)
            continue

        if event_type == "TYPE_VIEW_SCROLLED":
            candidate = find_scroll_candidate(event, page_payload)
            touch_point = build_swipe_touch_point_from_scroll_event(event, page_payload, candidate)
            detected = {
                "interaction_type": "swipe",
                "touch_point": touch_point,
                "matched_candidate": candidate,
                "inferred_input": None,
                "source": "accessibility_stream",
                "confidence": 0.78,
            }
            interaction_key = build_detected_interaction_key(detected, page_payload)
            if not manager.should_accept_detected_interaction(session.session_id, interaction_key):
                continue
            atom = manager.record_detected_interaction(session.session_id, detected, page_data=page_payload)
            if atom:
                recorded.append(atom)
            continue

        candidate = find_accessibility_candidate(
            event,
            page_payload,
            prefer_input=event_type in {"TYPE_VIEW_FOCUSED", "TYPE_VIEW_TEXT_SELECTION_CHANGED"},
        )
        if not candidate:
            continue

        if event_type == "TYPE_VIEW_FOCUSED" and is_component_input_focus_candidate(candidate):
            activate_input_candidate(session, candidate, build_touch_point_from_candidate(candidate, interaction_type="tap"))
            continue

        if is_generic_container_for_accessibility(candidate):
            continue

        touch_point = build_touch_point_from_candidate(candidate, interaction_type="tap")
        detected = {
            "interaction_type": "tap",
            "touch_point": touch_point,
            "matched_candidate": candidate,
            "inferred_input": None,
            "source": "accessibility_stream",
            "confidence": 0.86,
        }
        interaction_key = build_detected_interaction_key(detected, page_payload)
        if not manager.should_accept_detected_interaction(session.session_id, interaction_key):
            continue
        atom = manager.record_detected_interaction(session.session_id, detected, page_data=page_payload)
        if atom:
            recorded.append(atom)
    return recorded


def apply_pending_touch_events(
    manager,
    session,
    current_payload: dict,
    previous_payload: Optional[dict] = None,
    *,
    page_changed: bool = False,
) -> list[dict]:
    recorded: list[dict] = []
    for touch_event in manager.pop_touch_events(session.session_id):
        if is_keyboard_noise_after_active_input(touch_event, getattr(session, "active_input_candidate", None), current_payload):
            continue
        if is_likely_keyboard_touch(touch_event, current_payload):
            continue
        detected, match_payload = build_detected_from_best_touch_snapshot(
            touch_event,
            current_payload,
            previous_payload,
            page_changed=page_changed,
        )
        if (
            str(touch_event.get("type") or "tap") == "tap"
            and is_component_input_focus_candidate(detected.get("matched_candidate"))
        ):
            activate_input_candidate(session, detected["matched_candidate"], touch_event)
            continue
        if is_weak_container_touch(touch_event, detected.get("matched_candidate"), match_payload):
            continue
        interaction_key = build_detected_interaction_key(detected, match_payload)
        if not manager.should_accept_detected_interaction(session.session_id, interaction_key):
            continue
        atom = manager.record_detected_interaction(session.session_id, detected, page_data=current_payload)
        if atom:
            recorded.append(atom)
    return recorded


class RecordingSessionsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        device_pk = request.data.get("device_id")
        project_id = request.data.get("project_id")
        package_name = request.data.get("package_name", "")
        enable_stream_capture = bool(request.data.get("enable_stream_capture", False))

        if not device_pk:
            return fail("missing device_id")
        if not project_id:
            return fail("missing project_id")

        try:
            device = AppDevice.objects.get(id=device_pk)
        except AppDevice.DoesNotExist:
            return fail("device not found", status.HTTP_404_NOT_FOUND, 404)

        if device.status == "offline":
            return fail("device is offline")
        if device.status == "locked" and device.locked_by != request.user:
            locked_by = device.locked_by.username if device.locked_by else "another user"
            return fail(f"device is locked by {locked_by}")
        if device.status != "locked":
            device.lock(request.user)

        session_id = str(uuid.uuid4())
        manager = get_recording_manager()
        session = manager.create_session(
            session_id=session_id,
            device_id=device.device_id,
            user=request.user,
            project_id=int(project_id),
            package_name=package_name,
        )
        session.enable_stream_capture = enable_stream_capture

        screenshot_data = ""
        screen_width = 0
        screen_height = 0
        page_state: Dict[str, Any] = {}

        try:
            adb_path = get_adb_path()
        except Exception as exc:
            adb_path = ""
            logger.warning("Failed to resolve adb path for recording: %s", exc, exc_info=True)

        if adb_path:
            try:
                screenshot_bytes = capture_screenshot_bytes(adb_path, device.device_id)
                screenshot_data = f"data:image/png;base64,{base64.b64encode(screenshot_bytes).decode('utf-8')}"
            except Exception as exc:
                logger.warning("Failed to capture initial recording screenshot: %s", exc)

            try:
                screen_width, screen_height = get_screen_size(adb_path, device.device_id)
            except Exception as exc:
                logger.warning("Failed to read initial recording screen size: %s", exc)

            try:
                initial_payload = capture_page_state_payload(adb_path, device.device_id, include_screenshot=False)
                manager.set_last_page_state(session_id, initial_payload, build_page_signature(initial_payload))
                session.last_input_values = collect_input_values(initial_payload)
                session.input_baseline_values = dict(session.last_input_values)
                session.recorded_input_value_keys = {
                    input_value_signature(key, value)
                    for key, value in session.input_baseline_values.items()
                    if value
                }
                page_state = compact_page_state(initial_payload)
            except Exception as exc:
                logger.warning("Failed to initialize recording page state: %s", exc, exc_info=True)

            try:
                clear_pending_recording_events(manager, session_id)
                if session.enable_stream_capture:
                    start_touch_monitor(session_id, adb_path, device.device_id)
                    start_accessibility_monitor(session_id, adb_path, device.device_id)
            except Exception as exc:
                logger.warning("Failed to start recording monitors: %s", exc, exc_info=True)

        return ok(
            {
                **session.to_dict(),
                "device_name": device.name or device.device_id,
                "screenshot": screenshot_data,
                "screen_width": screen_width,
                "screen_height": screen_height,
                "page_state": page_state,
                "interactions": session.interactions,
                "pending_input": serialize_pending_input(session),
            },
            "recording session created",
        )


class RecordingSessionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        _manager, session, error = get_session_or_404(session_id)
        if error:
            return error
        return ok({**session.to_dict(), "interactions": session.interactions, "pending_input": serialize_pending_input(session)}, "ok")

    def delete(self, request, session_id):
        manager, session, error = get_session_or_404(session_id)
        if error:
            return error
        stop_recording_monitors(session_id)
        unlock_session_device(session)
        manager.delete_session(session_id)
        return ok(msg="recording canceled")


class RecordingInteractionsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        manager, session, error = get_session_or_404(session_id)
        if error:
            return error
        if not session.is_active:
            return fail("recording session is closed")

        interaction_type = request.data.get("type")
        atom = None
        matched_element = request.data.get("element_data")

        try:
            if interaction_type == "tap":
                x = int(request.data.get("x"))
                y = int(request.data.get("y"))
                auto_locate = request.data.get("auto_locate", True)
                if auto_locate and (not matched_element or is_weak_manual_match(matched_element)):
                    matched_element = self._locate_element_by_point(session, x, y)
                atom = manager.record_tap(session_id, x, y, matched_element, page_data=session.last_page_state, source="manual")
            elif interaction_type == "swipe":
                atom = manager.record_swipe(
                    session_id,
                    int(request.data.get("x1")),
                    int(request.data.get("y1")),
                    int(request.data.get("x2")),
                    int(request.data.get("y2")),
                    float(request.data.get("duration", 0.3)),
                    page_data=session.last_page_state,
                    source="manual",
                )
            elif interaction_type == "input":
                text = str(request.data.get("text") or "")
                if not text:
                    return fail("input text is empty")
                x = request.data.get("x")
                y = request.data.get("y")
                if (not matched_element or is_weak_manual_match(matched_element)) and x is not None and y is not None:
                    matched_element = self._locate_element_by_point(session, int(x), int(y))
                atom = manager.record_input(
                    session_id,
                    text,
                    matched_element,
                    x=int(x) if x is not None else None,
                    y=int(y) if y is not None else None,
                    page_data=session.last_page_state,
                    source="manual",
                )
            elif interaction_type == "wait":
                atom = manager.record_wait(session_id, float(request.data.get("duration", 1.0)))
            else:
                return fail(f"unsupported interaction type: {interaction_type}")
        except (TypeError, ValueError):
            return fail("invalid interaction parameters")

        if not atom:
            return fail("failed to record interaction", status.HTTP_500_INTERNAL_SERVER_ERROR, 500)

        return ok(
            {
                "interaction_count": len(session.interactions),
                "interaction": atom,
                "matched_element": matched_element,
                "interactions": session.interactions,
                "pending_input": serialize_pending_input(session),
            },
            "interaction recorded",
        )

    def put(self, request, session_id):
        manager, session, error = get_session_or_404(session_id)
        if error:
            return error
        if not session.is_active:
            return fail("recording session is closed")

        interactions = request.data.get("interactions")
        if not isinstance(interactions, list):
            return fail("interactions must be a list")

        manager.replace_interactions(session_id, interactions)
        return ok({"interaction_count": len(session.interactions), "interactions": session.interactions}, "interactions synced")

    def delete(self, request, session_id):
        manager, session, error = get_session_or_404(session_id)
        if error:
            return error
        manager.replace_interactions(session_id, [])
        return ok({"interaction_count": 0, "interactions": []}, "interactions cleared")

    def _locate_element_by_point(self, session, x: int, y: int) -> Optional[dict]:
        page_payload = session.last_page_state or {}
        candidates = page_payload.get("candidates") or []
        matched = find_candidate_by_point(candidates, x, y)
        if matched and not is_weak_manual_match(matched):
            return matched

        try:
            adb_path = get_adb_path()
            page_payload = capture_page_state_payload(adb_path, session.device_id, include_screenshot=False)
            candidates = page_payload.get("candidates") or []
            live_matched = find_candidate_by_point(candidates, x, y)
            return live_matched or matched
        except Exception as exc:
            logger.warning("Failed to locate element by point: %s", exc)
            return matched


class RecordingScreenshotView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        _manager, session, error = get_session_or_404(session_id)
        if error:
            return error

        with_candidates = bool(request.data.get("with_candidates", False))

        try:
            adb_path = get_adb_path()
            if with_candidates:
                payload = capture_page_state_payload(adb_path, session.device_id, include_screenshot=True)
                return ok(compact_page_state(payload), "screenshot and page state captured")

            screenshot_bytes = capture_screenshot_bytes(adb_path, session.device_id)
            screenshot_data = f"data:image/png;base64,{base64.b64encode(screenshot_bytes).decode('utf-8')}"
            return ok({"content": screenshot_data, "timestamp": int(timezone.now().timestamp())}, "screenshot captured")
        except Exception as exc:
            logger.error("Failed to capture screenshot: %s", exc, exc_info=True)
            return fail(f"screenshot capture failed: {exc}", status.HTTP_500_INTERNAL_SERVER_ERROR, 500)


class RecordingObserveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        manager, session, error = get_session_or_404(session_id)
        if error:
            return error
        if not session.is_active:
            return fail("recording session is closed")

        include_screenshot = bool(request.data.get("include_screenshot", False))
        reset = bool(request.data.get("reset", False))

        try:
            adb_path = get_adb_path()
            previous_payload, previous_signature = manager.get_last_page_state(session_id)
            had_previous_state = bool(previous_payload and previous_signature)
            capture_error = ""
            try:
                current_payload = capture_page_state_payload(adb_path, session.device_id, include_screenshot=include_screenshot)
                current_signature = build_page_signature(current_payload)
                manager.set_last_page_state(session_id, current_payload, current_signature)
            except Exception as capture_exc:
                capture_error = str(capture_exc)
                logger.warning("Observe capture failed, keep recording with last page state: %s", capture_exc)
                if not previous_payload:
                    previous_payload = build_fallback_page_payload(adb_path, session)
                    previous_signature = build_page_signature(previous_payload)
                current_payload = previous_payload
                current_signature = previous_signature or build_page_signature(current_payload)

            data = {
                "changed": False,
                "interaction": None,
                "recorded": None,
                "recorded_atoms": [],
                "interaction_count": len(session.interactions),
                "interactions": session.interactions,
                "page_state": compact_page_state(current_payload),
                "pending_input": serialize_pending_input(session),
                "capture_error": capture_error,
            }

            if reset or (not had_previous_state and not capture_error):
                manager.pop_touch_events(session_id)
                manager.pop_accessibility_events(session_id)
                session.last_input_values = collect_input_values(current_payload)
                session.input_baseline_values = dict(session.last_input_values)
                session.recorded_input_value_keys = {
                    input_value_signature(key, value)
                    for key, value in session.input_baseline_values.items()
                    if value
                }
                session.active_input_candidate = None
                manager.reset_last_recorded_interaction_key(session_id)
                data["pending_input"] = None
                return ok(data, "observe baseline updated")

            activate_input_method_focus_if_needed(session, adb_path, current_payload)
            data["pending_input"] = serialize_pending_input(session)

            snapshot_input = find_changed_input(manager, session, current_payload)
            if snapshot_input:
                if not getattr(session, "enable_stream_capture", False):
                    snapshot_input = None
                else:
                    manager.pop_touch_events(session_id)
                    manager.pop_accessibility_events(session_id)
                    atom = manager.record_detected_interaction(session_id, snapshot_input, page_data=current_payload)
                    if atom:
                        data["changed"] = True
                        data["interaction"] = {
                            "device_id": session.device_id,
                            "interaction_type": "input",
                            "touch_point": snapshot_input.get("touch_point") or {},
                            "matched_candidate": snapshot_input.get("matched_candidate"),
                            "inferred_input": snapshot_input.get("inferred_input"),
                        }
                        data["recorded"] = atom
                        data["recorded_atoms"] = [atom]
                        data["interaction_count"] = len(session.interactions)
                        data["interactions"] = session.interactions
                        data["pending_input"] = serialize_pending_input(session)
                        return ok(data, "input snapshot interaction recorded")

            inferred = None
            if previous_signature != current_signature and page_state_changed(previous_payload, current_payload):
                data["changed"] = True
                inferred = infer_interaction_from_page_diff(previous_payload, current_payload)

            if inferred and inferred.get("interaction_type") == "input":
                if not getattr(session, "enable_stream_capture", False):
                    inferred = None
                else:
                    manager.pop_touch_events(session_id)
                    manager.pop_accessibility_events(session_id)
                    data["interaction"] = {
                        "device_id": session.device_id,
                        "interaction_type": "input",
                        "touch_point": inferred.get("touch_point") or {},
                        "matched_candidate": inferred.get("matched_candidate"),
                        "inferred_input": inferred.get("inferred_input"),
                    }
                    atom = manager.record_detected_interaction(session_id, inferred, page_data=current_payload)
                    if atom:
                        data["recorded"] = atom
                        data["recorded_atoms"] = [atom]
                        data["interaction_count"] = len(session.interactions)
                        data["interactions"] = session.interactions
                        data["pending_input"] = serialize_pending_input(session)
                        return ok(data, "input interaction recorded")
                    return ok(data, "input changed but no atom was written")

            if getattr(session, "enable_stream_capture", False):
                recorded_atoms = apply_pending_accessibility_events(manager, session, current_payload)
                if recorded_atoms:
                    data["recorded"] = recorded_atoms[-1]
                    data["recorded_atoms"] = recorded_atoms
                    data["interaction_count"] = len(session.interactions)
                    data["interactions"] = session.interactions
                    data["pending_input"] = serialize_pending_input(session)
                    return ok(data, "accessibility stream interaction recorded")

                clear_stale_active_input_if_needed(session, current_payload)
                recorded_atoms = apply_pending_touch_events(
                    manager,
                    session,
                    current_payload,
                    previous_payload=previous_payload,
                    page_changed=bool(data["changed"]),
                )
                data["pending_input"] = serialize_pending_input(session)
                if recorded_atoms:
                    data["recorded"] = recorded_atoms[-1]
                    data["recorded_atoms"] = recorded_atoms
                    data["interaction_count"] = len(session.interactions)
                    data["interactions"] = session.interactions
                    data["pending_input"] = serialize_pending_input(session)
                    return ok(data, "touch stream interaction recorded")
            else:
                manager.pop_touch_events(session_id)
                manager.pop_accessibility_events(session_id)

            if inferred and not getattr(session, "enable_stream_capture", False):
                return ok(data, "builder mode: page change observed but no atom auto-recorded")

            if not inferred:
                return ok(data, "page unchanged" if not data["changed"] else "page changed but no stable interaction inferred")

            data["interaction"] = {
                "device_id": session.device_id,
                "interaction_type": inferred.get("interaction_type") or "tap",
                "touch_point": inferred.get("touch_point") or {},
                "matched_candidate": inferred.get("matched_candidate"),
                "inferred_input": inferred.get("inferred_input"),
            }

            interaction_key = build_detected_interaction_key(inferred, current_payload)
            if not manager.should_accept_detected_interaction(session_id, interaction_key):
                return ok(data, "duplicate interaction ignored")

            atom = manager.record_detected_interaction(session_id, inferred, page_data=current_payload)
            if atom:
                data["recorded"] = atom
                data["recorded_atoms"] = [atom]
                data["interaction_count"] = len(session.interactions)
                data["interactions"] = session.interactions
                return ok(data, "state diff interaction recorded")

            return ok(data, "page changed but no interaction was written")
        except Exception as exc:
            logger.error("Failed to observe page state: %s", exc, exc_info=True)
            return fail(f"observe failed: {exc}", status.HTTP_500_INTERNAL_SERVER_ERROR, 500)


class RecordingFinalizeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        manager, session, error = get_session_or_404(session_id)
        if error:
            return error

        interactions = request.data.get("interactions")
        if isinstance(interactions, list):
            manager.replace_interactions(session_id, interactions)

        test_case_id = request.data.get("test_case_id")
        name = str(request.data.get("name") or "").strip()
        description = str(request.data.get("description") or "").strip()
        auto_insert_wait = request.data.get("auto_insert_wait", True)

        ui_flow = manager.convert_to_ui_flow(session_id, auto_insert_wait=auto_insert_wait)
        if not ui_flow:
            return fail("no interactions to save")

        if not name:
            name = f"Recorded case {timezone.now().strftime('%Y%m%d_%H%M%S')}"

        try:
            if test_case_id:
                test_case = AppTestCase.objects.get(id=test_case_id)
                test_case.name = name or test_case.name
                test_case.description = description
                test_case.ui_flow = ui_flow
                test_case.updated_at = timezone.now()
                test_case.save()
                action_type = "updated"
            else:
                test_case = AppTestCase.objects.create(
                    project_id=session.project_id,
                    name=name,
                    description=description,
                    ui_flow=ui_flow,
                    created_by=session.user,
                )
                action_type = "created"

            manager.close_session(session_id)
            stop_recording_monitors(session_id)
            unlock_session_device(session)

            serializer = AppTestCaseSerializer(test_case)
            return ok(
                {
                    "test_case": serializer.data,
                    "step_count": len(ui_flow),
                    "duration": session.get_duration(),
                    "ui_flow": ui_flow,
                    "interactions": session.interactions,
                },
                f"test case {action_type}",
            )
        except AppTestCase.DoesNotExist:
            return fail("target test case not found", status.HTTP_404_NOT_FOUND, 404)
        except Exception as exc:
            logger.error("Failed to finalize recording session: %s", exc, exc_info=True)
            return fail(f"save test case failed: {exc}", status.HTTP_500_INTERNAL_SERVER_ERROR, 500)
