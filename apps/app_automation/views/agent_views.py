# -*- coding: utf-8 -*-
"""本地执行机 Agent API。

Agent 采用“本地主动轮询云端”的方式，避免云服务器反连用户电脑。
"""
import base64
import json
import os
import uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import AppDevice, AppExecutionAgent, AppTestExecution, AppTestSuite
from ..serializers import AppExecutionAgentSerializer
from ..tasks import send_execution_update


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or None


def _package_name_for_execution(execution):
    test_case = execution.test_case
    if not test_case:
        return ''
    if test_case.app_package:
        return test_case.app_package.package_name
    if test_case.project and test_case.project.android_app_package:
        return test_case.project.android_app_package.package_name
    return ''


def _execution_payload(execution):
    test_case = execution.test_case
    ui_flow = test_case.ui_flow if test_case else {}
    variables = test_case.variables if test_case else []
    return {
        'execution_id': execution.id,
        'test_case_id': test_case.id if test_case else None,
        'test_case_name': test_case.name if test_case else '',
        'test_suite_id': execution.test_suite_id,
        'device_id': execution.device.device_id if execution.device else '',
        'package_name': _package_name_for_execution(execution),
        'ui_flow': ui_flow,
        'variables': variables,
        'timeout': test_case.timeout if test_case else 300,
    }


def _sync_suite_progress(suite_id):
    if not suite_id:
        return
    try:
        suite = AppTestSuite.objects.get(id=suite_id)
    except AppTestSuite.DoesNotExist:
        return

    latest_total = suite.suite_cases.count()
    if latest_total <= 0:
        return

    latest_ids = list(
        AppTestExecution.objects.filter(test_suite=suite)
        .order_by('-created_at')
        .values_list('id', flat=True)[:latest_total]
    )
    executions = AppTestExecution.objects.filter(id__in=latest_ids)
    finished_statuses = ['completed', 'error', 'stopped']
    passed = executions.filter(status='completed', result='passed').count()
    failed = (
        executions.filter(status='completed', result='failed').count()
        + executions.filter(status='error').count()
    )
    finished = executions.filter(status__in=finished_statuses).count()
    running = executions.filter(status='running').exists()

    suite.passed_count = passed
    suite.failed_count = failed
    suite.last_run_at = timezone.now()
    if running or finished < latest_total:
        suite.execution_status = 'running'
        suite.execution_result = None
    else:
        suite.execution_status = 'completed'
        suite.execution_result = 'passed' if failed == 0 and passed == latest_total else 'failed'
    suite.save(update_fields=[
        'execution_status',
        'execution_result',
        'passed_count',
        'failed_count',
        'last_run_at',
    ])


def _save_agent_artifacts(execution, payload):
    artifact_dir = os.path.join(
        settings.MEDIA_ROOT,
        'app-automation',
        'agent-artifacts',
        f'execution_{execution.id}',
    )
    os.makedirs(artifact_dir, exist_ok=True)

    manifest = {
        'execution_id': execution.id,
        'received_at': timezone.now().isoformat(),
        'files': [],
    }

    log_text = payload.get('log_text')
    if log_text:
        log_path = os.path.join(artifact_dir, 'agent.log')
        with open(log_path, 'w', encoding='utf-8') as file_obj:
            file_obj.write(str(log_text))
        manifest['files'].append('agent.log')

    screenshot_base64 = payload.get('screenshot_base64')
    if screenshot_base64:
        image_path = os.path.join(artifact_dir, 'screenshot.png')
        with open(image_path, 'wb') as file_obj:
            file_obj.write(base64.b64decode(screenshot_base64))
        manifest['files'].append('screenshot.png')

    manifest_path = os.path.join(artifact_dir, 'manifest.json')
    with open(manifest_path, 'w', encoding='utf-8') as file_obj:
        json.dump(manifest, file_obj, ensure_ascii=False, indent=2)
    return artifact_dir


