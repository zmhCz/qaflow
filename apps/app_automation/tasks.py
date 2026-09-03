# -*- coding: utf-8 -*-
"""
APP自动化测试 Celery 任务
"""
from celery import shared_task
from django.utils import timezone
import json
import logging
import os
import time
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def send_scheduled_task_notification(task_id, success):
    """发送定时任务执行通知（Webhook + 邮件）"""
    try:
        from .models import AppScheduledTask, AppNotificationLog

        task = AppScheduledTask.objects.get(id=task_id)

        if success and not task.notify_on_success:
            return
        if not success and not task.notify_on_failure:
            return
        if not task.notification_type:
            return

        status_text = '成功' if success else '失败'
        last_result = task.last_result or {}
        result_message = last_result.get('message', '')
        local_run_time = timezone.localtime(task.last_run_time).strftime('%Y-%m-%d %H:%M:%S') if task.last_run_time else '未知'
        device_name = (task.device.name or task.device.device_id) if task.device else '未指定'

        detail_content = (
            f"任务名称: {task.name}\n\n"
            f"执行状态: {status_text}\n\n"
            f"执行时间: {local_run_time}\n\n"
            f"任务类型: {task.get_task_type_display()}\n\n"
            f"执行设备: {device_name}"
        )
        if result_message:
            detail_content += f"\n\n执行结果: {result_message}"

        # Webhook 通知
        if task.notification_type in ['webhook', 'both']:
            _send_app_webhook_notification(task, detail_content, status_text)

        # 邮件通知
        if task.notification_type in ['email', 'both']:
            _send_app_email_notification(task, detail_content, status_text)

    except Exception as e:
        logger.error(f"发送APP定时任务通知失败: {e}", exc_info=True)


def _send_app_webhook_notification(task, detail_content, status_text):
    """发送 Webhook 通知"""
    import requests
    import json
    from .models import AppNotificationLog

    try:
        from apps.core.models import UnifiedNotificationConfig
        configs = UnifiedNotificationConfig.objects.filter(
            config_type__in=['webhook_wechat', 'webhook_feishu', 'webhook_dingtalk'],
            is_active=True
        )
    except Exception as e:
        logger.error(f"获取通知配置失败: {e}")
        return

    all_bots = []
    for config in configs:
        for bot in config.get_webhook_bots():
            if bot.get('enabled', True):
                all_bots.append(bot)

    if not all_bots:
        return

    for bot in all_bots:
        webhook_url = bot.get('webhook_url')
        if not webhook_url:
            continue

        bot_type = bot.get('type', 'unknown')
        success = status_text == '成功'

        if bot_type == 'wechat':
            message_data = {"msgtype": "markdown", "markdown": {"content": f"**APP自动化定时任务执行{status_text}**\n\n{detail_content}"}}
        elif bot_type == 'feishu':
            message_data = {"msg_type": "interactive", "card": {"elements": [{"tag": "div", "text": {"content": f"**APP自动化定时任务执行{status_text}**\n\n{detail_content}", "tag": "lark_md"}}], "header": {"title": {"content": f"APP自动化定时任务执行{status_text}", "tag": "plain_text"}, "template": "green" if success else "red"}}}
        elif bot_type == 'dingtalk':
            message_data = {"msgtype": "markdown", "markdown": {"title": f"APP自动化定时任务执行{status_text}", "text": f"**APP自动化定时任务执行{status_text}**\n\n{detail_content}"}}
            secret = bot.get('secret')
            if secret:
                import time as _time, hmac, hashlib, base64, urllib.parse
                timestamp = str(round(_time.time() * 1000))
                sign = urllib.parse.quote_plus(base64.b64encode(hmac.new(secret.encode('utf-8'), f'{timestamp}\n{secret}'.encode('utf-8'), digestmod=hashlib.sha256).digest()))
                webhook_url += f'{"&" if "?" in webhook_url else "?"}timestamp={timestamp}&sign={sign}'
        else:
            continue

        try:
            resp = requests.post(webhook_url, json=message_data, headers={'Content-Type': 'application/json'}, timeout=10)
            log_status = 'success' if resp.status_code == 200 else 'failed'
            AppNotificationLog.objects.create(
                task=task, task_name=task.name, task_type=task.task_type,
                notification_type='task_execution', sender_name='系统Webhook通知',
                sender_email='system@notification.com',
                recipient_info=[{'name': bot.get('name', 'Unknown'), 'webhook_url': webhook_url}],
                webhook_bot_info=bot,
                notification_content=json.dumps(message_data, ensure_ascii=False),
                status=log_status,
                error_message='' if log_status == 'success' else f'HTTP {resp.status_code}: {resp.text}',
                response_info={'status_code': resp.status_code, 'response': resp.text[:500]},
                sent_at=timezone.now()
            )
        except Exception as e:
            logger.error(f"发送Webhook失败: {e}")
            AppNotificationLog.objects.create(
                task=task, task_name=task.name, task_type=task.task_type,
                notification_type='task_execution', sender_name='系统Webhook通知',
                sender_email='system@notification.com',
                recipient_info=[{'name': bot.get('name', 'Unknown')}],
                webhook_bot_info=bot,
                notification_content=json.dumps(message_data, ensure_ascii=False),
                status='failed', error_message=str(e)
            )


