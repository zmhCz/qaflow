# -*- coding: utf-8 -*-
"""Lightweight Android performance sampling during APP automation runs."""
from __future__ import annotations

import logging
import re
import subprocess
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from .logcat_helper import get_adb_path

logger = logging.getLogger(__name__)


class AndroidPerformanceMonitor:
    """Collect best-effort device/app metrics through ADB while a test is running."""

    def __init__(
        self,
        device_id: str,
        package_name: str,
        adb_path: Optional[str] = None,
        sample_interval: float = 2.0,
        max_samples: int = 600,
    ) -> None:
        self.device_id = device_id
        self.package_name = package_name or ""
        self.adb_path = adb_path or get_adb_path()
        self.sample_interval = max(float(sample_interval or 2.0), 0.5)
        self.max_samples = max(int(max_samples or 600), 1)
        self.samples: List[Dict[str, Any]] = []
        self.errors: List[str] = []
        self.started_at: Optional[datetime] = None
        self.ended_at: Optional[datetime] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if not self.device_id:
            self.errors.append("missing device_id")
            return
        self.started_at = datetime.utcnow()
        self._thread = threading.Thread(target=self._run_loop, name=f"app-perf-{self.device_id}", daemon=True)
        self._thread.start()

    def stop(self) -> Dict[str, Any]:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=max(self.sample_interval + 1, 3))
        self.ended_at = datetime.utcnow()
        return self.summary()

    def summary(self) -> Dict[str, Any]:
        duration = None
        if self.started_at and self.ended_at:
            duration = round((self.ended_at - self.started_at).total_seconds(), 3)

        cpu_values = [s["cpu_percent"] for s in self.samples if isinstance(s.get("cpu_percent"), (int, float))]
        memory_values = [s["memory_pss_mb"] for s in self.samples if isinstance(s.get("memory_pss_mb"), (int, float))]
        temp_values = [s["battery_temperature_c"] for s in self.samples if isinstance(s.get("battery_temperature_c"), (int, float))]
        battery_values = [s["battery_level"] for s in self.samples if isinstance(s.get("battery_level"), (int, float))]

        return {
            "enabled": True,
            "platform": "android",
            "device_id": self.device_id,
            "package_name": self.package_name,
            "adb_path": self.adb_path,
            "sample_interval": self.sample_interval,
            "sample_count": len(self.samples),
            "started_at": self.started_at.isoformat() + "Z" if self.started_at else None,
            "ended_at": self.ended_at.isoformat() + "Z" if self.ended_at else None,
            "duration": duration,
            "cpu": self._stats(cpu_values),
            "memory_pss_mb": self._stats(memory_values),
            "battery_temperature_c": self._stats(temp_values),
            "battery_level": self._stats(battery_values),
            "samples": self.samples[-self.max_samples:],
            "errors": self.errors[-20:],
        }

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            started = time.monotonic()
            try:
                sample = self._collect_sample()
                self.samples.append(sample)
                if len(self.samples) > self.max_samples:
                    self.samples = self.samples[-self.max_samples:]
            except Exception as exc:  # pragma: no cover - device/adb dependent
                message = str(exc)
                logger.warning("APP performance sample failed: %s", message)
                self.errors.append(message[:300])

            elapsed = time.monotonic() - started
            wait_time = max(self.sample_interval - elapsed, 0.1)
            self._stop_event.wait(wait_time)

    def _collect_sample(self) -> Dict[str, Any]:
        sample: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        sample_errors: List[str] = []

        if self.package_name:
            try:
                cpu = self._collect_cpu_percent()
                if cpu is not None:
                    sample["cpu_percent"] = round(cpu, 2)
            except Exception as exc:  # pragma: no cover - device/adb dependent
                sample_errors.append(f"cpu: {str(exc)[:160]}")

            try:
                memory = self._collect_memory_pss_mb()
                if memory is not None:
                    sample["memory_pss_mb"] = round(memory, 2)
            except Exception as exc:  # pragma: no cover - device/adb dependent
                sample_errors.append(f"memory: {str(exc)[:160]}")

        try:
            battery = self._collect_battery()
            sample.update(battery)
        except Exception as exc:  # pragma: no cover - device/adb dependent
            sample_errors.append(f"battery: {str(exc)[:160]}")

        if sample_errors:
            sample["errors"] = sample_errors
            self.errors.extend(sample_errors)
        return sample

    def _collect_cpu_percent(self) -> Optional[float]:
        output = self._adb(["shell", "dumpsys", "cpuinfo"], timeout=8)
        values = []
        for line in output.splitlines():
            if self.package_name not in line:
                continue
            match = re.search(r"(\d+(?:\.\d+)?)%", line)
            if match:
                values.append(float(match.group(1)))
        if values:
            return sum(values)

        output = self._adb(["shell", "sh", "-c", f"top -b -n 1 | grep {self.package_name} || true"], timeout=8)
        values = []
        for line in output.splitlines():
            if self.package_name not in line:
                continue
            percent_match = re.search(r"(\d+(?:\.\d+)?)%", line)
            if percent_match:
                values.append(float(percent_match.group(1)))
                continue
            numeric_values = re.findall(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])", line)
            if numeric_values:
                values.append(float(numeric_values[min(len(numeric_values) - 1, 2)]))
        return sum(values) if values else None

    def _collect_memory_pss_mb(self) -> Optional[float]:
        output = self._adb(["shell", "dumpsys", "meminfo", self.package_name], timeout=8)
        match = re.search(r"TOTAL\s+PSS:\s*([\d,]+)", output, re.IGNORECASE)
        if not match:
            match = re.search(r"^\s*TOTAL\s+([\d,]+)", output, re.MULTILINE)
        if not match:
            return None
        kb = int(match.group(1).replace(",", ""))
        return kb / 1024

    def _collect_battery(self) -> Dict[str, Any]:
        output = self._adb(["shell", "dumpsys", "battery"], timeout=8)
        data: Dict[str, Any] = {}
        for raw_line in output.splitlines():
            if ":" not in raw_line:
                continue
            key, value = raw_line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
            if key == "level":
                data["battery_level"] = self._to_number(value)
            elif key == "temperature":
                temperature = self._to_number(value)
                if temperature is not None:
                    data["battery_temperature_c"] = round(float(temperature) / 10, 1)
            elif key == "voltage":
                voltage = self._to_number(value)
                if voltage is not None:
                    data["battery_voltage_mv"] = voltage
            elif key == "status":
                data["battery_status"] = value
        return data

    def _adb(self, args: List[str], timeout: int = 8) -> str:
        cmd = [self.adb_path, "-s", self.device_id, *args]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "adb command failed").strip())
        return result.stdout or ""

    @staticmethod
    def _stats(values: List[float]) -> Dict[str, Any]:
        if not values:
            return {"avg": None, "max": None, "min": None, "last": None}
        return {
            "avg": round(sum(values) / len(values), 2),
            "max": round(max(values), 2),
            "min": round(min(values), 2),
            "last": round(values[-1], 2),
        }

    @staticmethod
    def _to_number(value: str) -> Optional[float]:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return int(number) if number.is_integer() else number