class AppExecutionAgentViewSet(viewsets.ModelViewSet):
    """执行机管理与本地 Agent 轮询接口。"""

    queryset = AppExecutionAgent.objects.all()
    serializer_class = AppExecutionAgentSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'agent_id'

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        return super().get_queryset().filter(created_by=self.request.user)

    @action(detail=False, methods=['post'], url_path='heartbeat')
    def heartbeat(self, request):
        """登记/刷新 Agent，并同步本机可见设备。"""
        agent_id = str(request.data.get('agent_id') or '').strip() or f'agent-{uuid.uuid4().hex[:10]}'
        name = str(request.data.get('name') or agent_id).strip()
        devices = request.data.get('devices') or []
        capabilities = request.data.get('capabilities') or {}
        now = timezone.now()

        agent, _ = AppExecutionAgent.objects.update_or_create(
            agent_id=agent_id,
            defaults={
                'name': name,
                'status': 'online',
                'capabilities': capabilities,
                'last_seen_at': now,
                'last_ip': _client_ip(request),
                'created_by': request.user,
            },
        )

        synced_device_ids = []
        for raw_device in devices:
            if not isinstance(raw_device, dict):
                continue
            device_id = str(raw_device.get('device_id') or '').strip()
            if not device_id:
                continue
            status_value = raw_device.get('status') or 'online'
            defaults = {
                'name': raw_device.get('name') or device_id,
                'status': status_value,
                'android_version': raw_device.get('android_version') or '',
                'connection_type': raw_device.get('connection_type') or 'real_device',
                'device_specs': raw_device.get('device_specs') or {},
                'agent': agent,
            }
            AppDevice.objects.update_or_create(device_id=device_id, defaults=defaults)
            synced_device_ids.append(device_id)

        if synced_device_ids:
            AppDevice.objects.filter(agent=agent).exclude(device_id__in=synced_device_ids).update(status='offline')

        return Response({
            'success': True,
            'data': AppExecutionAgentSerializer(agent).data,
            'device_count': len(synced_device_ids),
        })

    @action(detail=False, methods=['post'], url_path='claim')
    def claim(self, request):
        """领取一条待执行的 Agent 模式任务。"""
        agent_id = str(request.data.get('agent_id') or '').strip()
        if not agent_id:
            return Response({'success': False, 'message': '缺少 agent_id'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            agent = AppExecutionAgent.objects.get(agent_id=agent_id, created_by=request.user)
        except AppExecutionAgent.DoesNotExist:
            return Response({'success': False, 'message': 'Agent 不存在，请先 heartbeat 登记'}, status=status.HTTP_404_NOT_FOUND)

        device_ids = [str(item).strip() for item in (request.data.get('device_ids') or []) if str(item).strip()]
        now = timezone.now()
        with transaction.atomic():
            queryset = (
                AppTestExecution.objects.select_for_update()
                .select_related('test_case', 'test_case__app_package', 'test_case__project__android_app_package', 'device')
                .filter(execution_mode='agent', status='pending')
                .order_by('created_at', 'id')
            )
            if device_ids:
                queryset = queryset.filter(device__device_id__in=device_ids)
            execution = queryset.first()
            if not execution:
                agent.status = 'online'
                agent.last_seen_at = now
                agent.last_ip = _client_ip(request)
                agent.save(update_fields=['status', 'last_seen_at', 'last_ip', 'updated_at'])
                return Response({'success': True, 'data': None, 'message': '暂无待执行任务'})

            execution.status = 'running'
            execution.progress = max(execution.progress or 0, 5)
            execution.started_at = execution.started_at or now
            execution.agent = agent
            execution.agent_claimed_at = now
            execution.agent_last_heartbeat_at = now
            execution.task_id = execution.task_id or f'agent-{agent.agent_id}-{execution.id}'
            execution.save(update_fields=[
                'status',
                'progress',
                'started_at',
                'agent',
                'agent_claimed_at',
                'agent_last_heartbeat_at',
                'task_id',
                'updated_at',
            ])
            agent.status = 'busy'
            agent.last_seen_at = now
            agent.last_ip = _client_ip(request)
            agent.save(update_fields=['status', 'last_seen_at', 'last_ip', 'updated_at'])

        send_execution_update(execution.id, status='running', progress=execution.progress, message='本地 Agent 已领取任务')
        return Response({'success': True, 'data': _execution_payload(execution)})

    @action(detail=False, methods=['post'], url_path='executions/(?P<execution_id>[^/.]+)/status')
    def update_execution_status(self, request, execution_id=None):
        """接收 Agent 执行状态、结果和轻量附件。"""
        agent_id = str(request.data.get('agent_id') or '').strip()
        try:
            agent = AppExecutionAgent.objects.get(agent_id=agent_id, created_by=request.user)
            execution = AppTestExecution.objects.select_related('test_suite').get(
                id=execution_id,
                execution_mode='agent',
                agent=agent,
            )
        except AppExecutionAgent.DoesNotExist:
            return Response({'success': False, 'message': 'Agent 不存在'}, status=status.HTTP_404_NOT_FOUND)
        except AppTestExecution.DoesNotExist:
            return Response({'success': False, 'message': '执行记录不存在或未被该 Agent 领取'}, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        status_value = request.data.get('status') or execution.status
        result_value = request.data.get('result')
        progress = request.data.get('progress', execution.progress)
        message = str(request.data.get('message') or '').strip()
        total_steps = request.data.get('total_steps')
        passed_steps = request.data.get('passed_steps')
        failed_steps = request.data.get('failed_steps')

        execution.status = status_value
        execution.result = result_value or execution.result
        execution.progress = int(progress or 0)
        execution.agent_last_heartbeat_at = now
        execution.agent_message = message[:500]
        execution.agent_payload = request.data
        if total_steps is not None:
            execution.total_steps = int(total_steps or 0)
        if passed_steps is not None:
            execution.passed_steps = int(passed_steps or 0)
        if failed_steps is not None:
            execution.failed_steps = int(failed_steps or 0)
        if request.data.get('error_message'):
            execution.error_message = str(request.data.get('error_message'))
        if isinstance(request.data.get('performance_metrics'), dict):
            execution.performance_metrics = request.data.get('performance_metrics')
        if status_value in ('completed', 'error', 'stopped'):
            execution.finished_at = now
            if execution.started_at:
                execution.duration = (execution.finished_at - execution.started_at).total_seconds()
            execution.progress = 100 if status_value == 'completed' else execution.progress
            if request.data.get('log_text') or request.data.get('screenshot_base64'):
                execution.report_path = _save_agent_artifacts(execution, request.data)

        execution.save()

        agent.status = 'online' if status_value in ('completed', 'error', 'stopped') else 'busy'
        agent.last_seen_at = now
        agent.last_ip = _client_ip(request)
        agent.save(update_fields=['status', 'last_seen_at', 'last_ip', 'updated_at'])

        _sync_suite_progress(execution.test_suite_id)
        send_execution_update(
            execution.id,
            status=execution.status,
            progress=execution.progress,
            message=message or 'Agent 状态已回传',
            report_path=execution.report_path,
            finished_at=execution.finished_at,
            result=execution.result,
        )
        return Response({'success': True, 'data': {'execution_id': execution.id, 'status': execution.status, 'result': execution.result}})
