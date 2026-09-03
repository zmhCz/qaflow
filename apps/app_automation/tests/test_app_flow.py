# -*- coding: utf-8 -*-
"""APP UI Flow 测试入口。"""
import logging
import os

import allure
import pytest

from apps.app_automation.models import AppTestCase, AppTestExecution
from apps.app_automation.runners.ui_flow_runner import UiFlowRunner
from apps.app_automation.utils.airtest_base import AirtestBase
from apps.app_automation.utils.logcat_helper import AppLogcatCollector

logger = logging.getLogger(__name__)


def _make_progress_callback(execution_id):
    """生成执行进度回调。"""
    if not execution_id:
        return None

    def _send_ws(eid, status, progress, message):
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer

            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"app_execution_{eid}",
                    {
                        "type": "execution_update",
                        "execution_id": int(eid),
                        "status": status,
                        "progress": progress,
                        "message": message,
                        "report_path": None,
                        "finished_at": None,
                    },
                )
        except Exception as exc:  # pragma: no cover
            logger.debug("WebSocket 通知失败: %s", exc)

    def callback(current_step, total_steps, step_name, status):
        if total_steps <= 0:
            return

        if status == "running":
            progress = int(10 + ((current_step - 1) / total_steps) * 80)
            message = f"步骤 {current_step}/{total_steps}: {step_name} - 执行中"
        else:
            progress = int(10 + (current_step / total_steps) * 80)
            message = f"步骤 {current_step}/{total_steps}: {step_name} - {'通过' if status == 'passed' else '失败'}"

        progress = min(progress, 90)

        try:
            AppTestExecution.objects.filter(id=execution_id).update(progress=progress)
        except Exception as exc:  # pragma: no cover
            logger.debug("更新执行进度失败: %s", exc)

        _send_ws(execution_id, "running", progress, message)

    return callback


@allure.feature("APP自动化测试")
class TestAppFlow:
    """APP UI Flow 测试类。"""

    @pytest.fixture(scope="class")
    def airtest(self, device_id, username):
        """Airtest 基础环境。"""
        airtest_base = AirtestBase(device_id=device_id, username=username)
        if not airtest_base.setup_airtest():
            pytest.fail("Airtest 环境设置失败")

        yield airtest_base
        airtest_base.teardown_airtest()

    @allure.story("执行 UI Flow")
    def test_execute_ui_flow(self, test_case_id, package_name, execution_id, airtest, username):
        """执行 UI Flow 测试。"""
        test_case = AppTestCase.objects.get(id=test_case_id)
        allure.dynamic.title(f"用例名称: {test_case.name}")
        allure.dynamic.suite("APP自动化测试")

        collector = None
        results_dir = os.getenv("APP_ALLURE_RESULTS_DIR", "")
        if os.getenv("APP_LOGCAT_CAPTURE") == "1" and airtest.device_id:
            collector = AppLogcatCollector(device_id=airtest.device_id, results_dir=results_dir)
            collector.clear()

        if isinstance(test_case.ui_flow, list):
            ui_flow = test_case.ui_flow
        elif isinstance(test_case.ui_flow, dict):
            ui_flow = test_case.ui_flow.get("steps", [])
        else:
            ui_flow = []

        first_flow_step = next((step for step in ui_flow if isinstance(step, dict)), None)
        flow_handles_launch = bool(first_flow_step and first_flow_step.get("type") == "launch_activity")

        result = {"total": 0, "passed": 0, "failed": 0}
        clear_data_before_run = os.getenv("APP_CLEAR_DATA_BEFORE_RUN") == "1"
        force_stop_before_run = os.getenv("APP_FORCE_STOP_BEFORE_RUN") == "1"
        handle_startup_dialogs = os.getenv("APP_HANDLE_STARTUP_DIALOGS", "0") == "1"
        runner = None

        try:
            if package_name:
                if flow_handles_launch:
                    allure.attach(
                        "UI Flow 已包含启动步骤，跳过框架层默认启动，避免重复冷启动和重复触发启动弹窗。",
                        name="启动策略",
                        attachment_type=allure.attachment_type.TEXT,
                    )
                elif clear_data_before_run:
                    with allure.step(f"执行前清理应用数据: {package_name}"):
                        assert airtest.clear_app_data(package_name), f"应用清数据失败: {package_name}"
                elif force_stop_before_run:
                    with allure.step(f"执行前关闭应用（冷启动）: {package_name}"):
                        assert airtest.close_app(package_name), f"应用关闭失败: {package_name}"

                if not flow_handles_launch:
                    with allure.step(f"启动应用: {package_name}"):
                        assert airtest.open_app(package_name), f"应用启动失败: {package_name}"

                if handle_startup_dialogs and not flow_handles_launch:
                    with allure.step("处理启动弹窗"):
                        airtest.handle_startup_permission_dialogs()
            else:
                allure.attach(
                    "未配置应用包名，跳过启动应用步骤",
                    name="启动应用",
                    attachment_type=allure.attachment_type.TEXT,
                )

            runner = UiFlowRunner(username=username)

            variables = test_case.variables or []
            progress_callback = _make_progress_callback(execution_id)

            with allure.step("执行 UI Flow"):
                result = runner.run(
                    ui_flow=ui_flow,
                    variables=variables,
                    runtime={"stop_on_error": True},
                    progress_callback=progress_callback,
                )

            with allure.step("验证执行结果"):
                assert result["failed"] == 0, f"UI Flow 执行失败，失败步骤: {result['failed']}"
                assert result["passed"] > 0, "没有执行任何步骤"

            allure.attach(
                f"总步骤: {result['total']}\n通过: {result['passed']}\n失败: {result['failed']}",
                name="执行统计",
                attachment_type=allure.attachment_type.TEXT,
            )
        finally:
            if runner:
                try:
                    runner.attach_visual_evidence_overview()
                except Exception as exc:  # pragma: no cover
                    logger.warning("汇总关键截图附件失败: %s", exc)

            if collector:
                try:
                    artifacts = collector.save_artifacts(prefix=f"case_{test_case_id}")
                    summary_text = artifacts.get("summary_text", "")
                    if summary_text:
                        allure.attach(
                            summary_text,
                            name="logcat崩溃摘要",
                            attachment_type=allure.attachment_type.TEXT,
                        )

                    dump_path = artifacts.get("dump_path")
                    if dump_path and os.path.exists(dump_path):
                        allure.attach.file(
                            dump_path,
                            name="logcat完整日志",
                            attachment_type=allure.attachment_type.TEXT,
                        )
                except Exception as exc:  # pragma: no cover
                    logger.warning("采集 logcat 失败: %s", exc)
