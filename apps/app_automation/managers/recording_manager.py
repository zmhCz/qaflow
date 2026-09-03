# -*- coding: utf-8 -*-
"""Action-atom based recording manager for APP automation."""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


GENERIC_CONTAINER_MARKERS = (
    "recyclerview",
    "listview",
    "gridview",
    "scrollview",
    "nestedscrollview",
    "viewpager",
    "viewgroup",
    "framelayout",
    "linearlayout",
    "relativelayout",
    "constraintlayout",
)

INPUT_LIKE_MARKERS = (
    "edittext",
    "textfield",
    "input",
    "search",
    "keyword",
    "phone",
    "mobile",
    "password",
    "pwd",
    "verify",
    "code",
    "email",
    "account",
    "username",
    "name",
    "title",
    "content",
    "desc",
    "description",
    "remark",
    "nickname",
)


class RecordingSession:
    """In-memory session. Its canonical record is a list of action atoms."""

    def __init__(self, session_id: str, device_id: str, user, project_id: int, package_name: str = ""):
        self.session_id = session_id
        self.device_id = device_id
        self.user = user
        self.project_id = project_id
        self.package_name = package_name
        self.created_at = datetime.now()
        self.interactions: List[Dict[str, Any]] = []
        self.is_active = True
        self.last_page_state: Optional[Dict[str, Any]] = None
        self.last_page_signature: Optional[str] = None
        self.last_recorded_interaction_key: str = ""
        self.last_input_values: Dict[str, str] = {}
        self.input_baseline_values: Dict[str, str] = {}
        self.recorded_input_value_keys: set[str] = set()
        self.active_input_candidate: Optional[Dict[str, Any]] = None
        self.pending_touch_events: List[Dict[str, Any]] = []
        self.pending_accessibility_events: List[Dict[str, Any]] = []
        self.enable_stream_capture = False
        self._lock = threading.RLock()

    def add_interaction(self, interaction: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            interaction["timestamp"] = interaction.get("timestamp") or time.time()
            interaction["index"] = len(self.interactions)
            self.interactions.append(interaction)
        logger.debug(
            "Session %s recorded atom #%s: %s",
            self.session_id,
            interaction["index"],
            interaction.get("type"),
        )
        return interaction

    def add_touch_event(self, event: Dict[str, Any]) -> None:
        with self._lock:
            event = dict(event)
            event["captured_at"] = event.get("captured_at") or time.time()
            if self.pending_touch_events:
                last = self.pending_touch_events[-1]
                same_type = str(last.get("type") or "tap") == str(event.get("type") or "tap")
                close_time = abs(float(event["captured_at"]) - float(last.get("captured_at") or 0)) <= 0.35
                close_point = (
                    abs(int(event.get("x") or event.get("end_x") or 0) - int(last.get("x") or last.get("end_x") or 0)) <= 12
                    and abs(int(event.get("y") or event.get("end_y") or 0) - int(last.get("y") or last.get("end_y") or 0)) <= 12
                )
                if same_type and close_time and close_point:
                    return
            self.pending_touch_events.append(event)
            self.pending_touch_events = self.pending_touch_events[-50:]

    def pop_touch_events(self) -> List[Dict[str, Any]]:
        with self._lock:
            events = list(self.pending_touch_events)
            self.pending_touch_events = []
        return events

    def add_accessibility_event(self, event: Dict[str, Any]) -> None:
        with self._lock:
            event = dict(event)
            event["captured_at"] = event.get("captured_at") or time.time()
            self.pending_accessibility_events.append(event)
            self.pending_accessibility_events = self.pending_accessibility_events[-80:]

    def pop_accessibility_events(self) -> List[Dict[str, Any]]:
        with self._lock:
            events = list(self.pending_accessibility_events)
            self.pending_accessibility_events = []
        return events

    def get_duration(self) -> float:
        with self._lock:
            if not self.interactions:
                return 0.0
            return float(self.interactions[-1]["timestamp"]) - float(self.interactions[0]["timestamp"])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "device_id": self.device_id,
            "project_id": self.project_id,
            "package_name": self.package_name,
            "created_at": self.created_at.isoformat(),
            "interaction_count": len(self.interactions),
            "duration": self.get_duration(),
            "is_active": self.is_active,
            "enable_stream_capture": self.enable_stream_capture,
            "pending_touch_count": len(self.pending_touch_events),
            "pending_accessibility_count": len(self.pending_accessibility_events),
        }


