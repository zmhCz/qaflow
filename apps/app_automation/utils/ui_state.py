# -*- coding: utf-8 -*-
"""Small UI-state helpers shared by app automation runners."""
from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)
APP_PACKAGE = getattr(settings, "APP_AUTOMATION_TARGET_PACKAGE", "") or "com.example.demo"

ShellFn = Callable[[str], Any]
DumpFn = Callable[[], str]


def app_rid(name: str) -> str:
    return f"{APP_PACKAGE}:id/{name}"

STARTUP_DIALOG_SELECTORS = (
    {"resource_id": "com.android.permissioncontroller:id/permission_allow_button"},
    {"resource_id": "com.android.permissioncontroller:id/permission_allow_foreground_only_button"},
    {"resource_id": "com.android.permissioncontroller:id/permission_allow_one_time_button"},
    {"resource_id": app_rid("confirm_button")},
    {"resource_id": app_rid("btnOk")},
    {"text": "我知道了"},
    {"contains_text": "我知道了"},
)

POST_LOGIN_DIALOG_SELECTORS = (
    {"resource_id": app_rid("confirm_button")},
    {"resource_id": app_rid("btnOk")},
)


def normalize_shell_output(result: Any) -> str:
    if result is None:
        return ""
    if isinstance(result, bytes):
        return result.decode("utf-8", errors="ignore")
    if isinstance(result, (list, tuple)):
        return "".join(normalize_shell_output(item) for item in result)
    return str(result)


def extract_valid_xml(output: Any) -> str:
    text = normalize_shell_output(output)
    start = text.find("<?xml")
    end = text.rfind("</hierarchy>")
    if start >= 0 and end >= 0:
        return text[start : end + len("</hierarchy>")]
    start = text.find("<hierarchy")
    if start >= 0 and end >= 0:
        return text[start : end + len("</hierarchy>")]
    return ""


def dump_ui_xml(shell: ShellFn, retries: int = 3, interval: float = 0.35) -> str:
    commands = (
        "rm -f /data/local/tmp/uidump.xml /sdcard/uidump.xml >/dev/null 2>&1; uiautomator dump /data/local/tmp/uidump.xml >/dev/null 2>&1 && cat /data/local/tmp/uidump.xml",
        "uiautomator dump /data/local/tmp/uidump.xml >/dev/null 2>&1 && cat /data/local/tmp/uidump.xml",
        "uiautomator dump /sdcard/uidump.xml >/dev/null 2>&1 && cat /sdcard/uidump.xml",
    )
    last_output = ""

    for attempt in range(max(1, int(retries or 1))):
        for command in commands:
            try:
                output = shell(command)
            except Exception as exc:
                logger.debug("UI dump command failed: %s", exc)
                continue

            xml_text = extract_valid_xml(output)
            if xml_text:
                return xml_text
            last_output = normalize_shell_output(output)

        if attempt < retries - 1:
            time.sleep(interval)

    raise RuntimeError(f"UI dump did not return valid XML. Output: {last_output[:200]}")


def parse_bounds(bounds: str) -> tuple[int, int, int, int] | None:
    values = [int(value) for value in re.findall(r"\d+", str(bounds or ""))]
    if len(values) != 4:
        return None
    return values[0], values[1], values[2], values[3]


def node_center(node_attrs: dict[str, Any]) -> tuple[int, int] | None:
    bounds = parse_bounds(str(node_attrs.get("bounds", "")))
    if not bounds:
        return None
    x1, y1, x2, y2 = bounds
    return (x1 + x2) // 2, (y1 + y2) // 2


def load_hierarchy(xml_text: str) -> ET.Element:
    try:
        return ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise RuntimeError(f"Unable to parse UI hierarchy XML: {exc}") from exc


def _text_matches(actual: Any, expected: str, *, contains: bool = False) -> bool:
    actual_text = str(actual or "").strip()
    expected_text = str(expected or "").strip()
    if not expected_text:
        return True
    if not actual_text:
        return False
    return expected_text in actual_text if contains else actual_text == expected_text


def node_matches(attrs: dict[str, Any], selector: dict[str, Any]) -> bool:
    resource_id = selector.get("resource_id")
    if resource_id and attrs.get("resource-id") != resource_id:
        return False

    text = selector.get("text")
    if text and not _text_matches(attrs.get("text"), str(text)):
        return False

    contains_text = selector.get("contains_text")
    if contains_text and not _text_matches(attrs.get("text"), str(contains_text), contains=True):
        return False

    content_desc = selector.get("content_desc")
    if content_desc and not _text_matches(attrs.get("content-desc"), str(content_desc)):
        return False

    class_name = selector.get("class")
    if class_name and attrs.get("class") != class_name:
        return False

    return True


def find_node(xml_text: str, selector: dict[str, Any]) -> dict[str, Any] | None:
    root = load_hierarchy(xml_text)
    for node in root.iter("node"):
        attrs = dict(node.attrib)
        if node_matches(attrs, selector):
            return attrs
    return None


def tap_selector(shell: ShellFn, dump_xml: DumpFn, selector: dict[str, Any]) -> bool:
    try:
        node = find_node(dump_xml(), selector)
    except Exception as exc:
        logger.debug("UI selector lookup failed: %s", exc)
        return False

    if not node:
        return False

    center = node_center(node)
    if not center:
        return False

    x, y = center
    shell(f"input tap {x} {y}")
    return True


def tap_first_selector(shell: ShellFn, dump_xml: DumpFn, selectors: tuple[dict[str, Any], ...]) -> dict[str, Any] | None:
    for selector in selectors:
        if tap_selector(shell, dump_xml, selector):
            return selector
    return None


def handle_dialogs(
    *,
    shell: ShellFn,
    dump_xml: DumpFn,
    selectors: tuple[dict[str, Any], ...],
    timeout: float = 8.0,
    interval: float = 0.6,
    idle_rounds_to_stop: int = 2,
    settle_seconds: float = 1.0,
) -> int:
    deadline = time.time() + max(float(timeout or 0), 0.0)
    handled_count = 0
    idle_rounds = 0

    while time.time() < deadline:
        selector = tap_first_selector(shell, dump_xml, selectors)
        if selector:
            handled_count += 1
            idle_rounds = 0
            logger.info("Handled dialog selector: %s", selector)
            time.sleep(settle_seconds)
            continue

        idle_rounds += 1
        if idle_rounds >= idle_rounds_to_stop:
            break
        time.sleep(interval)

    return handled_count
