# -*- coding: utf-8 -*-
"""本地执行机 Agent API。

Agent 采用“本地主动轮询云端”的方式，避免云服务器反连用户电脑。
"""
import base64
import hmac
import json
import os
import secrets
import socket
import uuid

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils.crypto import salted_hmac
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from ..models import AppDevice, AppExecutionAgent, AppTestExecution, AppTestSuite
from ..serializers import AppExecutionAgentSerializer
from ..tasks import send_execution_update
from ..utils.agent_job import DEFAULT_LEASE_SECONDS, lease_deadline


VALID_HEALTH_STATUSES = {'unknown', 'ready', 'warning', 'blocked'}
AGENT_TOKEN_HEADER = 'HTTP_X_QAFLOW_AGENT_TOKEN'
FINAL_EXECUTION_STATUSES = {'completed', 'error', 'stopped'}
AGENT_ALLOWED_STATUS_TRANSITIONS = {
    'pending': {'running', 'error', 'stopped'},
    'running': {'running', 'completed', 'error', 'stopped'},
    'completed': set(),
    'error': set(),
    'stopped': set(),
}


def _hash_agent_token(raw_token):
    return salted_hmac('app_execution_agent_token', raw_token, secret=settings.SECRET_KEY).hexdigest()


def _generate_agent_token():
    return f'qfa_{secrets.token_urlsafe(32)}'


