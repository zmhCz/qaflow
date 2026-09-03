# -*- coding: utf-8 -*-
"""Execution precheck helpers for APP automation."""
from __future__ import annotations

import logging
import re
import subprocess
import time
from typing import Any, Dict, Optional

from ..constants import DeviceStatus
from .logcat_helper import get_adb_path

logger = logging.getLogger(__name__)


BLOCKING_VERDICTS = {"unavailable"}


def _run_adb(device_id: str, args: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [get_adb_path(), "-s", device_id, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=timeout,
        check=False,
    )


def _add_check(
    checks: list[Dict[str, Any]],
    key: str,
    name: str,
    passed: bool,
    message: str = "",
    detail: Optional[Dict[str, Any]] = None,
    suggestion: str = "",
) -> None:
    checks.append(
        {
            "key": key,
            "name": name,
            "passed": bool(passed),
            "message": message,
            "detail": detail or {},
            "suggestion": suggestion,
        }
    )


def _run_check(
    checks: list[Dict[str, Any]],
    key: str,
    name: str,
    func,
    suggestion: str = "",
    required: bool = True,
) -> Dict[str, Any]:
    start = time.time()
    try:
        detail = func() or {}
        elapsed_ms = int((time.time() - start) * 1000)
        _add_check(checks, key, name, True, f"正常，耗时 {elapsed_ms}ms", detail)
        return detail
    except subprocess.TimeoutExpired:
        _add_check(checks, key, name, False, "检查超时", {"required": required}, suggestion or "请检查设备连接和 USB 调试授权。")
    except Exception as exc:
        _add_check(checks, key, name, False, str(exc), {"required": required}, suggestion)
    return {}


def _require_adb_state(device_id: str) -> Dict[str, Any]:
    result = _run_adb(device_id, ["get-state"], timeout=6)
    state = (result.stdout or "").strip()
    if result.returncode != 0 or state != "device":
        raise RuntimeError((result.stderr or result.stdout or f"adb state={state or '-'}").strip())
    return {"state": state}


def _require_screen_size(device_id: str) -> Dict[str, Any]:
    result = _run_adb(device_id, ["shell", "wm", "size"], timeout=6)
    output = result.stdout or ""
    match = re.search(r"Physical size:\s*(\d+)x(\d+)", output)
    if result.returncode != 0 or not match:
        raise RuntimeError((result.stderr or output or "无法识别屏幕尺寸").strip())
    return {"size": f"{match.group(1)}x{match.group(2)}"}


def _require_screenshot(device_id: str) -> Dict[str, Any]:
    result = subprocess.run(
        [get_adb_path(), "-s", device_id, "exec-out", "screencap", "-p"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    byte_count = len(result.stdout or b"")
    if result.returncode != 0 or byte_count <= 0:
        stderr = (result.stderr or b"").decode("utf-8", errors="ignore").strip()
        raise RuntimeError(stderr or "截图结果为空")
    return {"bytes": byte_count}


def _require_ui_xml(device_id: str) -> Dict[str, Any]:
    command = (
        "rm -f /data/local/tmp/qaflow_uidump.xml >/dev/null 2>&1; "
        "uiautomator dump --compressed /data/local/tmp/qaflow_uidump.xml >/dev/null 2>&1 "
        "&& cat /data/local/tmp/qaflow_uidump.xml"
    )
    result = _run_adb(device_id, ["shell", "sh", "-c", command], timeout=15)
    output = result.stdout or ""
    if result.returncode != 0 or "</hierarchy>" not in output:
        raise RuntimeError((result.stderr or output[:200] or "未返回有效 UI XML").strip())
    return {"xml_length": len(output)}


def _check_package_installed(device_id: str, package_name: str) -> Dict[str, Any]:
    if not package_name:
        return {"skipped": True}
    result = _run_adb(device_id, ["shell", "pm", "path", package_name], timeout=8)
    output = (result.stdout or "").strip()
    if result.returncode != 0 or not output.startswith("package:"):
        raise RuntimeError(f"设备未安装应用包: {package_name}")
    return {"package_name": package_name, "path": output.splitlines()[0]}


def run_execution_precheck(device, package_name: str = "") -> Dict[str, Any]:
    """Return a normalized precheck result for execution submission and task guards."""
    checks: list[Dict[str, Any]] = []

    if not device:
        _add_check(checks, "device", "设备记录", False, "未找到执行设备", suggestion="请先选择可用设备。")
        return _build_result("", "", checks)

    if getattr(device, "status", "") == DeviceStatus.OFFLINE:
        _add_check(
            checks,
            "device_status",
            "平台设备状态",
            False,
            "设备在平台中标记为离线",
            {"device_status": device.status},
            "请刷新设备列表，确认 adb devices 显示为 device 状态。",
        )
        return _build_result(device.device_id, getattr(device, "name", "") or device.device_id, checks)

    _add_check(
        checks,
        "device_status",
        "平台设备状态",
        True,
        f"平台状态: {getattr(device, 'status', '-')}",
        {"device_status": getattr(device, "status", "")},
    )
    _run_check(checks, "adb_state", "ADB 连通", lambda: _require_adb_state(device.device_id), "请确认 USB 调试已授权，或重新插拔设备。")
    _run_check(checks, "screen_size", "屏幕尺寸", lambda: _require_screen_size(device.device_id), "无法获取屏幕尺寸时，通常是设备连接不稳定。")
    _run_check(checks, "screenshot", "截图能力", lambda: _require_screenshot(device.device_id), "截图失败会影响报告和元素定位，请先处理设备连接。")
    _run_check(checks, "ui_xml", "UI 树获取", lambda: _require_ui_xml(device.device_id), "UI 树失败会影响语义元素定位，请确认手机未锁屏。")
    if package_name:
        _run_check(
            checks,
            "package_installed",
            "应用安装状态",
            lambda: _check_package_installed(device.device_id, package_name),
            f"请先安装应用包 {package_name}，或检查用例绑定的包名是否正确。",
        )

    return _build_result(device.device_id, getattr(device, "name", "") or device.device_id, checks)


def _build_result(device_id: str, device_name: str, checks: list[Dict[str, Any]]) -> Dict[str, Any]:
    required_checks = [item for item in checks if item.get("detail", {}).get("required", True)]
    failed_required = [item for item in required_checks if not item["passed"]]
    passed_count = sum(1 for item in checks if item["passed"])

    if failed_required:
        verdict = "unavailable"
    elif passed_count == len(checks):
        verdict = "executable"
    else:
        verdict = "needs_attention"

    suggestions = [item["suggestion"] for item in checks if not item["passed"] and item.get("suggestion")]
    score = int((passed_count / max(len(checks), 1)) * 100)
    return {
        "device_id": device_id,
        "device_name": device_name,
        "score": score,
        "verdict": verdict,
        "verdict_text": {
            "executable": "可执行",
            "needs_attention": "需处理",
            "unavailable": "不可用",
        }.get(verdict, "需处理"),
        "can_submit": verdict not in BLOCKING_VERDICTS,
        "checks": checks,
        "suggestions": suggestions,
    }


def build_precheck_error_message(precheck: Dict[str, Any]) -> str:
    """Human-readable short message for API responses and execution errors."""
    failed = [item for item in precheck.get("checks", []) if not item.get("passed")]
    if not failed:
        return "执行前预检未通过"
    first = failed[0]
    suggestion = first.get("suggestion") or ""
    detail = f"{first.get('name')}: {first.get('message')}"
    return f"执行前预检未通过，{detail}" + (f"。建议：{suggestion}" if suggestion else "")
