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
import socket
import subprocess
import sys
import time
from typing import Any

import requests


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


def request_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def run_command(args: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )


def discover_adb_devices(adb_path: str) -> list[dict[str, Any]]:
    result = run_command([adb_path, "devices", "-l"], timeout=10)
    if result.returncode != 0:
        return []

    devices: list[dict[str, Any]] = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.strip().split()
        if len(parts) < 2 or parts[1] != "device":
            continue
        device_id = parts[0]
        model = ""
        for item in parts[2:]:
            if item.startswith("model:"):
                model = item.split(":", 1)[1]
                break
        android_version = ""
        version_result = run_command(
            [adb_path, "-s", device_id, "shell", "getprop", "ro.build.version.release"],
            timeout=8,
        )
        if version_result.returncode == 0:
            android_version = version_result.stdout.strip()
        devices.append({
            "device_id": device_id,
            "name": model or device_id,
            "status": "online",
            "android_version": android_version,
            "connection_type": "real_device",
            "device_specs": {"source": "qaflow_agent"},
        })
    return devices


def heartbeat(base_url: str, token: str, agent_id: str, name: str, devices: list[dict[str, Any]], dry_run: bool) -> dict[str, Any]:
    response = requests.post(
        api_url(base_url, "/api/app-automation/execution-agents/heartbeat/"),
        headers=request_headers(token),
        json={
            "agent_id": agent_id,
            "name": name,
            "devices": devices,
            "capabilities": {
                "adb": bool(devices),
                "dry_run": dry_run,
                "host": socket.gethostname(),
            },
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def claim_task(base_url: str, token: str, agent_id: str, device_ids: list[str]) -> dict[str, Any] | None:
    response = requests.post(
        api_url(base_url, "/api/app-automation/execution-agents/claim/"),
        headers=request_headers(token),
        json={"agent_id": agent_id, "device_ids": device_ids},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("data")


def report_status(base_url: str, token: str, agent_id: str, execution_id: int, payload: dict[str, Any]) -> None:
    response = requests.post(
        api_url(base_url, f"/api/app-automation/execution-agents/executions/{execution_id}/status/"),
        headers=request_headers(token),
        json={"agent_id": agent_id, **payload},
        timeout=20,
    )
    response.raise_for_status()


def run_dry_task(base_url: str, token: str, agent_id: str, task: dict[str, Any]) -> None:
    execution_id = int(task["execution_id"])
    steps = task.get("ui_flow", {}).get("steps", [])
    if isinstance(task.get("ui_flow"), list):
        steps = task.get("ui_flow")
    total_steps = len(steps) or 1

    report_status(base_url, token, agent_id, execution_id, {
        "status": "running",
        "progress": 30,
        "message": "Agent dry-run 已领取任务，正在模拟执行",
        "total_steps": total_steps,
    })
    time.sleep(0.5)
    report_status(base_url, token, agent_id, execution_id, {
        "status": "completed",
        "result": "passed",
        "progress": 100,
        "message": "Agent dry-run 执行完成，云端回传链路可用",
        "total_steps": total_steps,
        "passed_steps": total_steps,
        "failed_steps": 0,
        "log_text": json.dumps(task, ensure_ascii=False, indent=2),
    })


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QAFlow local execution Agent")
    parser.add_argument("--base-url", required=True, help="QAFlow server base URL, e.g. http://122.51.247.117")
    parser.add_argument("--username", required=True, help="QAFlow username")
    parser.add_argument("--password", default="", help="QAFlow password. Omit it to input interactively.")
    parser.add_argument("--agent-id", default=socket.gethostname(), help="Stable local agent id")
    parser.add_argument("--name", default=f"{socket.gethostname()} 本地执行机", help="Agent display name")
    parser.add_argument("--adb-path", default="adb", help="ADB executable path")
    parser.add_argument("--fake-device", default="", help="Register a fake device id for dry-run verification")
    parser.add_argument("--interval", type=int, default=10, help="Polling interval in seconds")
    parser.add_argument("--once", action="store_true", help="Run one heartbeat/claim cycle and exit")
    parser.add_argument("--dry-run", action="store_true", help="Do not control phone; report a simulated pass result")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    password = args.password or getpass.getpass("QAFlow password: ")
    token = login(args.base_url, args.username, password)
    print(f"[agent] logged in as {args.username}")

    while True:
        devices = discover_adb_devices(args.adb_path)
        if args.fake_device and not devices:
            devices = [{
                "device_id": args.fake_device,
                "name": f"{args.fake_device} dry-run",
                "status": "online",
                "android_version": "",
                "connection_type": "real_device",
                "device_specs": {"source": "fake-device"},
            }]

        heartbeat_result = heartbeat(args.base_url, token, args.agent_id, args.name, devices, args.dry_run)
        print(f"[agent] heartbeat ok, devices={heartbeat_result.get('device_count', 0)}")

        task = claim_task(args.base_url, token, args.agent_id, [item["device_id"] for item in devices])
        if task:
            print(f"[agent] claimed execution #{task['execution_id']}: {task.get('test_case_name', '')}")
            if args.dry_run:
                run_dry_task(args.base_url, token, args.agent_id, task)
                print(f"[agent] execution #{task['execution_id']} reported as passed")
            else:
                report_status(args.base_url, token, args.agent_id, int(task["execution_id"]), {
                    "status": "error",
                    "progress": 100,
                    "message": "当前 Agent 未启用真机执行器，请使用 --dry-run 验证回传链路",
                    "error_message": "real device runner is not wired in this first-stage agent",
                })
                print("[agent] real runner is not wired yet; reported error to server")
        else:
            print("[agent] no pending task")

        if args.once:
            return 0
        time.sleep(max(args.interval, 3))


if __name__ == "__main__":
    sys.exit(main())