class RecordingManager:
    """Manage recording sessions and convert action atoms to ui_flow steps."""

    def __init__(self):
        self._sessions: Dict[str, RecordingSession] = {}

    def create_session(
        self,
        session_id: str,
        device_id: str,
        user,
        project_id: int,
        package_name: str = "",
    ) -> RecordingSession:
        session = RecordingSession(session_id, device_id, user, project_id, package_name)
        self._sessions[session_id] = session
        logger.info("Created recording session: %s (device=%s, user=%s)", session_id, device_id, user.username)
        return session

    def get_session(self, session_id: str) -> Optional[RecordingSession]:
        return self._sessions.get(session_id)

    def close_session(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.is_active = False
            logger.info("Closed recording session: %s (atoms=%s)", session_id, len(session.interactions))

    def delete_session(self, session_id: str) -> None:
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info("Deleted recording session: %s", session_id)

    def set_last_page_state(
        self,
        session_id: str,
        payload: Optional[Dict[str, Any]],
        signature: Optional[str],
    ) -> None:
        session = self.get_session(session_id)
        if not session:
            return
        session.last_page_state = payload
        session.last_page_signature = signature

    def get_last_page_state(self, session_id: str) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        session = self.get_session(session_id)
        if not session:
            return None, None
        return session.last_page_state, session.last_page_signature

    def add_touch_event(self, session_id: str, event: Dict[str, Any]) -> None:
        session = self.get_session(session_id)
        if session:
            session.add_touch_event(event)

    def pop_touch_events(self, session_id: str) -> List[Dict[str, Any]]:
        session = self.get_session(session_id)
        if not session:
            return []
        return session.pop_touch_events()

    def add_accessibility_event(self, session_id: str, event: Dict[str, Any]) -> None:
        session = self.get_session(session_id)
        if session:
            session.add_accessibility_event(event)

    def pop_accessibility_events(self, session_id: str) -> List[Dict[str, Any]]:
        session = self.get_session(session_id)
        if not session:
            return []
        return session.pop_accessibility_events()

    def reset_last_recorded_interaction_key(self, session_id: str) -> None:
        session = self.get_session(session_id)
        if session:
            session.last_recorded_interaction_key = ""

    def should_accept_detected_interaction(self, session_id: str, interaction_key: str) -> bool:
        session = self.get_session(session_id)
        if not session:
            return False
        key = str(interaction_key or "").strip()
        if not key:
            return True
        if session.last_recorded_interaction_key == key:
            return False
        session.last_recorded_interaction_key = key
        return True

    def record_tap(
        self,
        session_id: str,
        x: int,
        y: int,
        element_data: Optional[Dict[str, Any]] = None,
        *,
        page_data: Optional[Dict[str, Any]] = None,
        source: str = "manual",
        confidence: float = 0.72,
        raw: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        return self._record_atom(
            session_id,
            self._build_tap_atom(x, y, element_data, page_data, source=source, confidence=confidence, raw=raw),
        )

    def record_swipe(
        self,
        session_id: str,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float = 0.3,
        *,
        page_data: Optional[Dict[str, Any]] = None,
        source: str = "manual",
        confidence: float = 0.7,
        raw: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        return self._record_atom(
            session_id,
            self._build_swipe_atom(x1, y1, x2, y2, duration, page_data, source=source, confidence=confidence, raw=raw),
        )

    def record_input(
        self,
        session_id: str,
        text: str,
        element_data: Optional[Dict[str, Any]] = None,
        x: Optional[int] = None,
        y: Optional[int] = None,
        *,
        page_data: Optional[Dict[str, Any]] = None,
        source: str = "manual",
        confidence: float = 0.86,
        raw: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        session = self.get_session(session_id)
        if session and not element_data and x is None and y is None:
            active_candidate = getattr(session, "active_input_candidate", None)
            if active_candidate:
                element_data = active_candidate
                touch_point = active_candidate.get("_touch_point") or {}
                if touch_point:
                    x = touch_point.get("x")
                    y = touch_point.get("y")

        if session and not element_data and x is None and y is None:
            last_target_atom = next(
                (
                    item
                    for item in reversed(session.interactions)
                    if item.get("type") in {"tap", "input"} and item.get("target")
                ),
                None,
            )
            if last_target_atom:
                target = last_target_atom.get("target") or {}
                fallback = target.get("fallback") or {}
                if fallback.get("type") == "pos" and isinstance(fallback.get("value"), list):
                    pos = fallback.get("value") or []
                    if len(pos) >= 2:
                        x, y = pos[0], pos[1]
                element_data = last_target_atom.get("element")

        atom = self._build_input_atom(text, element_data, x, y, page_data, source=source, confidence=confidence, raw=raw)
        if session:
            replaced = self._replace_last_focus_tap_with_input(session, atom)
            if replaced:
                session.active_input_candidate = None
                return replaced
            merged = self._merge_with_last_input_atom(session, atom)
            if merged:
                session.active_input_candidate = None
                return merged

        recorded = self._record_atom(session_id, atom)
        if session and recorded:
            session.active_input_candidate = None
        return recorded

    def record_wait(self, session_id: str, seconds: float) -> Optional[Dict[str, Any]]:
        return self._record_atom(
            session_id,
            {
                "id": self._new_atom_id(),
                "type": "wait",
                "name": f"Wait {seconds} seconds",
                "target": None,
                "page": {},
                "input": None,
                "assert_after": None,
                "source": "manual",
                "confidence": 1.0,
                "duration": float(seconds),
                "raw": {},
            },
        )

    def record_detected_interaction(
        self,
        session_id: str,
        detected: Dict[str, Any],
        page_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        touch_point = detected.get("touch_point") or {}
        matched_candidate = detected.get("matched_candidate")
        inferred_input = detected.get("inferred_input") or {}
        interaction_type = detected.get("interaction_type") or touch_point.get("type") or "tap"

        x = int(round(float(touch_point.get("x") or 0)))
        y = int(round(float(touch_point.get("y") or 0)))

        if interaction_type == "input":
            text = str(inferred_input.get("text") or touch_point.get("text") or "").strip()
            if not text:
                return None
            return self.record_input(
                session_id,
                text,
                inferred_input.get("candidate") or matched_candidate,
                x=x,
                y=y,
                page_data=page_data,
                source="observer",
                confidence=0.9,
                raw=detected,
            )

        if interaction_type == "swipe":
            return self.record_swipe(
                session_id,
                int(round(float(touch_point.get("start_x") or x))),
                int(round(float(touch_point.get("start_y") or y))),
                int(round(float(touch_point.get("end_x") or x))),
                int(round(float(touch_point.get("end_y") or y))),
                0.3,
                page_data=page_data,
                source="touch_stream",
                confidence=0.82,
                raw=detected,
            )

        return self.record_tap(
            session_id,
            x,
            y,
            matched_candidate,
            page_data=page_data,
            source=detected.get("source") or "observer",
            confidence=float(detected.get("confidence") or 0.8),
            raw=detected,
        )

    def replace_interactions(self, session_id: str, interactions: List[Dict[str, Any]]) -> bool:
        session = self.get_session(session_id)
        if not session:
            return False
        session.interactions = []
        for interaction in interactions:
            cleaned = dict(interaction)
            cleaned.pop("index", None)
            session.add_interaction(cleaned)
        return True

    def convert_to_ui_flow(
        self,
        session_id: str,
        auto_insert_wait: bool = True,
        wait_threshold: float = 1.0,
    ) -> List[Dict[str, Any]]:
        session = self.get_session(session_id)
        if not session:
            return []

        ui_flow: List[Dict[str, Any]] = []
        interactions = session.interactions

        for index, interaction in enumerate(interactions):
            if auto_insert_wait and index > 0:
                gap = float(interaction["timestamp"]) - float(interactions[index - 1]["timestamp"])
                if gap >= wait_threshold:
                    ui_flow.append(
                        {
                            "type": "wait",
                            "name": f"Wait {gap:.1f} seconds",
                            "config": {"duration": round(gap, 1)},
                        }
                    )

            step = self._interaction_to_step(interaction, index)
            if step:
                ui_flow.append(step)

        return ui_flow

    def _record_atom(self, session_id: str, atom: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        session = self.get_session(session_id)
        if not session:
            logger.error("Recording session %s does not exist", session_id)
            return None
        if not atom:
            return None
        return session.add_interaction(atom)

    def _merge_with_last_input_atom(self, session: RecordingSession, atom: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if atom.get("type") != "input" or not session.interactions:
            return None

        last = session.interactions[-1]
        if last.get("type") != "input":
            return None
        if self._target_identity(last.get("target")) != self._target_identity(atom.get("target")):
            return None

        last["text"] = atom.get("text") or ""
        last["input"] = atom.get("input") or {"value": last["text"], "raw_value": last["text"]}
        last["name"] = atom.get("name") or last.get("name")
        last["timestamp"] = time.time()
        last["raw"] = atom.get("raw") or last.get("raw") or {}
        return last

    def _replace_last_focus_tap_with_input(self, session: RecordingSession, atom: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if atom.get("type") != "input" or not session.interactions:
            return None

        last = session.interactions[-1]
        if last.get("type") != "tap":
            return None
        if self._target_identity(last.get("target")) != self._target_identity(atom.get("target")):
            return None

        atom["index"] = last.get("index", len(session.interactions) - 1)
        atom["timestamp"] = time.time()
        session.interactions[-1] = atom
        return atom

    def _target_identity(self, target: Optional[Dict[str, Any]]) -> tuple[str, str, str, str]:
        target = target or {}
        fallback = target.get("fallback") or {}
        fallback_value = fallback.get("value") if fallback.get("type") == "pos" else ""
        return (
            str(target.get("resource_id") or "").strip(),
            str(target.get("class") or "").strip(),
            str(target.get("bounds") or "").strip(),
            str(fallback_value or ""),
        )

    def _build_tap_atom(
        self,
        x: int,
        y: int,
        element: Optional[Dict[str, Any]],
        page_data: Optional[Dict[str, Any]],
        *,
        source: str,
        confidence: float,
        raw: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        target = self._build_target(element, x=x, y=y)
        label = self._build_target_label(target, fallback=f"position ({x}, {y})")
        return {
            "id": self._new_atom_id(),
            "type": "tap",
            "name": f"Tap {label}",
            "target": target,
            "page": self._build_page(page_data),
            "input": None,
            "assert_after": self._build_assert_after(page_data),
            "source": source,
            "confidence": confidence,
            "x": int(x),
            "y": int(y),
            "element": element,
            "element_name": label,
            "raw": raw or {},
        }

    def _build_swipe_atom(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float,
        page_data: Optional[Dict[str, Any]],
        *,
        source: str,
        confidence: float,
        raw: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        dx = int(x2) - int(x1)
        dy = int(y2) - int(y1)
        direction = "Swipe right" if abs(dx) > abs(dy) and dx > 0 else "Swipe left" if abs(dx) > abs(dy) else "Swipe down" if dy > 0 else "Swipe up"
        return {
            "id": self._new_atom_id(),
            "type": "swipe",
            "name": direction,
            "target": {"strategy": "gesture", "fallback": {"type": "pos", "value": [int(x1), int(y1)]}},
            "page": self._build_page(page_data),
            "input": None,
            "assert_after": self._build_assert_after(page_data),
            "source": source,
            "confidence": confidence,
            "x1": int(x1),
            "y1": int(y1),
            "x2": int(x2),
            "y2": int(y2),
            "duration": float(duration),
            "raw": raw or {},
        }

    def _build_input_atom(
        self,
        text: str,
        element: Optional[Dict[str, Any]],
        x: Optional[int],
        y: Optional[int],
        page_data: Optional[Dict[str, Any]],
        *,
        source: str,
        confidence: float,
        raw: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        target = self._build_target(element, x=x, y=y)
        label = self._build_target_label(target, fallback="focused field")
        preview = text[:20] + "..." if len(text) > 20 else text
        return {
            "id": self._new_atom_id(),
            "type": "input",
            "name": f"Input \"{preview}\" into {label}",
            "target": target,
            "page": self._build_page(page_data),
            "input": {"value": text, "raw_value": text},
            "assert_after": self._build_assert_after(page_data),
            "source": source,
            "confidence": confidence,
            "text": text,
            "x": int(x) if x is not None else None,
            "y": int(y) if y is not None else None,
            "element": element,
            "element_name": label,
            "raw": raw or {},
        }

    def _interaction_to_step(self, interaction: Dict[str, Any], index: int) -> Optional[Dict[str, Any]]:
        interaction_type = interaction.get("type")

        if interaction_type == "tap":
            return self._tap_to_step(interaction, index)
        if interaction_type == "swipe":
            return self._swipe_to_step(interaction)
        if interaction_type == "input":
            return self._input_to_step(interaction, index)
        if interaction_type == "wait":
            return {
                "type": "wait",
                "name": interaction.get("name") or f"Wait {interaction.get('duration', 1)} seconds",
                "config": {"duration": interaction.get("duration", 1)},
            }

        logger.warning("Unknown interaction type: %s", interaction_type)
        return None

    def _tap_to_step(self, interaction: Dict[str, Any], index: int) -> Dict[str, Any]:
        config = self._build_step_selector_config(interaction, fallback_pos=[interaction.get("x", 0), interaction.get("y", 0)])
        return {
            "type": "click",
            "name": interaction.get("name") or f"Tap element {index + 1}",
            "config": config,
        }

    def _swipe_to_step(self, interaction: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": "swipe",
            "name": interaction.get("name") or "Swipe",
            "config": {
                "start": [interaction["x1"], interaction["y1"]],
                "end": [interaction["x2"], interaction["y2"]],
                "duration": interaction.get("duration", 0.3),
            },
        }

    def _input_to_step(self, interaction: Dict[str, Any], index: int) -> Dict[str, Any]:
        text = str((interaction.get("input") or {}).get("value") or interaction.get("text") or "")
        config = {
            "text": text,
            "value": text,
            "clear_first": True,
            **self._build_step_selector_config(interaction, fallback_pos=[interaction.get("x"), interaction.get("y")]),
        }
        return {
            "type": "input",
            "name": interaction.get("name") or f"Input text {index + 1}",
            "config": config,
        }

    def _build_step_selector_config(self, interaction: Dict[str, Any], fallback_pos: Optional[List[Any]]) -> Dict[str, Any]:
        target = interaction.get("target") or self._build_target(interaction.get("element"), x=interaction.get("x"), y=interaction.get("y"))
        selector = self._selector_from_target(target)

        if selector:
            config: Dict[str, Any] = {
                "selector_type": "selector",
                "selector": selector,
            }
            fallback = (target or {}).get("fallback") or {}
            if fallback.get("type") == "pos" and fallback.get("value"):
                config["fallback_selector_type"] = "pos"
                config["fallback_selector"] = fallback.get("value")
            return config

        pos = self._safe_pos((target or {}).get("fallback", {}).get("value") or fallback_pos)
        if pos == [0, 0] and interaction.get("type") == "input":
            return {}
        return {
            "selector_type": "pos",
            "selector": pos,
        }

    def _build_target(self, element: Optional[Dict[str, Any]], x: Optional[int], y: Optional[int]) -> Dict[str, Any]:
        fallback_pos = self._safe_pos([x, y])
        if not element or not self._should_use_selector_as_primary(element):
            return {
                "strategy": "pos",
                "fallback": {"type": "pos", "value": fallback_pos},
            }

        target: Dict[str, Any] = {
            "strategy": "semantic",
            "fallback": {"type": "pos", "value": fallback_pos},
        }
        for source_key, target_key in (
            ("resource_id", "resource_id"),
            ("text", "text"),
            ("hint", "hint"),
            ("content_desc", "content_desc"),
            ("class_name", "class"),
            ("package_name", "package"),
        ):
            value = str(element.get(source_key) or "").strip()
            if value:
                target[target_key] = value

        bounds = str(element.get("raw_bounds") or "").strip()
        if bounds:
            target["bounds"] = bounds

        return target

    def _selector_from_target(self, target: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not target or target.get("strategy") != "semantic":
            return None
        selector = {
            key: target.get(key)
            for key in ("resource_id", "text", "hint", "content_desc", "class", "package", "bounds")
            if target.get(key)
        }
        if not any(selector.get(key) for key in ("resource_id", "text", "hint", "content_desc", "class")):
            return None
        return selector

    def _build_target_label(self, target: Optional[Dict[str, Any]], fallback: str) -> str:
        if not target:
            return fallback
        label = (
            target.get("text")
            or target.get("hint")
            or target.get("content_desc")
            or self._humanize_resource_id(target.get("resource_id"))
            or self._humanize_class_name(target.get("class"))
            or fallback
        )
        return str(label).strip() or fallback

    def _humanize_resource_id(self, resource_id: Any) -> str:
        text = str(resource_id or "").strip()
        if not text:
            return ""
        if "/" in text:
            text = text.rsplit("/", 1)[-1]
        elif ":" in text:
            text = text.rsplit(":", 1)[-1]
        if text in {"content", "drawerLayout", "action_bar_root"}:
            return ""
        text = re.sub(r"^(btn|iv|tv|et|ll|rl|fl|rv|cbk|ic|img|view)_?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
        text = text.replace("_", " ").replace("-", " ")
        return " ".join(part for part in text.split() if part).strip()

    def _humanize_class_name(self, class_name: Any) -> str:
        text = str(class_name or "").strip()
        if not text:
            return ""
        tail = text.rsplit(".", 1)[-1]
        if tail.lower() in {"framelayout", "linearlayout", "relativelayout", "viewgroup"}:
            return ""
        return re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", tail).strip()

    def _build_page(self, page_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        page_data = page_data or {}
        return {
            "package": page_data.get("package_name") or "",
            "activity": page_data.get("activity") or "",
            "screen_key": page_data.get("screen_key") or "",
        }

    def _build_assert_after(self, page_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        page = self._build_page(page_data)
        return {
            "type": "page_stable",
            "package": page.get("package"),
            "activity": page.get("activity"),
        }

    def _should_use_selector_as_primary(self, element: Optional[Dict[str, Any]]) -> bool:
        if not element:
            return False
        if not str(element.get("resource_id") or "").strip():
            return False
        return not self._is_generic_container(element)

    def _is_generic_container(self, element: Dict[str, Any]) -> bool:
        class_name = str(element.get("class_name") or "").strip().lower()
        signature = " ".join(
            str(element.get(field) or "").strip().lower()
            for field in ("resource_id", "text", "hint", "content_desc", "name")
        )
        interaction_role = str(element.get("interaction_role") or "").strip().lower()

        if interaction_role in {"input", "button", "checkbox", "switch", "slider", "tab", "option", "entry", "search", "rich_text"}:
            return False
        if any(marker in signature for marker in INPUT_LIKE_MARKERS):
            return False
        if element.get("scrollable"):
            return True
        return any(marker in class_name for marker in GENERIC_CONTAINER_MARKERS)

    def _safe_pos(self, value: Any) -> List[int]:
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            try:
                return [int(value[0] or 0), int(value[1] or 0)]
            except (TypeError, ValueError):
                return [0, 0]
        return [0, 0]

    def _new_atom_id(self) -> str:
        return f"atom_{uuid.uuid4().hex[:12]}"


_recording_manager = RecordingManager()


def get_recording_manager() -> RecordingManager:
    return _recording_manager