def _send_app_email_notification(task, detail_content, status_text):
    """发送邮件通知"""
    from .models import AppNotificationLog

    recipients = task.notify_emails if isinstance(task.notify_emails, list) else []
    if not recipients:
        return

    try:
        from django.core.mail import send_mail
        from django.conf import settings

        subject = f"APP自动化定时任务执行{status_text}: {task.name}"
        from_email = settings.DEFAULT_FROM_EMAIL

        send_mail(subject=subject, message=detail_content, from_email=from_email, recipient_list=recipients, fail_silently=False)

        AppNotificationLog.objects.create(
            task=task, task_name=task.name, task_type=task.task_type,
            notification_type='task_execution', sender_name='系统邮件通知',
            sender_email=from_email,
            recipient_info=[{'email': e} for e in recipients],
            notification_content=detail_content, status='success', sent_at=timezone.now()
        )
    except Exception as e:
        logger.error(f"发送邮件失败: {e}", exc_info=True)
        AppNotificationLog.objects.create(
            task=task, task_name=task.name, task_type=task.task_type,
            notification_type='task_execution', sender_name='系统邮件通知',
            sender_email='',
            recipient_info=[{'email': e} for e in recipients],
            notification_content=f"发送失败: {e}", status='failed', error_message=str(e)
        )


def send_execution_update(execution_id, status=None, progress=None, message=None, report_path=None, finished_at=None, result=None):
    """通过 WebSocket 发送执行状态更新"""
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            return
        payload = {
            "type": "execution_update",
            "execution_id": int(execution_id),
            "status": status,
            "result": result,
            "progress": progress,
            "message": message,
            "report_path": report_path,
            "finished_at": finished_at.isoformat() if finished_at else None,
        }
        async_to_sync(channel_layer.group_send)(
            f"app_execution_{execution_id}",
            payload
        )
    except Exception as e:
        logger.debug(f"发送执行状态更新失败: {e}")


def _get_execution_results_dir(execution_id):
    """Return the per-execution Allure results directory used for attachments."""
    from django.conf import settings

    return os.path.join(
        settings.MEDIA_ROOT,
        'app-automation',
        'allure-results',
        f'execution_{execution_id}',
    )


def _start_logcat_collector(device, execution_id):
    """Clear logcat before a run so exported logs map to this execution."""
    if not device or not getattr(device, 'device_id', ''):
        return None
    try:
        from .utils.logcat_helper import AppLogcatCollector

        collector = AppLogcatCollector(
            device_id=device.device_id,
            results_dir=_get_execution_results_dir(execution_id),
        )
        collector.clear()
        return collector
    except Exception as exc:
        logger.warning("初始化 logcat 采集失败: %s", exc)
        return None


def _save_logcat_artifacts(collector, execution_id, prefix='execution'):
    """Persist full logcat and crash summary; never block the test result."""
    if not collector:
        return {}
    try:
        return collector.save_artifacts(f'{prefix}_{execution_id}')
    except Exception as exc:
        logger.warning("保存 logcat 附件失败: %s", exc)
        return {}


def _sync_suite_progress(suite):
    """Refresh suite counters from its current execution records."""
    from django.db.models import Q
    from .models import AppTestExecution

    total = suite.suite_cases.count()
    if total <= 0:
        suite.passed_count = 0
        suite.failed_count = 0
        suite.last_run_at = timezone.now()
        suite.save(update_fields=['passed_count', 'failed_count', 'last_run_at'])
        return 0, 0

    latest_ids = list(
        AppTestExecution.objects.filter(test_suite=suite)
        .order_by('-created_at')
        .values_list('id', flat=True)[:total]
    )
    executions = AppTestExecution.objects.filter(id__in=latest_ids)
    passed = executions.filter(status='completed', result='passed').count()
    failed = executions.filter(Q(status='error') | Q(status='completed', result='failed')).count()
    suite.passed_count = passed
    suite.failed_count = failed
    suite.last_run_at = timezone.now()
    suite.save(update_fields=['passed_count', 'failed_count', 'last_run_at'])
    return passed, failed


def _normalize_case_ui_flow(test_case):
    ui_flow = test_case.ui_flow if test_case else []
    if isinstance(ui_flow, list):
        return ui_flow
    if isinstance(ui_flow, dict):
        for key in ('steps', 'ui_flow', 'flow'):
            value = ui_flow.get(key)
            if isinstance(value, list):
                return value
    return []


def _resolve_case_package(test_case, package_name=None):
    if package_name:
        return package_name
    return (
        test_case.app_package.package_name if test_case and test_case.app_package else ""
    ) or (
        test_case.project.android_app_package.package_name
        if test_case and test_case.project and test_case.project.android_app_package else ""
    )


def _make_suite_progress_callback(execution_id):
    """Update one execution after each step in suite fast mode."""
    if not execution_id:
        return None

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
            from .models import AppTestExecution

            AppTestExecution.objects.filter(id=execution_id).update(progress=progress)
        except Exception as exc:
            logger.debug("套件快跑进度写入失败: %s", exc)
        send_execution_update(execution_id, status='running', progress=progress, message=message)

    return callback


