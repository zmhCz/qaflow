# -*- coding: utf-8 -*-
"""APP 自动化执行期间的 logcat 采集工具。"""
from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

CRASH_MARKERS = (
    "FATAL EXCEPTION",
    "AndroidRuntime",
    "ANR in",
    "Process:",
    "SIGSEGV",
    "SIGABRT",
    "signal 11",
    "signal 6",
)


def get_adb_path() -> str:
    """从平台配置中读取 ADB 路径。"""
    try:
        from ..models import AppTestConfig

        config = AppTestConfig.objects.first()
        if config and config.adb_path:
            return config.adb_path
    except Exception as exc:  # pragma: no cover
        logger.warning("读取 ADB 配置失败，改用默认 adb: %s", exc)
    return "adb"


class AppLogcatCollector:
    """仅在单次用例执行生命周期内采集 logcat。"""

    def __init__(
        self,
        device_id: str,
        results_dir: Optional[str] = None,
        adb_path: Optional[str] = None,
    ) -> None:
        self.device_id = device_id
        self.adb_path = adb_path or get_adb_path()
        self.results_dir = Path(results_dir) if results_dir else None

    def clear(self) -> None:
        """清空当前设备 logcat 缓冲。"""
        try:
            self._run_adb(["logcat", "-c"], timeout=15)
        except Exception as exc:  # pragma: no cover
            logger.warning("清空 logcat 失败: %s", exc)

    def collect(self) -> str:
        """一次性导出当前设备 logcat。"""
        try:
            result = self._run_adb(["logcat", "-d", "-v", "threadtime"], timeout=60)
            return result.stdout or ""
        except Exception as exc:  # pragma: no cover
            logger.warning("采集 logcat 失败: %s", exc)
            return ""

    def save_artifacts(self, prefix: str) -> Dict[str, str]:
        """导出完整日志和摘要文件。"""
        dump_text = self.collect()
        summary_text = self._build_summary(dump_text)

        saved: Dict[str, str] = {
            "dump_text": dump_text,
            "summary_text": summary_text,
        }

        if not self.results_dir:
            return saved

        self.results_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_prefix = prefix.replace(os.sep, "_").replace(" ", "_")

        dump_path = self.results_dir / f"{safe_prefix}_logcat_{self.device_id}_{stamp}.txt"
        summary_path = self.results_dir / f"{safe_prefix}_logcat_summary_{self.device_id}_{stamp}.txt"

        dump_path.write_text(dump_text, encoding="utf-8", errors="ignore")
        summary_path.write_text(summary_text, encoding="utf-8", errors="ignore")

        saved["dump_path"] = str(dump_path)
        saved["summary_path"] = str(summary_path)
        return saved

    def _run_adb(self, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
        cmd = [self.adb_path, "-s", self.device_id, *args]
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError:
            logger.warning("找不到 ADB 命令: %s", self.adb_path)
            raise
        except subprocess.TimeoutExpired as exc:
            logger.warning("ADB 命令超时: %s", " ".join(cmd))
            return subprocess.CompletedProcess(cmd, returncode=1, stdout=exc.stdout or "", stderr=exc.stderr or "")

    def _build_summary(self, dump_text: str, context_lines: int = 30) -> str:
        """提取崩溃附近的关键日志。"""
        if not dump_text.strip():
            return "未获取到 logcat 输出。"

        lines = dump_text.splitlines()
        hit_indexes = []
        for idx, line in enumerate(lines):
            if any(marker.lower() in line.lower() for marker in CRASH_MARKERS):
                hit_indexes.append(idx)

        if not hit_indexes:
            tail = lines[-200:]
            return "\n".join(tail) if tail else "未发现明显崩溃关键字，以下为末尾日志为空。"

        selected = set()
        for idx in hit_indexes:
            start = max(0, idx - context_lines)
            end = min(len(lines), idx + context_lines + 1)
            for line_index in range(start, end):
                selected.add(line_index)

        return "\n".join(lines[i] for i in sorted(selected))