def _agent_token_from_request(request):
    raw_token = str(request.META.get(AGENT_TOKEN_HEADER) or '').strip()
    if not raw_token:
        auth_header = str(request.META.get('HTTP_AUTHORIZATION') or '').strip()
        if auth_header.lower().startswith('agent '):
            raw_token = auth_header.split(' ', 1)[1].strip()
    if not raw_token:
        return None

    token_prefix = raw_token[:16]
    token_hash = _hash_agent_token(raw_token)
    candidates = AppExecutionAgent.objects.filter(token_prefix=token_prefix, token_hash__gt='')
    for agent in candidates:
        if hmac.compare_digest(agent.token_hash, token_hash):
            agent.token_last_used_at = timezone.now()
            agent.last_ip = _client_ip(request)
            agent.save(update_fields=['token_last_used_at', 'last_ip', 'updated_at'])
            return agent
    return None


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
    snapshot = execution.execution_snapshot or {}
    snapshot_case = snapshot.get('test_case') if isinstance(snapshot.get('test_case'), dict) else {}
    ui_flow = snapshot_case.get('ui_flow') if snapshot_case else None
    variables = snapshot_case.get('variables') if snapshot_case else None
    if ui_flow is None:
        ui_flow = test_case.ui_flow if test_case else {}
    if variables is None:
        variables = test_case.variables if test_case else []
    return {
        'execution_id': execution.id,
        'test_case_id': test_case.id if test_case else None,
        'test_case_name': snapshot_case.get('name') or (test_case.name if test_case else ''),
        'test_suite_id': execution.test_suite_id,
        'device_id': execution.device.device_id if execution.device else '',
        'package_name': snapshot.get('package_name') or _package_name_for_execution(execution),
        'ui_flow': ui_flow,
        'variables': variables,
        'timeout': snapshot_case.get('timeout') or (test_case.timeout if test_case else 300),
        'attempt_no': execution.attempt_no,
        'lease_token': execution.lease_token,
        'lease_expires_at': execution.lease_expires_at,
        'protocol_version': snapshot.get('protocol_version') or '',
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

    def get_permissions(self):
        if self.action in ('heartbeat', 'claim', 'update_execution_status'):
            return [AllowAny()]
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        return super().get_queryset().filter(created_by=self.request.user)

    def _resolve_user_and_agent(self, request, agent_id='', require_agent=False):
        if request.user and request.user.is_authenticated:
            agent = None
            if agent_id:
                agent = AppExecutionAgent.objects.filter(agent_id=agent_id, created_by=request.user).first()
                if require_agent and not agent:
                    return None, None, Response(
                        {'success': False, 'message': 'Agent 不存在，请先生成令牌或完成 heartbeat 登记'},
                        status=status.HTTP_404_NOT_FOUND,
                    )
            return request.user, agent, None

        token_agent = _agent_token_from_request(request)
        if not token_agent:
            return None, None, Response(
                {'success': False, 'message': '缺少有效 Agent 令牌，请在执行机 Agent 页面生成绑定令牌'},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if agent_id and token_agent.agent_id != agent_id:
            return None, None, Response(
                {'success': False, 'message': 'Agent 令牌与 agent_id 不匹配'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return token_agent.created_by, token_agent, None

    @action(detail=False, methods=['post'], url_path='generate-token')
    def generate_token(self, request):
        """为本地 Agent 生成专用连接令牌，避免在本地反复输入平台账密。"""
        agent_id = str(request.data.get('agent_id') or '').strip() or socket.gethostname()
        name = str(request.data.get('name') or '').strip() or f'{agent_id} 本地执行机'

        existing = AppExecutionAgent.objects.filter(agent_id=agent_id).first()
        if existing and existing.created_by_id and existing.created_by_id != request.user.id:
            return Response(
                {'success': False, 'message': '该 Agent 标识已被其他用户绑定，请换一个 Agent 标识'},
                status=status.HTTP_409_CONFLICT,
            )

        raw_token = _generate_agent_token()
        now = timezone.now()
        agent, _ = AppExecutionAgent.objects.update_or_create(
            agent_id=agent_id,
            defaults={
                'name': name,
                'status': existing.status if existing else 'offline',
                'token_hash': _hash_agent_token(raw_token),
                'token_prefix': raw_token[:16],
                'token_created_at': now,
                'created_by': request.user,
            },
        )
        command = (
            'python scripts/qaflow_agent.py '
            f'--base-url {request.build_absolute_uri("/").rstrip("/")} '
            f'--agent-id {agent.agent_id} '
            f'--agent-token {raw_token} '
            '--save-config --once --dry-run'
        )
        return Response({
            'success': True,
            'data': {
                'agent': AppExecutionAgentSerializer(agent).data,
                'agent_token': raw_token,
                'command': command,
                'message': '令牌只展示一次，请不要发给无关人员。如泄露，可重新生成令牌覆盖旧令牌。',
            },
        })

    @action(detail=False, methods=['post'], url_path='heartbeat')
    def heartbeat(self, request):
        """登记/刷新 Agent，并同步本机可见设备。"""
        agent_id = str(request.data.get('agent_id') or '').strip() or f'agent-{uuid.uuid4().hex[:10]}'
        user, token_agent, error_response = self._resolve_user_and_agent(request, agent_id)
        if error_response:
            return error_response
        if token_agent:
            agent_id = token_agent.agent_id
        name = str(request.data.get('name') or agent_id).strip()
        devices = request.data.get('devices') or []
        capabilities = request.data.get('capabilities') or {}
        health_status = str(request.data.get('health_status') or 'unknown').strip()
        if health_status not in VALID_HEALTH_STATUSES:
            health_status = 'unknown'
        health_summary = str(request.data.get('health_summary') or '').strip()
        health_checks = request.data.get('health_checks') or []
        if not isinstance(health_checks, list):
            health_checks = []
        now = timezone.now()

        existing = AppExecutionAgent.objects.filter(agent_id=agent_id).first()
        if existing and existing.created_by_id and existing.created_by_id != user.id:
            return Response(
                {'success': False, 'message': '该 Agent 标识已被其他用户绑定'},
                status=status.HTTP_409_CONFLICT,
            )

        if existing:
            for field, value in {
                'name': name,
                'status': 'online',
                'health_status': health_status,
                'health_summary': health_summary[:500],
                'health_checks': health_checks,
                'health_checked_at': now if health_checks else None,
                'capabilities': capabilities,
                'last_seen_at': now,
                'last_ip': _client_ip(request),
                'created_by': user,
            }.items():
                setattr(existing, field, value)
            existing.save()
            agent = existing
        else:
            agent = AppExecutionAgent.objects.create(
                agent_id=agent_id,
                name=name,
                status='online',
                health_status=health_status,
                health_summary=health_summary[:500],
                health_checks=health_checks,
                health_checked_at=now if health_checks else None,
                capabilities=capabilities,
                last_seen_at=now,
                last_ip=_client_ip(request),
                created_by=user,
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
            existing_device = AppDevice.objects.filter(device_id=device_id).select_related('agent').first()
            if existing_device and existing_device.agent_id and existing_device.agent_id != agent.id:
                continue
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

        user, token_agent, error_response = self._resolve_user_and_agent(request, agent_id, require_agent=True)
        if error_response:
            return error_response
        agent = token_agent or AppExecutionAgent.objects.get(agent_id=agent_id, created_by=user)
        if agent.health_status == 'blocked':
            return Response({
                'success': True,
                'data': None,
                'message': agent.health_summary or '执行机环境不可执行，暂不领取任务',
            })

        device_ids = [str(item).strip() for item in (request.data.get('device_ids') or []) if str(item).strip()]
        now = timezone.now()
        with transaction.atomic():
            queryset = (
                AppTestExecution.objects.select_for_update()
                .select_related('test_case', 'test_case__app_package', 'test_case__project__android_app_package', 'device')
                .filter(
                    execution_mode='agent',
                    status='pending',
                    user=user,
                    device__agent=agent,
                )
                .filter(Q(agent=agent) | Q(agent__isnull=True))
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
            execution.attempt_no = (execution.attempt_no or 0) + 1
            execution.lease_token = secrets.token_urlsafe(32)
            execution.lease_expires_at = lease_deadline(DEFAULT_LEASE_SECONDS)
            execution.last_event_seq = 0
            execution.save(update_fields=[
                'status',
                'progress',
                'started_at',
                'agent',
                'agent_claimed_at',
                'agent_last_heartbeat_at',
                'task_id',
                'attempt_no',
                'lease_token',
                'lease_expires_at',
                'last_event_seq',
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
        user, token_agent, error_response = self._resolve_user_and_agent(request, agent_id, require_agent=True)
        if error_response:
            return error_response
        try:
            agent = token_agent or AppExecutionAgent.objects.get(agent_id=agent_id, created_by=user)
            execution = AppTestExecution.objects.select_related('test_suite').get(
                id=execution_id,
                execution_mode='agent',
                agent=agent,
            )
        except AppTestExecution.DoesNotExist:
            return Response({'success': False, 'message': '执行记录不存在或未被该 Agent 领取'}, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        status_value = request.data.get('status') or execution.status
        result_value = request.data.get('result')
        progress = request.data.get('progress', execution.progress)
        message = str(request.data.get('message') or '').strip()
        lease_token = str(request.data.get('lease_token') or '').strip()
        attempt_no = int(request.data.get('attempt_no') or 0)
        event_seq = request.data.get('event_seq')
        total_steps = request.data.get('total_steps')
        passed_steps = request.data.get('passed_steps')
        failed_steps = request.data.get('failed_steps')

        if status_value not in AGENT_ALLOWED_STATUS_TRANSITIONS:
            return Response({'success': False, 'message': 'Agent 上报的执行状态不合法'}, status=status.HTTP_400_BAD_REQUEST)

        if execution.status in FINAL_EXECUTION_STATUSES:
            return Response({
                'success': True,
                'data': {
                    'execution_id': execution.id,
                    'status': execution.status,
                    'result': execution.result,
                    'idempotent': True,
                    'message': '执行记录已是终态，忽略重复上报',
                }
            })

        if not execution.lease_token or not lease_token or not hmac.compare_digest(execution.lease_token, lease_token):
            return Response({'success': False, 'message': '任务租约无效，请重新领取任务'}, status=status.HTTP_409_CONFLICT)

        if attempt_no != execution.attempt_no:
            return Response({'success': False, 'message': '执行尝试次数不匹配，旧 Agent 上报已被拒绝'}, status=status.HTTP_409_CONFLICT)

        if execution.lease_expires_at and execution.lease_expires_at < now:
            return Response({'success': False, 'message': '任务租约已过期，请等待云端回收或重新执行'}, status=status.HTTP_409_CONFLICT)

        if status_value not in AGENT_ALLOWED_STATUS_TRANSITIONS.get(execution.status, set()):
            return Response({
                'success': False,
                'message': f'不允许从 {execution.status} 更新为 {status_value}',
            }, status=status.HTTP_409_CONFLICT)

        if event_seq is not None:
            event_seq = int(event_seq or 0)
            if event_seq <= execution.last_event_seq:
                return Response({
                    'success': True,
                    'data': {
                        'execution_id': execution.id,
                        'status': execution.status,
                        'result': execution.result,
                        'idempotent': True,
                        'message': '重复或旧事件已忽略',
                    }
                })
            execution.last_event_seq = event_seq

        execution.status = status_value
        execution.result = result_value or execution.result
        execution.progress = min(max(int(progress or 0), 0), 100)
        execution.agent_last_heartbeat_at = now
        execution.agent_message = message[:500]
        execution.agent_payload = request.data
        if status_value == 'running':
            execution.lease_expires_at = lease_deadline(DEFAULT_LEASE_SECONDS)
        if total_steps is not None:
            execution.total_steps = max(int(total_steps or 0), 0)
        if passed_steps is not None:
            execution.passed_steps = max(int(passed_steps or 0), 0)
        if failed_steps is not None:
            execution.failed_steps = max(int(failed_steps or 0), 0)
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
            execution.lease_expires_at = now

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