def _write_fast_suite_result_file(execution, test_case, result, runner, error_message=''):
    """
    Write a lightweight Allure-compatible result file.

    Suite fast mode does not enter pytest, but the standard QAFlow report already
    reads Allure result JSON. Keeping this small compatibility file preserves
    step status and screenshot evidence without paying the pytest startup cost.
    """
    results_dir = _get_execution_results_dir(execution.id)
    os.makedirs(results_dir, exist_ok=True)
    ui_flow = _normalize_case_ui_flow(test_case)
    passed = int(result.get('passed') or 0)
    failed = int(result.get('failed') or 0)
    stopped = bool(result.get('stopped'))
    total = int(result.get('total') or len(ui_flow) or 0)
    failed_index = int(result.get('failed_step_index') or (passed + 1 if failed else 0) or 0)
    started = int(time.time() * 1000)

    evidence_by_step = {}
    for item in getattr(runner, '_visual_evidence_attachments', []) or []:
        path = str(item.get('path') or '')
        if not path or not os.path.isfile(path):
            continue
        try:
            rel_path = os.path.relpath(path, results_dir)
        except ValueError:
            continue
        if rel_path.startswith('..'):
            continue
        step_index = int(item.get('step_index') or 0)
        evidence_by_step.setdefault(step_index, []).append({
            'name': item.get('name') or os.path.basename(path),
            'source': rel_path.replace(os.sep, '/'),
            'type': 'image/png',
        })

    steps = []
    for index, step in enumerate(ui_flow, 1):
        name = step.get('name') or step.get('type') or f'步骤 {index}'
        if stopped and index > passed:
            status = 'skipped'
        elif failed and index == failed_index:
            status = 'failed'
        elif index <= passed:
            status = 'passed'
        elif failed:
            status = 'skipped'
        else:
            status = 'passed'
        status_details = {}
        if status == 'failed' and error_message:
            status_details = {'message': error_message}
        steps.append({
            'name': f'步骤{index}-{name}',
            'status': status,
            'stage': 'finished',
            'start': started + index,
            'stop': started + index + 1,
            'statusDetails': status_details,
            'attachments': evidence_by_step.get(index, []),
        })

    if stopped:
        case_status = 'skipped'
    elif failed:
        case_status = 'failed'
    elif total == 0:
        case_status = 'skipped'
    else:
        case_status = 'passed'

    payload = {
        'name': test_case.name if test_case else f'执行记录 {execution.id}',
        'uuid': f'fast-suite-execution-{execution.id}',
        'historyId': f'app-fast-suite-{test_case.id if test_case else execution.id}',
        'testCaseId': f'app-fast-suite-{test_case.id if test_case else execution.id}',
        'fullName': 'apps.app_automation.tasks.fast_suite.TestAppFlow#test_execute_ui_flow',
        'status': case_status,
        'stage': 'finished',
        'start': started,
        'stop': int(time.time() * 1000),
        'statusDetails': {'message': error_message} if error_message else {},
        'labels': [
            {'name': 'feature', 'value': 'APP自动化测试'},
            {'name': 'suite', 'value': 'APP套件快跑'},
            {'name': 'testClass', 'value': 'FastSuiteRunner'},
            {'name': 'testMethod', 'value': 'test_execute_ui_flow'},
        ],
        'steps': [{
            'name': '执行 UI Flow',
            'status': case_status,
            'stage': 'finished',
            'start': started,
            'stop': int(time.time() * 1000),
            'steps': steps,
        }],
    }
    result_path = os.path.join(results_dir, f'fast-suite-{execution.id}-result.json')
    with open(result_path, 'w', encoding='utf-8') as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    return result_path


def _run_app_flow_direct(test_case, execution, airtest, package_name, username, stop_checker=None):
    from .runners.ui_flow_runner import UiFlowRunner

    ui_flow = _normalize_case_ui_flow(test_case)
    first_flow_step = next((step for step in ui_flow if isinstance(step, dict)), None)
    flow_handles_launch = bool(first_flow_step and first_flow_step.get("type") == "launch_activity")

    clear_data_before_run = os.getenv("APP_CLEAR_DATA_BEFORE_RUN") == "1"
    force_stop_before_run = os.getenv("APP_FORCE_STOP_BEFORE_RUN") == "1"
    handle_startup_dialogs = os.getenv("APP_HANDLE_STARTUP_DIALOGS", "0") == "1"

    if package_name:
        if flow_handles_launch:
            logger.info("UI Flow 已包含启动步骤，套件快跑跳过框架层默认启动: %s", test_case.name)
        elif clear_data_before_run:
            if not airtest.clear_app_data(package_name):
                raise RuntimeError(f"应用清数据失败: {package_name}")
        elif force_stop_before_run:
            if not airtest.close_app(package_name):
                raise RuntimeError(f"应用关闭失败: {package_name}")

        if not flow_handles_launch:
            if not airtest.open_app(package_name):
                raise RuntimeError(f"应用启动失败: {package_name}")

        if handle_startup_dialogs and not flow_handles_launch:
            airtest.handle_startup_permission_dialogs()
    else:
        logger.info("未配置应用包名，套件快跑跳过框架层启动应用步骤: %s", test_case.name)

    runner = UiFlowRunner(username=username)
    runner.screenshots_dir = _get_execution_results_dir(execution.id)
    os.makedirs(runner.screenshots_dir, exist_ok=True)

    error_message = ''
    try:
        result = runner.run(
            ui_flow=ui_flow,
            variables=test_case.variables or [],
            runtime={
                "stop_on_error": True,
                "allure_enabled": False,
                "stop_checker": stop_checker,
            },
            progress_callback=_make_suite_progress_callback(execution.id),
        )
    except Exception as exc:
        error_message = str(exc)
        result = dict(getattr(runner, 'last_run_result', {}) or {})
        result.setdefault('total', len(ui_flow))
        result.setdefault('passed', 0)
        if int(result.get('failed') or 0) <= 0:
            result['failed'] = 1
        if not result.get('failed_step_index'):
            result['failed_step_index'] = min(int(result.get('passed') or 0) + 1, len(ui_flow) or 1)
        result['error'] = error_message

    _write_fast_suite_result_file(execution, test_case, result, runner, error_message=error_message)
    return {
        'success': not error_message and not result.get('stopped') and int(result.get('failed') or 0) == 0,
        'error': error_message,
        'test_results': result,
        'output': error_message,
        'fast_suite_mode': True,
    }


