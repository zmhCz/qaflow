# -*- coding: utf-8 -*-
"""APP测试套件管理视图"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.filters import SearchFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.http import HttpResponse
from django.conf import settings
import logging
import threading
import io
import json
import os
import zipfile

from ..models import AppTestSuite, AppTestSuiteCase, AppTestCase, AppDevice, AppTestExecution
from .test_case_views import AppPagination
from ..serializers import (
    AppTestSuiteSerializer,
    AppTestSuiteCreateSerializer,
    AppTestSuiteUpdateSerializer,
    AppTestSuiteCaseSerializer,
    AppTestExecutionSerializer,
)
from ..utils.execution_precheck import build_precheck_error_message, run_execution_precheck
from ..utils.report_summary import build_suite_report_summary, _local_time
from ..utils.task_dispatcher import dispatch_app_task

logger = logging.getLogger(__name__)


def _revoke_suite_tasks_async(suite_id, task_ids):
    """Best-effort Celery revoke without blocking the stop API response."""
    if not task_ids:
        return

    def _worker():
        try:
            from celery import current_app
            for task_id in task_ids:
                current_app.control.revoke(task_id, terminate=True, signal='SIGTERM')
                logger.info("套件执行 Celery 任务已请求终止: suite=%s, task_id=%s", suite_id, task_id)
        except Exception as exc:
            logger.warning("请求终止套件 Celery 任务失败: %s", exc)

    threading.Thread(target=_worker, name=f'app-suite-stop-{suite_id}', daemon=True).start()


def _latest_suite_executions(suite):
    """Return the latest suite execution round ordered by saved suite case order."""
    case_count = suite.suite_cases.count()
    latest_ids = list(
        AppTestExecution.objects.filter(test_suite=suite)
        .order_by('-created_at', '-id')
        .values_list('id', flat=True)[:case_count or 50]
    )
    return _suite_executions_by_ids(suite, latest_ids)


def _suite_executions_by_ids(suite, execution_ids):
    """Return selected suite executions ordered by saved suite case order."""
    suite_cases = list(
        suite.suite_cases
        .select_related('test_case')
        .order_by('order', 'id')
    )
    ids = [int(item) for item in execution_ids or [] if str(item).isdigit()]
    if not ids:
        return []
    latest_executions = list(
        AppTestExecution.objects.filter(test_suite=suite, id__in=ids)
        .select_related('test_case', 'test_case__project', 'test_case__app_package', 'device', 'user')
    )
    exec_map = {item.test_case_id: item for item in latest_executions}
    ordered_execs = [
        exec_map[sc.test_case_id]
        for sc in suite_cases
        if sc.test_case_id in exec_map
    ]
    suite_case_ids = {sc.test_case_id for sc in suite_cases}
    extra_execs = [
        item for item in sorted(latest_executions, key=lambda item: item.id)
        if item.test_case_id not in suite_case_ids
    ]
    return ordered_execs + extra_execs


def _suite_execution_rounds(suite, limit=10):
    """Return recent suite execution rounds grouped by one submitted suite run."""
    case_count = max(suite.suite_cases.count(), 1)
    execution_ids = list(
        AppTestExecution.objects.filter(test_suite=suite)
        .order_by('-created_at', '-id')
        .values_list('id', flat=True)[:case_count * max(int(limit or 10), 1)]
    )
    rounds = []
    for offset in range(0, len(execution_ids), case_count):
        chunk_ids = execution_ids[offset:offset + case_count]
        if not chunk_ids:
            continue
        executions = _suite_executions_by_ids(suite, chunk_ids)
        if not executions:
            continue
        finished_statuses = {'completed', 'error', 'stopped'}
        started_values = [item.started_at or item.created_at for item in executions if item.started_at or item.created_at]
        finished_values = [item.finished_at for item in executions if item.finished_at]
        passed = sum(1 for item in executions if item.status == 'completed' and item.result == 'passed')
        failed = sum(1 for item in executions if item.status == 'completed' and item.result == 'failed')
        error = sum(1 for item in executions if item.status == 'error')
        stopped = sum(1 for item in executions if item.status == 'stopped')
        completed = sum(1 for item in executions if item.status in finished_statuses)
        running = sum(1 for item in executions if item.status == 'running')
        pending = sum(1 for item in executions if item.status == 'pending')

        if running:
            status, result, status_text = 'running', '', '执行中'
        elif pending and completed < len(executions):
            status, result, status_text = 'pending', '', '等待中'
        elif error:
            status, result, status_text = 'error', '', '执行异常'
        elif stopped:
            status, result, status_text = 'stopped', 'skipped', '已停止'
        elif failed:
            status, result, status_text = 'completed', 'failed', '失败'
        elif completed == len(executions) and passed == len(executions):
            status, result, status_text = 'completed', 'passed', '通过'
        else:
            status, result, status_text = 'completed', 'skipped', '结果不完整'

        rounds.append({
            'run_index': len(rounds) + 1,
            'suite_id': suite.id,
            'suite_name': suite.name,
            'execution_ids': [item.id for item in executions],
            'status': status,
            'result': result,
            'status_text': status_text,
            'started_at': _local_time(min(started_values) if started_values else None),
            'finished_at': _local_time(max(finished_values) if finished_values else None),
            'case_total': len(executions),
            'passed_count': passed,
            'failed_count': failed + error,
        })
    return rounds


def _suite_execution_files(executions, *, logcat_only=False):
    files = []
    allowed_suffixes = (
        '.json', '.txt', '.log', '.xml', '.png', '.jpg', '.jpeg',
        '.html', '.csv'
    )
    for execution in executions:
        results_dir = os.path.abspath(os.path.join(
            settings.MEDIA_ROOT,
            'app-automation',
            'allure-results',
            f'execution_{execution.id}',
        ))
        if not os.path.isdir(results_dir):
            continue
        for name in os.listdir(results_dir):
            lower_name = name.lower()
            if logcat_only:
                if 'logcat' not in lower_name or not lower_name.endswith('.txt'):
                    continue
            elif not lower_name.endswith(allowed_suffixes):
                continue
            path = os.path.abspath(os.path.join(results_dir, name))
            if os.path.isfile(path) and path.startswith(results_dir):
                files.append((execution, path))
    return sorted(files, key=lambda item: (item[0].id, item[1]))


def _download_suite_files_response(suite, executions, *, logcat_only=False):
    files = _suite_execution_files(executions, logcat_only=logcat_only)
    if not files:
        return Response({
            'success': False,
            'message': '本轮套件暂无可导出的日志或排障附件。'
        }, status=status.HTTP_404_NOT_FOUND)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        manifest = {
            'suite_id': suite.id,
            'suite_name': suite.name,
            'file_count': len(files),
            'execution_ids': [execution.id for execution in executions],
            'note': '按 execution_<id>/ 文件夹归档，便于定位到具体用例。',
        }
        archive.writestr(
            'manifest.json',
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )
        for execution, path in files:
            archive.write(path, arcname=f'execution_{execution.id}/{os.path.basename(path)}')

    buffer.seek(0)
    suffix = 'logcat' if logcat_only else 'evidence'
    filename = f"qaflow_suite_{suite.id}_{suffix}.zip"
    response = HttpResponse(buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Content-Length'] = str(buffer.getbuffer().nbytes)
    return response


class AppTestSuiteViewSet(viewsets.ModelViewSet):
    """APP测试套件 ViewSet"""
    queryset = AppTestSuite.objects.all()
    permission_classes = [IsAuthenticated]
    pagination_class = AppPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['project']
    search_fields = ['name', 'description']

    def get_serializer_class(self):
        if self.action == 'create':
            return AppTestSuiteCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return AppTestSuiteUpdateSerializer
        return AppTestSuiteSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    # ---------- 用例管理 ----------

    @action(detail=True, methods=['get'])
    def test_cases(self, request, pk=None):
        """获取套件中的所有用例（按顺序）"""
        suite = self.get_object()
        cases = suite.suite_cases.select_related('test_case', 'test_case__app_package').all()
        serializer = AppTestSuiteCaseSerializer(cases, many=True)
        return Response({'success': True, 'data': serializer.data})

    @action(detail=True, methods=['post'])
    def add_test_case(self, request, pk=None):
        """向套件添加用例"""
        suite = self.get_object()
        test_case_id = request.data.get('test_case_id')
        order = request.data.get('order')

        if not test_case_id:
            return Response({'success': False, 'message': '请提供 test_case_id'},
                            status=status.HTTP_400_BAD_REQUEST)

        # 默认排在最后
        if order is None:
            max_order = suite.suite_cases.order_by('-order').values_list('order', flat=True).first()
            order = (max_order or 0) + 1

        try:
            sc = AppTestSuiteCase.objects.create(
                test_suite=suite,
                test_case_id=test_case_id,
                order=order
            )
            serializer = AppTestSuiteCaseSerializer(sc)
            return Response({'success': True, 'data': serializer.data},
                            status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'success': False, 'message': str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def add_test_cases(self, request, pk=None):
        """批量添加用例到套件"""
        suite = self.get_object()
        test_case_ids = request.data.get('test_case_ids', [])

        if not test_case_ids:
            return Response({'success': False, 'message': '请提供 test_case_ids'},
                            status=status.HTTP_400_BAD_REQUEST)

        max_order = suite.suite_cases.order_by('-order').values_list('order', flat=True).first()
        current_order = (max_order or 0) + 1

        # 排除已存在的
        existing_ids = set(suite.suite_cases.values_list('test_case_id', flat=True))
        added = 0
        for tc_id in test_case_ids:
            if tc_id not in existing_ids:
                AppTestSuiteCase.objects.create(
                    test_suite=suite,
                    test_case_id=tc_id,
                    order=current_order
                )
                current_order += 1
                added += 1

        return Response({
            'success': True,
            'message': f'成功添加 {added} 个用例',
            'added': added
        })

    @action(detail=True, methods=['post'])
    def remove_test_case(self, request, pk=None):
        """从套件移除用例"""
        suite = self.get_object()
        test_case_id = request.data.get('test_case_id')

        try:
            sc = AppTestSuiteCase.objects.get(
                test_suite=suite, test_case_id=test_case_id
            )
            sc.delete()
            return Response({'success': True, 'message': '已移除'})
        except AppTestSuiteCase.DoesNotExist:
            return Response({'success': False, 'message': '用例不在该套件中'},
                            status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'])
    def update_test_case_order(self, request, pk=None):
        """更新套件中用例的顺序"""
        suite = self.get_object()
        test_case_orders = request.data.get('test_case_orders', [])

        try:
            for item in test_case_orders:
                AppTestSuiteCase.objects.filter(
                    test_suite=suite,
                    test_case_id=item['test_case_id']
                ).update(order=item['order'])
            return Response({'success': True, 'message': '顺序更新成功'})
        except Exception as e:
            return Response({'success': False, 'message': str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

    # ---------- 套件执行 ----------

    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        """执行测试套件（顺序执行所有用例）"""
        suite = self.get_object()
        device_id = request.data.get('device_id')
        package_name = request.data.get('package_name')
        execution_mode = request.data.get('execution_mode') or 'server'

        if not device_id:
            return Response({'success': False, 'message': '请选择执行设备'},
                            status=status.HTTP_400_BAD_REQUEST)

        # 检查套件是否包含用例
        suite_cases = suite.suite_cases.select_related(
            'test_case',
            'test_case__app_package',
            'test_case__project__android_app_package',
        ).all()
        if not suite_cases.exists():
            return Response({'success': False, 'message': '该套件未包含任何测试用例'},
                            status=status.HTTP_400_BAD_REQUEST)

        if not package_name:
            package_name = (
                suite.project.android_app_package.package_name
                if suite.project and suite.project.android_app_package else ''
            )
        if not package_name:
            first_case = suite_cases[0].test_case
            package_name = (
                first_case.app_package.package_name if first_case.app_package else ''
            ) or (
                first_case.project.android_app_package.package_name
                if first_case.project and first_case.project.android_app_package else ''
            )

        try:
            device = AppDevice.objects.get(device_id=device_id)
            if device.status == 'locked' and device.locked_by != request.user:
                return Response({'success': False, 'message': '设备已被其他用户锁定'},
                                status=status.HTTP_400_BAD_REQUEST)

            if execution_mode not in ('server', 'agent'):
                return Response({'success': False, 'message': '执行模式不正确'},
                                status=status.HTTP_400_BAD_REQUEST)

            if execution_mode == 'server':
                precheck = run_execution_precheck(device, package_name=package_name)
                if not precheck.get('can_submit'):
                    return Response({
                        'success': False,
                        'message': build_precheck_error_message(precheck),
                        'precheck': precheck,
                    }, status=status.HTTP_400_BAD_REQUEST)

            # 为每个用例创建执行记录
            executions = []
            for sc in suite_cases:
                execution = AppTestExecution.objects.create(
                    test_case=sc.test_case,
                    test_suite=suite,
                    device=device,
                    user=request.user,
                    status='pending',
                    execution_mode=execution_mode,
                )
                executions.append(execution)

            # 更新套件状态
            suite.execution_status = 'running'
            suite.execution_result = None
            suite.passed_count = 0
            suite.failed_count = 0
            suite.last_run_at = timezone.now()
            suite.save(update_fields=[
                'execution_status', 'execution_result', 'passed_count', 'failed_count', 'last_run_at'
            ])

            # 触发 Celery 任务，顺序执行
            from ..tasks import execute_app_suite_task
            execution_ids = [e.id for e in executions]
            if execution_mode == 'agent':
                for execution in executions:
                    execution.task_id = f'agent-pending-{execution.id}'
                    execution.save(update_fields=['task_id'])
                logger.info("测试套件已提交到 Agent 队列: suite=%s, cases=%s", suite.name, len(executions))
                return Response({
                    'success': True,
                    'message': f'测试套件已提交到本地 Agent 队列，共 {len(executions)} 个用例',
                    'data': {
                        'suite_id': suite.id,
                        'task_id': f'agent-suite-{suite.id}',
                        'execution_ids': execution_ids,
                        'test_case_count': len(executions),
                    }
                })

            task = dispatch_app_task(
                execute_app_suite_task,
                suite_id=suite.id,
                execution_ids=execution_ids,
                package_name=package_name,
                mark_execution_ids=execution_ids,
            )

            # 记录 task_id 到第一个执行
            if executions:
                executions[0].task_id = task.id
                executions[0].save(update_fields=['task_id'])

            logger.info(f"测试套件已提交执行: suite={suite.name}, "
                        f"cases={len(executions)}, task_id={task.id}, mode={task.mode}")

            return Response({
                'success': True,
                'message': (
                    f'测试套件已提交执行，共 {len(executions)} 个用例'
                    if not task.fallback_used
                    else f'队列不可用，已切换本机执行，共 {len(executions)} 个用例'
                ),
                'data': {
                    'suite_id': suite.id,
                    'task_id': task.id,
                    'execution_ids': execution_ids,
                    'test_case_count': len(executions),
                }
            })

        except AppDevice.DoesNotExist:
            return Response({'success': False, 'message': '设备不存在'},
                            status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"执行套件失败: {str(e)}", exc_info=True)
            suite.execution_status = 'error'
            suite.save(update_fields=['execution_status'])
            return Response({'success': False, 'message': f'执行失败: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        """停止测试套件执行"""
        suite = self.get_object()

        if suite.execution_status != 'running':
            return Response({
                'success': False,
                'message': '只能停止执行中的套件'
            }, status=status.HTTP_400_BAD_REQUEST)

        running_executions = list(
            AppTestExecution.objects.filter(
                test_suite=suite,
                status__in=['pending', 'running'],
            )
        )

        task_ids = {
            item.task_id
            for item in running_executions
            if item.task_id and not item.task_id.startswith('local-')
        }
        _revoke_suite_tasks_async(suite.id, task_ids)

        now = timezone.now()
        stopped_count = 0
        for execution in running_executions:
            execution.status = 'stopped'
            execution.result = None
            execution.error_message = execution.error_message or '用户手动停止套件执行'
            execution.finished_at = now
            if execution.started_at:
                execution.duration = (execution.finished_at - execution.started_at).total_seconds()
            execution.save(update_fields=[
                'status', 'result', 'error_message', 'finished_at', 'duration', 'updated_at'
            ])
            stopped_count += 1

            try:
                from ..tasks import send_execution_update
                send_execution_update(
                    execution.id,
                    status='stopped',
                    progress=execution.progress,
                    message='套件已手动停止',
                    report_path=execution.report_path,
                    finished_at=execution.finished_at,
                    result=None,
                )
            except Exception as exc:
                logger.debug("发送套件停止状态失败: %s", exc)

        suite.execution_status = 'stopped'
        suite.execution_result = 'skipped'
        latest_ids = list(
            AppTestExecution.objects.filter(test_suite=suite)
            .order_by('-created_at')
            .values_list('id', flat=True)[:suite.suite_cases.count()]
        )
        latest_executions = AppTestExecution.objects.filter(id__in=latest_ids)
        suite.passed_count = latest_executions.filter(status='completed', result='passed').count()
        suite.failed_count = latest_executions.filter(status='completed', result='failed').count() + latest_executions.filter(status='error').count()
        suite.last_run_at = now
        suite.save(update_fields=[
            'execution_status', 'execution_result', 'passed_count', 'failed_count', 'last_run_at'
        ])

        return Response({
            'success': True,
            'message': f'已请求停止套件执行，影响 {stopped_count} 条待执行/执行中用例'
        })

    @action(detail=True, methods=['get'])
    def executions(self, request, pk=None):
        """获取套件执行历史，按每一次套件提交聚合展示。"""
        suite = self.get_object()
        try:
            limit = int(request.query_params.get('limit') or 10)
        except (TypeError, ValueError):
            limit = 10
        return Response({'success': True, 'data': _suite_execution_rounds(suite, limit=limit)})

    @action(detail=True, methods=['get'], url_path='report-summary')
    def report_summary(self, request, pk=None):
        """获取套件整体报告摘要；可按 execution_ids 查看历史轮次。"""
        suite = self.get_object()
        raw_ids = request.query_params.get('execution_ids') or ''
        execution_ids = [item.strip() for item in raw_ids.split(',') if item.strip()]
        execs = _suite_executions_by_ids(suite, execution_ids) if execution_ids else _latest_suite_executions(suite)
        summary = build_suite_report_summary(suite, execs, request=request)
        return Response({
            'code': 0,
            'success': True,
            'data': summary,
        })

    @action(detail=True, methods=['get'], url_path='download-logcat')
    def download_logcat(self, request, pk=None):
        """导出套件最近一轮所有用例采集到的 logcat。"""
        suite = self.get_object()
        execs = _latest_suite_executions(suite)
        return _download_suite_files_response(suite, execs, logcat_only=True)

    @action(detail=True, methods=['get'], url_path='download-evidence')
    def download_evidence(self, request, pk=None):
        """导出套件最近一轮所有用例的排障附件。"""
        suite = self.get_object()
        execs = _latest_suite_executions(suite)
        return _download_suite_files_response(suite, execs, logcat_only=False)
