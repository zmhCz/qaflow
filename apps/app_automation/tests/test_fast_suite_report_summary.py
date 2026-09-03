# -*- coding: utf-8 -*-
"""Fast-suite result compatibility tests."""

from datetime import datetime
from types import SimpleNamespace

from django.conf import settings
from django.utils import timezone

from apps.app_automation.tasks import _write_fast_suite_result_file
from apps.app_automation.utils.report_summary import build_execution_report_summary


def test_fast_suite_result_file_keeps_steps_and_screenshot_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path))
    results_dir = tmp_path / "app-automation" / "allure-results" / "execution_9001"
    results_dir.mkdir(parents=True)
    screenshot = results_dir / "step_01_before.png"
    screenshot.write_bytes(b"\x89PNG\r\n\x1a\n")

    test_case = SimpleNamespace(
        id=3001,
        name="进入消息TAB",
        ui_flow=[
            {"type": "launch_activity", "name": "冷启动APP"},
            {"type": "click", "name": "点击消息TAB"},
        ],
        project=None,
        app_package=None,
    )
    execution = SimpleNamespace(
        id=9001,
        test_case=test_case,
        test_suite=None,
        device=None,
        user=None,
        status="completed",
        result="passed",
        total_steps=2,
        passed_steps=2,
        failed_steps=0,
        performance_metrics={},
        started_at=timezone.make_aware(datetime(2026, 8, 31, 10, 0, 0)),
        finished_at=timezone.make_aware(datetime(2026, 8, 31, 10, 1, 0)),
        duration=60,
        report_path="",
        error_message="",
        case_name=test_case.name,
        device_name="",
        user_name="",
    )
    runner = SimpleNamespace(
        _visual_evidence_attachments=[
            {
                "path": str(screenshot),
                "name": "步骤1-冷启动APP-操作前位置",
                "step_index": 1,
                "step_name": "冷启动APP",
            }
        ]
    )

    _write_fast_suite_result_file(execution, test_case, {"total": 2, "passed": 2, "failed": 0}, runner)

    request = SimpleNamespace(build_absolute_uri=lambda path: f"http://testserver{path}")
    summary = build_execution_report_summary(execution, request=request)

    assert summary["step_outline"]["source"] == "allure"
    assert summary["steps"] == {"total": 2, "passed": 2, "failed": 0, "pass_rate": 100.0}
    assert summary["artifacts"]["counts"]["screenshots"] == 1
    assert summary["visual_evidence"]["total"] == 1
