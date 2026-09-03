#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""QAFlow local execution Agent.

First-stage goal: verify the cloud-control/local-execution callback loop. In
dry-run mode the agent does not control the phone; it claims one queued task and
reports a completed result back to QAFlow.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from typing import Any

import requests


DEFAULT_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".qaflow", "agent.json")


def api_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def login(base_url: str, username: str, password: str) -> str:
    response = requests.post(
        api_url(base_url, "/api/auth/login/"),
        json={"username": username, "password": password},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    token = data.get("access")
    if not token:
        raise RuntimeError("登录成功但未返回 access token")
    return token


def load_config(config_file: str) -> dict[str, Any]:
    if not os.path.exists(config_file):
        return {}
    with open(config_file, "r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def save_config(config_file: str, payload: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(config_file), exist_ok=True)
    with open(config_file, "w", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj, ensure_ascii=False, indent=2)


def request_headers(token: str, token_type: str = "jwt") -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token_type == "agent":
        headers["X-QAFlow-Agent-Token"] = token
    else:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def run_command(args: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )


def make_check(
    code: str,
    name: str,
    status: str,
    message: str,
    suggestion: str = "",
    detail: str = "",
) -> dict[str, str]:
    return {
        "code": code,
        "name": name,
        "status": status,
        "message": message,
        "suggestion": suggestion,
        "detail": detail,
    }


def normalize_adb_path(adb_path: str) -> str:
    if adb_path != "adb":
        return adb_path
    return shutil.which("adb") or adb_path


def adb_version_check(adb_path: str) -> tuple[dict[str, str], bool]:
    resolved_adb = normalize_adb_path(adb_path)
    result = run_command([resolved_adb, "version"], timeout=8)
    if result.returncode == 0:
        first_line = (result.stdout or "").splitlines()[0] if result.stdout else "ADB 可用"
        return (
            make_check(
                "adb_available",
                "ADB 环境",
                "passed",
                "已检测到 ADB，可执行 Android 设备控制命令",
                detail=first_line,
            ),
            True,
        )
    return (
        make_check(
            "adb_available",
            "ADB 环境",
            "failed",
            "未检测到可用 ADB，当前电脑不能控制 Android 手机",
            "安装 Android Platform Tools，并把 adb 加入 PATH；或启动 Agent 时用 --adb-path 指定 adb.exe 路径",
            (result.stderr or result.stdout or "").strip(),
        ),
        False,
    )


def parse_adb_device_states(adb_path: str) -> tuple[list[dict[str, str]], str]:
    result = run_command([adb_path, "devices", "-l"], timeout=10)
    if result.returncode != 0:
        return [], (result.stderr or result.stdout or "").strip()

    devices: list[dict[str, str]] = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        device_id = parts[0]
        state = parts[1]
        model = ""
        for item in parts[2:]:
            if item.startswith("model:"):
                model = item.split(":", 1)[1]
                break
        devices.append({"device_id": device_id, "state": state, "model": model})
    return devices, ""


def discover_adb_devices(adb_path: str) -> list[dict[str, Any]]:
    adb_path = normalize_adb_path(adb_path)
    device_states, _ = parse_adb_device_states(adb_path)
    devices: list[dict[str, Any]] = []
    for item in device_states:
        if item["state"] != "device":
            continue
        device_id = item["device_id"]
        android_version = ""
        version_result = run_command(
            [adb_path, "-s", device_id, "shell", "getprop", "ro.build.version.release"],
            timeout=8,
        )
        if version_result.returncode == 0:
            android_version = version_result.stdout.strip()
        devices.append({
            "device_id": device_id,
            "name": item["model"] or device_id,
            "status": "online",
            "android_version": android_version,
            "connection_type": "real_device",
            "device_specs": {"source": "qaflow_agent"},
        })
    return devices


def build_health_report(
    base_url: str,
    username: str,
    adb_path: str,
    devices: list[dict[str, Any]],
    dry_run: bool,
    fake_device: str = "",
) -> dict[str, Any]:
    checks = [
        make_check(
            "agent_started",
            "Agent 启动",
            "passed",
            "本地 Agent 已启动并开始执行环境体检",
            detail=f"{platform.system()} {platform.release()} / Python {platform.python_version()}",
        ),
        make_check(
            "python_version",
            "Python 版本",
            "passed" if sys.version_info >= (3, 11) else "failed",
            "当前 Python 版本满足要求" if sys.version_info >= (3, 11) else "当前 Python 版本过低",
            "" if sys.version_info >= (3, 11) else "请使用 Python 3.11 或更高版本运行 Agent",
            platform.python_version(),
        ),
        make_check(
            "python_dependencies",
            "Python 依赖",
            "passed",
            "requests 等 Agent 基础依赖已可用",
        ),
        make_check(
            "cloud_auth",
            "云端连接与登录",
            "passed",
            "已连接 QAFlow 云端并完成登录",
            detail=f"{base_url.rstrip('/')} / {username}",
        ),
    ]

    adb_check, adb_ok = adb_version_check(adb_path)
    checks.append(adb_check)

    authorized_devices = devices
    if fake_device and not authorized_devices:
        checks.append(make_check(
            "dry_run_device",
            "演示设备",
            "warning",
            "当前使用 fake-device 验证链路，没有控制真实手机",
            "验证真机能力时，请去掉 --fake-device 并连接已授权 Android 手机",
            fake_device,
        ))
        authorized_devices = [{
            "device_id": fake_device,
            "name": f"{fake_device} dry-run",
            "status": "online",
            "android_version": "",
            "connection_type": "real_device",
            "device_specs": {"source": "fake-device"},
        }]

    if adb_ok:
        adb_device_states, device_error = parse_adb_device_states(normalize_adb_path(adb_path))
        if device_error:
            checks.append(make_check(
                "device_discovery",
                "设备发现",
                "failed",
                "执行 adb devices 失败，无法获取设备列表",
                "请检查 USB 连接、ADB 服务和手机 USB 调试状态",
                device_error,
            ))
        elif not adb_device_states and not fake_device:
            checks.append(make_check(
                "device_discovery",
                "设备发现",
                "failed",
                "未发现 Android 设备",
                "请插入手机，开启开发者模式和 USB 调试，并确认数据线支持传输数据",
            ))
        else:
            unauthorized = [item for item in adb_device_states if item["state"] == "unauthorized"]
            offline = [item for item in adb_device_states if item["state"] == "offline"]
            usable = [item for item in adb_device_states if item["state"] == "device"]
            if usable:
                checks.append(make_check(
                    "device_authorized",
                    "设备授权",
                    "passed",
                    f"发现 {len(usable)} 台已授权设备",
                    detail="、".join(item["device_id"] for item in usable),
                ))
            elif unauthorized:
                checks.append(make_check(
                    "device_authorized",
                    "设备授权",
                    "failed",
                    "手机尚未授权当前电脑",
                    "请看手机屏幕上的 USB 调试授权弹窗，勾选允许并点击确定",
                    "、".join(item["device_id"] for item in unauthorized),
                ))
            elif offline:
                checks.append(make_check(
                    "device_authorized",
                    "设备授权",
                    "failed",
                    "设备处于 offline 状态",
                    "请重新插拔手机，或执行 adb kill-server 后重新启动 Agent",
                    "、".join(item["device_id"] for item in offline),
                ))

    real_devices = [item for item in devices if item.get("device_specs", {}).get("source") != "fake-device"]
    if real_devices:
        target_device = real_devices[0]["device_id"]
        resolved_adb = normalize_adb_path(adb_path)
        screenshot_result = run_command(
            [resolved_adb, "-s", target_device, "shell", "screencap", "-p", "/sdcard/qaflow_agent_check.png"],
            timeout=12,
        )
        checks.append(make_check(
            "screenshot",
            "截图能力",
            "passed" if screenshot_result.returncode == 0 else "failed",
            "已验证手机截图能力" if screenshot_result.returncode == 0 else "手机截图命令执行失败",
            "" if screenshot_result.returncode == 0 else "请确认手机未锁屏、USB 调试授权正常，并重新检测",
            (screenshot_result.stderr or screenshot_result.stdout or "").strip(),
        ))

        hierarchy_result = run_command(
            [resolved_adb, "-s", target_device, "shell", "uiautomator", "dump", "/sdcard/qaflow_agent_window.xml"],
            timeout=15,
        )
        checks.append(make_check(
            "ui_hierarchy",
            "UI 层级能力",
            "passed" if hierarchy_result.returncode == 0 else "failed",
            "已验证 UI 层级获取能力" if hierarchy_result.returncode == 0 else "UI 层级获取失败",
            "" if hierarchy_result.returncode == 0 else "请确认手机亮屏且当前页面允许无障碍/UIAutomator 获取控件树",
            (hierarchy_result.stderr or hierarchy_result.stdout or "").strip(),
        ))
    elif dry_run or fake_device:
        checks.append(make_check(
            "automation_capability",
            "自动化能力",
            "warning",
            "dry-run 只验证云端回传链路，尚未验证真机截图和 UI 层级能力",
            "连接真实 Android 手机后去掉 --fake-device 重新运行 Agent",
        ))

    failed_count = len([item for item in checks if item["status"] == "failed"])
    warning_count = len([item for item in checks if item["status"] == "warning"])
    if failed_count:
        health_status = "blocked"
        health_summary = f"环境不可执行：{failed_count} 项失败，{warning_count} 项提醒"
    elif warning_count:
        health_status = "warning"
        health_summary = f"环境部分可用：{warning_count} 项提醒"
    else:
        health_status = "ready"
        health_summary = "环境可执行：本地 Agent、ADB、设备授权和基础自动化能力均正常"

    return {
        "status": health_status,
        "summary": health_summary,
        "checks": checks,
        "devices": authorized_devices,
    }


def heartbeat(
    base_url: str,
    token: str,
    token_type: str,
    agent_id: str,
    name: str,
    devices: list[dict[str, Any]],
    dry_run: bool,
    health_report: dict[str, Any],
) -> dict[str, Any]:
    adb_available = any(
        item.get("code") == "adb_available" and item.get("status") == "passed"
        for item in health_report["checks"]
    )
    real_device_count = len([
        item for item in devices
        if item.get("device_specs", {}).get("source") != "fake-device"
    ])
    response = requests.post(
        api_url(base_url, "/api/app-automation/execution-agents/heartbeat/"),
        headers=request_headers(token, token_type),
        json={
            "agent_id": agent_id,
            "name": name,
            "devices": devices,
            "health_status": health_report["status"],
            "health_summary": health_report["summary"],
            "health_checks": health_report["checks"],
            "capabilities": {
                "adb": adb_available,
                "dry_run": dry_run,
                "host": socket.gethostname(),
                "health_status": health_report["status"],
                "real_device_count": real_device_count,
            },
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def claim_task(base_url: str, token: str, token_type: str, agent_id: str, device_ids: list[str]) -> dict[str, Any] | None:
    response = requests.post(
        api_url(base_url, "/api/app-automation/execution-agents/claim/"),
        headers=request_headers(token, token_type),
        json={"agent_id": agent_id, "device_ids": device_ids},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("data")


def report_status(base_url: str, token: str, token_type: str, agent_id: str, execution_id: int, payload: dict[str, Any]) -> None:
    response = requests.post(
        api_url(base_url, f"/api/app-automation/execution-agents/executions/{execution_id}/status/"),
        headers=request_headers(token, token_type),
        json={"agent_id": agent_id, **payload},
        timeout=20,
    )
    response.raise_for_status()


def run_dry_task(base_url: str, token: str, token_type: str, agent_id: str, task: dict[str, Any]) -> None:
    execution_id = int(task["execution_id"])
    lease_token = task.get("lease_token") or ""
    attempt_no = int(task.get("attempt_no") or 0)
    steps = task.get("ui_flow", {}).get("steps", [])
    if isinstance(task.get("ui_flow"), list):
        steps = task.get("ui_flow")
    total_steps = len(steps) or 1

    report_status(base_url, token, token_type, agent_id, execution_id, {
        "status": "running",
        "progress": 30,
        "message": "Agent dry-run 已领取任务，正在模拟执行",
        "total_steps": total_steps,
        "lease_token": lease_token,
        "attempt_no": attempt_no,
        "event_seq": 1,
    })
    time.sleep(0.5)
    report_status(base_url, token, token_type, agent_id, execution_id, {
        "status": "completed",
        "result": "passed",
        "progress": 100,
        "message": "Agent dry-run 执行完成，云端回传链路可用",
        "total_steps": total_steps,
        "passed_steps": total_steps,
        "failed_steps": 0,
        "lease_token": lease_token,
        "attempt_no": attempt_no,
        "event_seq": 2,
        "log_text": json.dumps(task, ensure_ascii=False, indent=2),
    })


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QAFlow local execution Agent")
    parser.add_argument("--base-url", default="", help="QAFlow server base URL, e.g. http://122.51.247.117")
    parser.add_argument("--username", default="", help="QAFlow username")
    parser.add_argument("--password", default="", help="QAFlow password. Omit it to input interactively.")
    parser.add_argument("--agent-token", default="", help="Agent binding token generated by QAFlow. Preferred for daily use.")
    parser.add_argument("--agent-id", default="", help="Stable local agent id")
    parser.add_argument("--name", default="", help="Agent display name")
    parser.add_argument("--adb-path", default="adb", help="ADB executable path")
    parser.add_argument("--config-file", default=DEFAULT_CONFIG_PATH, help="Local Agent config file")
    parser.add_argument("--save-config", action="store_true", help="Save base-url/agent-id/agent-token locally for later runs")
    parser.add_argument("--fake-device", default="", help="Register a fake device id for dry-run verification")
    parser.add_argument("--interval", type=int, default=10, help="Polling interval in seconds")
    parser.add_argument("--once", action="store_true", help="Run one heartbeat/claim cycle and exit")
    parser.add_argument("--dry-run", action="store_true", help="Do not control phone; report a simulated pass result")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config_file)
    base_url = args.base_url or config.get("base_url") or ""
    agent_id = args.agent_id or config.get("agent_id") or socket.gethostname()
    name = args.name or config.get("name") or f"{agent_id} 本地执行机"
    agent_token = args.agent_token or config.get("agent_token") or ""
    username = args.username or config.get("username") or ""

    if not base_url:
        raise RuntimeError("缺少 --base-url，也没有找到本地配置。请先从 QAFlow 执行机页面生成启动命令。")

    if agent_token:
        token = agent_token
        token_type = "agent"
        print(f"[agent] using saved agent token, agent_id={agent_id}")
    else:
        if not username:
            raise RuntimeError("缺少 --username。建议在 QAFlow 执行机页面生成 Agent 令牌，避免反复输入账密。")
        password = args.password or getpass.getpass("QAFlow password: ")
        token = login(base_url, username, password)
        token_type = "jwt"
        print(f"[agent] logged in as {username}")

    if args.save_config:
        save_config(args.config_file, {
            "base_url": base_url,
            "agent_id": agent_id,
            "name": name,
            "agent_token": agent_token,
            "adb_path": args.adb_path,
        })
        print(f"[agent] config saved to {args.config_file}")

    while True:
        devices = discover_adb_devices(args.adb_path)
        health_report = build_health_report(
            base_url,
            username or agent_id,
            args.adb_path,
            devices,
            args.dry_run,
            args.fake_device,
        )
        devices = health_report["devices"]

        heartbeat_result = heartbeat(base_url, token, token_type, agent_id, name, devices, args.dry_run, health_report)
        print(
            f"[agent] heartbeat ok, devices={heartbeat_result.get('device_count', 0)}, "
            f"health={health_report['status']} - {health_report['summary']}"
        )

        task = claim_task(base_url, token, token_type, agent_id, [item["device_id"] for item in devices])
        if task:
            print(f"[agent] claimed execution #{task['execution_id']}: {task.get('test_case_name', '')}")
            if args.dry_run:
                run_dry_task(base_url, token, token_type, agent_id, task)
                print(f"[agent] execution #{task['execution_id']} reported as passed")
            else:
                report_status(base_url, token, token_type, agent_id, int(task["execution_id"]), {
                    "status": "error",
                    "progress": 100,
                    "message": "当前 Agent 未启用真机执行器，请使用 --dry-run 验证回传链路",
                    "error_message": "real device runner is not wired in this first-stage agent",
                    "lease_token": task.get("lease_token") or "",
                    "attempt_no": int(task.get("attempt_no") or 0),
                    "event_seq": 1,
                })
                print("[agent] real runner is not wired yet; reported error to server")
        else:
            print("[agent] no pending task")

        if args.once:
            return 0
        time.sleep(max(args.interval, 3))


if __name__ == "__main__":
    sys.exit(main())