@shared_task
def execute_app_test_task(execution_id, package_name: str = None, scheduled_task_id: int = None):
    """
    异步执行APP测试任务
    
    Args:
        execution_id: AppTestExecution 的 ID
        package_name: 可选的应用包名
        scheduled_task_id: 可选的定时任务 ID（来自定时调度）
    """
    from django.conf import settings
    from .models import AppTestExecution, AppDevice
    from .executors.test_executor import AppTestExecutor
    from .utils.execution_precheck import build_precheck_error_message, run_execution_precheck
    from .utils.performance_monitor import AndroidPerformanceMonitor
    
    execution = None
    device = None
    performance_metrics = {}
    logcat_collector = None
    
    try:
        # 获取执行记录
        execution = AppTestExecution.objects.get(id=execution_id)
        test_case = execution.test_case
        
        device = execution.device
        
        # 更新状态为执行中
        execution.status = 'running'
        execution.started_at = timezone.now()
        execution.progress = 0
        execution.save()
        send_execution_update(execution_id, status='running', progress=0, message='任务开始执行')
        
        logger.info(f"开始执行APP测试: {test_case.name}")
        
        # 1. 检查并锁定设备
        if device.status == 'locked' and device.locked_by != execution.user:
            raise RuntimeError(f"设备 {device.device_id} 已被其他用户锁定")
        
        if device.status != 'locked':
            device.lock(execution.user)
        logcat_collector = _start_logcat_collector(device, execution_id)
        
        logger.info(f"设备已锁定: {device.device_id}")
        
        # 2. 由 pytest + allure 插件执行测试
        # 进度分配：0~10% 环境准备，10~90% 步骤执行（由子进程内回调动态更新），90~100% 报告生成
        execution.progress = 10
        execution.save()
        send_execution_update(execution_id, status='running', progress=10, message='正在准备测试环境')
        
        if package_name:
            final_package_name = package_name
        else:
            final_package_name = (
                test_case.app_package.package_name if test_case.app_package else ""
            ) or (
                test_case.project.android_app_package.package_name
                if test_case.project and test_case.project.android_app_package else ""
            )

        precheck = run_execution_precheck(device, package_name=final_package_name)
        if not precheck.get('can_submit'):
            raise RuntimeError(build_precheck_error_message(precheck))

        performance_monitor = AndroidPerformanceMonitor(
            device_id=device.device_id,
            package_name=final_package_name,
        )
        performance_monitor.start()
        try:
            executor = AppTestExecutor()
            report_result = executor.run_tests(
                test_case_id=test_case.id,
                device_id=device.device_id,
                package_name=final_package_name,
                execution_id=execution_id,
                username=execution.user.username if execution.user else 'unknown',
            )
        finally:
            performance_metrics = performance_monitor.stop()
            _save_logcat_artifacts(logcat_collector, execution_id)
        
        # 从数据库重新读取最新进度（子进程中的回调可能已经更新过）
        execution.refresh_from_db()
        execution.performance_metrics = performance_metrics
        
        if report_result.get('report_path'):
            execution.report_path = report_result['report_path']
            logger.info(f"报告已生成: {report_result['report_path']}")
        
        test_results = report_result.get('test_results', {})
        execution.total_steps = test_results.get('total', 0)
        execution.passed_steps = test_results.get('passed', 0)
        # parser 已将 broken 算在 failed 里，直接使用
        execution.failed_steps = test_results.get('failed', 0)
        if test_results.get('broken', 0):
            logger.info(f"检测到 broken 用例 {test_results.get('broken')} 个（已计入失败统计）。")
        
        execution.progress = 95
        execution.save()
        send_execution_update(
            execution_id,
            status='running',
            progress=95,
            message='正在生成测试报告',
            report_path=execution.report_path
        )
        
        # 3. 完成测试 — 分离任务状态和测试结果
        execution.status = 'completed'
        if execution.total_steps == 0:
            execution.result = 'skipped'
        elif execution.failed_steps == 0:
            execution.result = 'passed'
        else:
            execution.result = 'failed'
        execution.finished_at = timezone.now()
        execution.duration = (execution.finished_at - execution.started_at).total_seconds()
        execution.progress = 100
        execution.save()
        send_execution_update(
            execution_id,
            status=execution.status,
            progress=100,
            message='执行完成',
            report_path=execution.report_path,
            finished_at=execution.finished_at,
            result=execution.result,
        )
        
        logger.info(f"APP测试执行完成: {test_case.name}, 状态: {execution.status}, 结果: {execution.result}")

        # 定时任务通知
        if scheduled_task_id:
            try:
                from .models import AppScheduledTask
                st = AppScheduledTask.objects.get(id=scheduled_task_id)
                is_success = execution.result == 'passed'
                if is_success:
                    st.successful_runs += 1
                else:
                    st.failed_runs += 1
                st.last_result = {'status': execution.status, 'result': execution.result, 'message': f'{test_case.name} - {execution.result or execution.status}'}
                st.save(update_fields=['successful_runs', 'failed_runs', 'last_result'])
                send_scheduled_task_notification(scheduled_task_id, success=is_success)
            except Exception as ne:
                logger.error(f"更新定时任务状态失败: {ne}")

    except AppTestExecution.DoesNotExist:
        logger.error(f"执行记录不存在: {execution_id}")
    except Exception as e:
        logger.error(f"执行APP测试失败: {str(e)}", exc_info=True)
        
        if execution:
            _save_logcat_artifacts(logcat_collector, execution_id)
            execution.status = 'error'       # 任务异常（非用例失败）
            execution.result = None           # 没有测试结果
            execution.error_message = str(e)
            execution.performance_metrics = performance_metrics
            execution.finished_at = timezone.now()
            if execution.started_at:
                execution.duration = (execution.finished_at - execution.started_at).total_seconds()
            execution.save()
            send_execution_update(
                execution_id,
                status='error',
                progress=execution.progress or 0,
                message=str(e),
                report_path=execution.report_path,
                finished_at=execution.finished_at,
                result=None,
            )
            
            # 尝试生成报告
            try:
                executor = AppTestExecutor()
                executor._generate_allure_report(execution_id=execution_id)
            except Exception:
                pass
    finally:
        # 7. 清理：释放设备
        try:
            if device and device.locked_by == execution.user:
                device.unlock()
                logger.info(f"设备已释放: {device.device_id}")
        except Exception as e:
            logger.error(f"释放设备失败: {str(e)}")


@shared_task
def execute_app_exploration_task(task_id: int, run_id: int | None = None):
    """Run an APP exploratory testing task with the rule-based MVP engine."""
    from .models import AppExplorationRun, AppExplorationTask
    from .utils.execution_precheck import build_precheck_error_message, run_execution_precheck
    from .utils.exploration_runner import run_app_exploration
    from .utils.page_map_persistence import persist_exploration_page_map

    task = None
    run = None
    device = None
    try:
        task = AppExplorationTask.objects.select_related('device').get(id=task_id)
        if run_id:
            run = AppExplorationRun.objects.filter(id=run_id, task=task).first()
        if not run:
            run = AppExplorationRun.objects.create(
                task=task,
                device=task.device,
                app_package=task.app_package,
                status='pending',
                strategy=task.strategy or 'rule_mvp',
            )
        if task.status == 'stopped':
            return {'success': True, 'task_id': task.id, 'stopped': True}
        device = task.device

        if not device:
            raise RuntimeError('探索任务未绑定设备')
        if device.status == 'locked' and device.locked_by != task.created_by:
            raise RuntimeError(f'设备 {device.device_id} 已被其他用户锁定')
        if device.status != 'locked':
            device.lock(task.created_by)

        package_name = task.app_package.package_name if task.app_package else ''
        precheck = run_execution_precheck(device, package_name=package_name)
        if not precheck.get('can_submit'):
            raise RuntimeError(build_precheck_error_message(precheck))

        task.status = 'running'
        task.progress = 1
        task.started_at = timezone.now()
        task.error_message = ''
        summary = dict(task.summary or {})
        summary['current_stage'] = '任务已启动，正在执行设备预检查'
        task.summary = summary
        task.save(update_fields=['status', 'progress', 'started_at', 'error_message', 'summary', 'updated_at'])
        run.status = 'running'
        run.started_at = task.started_at
        run.summary = summary
        run.error_message = ''
        run.save(update_fields=['status', 'started_at', 'summary', 'error_message', 'updated_at'])

        summary = run_app_exploration(task.id, run.id)
        try:
            page_map_stats = persist_exploration_page_map(task, run, summary)
            if isinstance(summary, dict):
                summary['page_map_persistence'] = page_map_stats
        except Exception as persist_error:
            logger.warning('APP探索页面地图沉淀失败: %s', persist_error, exc_info=True)
            if isinstance(summary, dict):
                summary['page_map_persistence'] = {
                    'status': 'failed',
                    'error': str(persist_error),
                }

        task.refresh_from_db()
        if task.status != 'stopped':
            task.status = 'completed'
            has_quality_warning = bool(
                (summary or {}).get('quality_warnings')
                or (summary or {}).get('exploration_success') is False
            )
            task.result = 'warning' if task.issue_count or has_quality_warning else 'passed'
            task.progress = 100
        task.finished_at = timezone.now()
        if task.started_at:
            task.duration = (task.finished_at - task.started_at).total_seconds()
        task.summary = summary
        task.save(update_fields=['status', 'result', 'progress', 'finished_at', 'duration', 'summary', 'updated_at'])
        run.status = task.status
        run.result = task.result
        run.finished_at = task.finished_at
        run.duration = task.duration
        run.total_steps = task.total_steps
        run.explored_pages = task.explored_pages
        run.issue_count = task.issue_count
        run.summary = summary
        run.save(update_fields=['status', 'result', 'finished_at', 'duration', 'total_steps', 'explored_pages', 'issue_count', 'summary', 'updated_at'])
        return {'success': True, 'task_id': task.id, 'run_id': run.id, 'summary': summary}

    except Exception as exc:
        logger.error('APP探索任务执行失败: %s', exc, exc_info=True)
        if task:
            task.status = 'error'
            task.result = 'failed'
            task.error_message = str(exc)
            task.finished_at = timezone.now()
            if task.started_at:
                task.duration = (task.finished_at - task.started_at).total_seconds()
            task.save(update_fields=['status', 'result', 'error_message', 'finished_at', 'duration', 'updated_at'])
        if run:
            run.status = 'error'
            run.result = 'failed'
            run.error_message = str(exc)
            run.finished_at = timezone.now()
            if run.started_at:
                run.duration = (run.finished_at - run.started_at).total_seconds()
            run.save(update_fields=['status', 'result', 'error_message', 'finished_at', 'duration', 'updated_at'])
        return {'success': False, 'task_id': task_id, 'run_id': run.id if run else None, 'error': str(exc)}
    finally:
        if device:
            try:
                device.unlock()
            except Exception as unlock_error:
                logger.warning('探索任务释放设备失败: %s', unlock_error)


@shared_task
def analyze_app_exploration_task(task_id: int, force: bool = False):
    """Run the slow LLM analysis in the background and persist progress."""
    from .models import AppExplorationTask
    from .utils.exploration_ai_advisor import analyze_exploration_with_ai

    def update_state(task, status_value, stage, message='', error=''):
        summary = dict(task.summary or {})
        summary['ai_analysis_status'] = status_value
        summary['ai_analysis_stage'] = stage
        summary['ai_analysis_message'] = message
        summary['ai_analysis_error'] = error
        if status_value == 'running':
            summary.setdefault('ai_analysis_started_at', timezone.now().isoformat())
        if status_value in ('completed', 'failed'):
            summary['ai_analysis_finished_at'] = timezone.now().isoformat()
        task.summary = summary
        task.save(update_fields=['summary', 'updated_at'])

    task = None
    try:
        task = AppExplorationTask.objects.get(id=task_id)
        summary = dict(task.summary or {})
        if summary.get('ai_analysis') and not force:
            update_state(task, 'completed', '已返回缓存结果', 'AI 分析已完成')
            return {'success': True, 'task_id': task_id, 'cached': True}

        update_state(task, 'running', '构建报告上下文', '正在整理探索报告、步骤和页面证据')
        update_state(task, 'running', '请求大模型', '正在请求 AI 模型生成分析报告')
        analysis = analyze_exploration_with_ai(task)

        task.refresh_from_db()
        summary = dict(task.summary or {})
        if analysis.get('status') == 'success':
            summary['ai_analysis'] = analysis
            summary['ai_analysis_status'] = 'completed'
            summary['ai_analysis_stage'] = '分析完成'
            summary['ai_analysis_message'] = analysis.get('message') or 'AI 分析完成'
            summary['ai_analysis_error'] = ''
            summary['ai_analysis_finished_at'] = timezone.now().isoformat()
            task.summary = summary
            task.save(update_fields=['summary', 'updated_at'])
            return {'success': True, 'task_id': task_id}

        summary['ai_analysis_status'] = 'failed'
        summary['ai_analysis_stage'] = '分析失败'
        summary['ai_analysis_message'] = analysis.get('message') or 'AI 分析失败'
        summary['ai_analysis_error'] = analysis.get('message') or 'AI 分析失败'
        summary['ai_analysis_finished_at'] = timezone.now().isoformat()
        task.summary = summary
        task.save(update_fields=['summary', 'updated_at'])
        return {'success': False, 'task_id': task_id, 'error': summary['ai_analysis_error']}

    except Exception as exc:
        logger.error('APP探索 AI 分析失败: %s', exc, exc_info=True)
        if task:
            summary = dict(task.summary or {})
            summary['ai_analysis_status'] = 'failed'
            summary['ai_analysis_stage'] = '分析失败'
            summary['ai_analysis_message'] = 'AI 分析失败'
            summary['ai_analysis_error'] = str(exc)
            summary['ai_analysis_finished_at'] = timezone.now().isoformat()
            task.summary = summary
            task.save(update_fields=['summary', 'updated_at'])
        return {'success': False, 'task_id': task_id, 'error': str(exc)}


@shared_task
def execute_app_suite_task(suite_id, execution_ids, package_name=None, scheduled_task_id=None):
    """
    异步执行APP测试套件（顺序执行多个用例）

    Args:
        suite_id: AppTestSuite 的 ID
        execution_ids: AppTestExecution ID 列表（按执行顺序）
        package_name: 可选的应用包名覆盖
        scheduled_task_id: 可选的定时任务 ID
    """
    from .models import AppTestSuite, AppTestExecution, AppDevice
    from .executors.test_executor import AppTestExecutor
    from .utils.airtest_base import AirtestBase
    from .utils.execution_precheck import build_precheck_error_message, run_execution_precheck
    from .utils.performance_monitor import AndroidPerformanceMonitor

    suite = None
    device = None
    airtest = None
    passed = 0
    failed = 0
    precheck_cache = {}
    fast_suite_enabled = os.getenv("APP_SUITE_FAST_MODE", "1").lower() not in {"0", "false", "no", "off"}

    try:
        suite = AppTestSuite.objects.get(id=suite_id)
        executions = list(
            AppTestExecution.objects.filter(id__in=execution_ids)
            .select_related(
                'test_case',
                'test_case__app_package',
                'test_case__project__android_app_package',
                'device',
                'user',
            )
            .order_by('id')
        )
        # 按 execution_ids 排序
        exec_map = {e.id: e for e in executions}
        executions = [exec_map[eid] for eid in execution_ids if eid in exec_map]

        if not executions:
            logger.error(f"套件 {suite_id} 未找到执行记录")
            return

        device = executions[0].device
        user = executions[0].user

        # 锁定设备
        if device.status != 'locked':
            device.lock(user)
        logger.info(f"套件执行开始: {suite.name}, 设备: {device.device_id}, 共 {len(executions)} 个用例")
        if fast_suite_enabled:
            airtest = AirtestBase(
                device_id=device.device_id,
                username=user.username if user else 'unknown',
            )
            if not airtest.setup_airtest():
                raise RuntimeError("Airtest 环境设置失败")
            logger.info("套件快跑模式已启用，一次连接设备后连续执行套件用例: %s", suite.name)

        for idx, execution in enumerate(executions):
            suite.refresh_from_db(fields=['execution_status'])
            execution.refresh_from_db(fields=['status'])
            if suite.execution_status == 'stopped':
                if execution.status == 'pending':
                    execution.status = 'stopped'
                    execution.result = None
                    execution.error_message = execution.error_message or '套件已手动停止，跳过后续用例'
                    execution.finished_at = timezone.now()
                    execution.save(update_fields=['status', 'result', 'error_message', 'finished_at', 'updated_at'])
                    send_execution_update(
                        execution.id,
                        status='stopped',
                        progress=execution.progress,
                        message='套件已停止，跳过该用例',
                        finished_at=execution.finished_at,
                        result=None,
                    )
                _sync_suite_progress(suite)
                continue

            if execution.status == 'stopped':
                _sync_suite_progress(suite)
                continue

            test_case = execution.test_case
            performance_metrics = {}
            logcat_collector = None
            if not test_case:
                execution.status = 'error'
                execution.result = None
                execution.error_message = '用例不存在'
                execution.finished_at = timezone.now()
                execution.save()
                failed += 1
                continue

            try:
                # 更新为运行中
                execution.status = 'running'
                execution.started_at = timezone.now()
                execution.progress = 0
                execution.save()
                send_execution_update(
                    execution.id, status='running', progress=0,
                    message=f'开始执行 ({idx + 1}/{len(executions)})'
                )

                # 确定包名
                final_pkg = _resolve_case_package(test_case, package_name)

                precheck_key = (getattr(device, 'device_id', ''), final_pkg)
                if precheck_key not in precheck_cache:
                    precheck_cache[precheck_key] = run_execution_precheck(device, package_name=final_pkg)
                precheck = precheck_cache[precheck_key]
                if not precheck.get('can_submit'):
                    raise RuntimeError(build_precheck_error_message(precheck))

                execution.progress = 10
                execution.save()
                send_execution_update(
                    execution.id, status='running', progress=10,
                    message='正在准备测试环境'
                )

                logcat_collector = _start_logcat_collector(device, execution.id)

                performance_monitor = AndroidPerformanceMonitor(
                    device_id=device.device_id,
                    package_name=final_pkg,
                )
                performance_monitor.start()
                try:
                    if fast_suite_enabled:
                        def _should_stop_current_case():
                            try:
                                suite.refresh_from_db(fields=['execution_status'])
                                execution.refresh_from_db(fields=['status'])
                                return suite.execution_status == 'stopped' or execution.status == 'stopped'
                            except Exception as exc:
                                logger.debug("套件快跑停止检查失败: %s", exc)
                                return False

                        report_result = _run_app_flow_direct(
                            test_case=test_case,
                            execution=execution,
                            airtest=airtest,
                            package_name=final_pkg,
                            username=execution.user.username if execution.user else 'unknown',
                            stop_checker=_should_stop_current_case,
                        )
                    else:
                        executor = AppTestExecutor()
                        report_result = executor.run_tests(
                            test_case_id=test_case.id,
                            device_id=device.device_id,
                            package_name=final_pkg,
                            execution_id=execution.id,
                            username=execution.user.username if execution.user else 'unknown',
                            generate_allure_report=False,
                        )
                finally:
                    performance_metrics = performance_monitor.stop()
                    _save_logcat_artifacts(logcat_collector, execution.id)

                execution.refresh_from_db()
                if execution.status == 'stopped':
                    execution.performance_metrics = performance_metrics
                    execution.finished_at = execution.finished_at or timezone.now()
                    if execution.started_at and not execution.duration:
                        execution.duration = (execution.finished_at - execution.started_at).total_seconds()
                    execution.save(update_fields=['performance_metrics', 'finished_at', 'duration', 'updated_at'])
                    _sync_suite_progress(suite)
                    send_execution_update(
                        execution.id,
                        status='stopped',
                        progress=execution.progress,
                        message='套件已手动停止',
                        report_path=execution.report_path,
                        finished_at=execution.finished_at,
                        result=None,
                    )
                    continue
                execution.performance_metrics = performance_metrics

                if report_result.get('report_path'):
                    execution.report_path = report_result['report_path']

                test_results = report_result.get('test_results', {})
                execution.total_steps = test_results.get('total', 0)
                execution.passed_steps = test_results.get('passed', 0)
                execution.failed_steps = test_results.get('failed', 0)
                if test_results.get('broken', 0):
                    logger.info(f"检测到 broken 用例 {test_results.get('broken')} 个（已计入失败统计）。")

                if test_results.get('stopped'):
                    execution.status = 'stopped'
                    execution.result = None
                    execution.error_message = execution.error_message or '套件已手动停止'
                    execution.finished_at = timezone.now()
                    execution.duration = (execution.finished_at - execution.started_at).total_seconds()
                    execution.progress = 100
                    execution.save()
                    _sync_suite_progress(suite)
                    send_execution_update(
                        execution.id,
                        status='stopped',
                        progress=100,
                        message='套件已手动停止',
                        report_path=execution.report_path,
                        finished_at=execution.finished_at,
                        result=None,
                    )
                    continue

                execution.status = 'completed'
                if execution.total_steps == 0:
                    execution.result = 'skipped'
                elif execution.failed_steps == 0:
                    execution.result = 'passed'
                else:
                    execution.result = 'failed'

                if execution.result != 'passed':
                    executor = AppTestExecutor()
                    report_path = executor._generate_allure_report(execution_id=execution.id)
                    if report_path:
                        execution.report_path = report_path

                execution.finished_at = timezone.now()
                execution.duration = (execution.finished_at - execution.started_at).total_seconds()
                execution.progress = 100
                execution.save()

                if execution.result == 'passed':
                    passed += 1
                else:
                    failed += 1
                _sync_suite_progress(suite)

                send_execution_update(
                    execution.id, status=execution.status, progress=100,
                    message='执行完成',
                    report_path=execution.report_path,
                    finished_at=execution.finished_at,
                    result=execution.result,
                )

                logger.info(f"用例 {test_case.name} 执行完成: status={execution.status}, result={execution.result}")

            except Exception as e:
                logger.error(f"用例 {test_case.name} 执行失败: {str(e)}", exc_info=True)
                _save_logcat_artifacts(logcat_collector, execution.id)
                execution.status = 'error'
                execution.result = None
                execution.error_message = str(e)
                execution.performance_metrics = performance_metrics
                execution.finished_at = timezone.now()
                if execution.started_at:
                    execution.duration = (execution.finished_at - execution.started_at).total_seconds()
                execution.save()
                failed += 1
                _sync_suite_progress(suite)
                send_execution_update(
                    execution.id, status='error',
                    progress=execution.progress or 0,
                    message=str(e),
                    finished_at=execution.finished_at,
                    result=None,
                )

        # 更新套件统计
        suite.refresh_from_db(fields=['execution_status'])
        suite_was_stopped = suite.execution_status == 'stopped'
        if suite_was_stopped:
            suite.execution_result = 'skipped'
        else:
            suite.execution_status = 'completed'
            if passed == 0 and failed == 0:
                suite.execution_result = 'skipped'
            elif failed == 0:
                suite.execution_result = 'passed'
            else:
                suite.execution_result = 'failed'
        passed, failed = _sync_suite_progress(suite)
        suite.last_run_at = timezone.now()
        suite.save(update_fields=['execution_status', 'execution_result', 'passed_count', 'failed_count', 'last_run_at'])

        logger.info(f"套件执行完成: {suite.name}, 通过: {passed}, 失败: {failed}")

        # 定时任务通知
        if scheduled_task_id:
            try:
                from .models import AppScheduledTask
                st = AppScheduledTask.objects.get(id=scheduled_task_id)
                is_success = failed == 0
                if is_success:
                    st.successful_runs += 1
                else:
                    st.failed_runs += 1
                st.last_result = {
                    'status': suite.execution_status,
                    'result': suite.execution_result,
                    'message': f'通过: {passed}, 失败: {failed}'
                }
                st.save(update_fields=['successful_runs', 'failed_runs', 'last_result'])
                send_scheduled_task_notification(scheduled_task_id, success=is_success)
            except Exception as ne:
                logger.error(f"更新定时任务状态失败: {ne}")

    except AppTestSuite.DoesNotExist:
        logger.error(f"测试套件不存在: {suite_id}")
    except Exception as e:
        logger.error(f"执行套件失败: {str(e)}", exc_info=True)
        if suite:
            suite.execution_status = 'error'
            suite.execution_result = None
            suite.failed_count = failed
            suite.passed_count = passed
            suite.last_run_at = timezone.now()
            suite.save(update_fields=['execution_status', 'execution_result', 'passed_count', 'failed_count', 'last_run_at'])
    finally:
        # 释放设备
        try:
            if airtest:
                airtest.teardown_airtest()
            if device:
                device.refresh_from_db()
                if device.status == 'locked':
                    device.unlock()
                    logger.info(f"设备已释放: {device.device_id}")
        except Exception as e:
            logger.error(f"释放设备失败: {str(e)}")


@shared_task
def check_and_release_expired_devices():
    """
    检查并释放过期锁定的设备
    """
    from .models import AppDevice
    
    try:
        devices = AppDevice.objects.filter(status='locked')
        released_count = 0
        
        for device in devices:
            if device.is_lock_expired():
                device.unlock()
                released_count += 1
                logger.info(f"释放过期锁定的设备: {device.device_id}")
        
        logger.info(f"检查设备锁定完成，释放 {released_count} 个设备")
        
    except Exception as e:
        logger.error(f"检查设备锁定失败: {str(e)}", exc_info=True)
