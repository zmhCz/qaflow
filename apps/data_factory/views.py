"""
数据工厂API视图
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet
from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q, Count
from django.db import IntegrityError, transaction, close_old_connections
from django.utils import timezone
from django.http import HttpResponse
from django.core.cache import cache
from django.views.decorators.csrf import csrf_exempt
from asgiref.sync import sync_to_async
import asyncio
import json
import os
import random
import re
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace

import logging
from pathlib import Path
import hashlib
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import psutil
except ImportError:  # pragma: no cover - optional runtime dependency
    psutil = None

from .business_load import get_scenario_options
from .models import BusinessAccount, BusinessLoadTask, DataFactoryRecord
from .serializers import (
    BusinessAccountAllocateSerializer,
    BusinessAccountImportSerializer,
    BusinessAccountReleaseSerializer,
    BusinessAccountSerializer,
    BusinessLoadTaskSerializer,
    DataFactoryRecordSerializer,
    ToolExecuteSerializer,
)
from .tool_list import get_categories, get_tool_list
from .tools.string_tools import StringTools
from .tools.encoding_tools import EncodingTools
from .tools.random_tools import RandomTools
from .tools.encryption_tools import EncryptionTools
from .tools.test_data_tools import TestDataTools
from .tools.json_tools import JsonTools
from .tools.crontab_tools import CrontabTools
from .tools.image_tools import ImageTools

logger = logging.getLogger(__name__)

DEFAULT_BUSINESS_BASE_URL = (getattr(settings, 'DATA_FACTORY_DEFAULT_BASE_URL', '') or '').rstrip('/')
DEFAULT_BUSINESS_SMS_CODE = getattr(settings, 'DATA_FACTORY_DEFAULT_SMS_CODE', '') or ''
DEFAULT_BUSINESS_PROBE_PHONE = getattr(settings, 'DATA_FACTORY_DEFAULT_PROBE_PHONE', '') or ''

class DataFactoryPagination(PageNumberPagination):
    """数据工厂自定义分页"""
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class BusinessAccountPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 200


class BusinessAccountViewSet(viewsets.ModelViewSet):
    """Business test account pool."""

    serializer_class = BusinessAccountSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = BusinessAccountPagination
    MAX_RANGE_IMPORT_SIZE = 10000
    ACCOUNT_RANGE_PATTERN = re.compile(r'^(\d+)\s*~\s*(\d+)$')

    def get_queryset(self):
        queryset = BusinessAccount.objects.select_related('created_by', 'locked_by').all()
        environment = self.request.query_params.get('environment')
        business_domain = self.request.query_params.get('business_domain')
        account_status = self.request.query_params.get('status')
        keyword = self.request.query_params.get('keyword')

        if environment:
            queryset = queryset.filter(environment=environment)
        if business_domain:
            queryset = queryset.filter(business_domain=business_domain)
        if account_status:
            queryset = queryset.filter(status=account_status)
        if keyword:
            queryset = queryset.filter(
                Q(account_no__icontains=keyword)
                | Q(phone__icontains=keyword)
                | Q(user_id__icontains=keyword)
                | Q(nickname__icontains=keyword)
                | Q(purpose__icontains=keyword)
                | Q(remark__icontains=keyword)
            )

        return queryset.order_by('environment', 'business_domain', 'account_no')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=['get'])
    def options(self, request):
        return Response({
            'environments': [{'value': value, 'label': label} for value, label in BusinessAccount.ENVIRONMENTS],
            'business_domains': [{'value': value, 'label': label} for value, label in BusinessAccount.BUSINESS_DOMAINS],
            'statuses': [{'value': value, 'label': label} for value, label in BusinessAccount.STATUSES],
        })

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        queryset = self.get_queryset()
        aggregate_queryset = queryset.order_by()
        by_status = dict(aggregate_queryset.values_list('status').annotate(count=Count('id')))
        by_domain = dict(aggregate_queryset.values_list('business_domain').annotate(count=Count('id')))
        by_environment = dict(aggregate_queryset.values_list('environment').annotate(count=Count('id')))
        return Response({
            'total': queryset.count(),
            'available': by_status.get('available', 0),
            'in_use': by_status.get('in_use', 0),
            'disabled': by_status.get('disabled', 0),
            'invalid': by_status.get('invalid', 0),
            'by_status': by_status,
            'by_domain': by_domain,
            'by_environment': by_environment,
        })

    @action(detail=False, methods=['post'])
    def bulk_import(self, request):
        serializer = BusinessAccountImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        accounts = self._normalize_import_accounts(data)

        created = []
        updated = []
        skipped = []

        for item in accounts:
            account_no = item.get('account_no', '').strip()
            if not account_no:
                skipped.append({'reason': '账号编号为空', 'raw': item})
                continue

            defaults = {
                'phone': item.get('phone', '').strip(),
                'user_id': item.get('user_id', '').strip(),
                'nickname': item.get('nickname', '').strip(),
                'business_domain': data['business_domain'],
                'purpose': item.get('purpose', data.get('purpose', '')),
                'tags': item.get('tags') or data.get('tags', []),
                'extra_data': item.get('extra_data') or {},
                'remark': item.get('remark', ''),
                'created_by': request.user,
            }
            if item.get('password'):
                defaults['password'] = item['password']
            if item.get('token'):
                defaults['token'] = item['token']

            try:
                obj, is_created = BusinessAccount.objects.update_or_create(
                    environment=data['environment'],
                    account_no=account_no,
                    defaults=defaults,
                )
            except IntegrityError as exc:
                skipped.append({'account_no': account_no, 'reason': str(exc)})
                continue

            payload = BusinessAccountSerializer(obj).data
            if is_created:
                created.append(payload)
            else:
                updated.append(payload)

        return Response({
            'created_count': len(created),
            'updated_count': len(updated),
            'skipped_count': len(skipped),
            'created': created,
            'updated': updated,
            'skipped': skipped,
        })

    @action(detail=False, methods=['post'])
    def allocate(self, request):
        serializer = BusinessAccountAllocateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            queryset = BusinessAccount.objects.select_for_update().filter(
                environment=data['environment'],
                status='available',
            )
            if data.get('business_domain'):
                queryset = queryset.filter(business_domain=data['business_domain'])
            available_before_tags = queryset.count()
            for tag in data.get('tags', []):
                queryset = queryset.filter(tags__contains=[tag])
            available_after_tags = queryset.count()

            accounts = list(queryset.order_by('last_used_at', 'id')[:data['count']])
            if len(accounts) < data['count']:
                tags = data.get('tags', [])
                if tags:
                    error_message = (
                        f'按标签 {", ".join(tags)} 筛选后可用账号不足，需要 {data["count"]} 个，'
                        f'当前仅 {available_after_tags} 个；不按标签筛选时可用 {available_before_tags} 个'
                    )
                else:
                    error_message = f'可用账号不足，需要 {data["count"]} 个，当前仅 {available_after_tags} 个'
                return Response(
                    {
                        'error': error_message,
                        'available_count': available_after_tags,
                        'available_without_tags': available_before_tags,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            now = timezone.now()
            account_ids = [item.id for item in accounts]
            BusinessAccount.objects.filter(id__in=account_ids).update(
                status='in_use',
                locked_by=request.user,
                locked_at=now,
                last_used_at=now,
                purpose=data.get('purpose', ''),
            )

        locked_accounts = BusinessAccount.objects.filter(id__in=account_ids).select_related('created_by', 'locked_by')
        return Response({
            'count': len(account_ids),
            'accounts': BusinessAccountSerializer(locked_accounts, many=True).data,
        })

    @action(detail=False, methods=['post'])
    def release(self, request):
        serializer = BusinessAccountReleaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account_ids = serializer.validated_data['account_ids']
        updated = BusinessAccount.objects.filter(id__in=account_ids).update(
            status='available',
            locked_by=None,
            locked_at=None,
        )
        return Response({'released_count': updated})

    @action(detail=True, methods=['post'])
    def release_one(self, request, pk=None):
        account = self.get_object()
        account.status = 'available'
        account.locked_by = None
        account.locked_at = None
        account.save(update_fields=['status', 'locked_by', 'locked_at', 'updated_at'])
        return Response(BusinessAccountSerializer(account).data)

    def _normalize_import_accounts(self, data):
        accounts = list(data.get('accounts') or [])
        raw_text = data.get('raw_text', '')

        for line in raw_text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            range_match = self.ACCOUNT_RANGE_PATTERN.match(line)
            if range_match:
                start_text, end_text = range_match.groups()
                start_number = int(start_text)
                end_number = int(end_text)
                if start_number > end_number:
                    raise ValidationError(f'号段起始值不能大于结束值：{line}')

                range_size = end_number - start_number + 1
                if range_size > self.MAX_RANGE_IMPORT_SIZE:
                    raise ValidationError(
                        f'单次号段导入最多支持 {self.MAX_RANGE_IMPORT_SIZE} 条，当前为 {range_size} 条'
                    )

                width = len(start_text)
                for account_number in range(start_number, end_number + 1):
                    account_value = str(account_number).zfill(width)
                    accounts.append({
                        'account_no': account_value,
                        'phone': account_value,
                    })
                continue

            if '~' in line:
                raise ValidationError(f'号段格式不正确，请使用纯数字格式：18800001000~18800001099；当前为：{line}')

            parts = [part.strip() for part in line.replace('\t', ',').split(',')]
            accounts.append({
                'account_no': parts[0] if len(parts) > 0 else '',
                'phone': parts[1] if len(parts) > 1 else '',
                'user_id': parts[2] if len(parts) > 2 else '',
                'nickname': parts[3] if len(parts) > 3 else '',
                'password': parts[4] if len(parts) > 4 else '',
                'token': parts[5] if len(parts) > 5 else '',
            })

        return accounts


class BusinessLoadTaskPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class BusinessLoadTaskViewSet(viewsets.ModelViewSet):
    """Composable business load-test task APIs."""

    serializer_class = BusinessLoadTaskSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = BusinessLoadTaskPagination
    DEFAULT_TEST_PROBE_PHONE = DEFAULT_BUSINESS_PROBE_PHONE
    TRIAL_RUN_HARD_ACCOUNT_LIMIT = 5
    TRIAL_RUN_HARD_DURATION_LIMIT = 600
    IM_TARGET_TYPES = {
        'c2c': {'label': '单聊', 'biz_type': 1},
        'group': {'label': '群聊', 'biz_type': 2},
        'room': {'label': '语音房', 'biz_type': 5},
        'party': {'label': '派对房', 'biz_type': 6},
    }
    IM_SAFE_ACCOUNT_WARN_LIMIT = 50
    IM_SAFE_MIN_INTERVAL_MS = 500
    IM_SAFE_DURATION_LIMIT = 600

    def get_queryset(self):
        queryset = BusinessLoadTask.objects.select_related('created_by').all()
        scenario_type = self.request.query_params.get('scenario_type')
        task_status = self.request.query_params.get('status')
        environment = self.request.query_params.get('environment')
        business_domain = self.request.query_params.get('business_domain')
        keyword = self.request.query_params.get('keyword')

        if scenario_type:
            queryset = queryset.filter(scenario_type=scenario_type)
        if task_status:
            queryset = queryset.filter(status=task_status)
        if environment:
            queryset = queryset.filter(environment=environment)
        if business_domain:
            queryset = queryset.filter(business_domain=business_domain)
        if keyword:
            queryset = queryset.filter(Q(name__icontains=keyword) | Q(purpose__icontains=keyword))

        return queryset.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=['get'])
    def options(self, request):
        return Response({
            'scenarios': get_scenario_options(),
            'environments': [{'value': value, 'label': label} for value, label in BusinessAccount.ENVIRONMENTS],
            'business_domains': [{'value': value, 'label': label} for value, label in BusinessAccount.BUSINESS_DOMAINS],
            'statuses': [{'value': value, 'label': label} for value, label in BusinessLoadTask.STATUSES],
        })

    @action(detail=False, methods=['get'], url_path='community-candidates')
    def community_candidates(self, request):
        """Return community candidates for the load task resource picker."""
        keyword = (request.query_params.get('keyword') or '').strip()
        environment = request.query_params.get('environment') or 'test'
        base_url = (request.query_params.get('base_url') or DEFAULT_BUSINESS_BASE_URL).rstrip('/')
        candidates = {}

        def add_candidate(server_id, server_name='', source='历史任务', server_no=None, raw=None):
            if not server_id:
                return
            server_id_text = str(server_id).strip()
            if not server_id_text:
                return
            candidate = {
                'server_id': int(server_id_text) if server_id_text.isdigit() else server_id_text,
                'server_name': server_name or f'社区 {server_id_text}',
                'server_no': server_no,
                'source': source,
                'raw': raw or {},
            }
            existing = candidates.get(server_id_text)
            if existing:
                candidates[server_id_text] = self._merge_community_candidate(existing, candidate)
            else:
                candidates[server_id_text] = candidate

        if keyword:
            try:
                for item in self._search_online_communities(request, base_url, keyword):
                    add_candidate(
                        item.get('server_id'),
                        item.get('server_name'),
                        item.get('source', '线上搜索'),
                        item.get('server_no'),
                        item.get('raw'),
                    )
            except Exception as exc:
                logger.warning('Online community search failed: %s', exc)

        add_candidate(55984, '默认测试社区', '系统默认', None)
        for task in BusinessLoadTask.objects.filter(environment=environment).order_by('-updated_at')[:100]:
            config = task.config or {}
            add_candidate(config.get('server_id'), config.get('server_name'), '历史任务', config.get('server_no'))

        filtered = self._filter_community_candidates(candidates.values(), keyword)
        if keyword.isdigit() and not filtered:
            add_candidate(keyword, f'社区 {keyword}', '手动输入', keyword)
            filtered = self._filter_community_candidates(candidates.values(), keyword)
        if keyword:
            filtered = self._annotate_exclusive_room_capability(request, base_url, filtered[:30])

        return Response({'communities': filtered[:30]})

    @action(detail=False, methods=['post'], url_path='room-list-preview')
    def room_list_preview(self, request):
        """Login with a probe account and fetch a small room list from one community."""
        server_id = request.data.get('server_id')
        if not server_id:
            return Response({'error': '请先选择社区'}, status=status.HTTP_400_BAD_REQUEST)

        base_url = (request.data.get('base_url') or DEFAULT_BUSINESS_BASE_URL).rstrip('/')
        room_source = str(request.data.get('room_source') or 'normal').strip().lower()
        probe_phone = self._resolve_probe_phone(request)
        if not probe_phone:
            return Response({'error': '没有可用探测账号，请先在账号池添加手机号，或手动填写探测手机号'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            page_size = min(max(int(request.data.get('page_size') or 50), 1), 100)
            max_pages = min(max(int(request.data.get('max_pages') or 2), 1), 5)
        except (TypeError, ValueError):
            return Response({'error': 'page_size/max_pages 必须是数字'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token, user_id = self._get_probe_token(
                base_url=base_url,
                phone=probe_phone,
                sms_code=request.data.get('sms_code') or DEFAULT_BUSINESS_SMS_CODE,
                server_id=server_id,
            )
            plugin = None
            if room_source == 'exclusive':
                community_detail = self._enter_business_server_detail(base_url, token, server_id)
                plugin = self._find_exclusive_room_plugin(community_detail)
                rooms = self._fetch_exclusive_room_preview(
                    base_url=base_url,
                    token=token,
                    server_id=server_id,
                    plugin=plugin,
                    page_size=page_size,
                    max_pages=max_pages,
                )
            else:
                rooms = self._fetch_room_preview(
                    base_url=base_url,
                    token=token,
                    server_id=server_id,
                    page_size=page_size,
                    max_pages=max_pages,
                )
        except ValidationError as exc:
            return Response({'error': exc.detail if isinstance(exc.detail, str) else str(exc.detail)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception('Load room preview failed')
            return Response({'error': f'加载语音房失败：{exc}'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'server_id': server_id,
            'probe_phone': probe_phone,
            'probe_user_id': user_id,
            'room_source': room_source,
            'exclusive_plugin': plugin,
            'rooms': rooms,
            'room_count': len(rooms),
            'message': f'已加载 {len(rooms)} 个{"专属房" if room_source == "exclusive" else "语音房"}',
        })

    @action(detail=True, methods=['post'])
    def precheck(self, request, pk=None):
        task = self.get_object()
        result = self._build_precheck_result(task)
        task.metrics = {
            **(task.metrics or {}),
            'last_precheck': result,
        }
        task.logs = self._append_task_log(task, '预检查完成', result)
        task.save(update_fields=['metrics', 'logs', 'updated_at'])
        return Response(result)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        task = self.get_object()
        precheck = self._build_precheck_result(task)
        if not precheck['passed']:
            task.status = 'failed'
            task.metrics = {
                **(task.metrics or {}),
                'last_precheck': precheck,
            }
            task.logs = self._append_task_log(task, '启动失败：预检查不通过', precheck)
            task.finished_at = timezone.now()
            task.save(update_fields=['status', 'metrics', 'logs', 'finished_at', 'updated_at'])
            return Response({'error': precheck['message'], 'precheck': precheck}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        task.status = 'running'
        task.started_at = now
        task.finished_at = None
        task.metrics = {
            **(task.metrics or {}),
            'last_precheck': precheck,
            'last_trial_run': None,
            'last_execution_mode': 'start',
            'planned_account_count': task.account_count,
            'planned_capability_count': len(task.capability_chain or []),
            'dry_run': False,
        }
        log_message = f'任务已启动：后台执行 {task.account_count} 个账号'
        task.logs = self._append_task_log(task, log_message, {'capability_chain': task.capability_chain})
        task.save(update_fields=['status', 'started_at', 'finished_at', 'metrics', 'logs', 'updated_at'])
        self._start_business_load_background(task.id)
        return Response(BusinessLoadTaskSerializer(task).data)

    def _start_business_load_background(self, task_id):
        thread = threading.Thread(
            target=self._run_business_load_task_background,
            args=(task_id,),
            daemon=True,
        )
        thread.start()
        return thread

    def _run_business_load_task_background(self, task_id):
        task = BusinessLoadTask.objects.filter(id=task_id).first()
        if not task:
            return

        start_time = time.perf_counter()
        started_at = task.started_at or timezone.now()
        try:
            precheck = self._build_precheck_result(task)
            if not precheck.get('passed'):
                task.status = 'failed'
                task.finished_at = timezone.now()
                task.metrics = {
                    **(task.metrics or {}),
                    'last_precheck': precheck,
                    'last_execution_mode': 'start',
                }
                task.logs = self._append_task_log(task, '任务执行失败：预检查不通过', precheck)
                task.save(update_fields=['status', 'finished_at', 'metrics', 'logs', 'updated_at'])
                return

            account_limit = max(1, int(task.account_count or 1))
            execution_result = self._run_trial_execution(task, precheck, account_limit)
            failed_count = execution_result.get('summary', {}).get('failed_count', 0)
            was_stopped = BusinessLoadTask.objects.filter(id=task.id, status='stopped').exists()
            task = BusinessLoadTask.objects.get(id=task.id)
            task.status = 'stopped' if was_stopped else ('completed' if failed_count == 0 else 'failed')
            task.finished_at = timezone.now()
            task.metrics = {
                **(task.metrics or {}),
                'last_precheck': precheck,
                'last_trial_run': {
                    **execution_result,
                    'mode': 'start',
                    'duration_ms': int((time.perf_counter() - start_time) * 1000),
                    'started_at': started_at.isoformat(),
                    'finished_at': timezone.now().isoformat(),
                },
                'last_execution_mode': 'start',
                'dry_run': False,
            }
            task.logs = self._append_task_log(task, execution_result.get('message', '任务执行完成'), {
                'summary': execution_result.get('summary'),
                'performance_summary': execution_result.get('performance', {}).get('summary'),
            })
            task.save(update_fields=['status', 'finished_at', 'metrics', 'logs', 'updated_at'])
        except Exception as exc:
            logger.exception('Business load task background execution failed')
            task = BusinessLoadTask.objects.filter(id=task_id).first()
            if not task:
                return
            failure_result = {
                'mode': 'start',
                'passed': False,
                'message': f'任务执行异常：{exc}',
                'summary': {
                    'total_accounts': task.account_count,
                    'failed_count': task.account_count,
                    'success_rate': 0,
                },
                'account_results': [],
                'room_entry_records': [],
                'performance': self._summarize_runner_performance([
                    self._capture_runner_performance_snapshot('failed')
                ]),
            }
            task.status = 'failed'
            task.finished_at = timezone.now()
            task.metrics = {
                **(task.metrics or {}),
                'last_trial_run': failure_result,
                'last_execution_mode': 'start',
                'dry_run': False,
            }
            task.logs = self._append_task_log(task, failure_result['message'], {'error': str(exc)})
            task.save(update_fields=['status', 'finished_at', 'metrics', 'logs', 'updated_at'])

    @action(detail=True, methods=['post'], url_path='trial-run')
    def trial_run(self, request, pk=None):
        """Run a small, real business-flow smoke test and persist visible results."""
        task = self.get_object()
        precheck = self._build_precheck_result(task)
        if not precheck['passed']:
            task.status = 'failed'
            task.metrics = {
                **(task.metrics or {}),
                'last_precheck': precheck,
            }
            task.logs = self._append_task_log(task, '试跑失败：预检查不通过', precheck)
            task.finished_at = timezone.now()
            task.save(update_fields=['status', 'metrics', 'logs', 'finished_at', 'updated_at'])
            return Response({'error': precheck['message'], 'precheck': precheck}, status=status.HTTP_400_BAD_REQUEST)

        requested_limit = request.data.get('max_accounts') or task.config.get('trial_account_limit') or 3
        try:
            requested_limit = int(requested_limit)
        except (TypeError, ValueError):
            requested_limit = 3
        account_limit = min(max(requested_limit, 1), task.account_count, self.TRIAL_RUN_HARD_ACCOUNT_LIMIT)

        task.status = 'running'
        task.started_at = timezone.now()
        task.metrics = {
            **(task.metrics or {}),
            'last_precheck': precheck,
            'last_execution_mode': 'trial_run',
        }
        task.logs = self._append_task_log(task, f'开始真实小流量试跑：最多 {account_limit} 个账号', {
            'account_limit': account_limit,
            'hard_limit': self.TRIAL_RUN_HARD_ACCOUNT_LIMIT,
        })
        task.save(update_fields=['status', 'started_at', 'metrics', 'logs', 'updated_at'])

        try:
            trial_result = self._run_trial_execution(task, precheck, account_limit)
            failed_count = trial_result.get('summary', {}).get('failed_count', 0)
            was_stopped = BusinessLoadTask.objects.filter(id=task.id, status='stopped').exists()
            task.status = 'stopped' if was_stopped else ('completed' if failed_count == 0 else 'failed')
            task.finished_at = timezone.now()
            task.metrics = {
                **(task.metrics or {}),
                'last_precheck': precheck,
                'last_trial_run': trial_result,
                'last_execution_mode': 'trial_run',
                'dry_run': False,
            }
            task.logs = self._append_task_log(task, trial_result.get('message', '真实小流量试跑完成'), {
                'summary': trial_result.get('summary'),
                'performance_summary': trial_result.get('performance', {}).get('summary'),
            })
            task.save(update_fields=['status', 'finished_at', 'metrics', 'logs', 'updated_at'])
            return Response(BusinessLoadTaskSerializer(task).data)
        except Exception as exc:
            logger.exception('Business load trial run failed')
            failure_result = {
                'mode': 'trial_run',
                'passed': False,
                'message': f'试跑异常：{exc}',
                'summary': {
                    'total_accounts': account_limit,
                    'failed_count': account_limit,
                    'success_rate': 0,
                },
                'account_results': [],
                'room_entry_records': [],
                'performance': self._summarize_runner_performance([
                    self._capture_runner_performance_snapshot('failed')
                ]),
            }
            task.status = 'failed'
            task.finished_at = timezone.now()
            task.metrics = {
                **(task.metrics or {}),
                'last_precheck': precheck,
                'last_trial_run': failure_result,
                'last_execution_mode': 'trial_run',
                'dry_run': False,
            }
            task.logs = self._append_task_log(task, failure_result['message'], {'error': str(exc)})
            task.save(update_fields=['status', 'finished_at', 'metrics', 'logs', 'updated_at'])
            return Response({'error': str(exc), 'task': BusinessLoadTaskSerializer(task).data}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='team-room-republish')
    def team_room_republish(self, request, pk=None):
        """Republish one configured team room with room-level overrides."""
        task = self.get_object()
        if task.scenario_type != 'team_recruit_publish':
            return Response({'error': '只有发布组队场景支持房间级重新发布'}, status=status.HTTP_400_BAD_REQUEST)

        channel_id = str(request.data.get('channel_id') or '').strip()
        if not channel_id:
            return Response({'error': '请选择需要重新发布的房间'}, status=status.HTTP_400_BAD_REQUEST)

        config = dict(task.config or {})
        target_rooms = self._parse_target_rooms(config.get('target_rooms') or [])
        target_room = next((room for room in target_rooms if str(room.get('channel_id')) == channel_id), None)
        if not target_room:
            return Response({'error': '该房间不在当前任务的发布组队房间列表中，请先编辑任务并选择房间'}, status=status.HTTP_400_BAD_REQUEST)

        overrides = self._normalize_team_room_publish_overrides(request.data)
        room_overrides = dict(config.get('team_room_overrides') or {})
        room_overrides[channel_id] = {
            **room_overrides.get(channel_id, {}),
            **overrides,
            'updated_at': timezone.now().isoformat(),
        }
        config['team_room_overrides'] = room_overrides

        precheck = self._build_precheck_result(task)
        if precheck.get('missing_count'):
            return Response({'error': precheck.get('message'), 'precheck': precheck}, status=status.HTTP_400_BAD_REQUEST)

        account_plan = list(precheck.get('account_room_plan') or [])
        if not account_plan:
            return Response({'error': '没有可用账号执行重新发布'}, status=status.HTTP_400_BAD_REQUEST)

        plan = {**account_plan[0], **target_room}
        republish_task = SimpleNamespace(id=task.id, config={**config, **overrides})
        result = self._run_team_recruit_account(
            task=republish_task,
            base_url=(config.get('base_url') or DEFAULT_BUSINESS_BASE_URL).rstrip('/'),
            server_id=config.get('server_id'),
            plan=plan,
            index=1,
        )

        metrics = dict(task.metrics or {})
        records = dict(metrics.get('team_room_publish_records') or {})
        records[channel_id] = {
            'channel_id': channel_id,
            'channel_name': target_room.get('channel_name') or '',
            'room_type_label': target_room.get('room_type_label') or '',
            'display_order': target_room.get('display_order'),
            'last_result': result,
            'last_overrides': overrides,
            'last_published_at': timezone.now().isoformat(),
            'passed': bool(result.get('passed')),
        }
        metrics['team_room_publish_records'] = records
        metrics['last_team_room_republish'] = records[channel_id]

        task.config = config
        task.metrics = metrics
        task.logs = self._append_task_log(
            task,
            f'房间重新发布组队{"成功" if result.get("passed") else "失败"}：{target_room.get("channel_name") or channel_id}',
            {'channel_id': channel_id, 'passed': result.get('passed'), 'error': result.get('error')},
        )
        task.status = 'completed' if result.get('passed') else 'failed'
        task.finished_at = timezone.now()
        task.save(update_fields=['config', 'metrics', 'logs', 'status', 'finished_at', 'updated_at'])
        return Response(BusinessLoadTaskSerializer(task).data)

    @action(detail=True, methods=['post'], url_path='team-room-cancel')
    def team_room_cancel(self, request, pk=None):
        """Cancel the active team recruit for one configured room."""
        task = self.get_object()
        if task.scenario_type != 'team_recruit_publish':
            return Response({'error': '只有发布组队场景支持取消招募'}, status=status.HTTP_400_BAD_REQUEST)

        channel_id = str(request.data.get('channel_id') or '').strip()
        if not channel_id:
            return Response({'error': '请选择需要取消招募的房间'}, status=status.HTTP_400_BAD_REQUEST)

        config = dict(task.config or {})
        server_id = config.get('server_id')
        if not server_id:
            return Response({'error': '任务缺少目标社区，无法取消招募'}, status=status.HTTP_400_BAD_REQUEST)

        target_rooms = self._parse_target_rooms(config.get('target_rooms') or [])
        target_room = next((room for room in target_rooms if str(room.get('channel_id')) == channel_id), None)
        if not target_room:
            return Response({'error': '该房间不在当前任务的发布组队房间列表中'}, status=status.HTTP_400_BAD_REQUEST)

        account = self._pick_available_business_account(task)
        if not account:
            return Response({'error': '没有可用账号执行取消招募'}, status=status.HTTP_400_BAD_REQUEST)

        base_url = (config.get('base_url') or DEFAULT_BUSINESS_BASE_URL).rstrip('/')
        result = {
            'passed': False,
            'channel_id': channel_id,
            'channel_name': target_room.get('channel_name') or '',
            'account_no': account.get('account_no') or '',
            'phone': account.get('phone') or '',
            'steps': [],
            'error': '',
        }
        started_at = timezone.now()
        start_time = time.perf_counter()
        try:
            token, user_id = self._execute_trial_step(
                result,
                'login',
                '登录',
                lambda: self._login_business_account(base_url, account.get('phone') or account.get('account_no'), DEFAULT_BUSINESS_SMS_CODE, server_id),
            )
            result['user_id'] = user_id
            self._execute_trial_step(
                result,
                'close_team',
                '取消招募',
                lambda: self._close_business_team(base_url, token, server_id, channel_id),
            )
            result['passed'] = True
        except Exception as exc:
            result['error'] = str(exc)
            result['passed'] = False
        finally:
            result['started_at'] = started_at.isoformat()
            result['finished_at'] = timezone.now().isoformat()
            result['elapsed_ms'] = int((time.perf_counter() - start_time) * 1000)

        metrics = dict(task.metrics or {})
        records = dict(metrics.get('team_room_publish_records') or {})
        current_record = dict(records.get(channel_id) or {})
        records[channel_id] = {
            **current_record,
            'channel_id': channel_id,
            'channel_name': target_room.get('channel_name') or current_record.get('channel_name') or '',
            'room_type_label': target_room.get('room_type_label') or current_record.get('room_type_label') or '',
            'display_order': target_room.get('display_order') or current_record.get('display_order'),
            'last_cancel_result': result,
            'last_cancelled_at': timezone.now().isoformat(),
            'cancelled': bool(result.get('passed')),
        }
        metrics['team_room_publish_records'] = records
        metrics['last_team_room_cancel'] = records[channel_id]

        task.metrics = metrics
        task.logs = self._append_task_log(
            task,
            f'房间取消招募{"成功" if result.get("passed") else "失败"}：{target_room.get("channel_name") or channel_id}',
            {'channel_id': channel_id, 'passed': result.get('passed'), 'error': result.get('error')},
        )
        task.save(update_fields=['metrics', 'logs', 'updated_at'])
        return Response(BusinessLoadTaskSerializer(task).data)

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        task = self.get_object()
        if task.status not in ('running', 'ready'):
            return Response({'error': '只有待执行或执行中的任务可以停止'}, status=status.HTTP_400_BAD_REQUEST)
        task.status = 'stopped'
        task.finished_at = timezone.now()
        task.logs = self._append_task_log(task, '任务已手动停止', {})
        task.save(update_fields=['status', 'finished_at', 'logs', 'updated_at'])
        return Response(BusinessLoadTaskSerializer(task).data)

    def _resolve_probe_phone(self, request):
        body = getattr(request, 'data', {}) or {}
        query_params = getattr(request, 'query_params', {}) or {}
        probe_phone = str(body.get('probe_phone') or query_params.get('probe_phone') or '').strip()
        if probe_phone:
            return probe_phone

        account_id = body.get('account_id') or query_params.get('account_id')
        environment = body.get('environment') or query_params.get('environment') or 'test'
        account_queryset = BusinessAccount.objects.filter(
            environment=environment,
            status='available',
        ).exclude(phone='')
        if account_id:
            account_queryset = account_queryset.filter(id=account_id)
        else:
            account_queryset = account_queryset.filter(business_domain__in=['room', 'community', 'common'])

        account = account_queryset.order_by('last_used_at', 'id').first()
        if account:
            return account.phone or account.account_no
        if environment == 'test':
            return self.DEFAULT_TEST_PROBE_PHONE
        return ''

    def _search_online_communities(self, request, base_url, keyword):
        probe_phone = self._resolve_probe_phone(request)
        if not probe_phone:
            raise ValidationError('没有可用探测账号，无法调用线上社区搜索')

        token, _user_id = self._get_probe_token(
            base_url=base_url,
            phone=probe_phone,
            sms_code=getattr(request, 'query_params', {}).get('sms_code') or DEFAULT_BUSINESS_SMS_CODE,
            server_id=55984,
        )
        response = requests.get(
            f'{base_url}/webapi/nchannel/channel/business/findServerByParamV2',
            params={
                'no': 1,
                'size': 20,
                'serverName': keyword,
            },
            headers=self._build_business_headers(base_url, token=token, server_id=55984),
            timeout=15,
        )
        result = self._response_json(response)
        if not result.get('success'):
            message = result.get('retMsg') or result.get('message') or '社区搜索接口返回失败'
            raise ValidationError(message)

        ret_data = result.get('retData') or {}
        raw_items = []
        raw_items.extend(ret_data.get('list') or [])
        raw_items.extend(ret_data.get('personalServers') or [])

        communities = [self._normalize_community_candidate(item, '线上搜索') for item in raw_items]
        if keyword.isdigit():
            exact_matches = [
                item for item in communities
                if str(item.get('server_no') or '') == keyword or str(item.get('server_id') or '') == keyword
            ]
            if exact_matches:
                for item in exact_matches:
                    item['source'] = '社区号精确搜索'
                return exact_matches
        return communities

    def _merge_community_candidate(self, existing, incoming):
        source_priority = {
            '社区号精确搜索': 50,
            '线上搜索': 40,
            '系统默认': 20,
            '历史任务': 10,
            '手动输入': 0,
        }
        existing_priority = source_priority.get(existing.get('source'), 0)
        incoming_priority = source_priority.get(incoming.get('source'), 0)
        primary, secondary = (incoming, existing) if incoming_priority >= existing_priority else (existing, incoming)
        return {
            **secondary,
            **primary,
            'server_name': primary.get('server_name') or secondary.get('server_name') or '',
            'server_no': primary.get('server_no') or secondary.get('server_no'),
            'raw': primary.get('raw') or secondary.get('raw') or {},
            'has_exclusive_rooms': primary.get('has_exclusive_rooms') or secondary.get('has_exclusive_rooms') or False,
            'exclusive_plugin': primary.get('exclusive_plugin') or secondary.get('exclusive_plugin'),
        }

    def _filter_community_candidates(self, communities, keyword):
        items = list(communities or [])
        keyword = str(keyword or '').strip()
        if not keyword:
            return items

        if keyword.isdigit():
            server_no_matches = [
                item for item in items
                if str(item.get('server_no') or '').strip() == keyword
            ]
            if server_no_matches:
                return server_no_matches

            server_id_matches = [
                item for item in items
                if str(item.get('server_id') or '').strip() == keyword
            ]
            if server_id_matches:
                return server_id_matches

        keyword_lower = keyword.lower()
        return [
            item for item in items
            if keyword_lower in str(item.get('server_id') or '').lower()
            or keyword_lower in str(item.get('server_no') or '').lower()
            or keyword_lower in str(item.get('server_name') or '').lower()
        ]

    def _normalize_community_candidate(self, raw_item, source='线上搜索'):
        server_id = raw_item.get('serverId') or raw_item.get('server_id') or raw_item.get('id')
        server_no = raw_item.get('serverNo') or raw_item.get('server_no')
        server_name = raw_item.get('serverName') or raw_item.get('server_name') or raw_item.get('name')
        exclusive_plugin = self._find_exclusive_room_plugin(raw_item, raise_error=False)
        return {
            'server_id': int(server_id) if str(server_id or '').isdigit() else server_id,
            'server_no': int(server_no) if str(server_no or '').isdigit() else server_no,
            'server_name': server_name or f'社区 {server_no or server_id}',
            'source': source,
            'has_exclusive_rooms': bool(exclusive_plugin),
            'exclusive_plugin': exclusive_plugin,
            'raw': raw_item,
        }

    def _annotate_exclusive_room_capability(self, request, base_url, communities):
        """Attach exclusive-room availability for visible search results only."""
        items = list(communities or [])
        unknown_items = [
            item for item in items
            if item.get('server_id') and not item.get('has_exclusive_rooms') and item.get('source') != '手动输入'
        ]
        if not unknown_items:
            return items

        try:
            probe_phone = self._resolve_probe_phone(request)
            if not probe_phone:
                return items
            token, _user_id = self._get_probe_token(
                base_url=base_url,
                phone=probe_phone,
                sms_code=getattr(request, 'query_params', {}).get('sms_code') or DEFAULT_BUSINESS_SMS_CODE,
                server_id=unknown_items[0].get('server_id'),
            )
        except Exception as exc:
            logger.warning('Resolve exclusive room capability token failed: %s', exc)
            return items

        for item in unknown_items[:5]:
            try:
                detail = self._enter_business_server_detail(base_url, token, item.get('server_id'))
                plugin = self._find_exclusive_room_plugin(detail, raise_error=False)
                item['has_exclusive_rooms'] = bool(plugin)
                item['exclusive_plugin'] = plugin
            except Exception as exc:
                logger.info('Resolve exclusive room capability failed server_id=%s: %s', item.get('server_id'), exc)
                item['has_exclusive_rooms'] = False
                item['exclusive_plugin'] = None
        return items

    def _build_business_headers(self, base_url, token='', server_id=None):
        headers = {
            'accept': 'application/json',
            'accept-language': 'zh-CN,zh;q=0.9',
            'adan': 'userSourceType=0',
            'appid': 'nnPcWeb_8GIXaARk',
            'busitype': 'nn_aksjfdasoifnkls',
            'content-type': 'application/json',
            'deviceid': '1f128e40-d7a0-60f0-978f-9b40fde68c60',
            'origin': base_url,
            'referer': f'{base_url}/community/{server_id or 55984}/hall',
            'registercanal': 'guanwang_nn',
            'reqchannel': '4',
            'user-agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
            ),
        }
        if token:
            headers['token'] = token
        return headers

    def _get_probe_token(self, base_url, phone, sms_code, server_id=None):
        cache_key_source = f'{base_url}|{phone}'
        cache_key = f'data_factory_probe_token:{hashlib.sha1(cache_key_source.encode("utf-8")).hexdigest()}'
        cached_token = cache.get(cache_key)
        if cached_token:
            return cached_token

        token, user_id = self._login_probe_account(base_url, phone, sms_code, server_id)
        cache.set(cache_key, (token, user_id), 50 * 60)
        return token, user_id

    def _login_probe_account(self, base_url, phone, sms_code, server_id=None):
        url = f'{base_url}/webapi/u-nnpc/registerLogin'
        payload = {
            'telNum': str(phone),
            'smsCode': str(sms_code or DEFAULT_BUSINESS_SMS_CODE),
            'countryCode': '86',
        }
        response = requests.post(
            url,
            json=payload,
            headers=self._build_business_headers(base_url, server_id=server_id),
            timeout=15,
        )
        result = self._response_json(response)
        if not result.get('success') or result.get('retCode') != '100':
            message = result.get('retMsg') or result.get('message') or '登录失败'
            raise ValidationError(f'探测账号登录失败：{message}')

        ret_data = result.get('retData') or {}
        token = ret_data.get('token')
        if not token:
            raise ValidationError('探测账号登录成功但未返回 token')
        return token, ret_data.get('userId')

    def _run_trial_execution(self, task, precheck, account_limit):
        start_time = time.perf_counter()
        started_at = timezone.now()
        if task.scenario_type == 'im_message_flood':
            return self._run_im_message_trial_execution(task, precheck, account_limit, start_time, started_at)

        base_url = (task.config.get('base_url') or DEFAULT_BUSINESS_BASE_URL).rstrip('/')
        server_id = task.config.get('server_id')
        if not server_id:
            raise ValidationError('任务缺少 server_id，无法试跑')

        account_plan = list(precheck.get('account_room_plan') or [])[:account_limit]
        account_plan = self._resolve_auto_trial_rooms(task, base_url, server_id, account_plan)
        if task.scenario_type == 'community_activity_simulation':
            return self._run_community_activity_trial_execution(task, base_url, server_id, account_plan, start_time, started_at)
        if task.scenario_type == 'team_recruit_publish':
            return self._run_team_recruit_trial_execution(task, base_url, server_id, account_plan, start_time, started_at)
        if task.scenario_type == 'voice_room_online':
            return self._run_keepalive_trial_execution(task, base_url, server_id, account_plan, start_time, started_at)

        performance_samples = [self._capture_runner_performance_snapshot('start')]
        account_results = []
        room_entry_records = []

        for index, plan in enumerate(account_plan, start=1):
            result = self._run_trial_account(base_url, server_id, plan, index)
            account_results.append(result)
            if result.get('room_entry'):
                room_entry_records.append(result['room_entry'])
            performance_samples.append(self._capture_runner_performance_snapshot(f'account_{index}'))

        performance_samples.append(self._capture_runner_performance_snapshot('finish'))
        summary = self._summarize_trial_account_results(account_results)
        performance = self._summarize_runner_performance(performance_samples)
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        message = (
            f'真实小流量试跑完成：账号 {summary["total_accounts"]} 个，'
            f'进房成功 {summary["enter_room_success"]} 个，失败 {summary["failed_count"]} 个'
        )
        return {
            'mode': 'trial_run',
            'passed': summary['failed_count'] == 0,
            'message': message,
            'started_at': started_at.isoformat(),
            'finished_at': timezone.now().isoformat(),
            'duration_ms': duration_ms,
            'safety': {
                'requested_accounts': task.account_count,
                'executed_accounts': len(account_results),
                'hard_account_limit': self.TRIAL_RUN_HARD_ACCOUNT_LIMIT,
                'heartbeat_count_per_account': 1,
                'leave_room_after_trial': True,
            },
            'summary': summary,
            'account_results': account_results,
            'room_entry_records': room_entry_records,
            'performance': performance,
        }

    def _run_team_recruit_trial_execution(self, task, base_url, server_id, account_plan, start_time, started_at):
        performance_samples = [self._capture_runner_performance_snapshot('start')]
        indexed_plans = list(enumerate(account_plan, start=1))
        account_results = [None] * len(indexed_plans)
        room_entry_records = []
        worker_count = self._get_team_recruit_worker_count(task, len(indexed_plans))

        for index, plan in indexed_plans:
            self._persist_team_room_publish_progress(
                task.id,
                plan,
                {
                    'index': index,
                    'account_no': plan.get('account_no'),
                    'phone': plan.get('phone'),
                    'channel_id': plan.get('channel_id') or '',
                    'channel_name': plan.get('channel_name') or '',
                    'room_type_label': plan.get('room_type_label') or '',
                    'steps': [],
                    'passed': False,
                },
                '排队中',
            )

        active_sessions = []
        if not indexed_plans:
            account_results = []
        elif worker_count <= 1:
            publish_interval = self._get_team_publish_interval_seconds(task)
            for position, (index, plan) in enumerate(indexed_plans, start=1):
                result = self._run_team_recruit_account(task, base_url, server_id, plan, index, defer_keepalive=True)
                account_results[index - 1] = result
                active_session = result.pop('_active_session', None)
                if active_session:
                    active_sessions.append(active_session)
                if result.get('room_entry'):
                    room_entry_records.append(result['room_entry'])
                performance_samples.append(self._capture_runner_performance_snapshot(f'team_account_{index}'))
                if publish_interval and position < len(indexed_plans):
                    time.sleep(publish_interval)
        else:
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                future_map = {
                    executor.submit(
                        self._run_team_recruit_account_threadsafe,
                        task,
                        base_url,
                        server_id,
                        plan,
                        index,
                        True,
                    ): index
                    for index, plan in indexed_plans
                }
                for future in as_completed(future_map):
                    index = future_map[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        plan = indexed_plans[index - 1][1]
                        result = {
                            'index': index,
                            'account_no': plan.get('account_no'),
                            'phone': plan.get('phone'),
                            'server_id': server_id,
                            'channel_id': plan.get('channel_id') or '',
                            'channel_name': plan.get('channel_name') or '',
                            'room_type_label': plan.get('room_type_label') or '',
                            'steps': [],
                            'error': str(exc),
                            'passed': False,
                        }
                        self._persist_team_room_publish_progress(task.id, plan, result, '执行失败')
                    account_results[index - 1] = result
                    active_session = result.pop('_active_session', None)
                    if active_session:
                        active_sessions.append(active_session)
                    if result.get('room_entry'):
                        room_entry_records.append(result['room_entry'])
                    performance_samples.append(self._capture_runner_performance_snapshot(f'team_account_{index}'))

        account_results = [item for item in account_results if item is not None]
        visibility_summary = self._verify_team_recruit_visibility(
            task,
            base_url,
            server_id,
            active_sessions,
        )

        keepalive_summary = self._run_team_recruit_keepalive_scheduler(
            task,
            active_sessions,
            performance_samples,
        )

        performance_samples.append(self._capture_runner_performance_snapshot('finish'))
        summary = self._summarize_trial_account_results(account_results)
        summary.update({
            'publish_team_success': sum(1 for item in account_results if self._step_success(item, 'publish_team')),
            'im_notification_success': sum(1 for item in account_results if self._step_success(item, 'im_send_notification')),
            'team_keepalive_rounds': sum(int(item.get('team_keepalive_rounds') or 0) for item in account_results),
            'close_team_success': sum(1 for item in account_results if self._step_success(item, 'close_team')),
            'active_team_rooms': keepalive_summary['active_count'],
            'team_visible_success': visibility_summary['visible_count'],
            'team_visible_expected': visibility_summary['expected_count'],
            'team_visible_missing': len(visibility_summary['missing_channel_ids']),
            'team_keepalive_failed': keepalive_summary['failed_heartbeats'],
        })
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        message = (
            f'发布组队试跑完成：账号 {summary["total_accounts"]} 个，'
            f'发布成功 {summary["publish_team_success"]} 个，'
            f'IM通知成功 {summary["im_notification_success"]} 个，'
            f'端上可见 {summary["team_visible_success"]}/{summary["team_visible_expected"]} 个，'
            f'保活 {summary["team_keepalive_rounds"]} 轮，失败 {summary["failed_count"]} 个'
        )
        return {
            'mode': 'trial_run',
            'scenario_mode': 'team_recruit_publish',
            'passed': summary['failed_count'] == 0 and visibility_summary['passed'],
            'message': message,
            'started_at': started_at.isoformat(),
            'finished_at': timezone.now().isoformat(),
            'duration_ms': duration_ms,
            'safety': {
                'requested_accounts': task.account_count,
                'executed_accounts': len(account_results),
                'hard_account_limit': self.TRIAL_RUN_HARD_ACCOUNT_LIMIT,
                'close_team_after_trial': True,
                'leave_room_after_trial': True,
                'keepalive_after_notify': task.config.get('team_keepalive_after_notify') is not False,
                'heartbeat_interval_seconds': self._get_team_heartbeat_interval(task.config),
                'worker_count': worker_count,
                'keepalive_batch_size': self._get_team_keepalive_batch_size(task, len(active_sessions)),
                'keepalive_scheduler': 'per_room_deadline',
            },
            'team_visibility': visibility_summary,
            'summary': summary,
            'account_results': account_results,
            'room_entry_records': room_entry_records,
            'performance': self._summarize_runner_performance(performance_samples),
        }

    def _get_team_recruit_worker_count(self, task, account_count):
        if account_count <= 1:
            return 1
        config = task.config or {}
        if config.get('team_publish_reliable_visible') is not False:
            return 1
        configured_workers = self._safe_int(config.get('team_publish_concurrency'), None)
        if configured_workers is None:
            configured_workers = account_count
        return max(1, min(account_count, configured_workers, 10))

    def _get_team_publish_interval_seconds(self, task):
        config = task.config or {}
        interval_ms = self._safe_int(config.get('team_publish_interval_ms'), 500)
        return max(0, min(interval_ms, 5000)) / 1000

    def _get_team_keepalive_batch_size(self, task, active_count):
        if active_count <= 1:
            return max(1, active_count)
        config = task.config or {}
        configured_batch = self._safe_int(
            config.get('team_keepalive_batch_size')
            or config.get('request_rate_per_second')
            or config.get('enter_rate_per_second'),
            10,
        )
        return max(1, min(active_count, configured_batch, 20))

    def _verify_team_recruit_visibility(self, task, base_url, server_id, active_sessions):
        target_sessions = [
            session for session in active_sessions
            if session.get('token')
            and str(session.get('channel_id') or '').strip()
            and self._step_success(session.get('result') or {}, 'publish_team')
        ]
        target_channel_ids = [str(session.get('channel_id')) for session in target_sessions]
        expected_ids = set(target_channel_ids)
        if not expected_ids:
            return {
                'passed': True,
                'expected_count': 0,
                'visible_count': 0,
                'missing_channel_ids': [],
                'get_team_visible_count': 0,
                'page_query_visible_count': 0,
                'attempts': [],
            }

        config = task.config or {}
        wait_seconds = max(1, min(self._safe_int(config.get('team_visibility_wait_seconds'), 10), 60))
        deadline = time.monotonic() + wait_seconds
        attempts = []
        latest_state = {
            'get_team_visible_ids': set(),
            'page_query_visible_ids': set(),
            'visible_ids': set(),
        }

        while True:
            latest_state = self._fetch_team_recruit_visible_state(
                base_url=base_url,
                token=target_sessions[0]['token'],
                server_id=server_id,
                target_channel_ids=expected_ids,
            )
            visible_ids = latest_state['visible_ids']
            missing_ids = sorted(expected_ids - visible_ids)
            attempts.append({
                'elapsed_ms': int((wait_seconds - max(0, deadline - time.monotonic())) * 1000),
                'visible_count': len(visible_ids),
                'missing_channel_ids': missing_ids,
                'get_team_visible_count': len(latest_state['get_team_visible_ids']),
                'page_query_visible_count': len(latest_state['page_query_visible_ids']),
            })
            if not missing_ids or time.monotonic() >= deadline:
                break
            time.sleep(1)

        visible_ids = latest_state['visible_ids']
        missing_ids = sorted(expected_ids - visible_ids)
        summary = {
            'passed': not missing_ids,
            'expected_count': len(expected_ids),
            'visible_count': len(visible_ids),
            'missing_channel_ids': missing_ids,
            'get_team_visible_count': len(latest_state['get_team_visible_ids']),
            'page_query_visible_count': len(latest_state['page_query_visible_ids']),
            'attempts': attempts,
        }
        for session in target_sessions:
            result = session.get('result') or {}
            channel_id = str(session.get('channel_id') or '')
            success = channel_id in visible_ids
            result.setdefault('steps', []).append({
                'key': 'team_visible_check',
                'label': '端上组队可见性检查',
                'required': True,
                'success': success,
                'elapsed_ms': 0,
                'message': (
                    '已在端上同口径列表中可见'
                    if success
                    else '发布接口成功，但端上同口径列表未出现该组队房'
                ),
            })
            result['team_visibility'] = summary
            result['passed'] = all(step.get('success') or not step.get('required', True) for step in result.get('steps') or [])
            self._persist_team_room_publish_progress(
                task.id,
                session.get('plan') or {},
                result,
                '端上可见' if success else '端上不可见',
            )
        return summary

    def _fetch_team_recruit_visible_state(self, base_url, token, server_id, target_channel_ids):
        target_channel_ids = {str(item) for item in target_channel_ids}
        headers = self._build_business_headers(base_url, token=token, server_id=server_id)
        get_team_visible_ids = set()
        page_query_visible_ids = set()

        try:
            response = requests.get(
                f'{base_url}/webapi/nchannel/channel/business/{server_id}/getTeamListByServerId',
                headers=headers,
                timeout=15,
            )
            result = self._response_json(response)
            team_list = result.get('retData') or []
            if isinstance(team_list, list):
                get_team_visible_ids = {
                    str(item.get('channelId'))
                    for item in team_list
                    if isinstance(item, dict) and str(item.get('channelId')) in target_channel_ids
                }
        except Exception:
            logger.debug('Fetch getTeamListByServerId visibility failed', exc_info=True)

        try:
            response = requests.post(
                f'{base_url}/webapi/nchannel/server/channel/pageQuery',
                json={'serverId': int(server_id), 'lastSortIndex': -1, 'pageSize': 100},
                headers=headers,
                timeout=15,
            )
            result = self._response_json(response)
            ret_data = result.get('retData') or {}
            page_rooms = []
            if isinstance(ret_data.get('topList'), list):
                page_rooms.extend(ret_data.get('topList'))
            if isinstance(ret_data.get('pageList'), list):
                page_rooms.extend(ret_data.get('pageList'))
            for room in page_rooms:
                if not isinstance(room, dict):
                    continue
                channel_id = str(room.get('channelId') or '')
                if channel_id in target_channel_ids and room.get('teamInfo'):
                    page_query_visible_ids.add(channel_id)
        except Exception:
            logger.debug('Fetch pageQuery teamInfo visibility failed', exc_info=True)

        return {
            'get_team_visible_ids': get_team_visible_ids,
            'page_query_visible_ids': page_query_visible_ids,
            'visible_ids': get_team_visible_ids & page_query_visible_ids,
        }

    def _run_team_recruit_keepalive_scheduler(self, task, active_sessions, performance_samples=None):
        active_sessions = [session for session in active_sessions if session.get('token') and session.get('rid')]
        if not active_sessions:
            return {
                'active_count': 0,
                'rounds': 0,
                'failed_heartbeats': 0,
                'interrupted': False,
                'cleanup_count': 0,
            }

        config = task.config or {}
        if config.get('team_keepalive_after_notify') is False:
            self._cleanup_team_recruit_sessions(task, active_sessions, cleanup_reason='保活关闭后清理')
            return {
                'active_count': len(active_sessions),
                'rounds': 0,
                'failed_heartbeats': 0,
                'interrupted': False,
                'cleanup_count': len(active_sessions),
            }

        interval = self._get_team_heartbeat_interval(config)
        batch_size = self._get_team_keepalive_batch_size(task, len(active_sessions))
        total_rounds = 0
        failed_heartbeats = 0
        interrupted = False

        for session in active_sessions:
            session['next_heartbeat_at'] = session.get('next_heartbeat_at') or (session.get('entered_at') or time.monotonic()) + interval
            session['deadline_at'] = session.get('deadline_at') or (session.get('entered_at') or time.monotonic()) + self._get_team_keepalive_duration(config, session.get('team_context'))

        while True:
            if self._is_business_task_interrupted(task.id):
                interrupted = True
                for session in active_sessions:
                    session['interrupted'] = True
                break

            now = time.monotonic()
            pending_sessions = [
                session for session in active_sessions
                if not session.get('keepalive_done') and now < session.get('deadline_at', now)
            ]
            if not pending_sessions:
                break

            due_sessions = [
                session for session in pending_sessions
                if now >= session.get('next_heartbeat_at', now)
            ]
            if not due_sessions:
                next_due_at = min(session.get('next_heartbeat_at', now + 1) for session in pending_sessions)
                next_deadline_at = min(session.get('deadline_at', now + 1) for session in pending_sessions)
                sleep_seconds = max(0.05, min(next_due_at, next_deadline_at) - time.monotonic())
                time.sleep(min(sleep_seconds, 1))
                continue

            with ThreadPoolExecutor(max_workers=min(batch_size, len(due_sessions))) as executor:
                future_map = {
                    executor.submit(self._send_team_keepalive_once_threadsafe, session): session
                    for session in due_sessions
                }
                for future in as_completed(future_map):
                    session = future_map[future]
                    result = session['result']
                    plan = session['plan']
                    round_no = int(session.get('rounds') or 0) + 1
                    step = {
                        'key': f'team_keepalive_{round_no}',
                        'label': f'组队保活#{round_no}',
                        'required': True,
                        'success': False,
                        'elapsed_ms': 0,
                    }
                    try:
                        step.update(future.result())
                    except Exception as exc:
                        step['error'] = str(exc)
                        session['failed_heartbeats'] = int(session.get('failed_heartbeats') or 0) + 1
                        failed_heartbeats += 1
                    else:
                        if step.get('success'):
                            session['rounds'] = round_no
                            total_rounds += 1
                        else:
                            session['failed_heartbeats'] = int(session.get('failed_heartbeats') or 0) + 1
                            failed_heartbeats += 1

                    result['steps'].append(step)
                    result['team_keepalive_rounds'] = int(session.get('rounds') or 0)
                    result['team_keepalive_failed'] = int(session.get('failed_heartbeats') or 0)
                    result['team_keepalive_interrupted'] = False
                    if result.get('room_entry'):
                        result['room_entry']['heartbeat_rounds'] = result['team_keepalive_rounds']
                    session['next_heartbeat_at'] = time.monotonic() + interval
                    self._persist_team_room_publish_progress(task.id, plan, result, '保活中')

            if performance_samples is not None:
                performance_samples.append(self._capture_runner_performance_snapshot(f'team_keepalive_round_{total_rounds}'))

        for session in active_sessions:
            result = session['result']
            result['team_keepalive_rounds'] = int(session.get('rounds') or 0)
            result['team_keepalive_failed'] = int(session.get('failed_heartbeats') or 0)
            result['team_keepalive_interrupted'] = interrupted or bool(session.get('interrupted'))
            result['steps'].append({
                'key': 'team_keepalive_interrupted' if result['team_keepalive_interrupted'] else 'team_keepalive_completed',
                'label': '组队保活中断' if result['team_keepalive_interrupted'] else '组队保活完成',
                'required': False,
                'success': True,
                'elapsed_ms': 0,
                'message': (
                    '任务已被手动中断，开始关闭组队并退房'
                    if result['team_keepalive_interrupted']
                    else f'已按每个用户进房时间独立保活 {result["team_keepalive_rounds"]} 轮'
                ),
            })
            self._persist_team_room_publish_progress(task.id, session['plan'], result, '保活完成')

        cleanup_count = self._cleanup_team_recruit_sessions(task, active_sessions)
        return {
            'active_count': len(active_sessions),
            'rounds': total_rounds,
            'failed_heartbeats': failed_heartbeats,
            'interrupted': interrupted,
            'cleanup_count': cleanup_count,
        }

    def _send_team_keepalive_once_threadsafe(self, session):
        close_old_connections()
        started = time.perf_counter()
        try:
            self._send_room_heartbeat(
                base_url=session['base_url'],
                token=session['token'],
                rid=session['rid'],
            )
            return {
                'success': True,
                'elapsed_ms': int((time.perf_counter() - started) * 1000),
            }
        finally:
            close_old_connections()

    def _cleanup_team_recruit_sessions(self, task, active_sessions, cleanup_reason='到期清理'):
        config = task.config or {}
        if config.get('cleanup_after_stop') is False:
            for session in active_sessions:
                result = session['result']
                result['steps'].append({
                    'key': 'team_cleanup_skipped',
                    'label': '清理跳过',
                    'required': False,
                    'success': True,
                    'elapsed_ms': 0,
                    'message': '配置为不清理，组队和房间状态保留',
                })
                result['passed'] = all(step.get('success') or not step.get('required', True) for step in result.get('steps') or [])
                self._persist_team_room_publish_progress(task.id, session['plan'], result, '完成' if result.get('passed') else '执行失败')
            return 0

        batch_size = self._get_team_keepalive_batch_size(task, len(active_sessions))
        cleaned = 0
        with ThreadPoolExecutor(max_workers=max(1, min(batch_size, len(active_sessions)))) as executor:
            future_map = {
                executor.submit(self._cleanup_team_recruit_session_threadsafe, session, cleanup_reason): session
                for session in active_sessions
            }
            for future in as_completed(future_map):
                session = future_map[future]
                result = session['result']
                try:
                    cleanup_steps = future.result()
                except Exception as exc:
                    cleanup_steps = [{
                        'key': 'team_cleanup_failed',
                        'label': '清理失败',
                        'required': True,
                        'success': False,
                        'elapsed_ms': 0,
                        'error': str(exc),
                    }]
                result['steps'].extend(cleanup_steps)
                if result.get('room_entry') and any(step.get('key') == 'close_team' and step.get('success') for step in cleanup_steps):
                    result['room_entry']['team_closed'] = True
                if result.get('room_entry') and any(step.get('key') == 'leave_room' and step.get('success') for step in cleanup_steps):
                    result['room_entry']['left'] = True
                result['passed'] = all(step.get('success') or not step.get('required', True) for step in result.get('steps') or [])
                result['elapsed_ms'] = int((time.perf_counter() - session.get('account_started_at', time.perf_counter())) * 1000)
                cleaned += 1
                self._persist_team_room_publish_progress(task.id, session['plan'], result, '已清理')
        return cleaned

    def _cleanup_team_recruit_session_threadsafe(self, session, cleanup_reason):
        close_old_connections()
        steps = []
        started = time.perf_counter()
        try:
            self._close_business_team(
                session['base_url'],
                session['token'],
                session['server_id'],
                session['channel_id'],
            )
            steps.append({
                'key': 'close_team',
                'label': '关闭组队',
                'required': True,
                'success': True,
                'elapsed_ms': int((time.perf_counter() - started) * 1000),
                'message': cleanup_reason,
            })
        except Exception as exc:
            steps.append({
                'key': 'close_team',
                'label': '关闭组队',
                'required': True,
                'success': False,
                'elapsed_ms': int((time.perf_counter() - started) * 1000),
                'error': str(exc),
            })

        started = time.perf_counter()
        try:
            self._leave_business_room(
                session['base_url'],
                session['token'],
                session['channel_id'],
                session.get('channel_type') or -98,
                session['rid'],
            )
            steps.append({
                'key': 'leave_room',
                'label': '退出房间',
                'required': True,
                'success': True,
                'elapsed_ms': int((time.perf_counter() - started) * 1000),
            })
        except Exception as exc:
            steps.append({
                'key': 'leave_room',
                'label': '退出房间',
                'required': True,
                'success': False,
                'elapsed_ms': int((time.perf_counter() - started) * 1000),
                'error': str(exc),
            })
        close_old_connections()
        return steps

    def _run_team_recruit_account_threadsafe(self, task, base_url, server_id, plan, index, defer_keepalive=False):
        close_old_connections()
        try:
            return self._run_team_recruit_account(task, base_url, server_id, plan, index, defer_keepalive=defer_keepalive)
        finally:
            close_old_connections()

    def _run_team_recruit_account(self, task, base_url, server_id, plan, index, defer_keepalive=False):
        account_started = time.perf_counter()
        phone = str(plan.get('phone') or plan.get('account_no') or '').strip()
        config = task.config or {}
        result = {
            'index': index,
            'account_no': plan.get('account_no'),
            'phone': phone,
            'configured_user_id': plan.get('user_id'),
            'nickname': plan.get('nickname'),
            'server_id': server_id,
            'channel_id': plan.get('channel_id') or '',
            'channel_name': plan.get('channel_name') or '',
            'room_type_label': plan.get('room_type_label') or '',
            'rid': '',
            'steps': [],
            'error': '',
            'passed': False,
        }
        if not phone:
            result['error'] = '账号缺少手机号，无法登录'
            result['elapsed_ms'] = 0
            return result

        token = ''
        rid = ''
        team_published = False
        deferred_cleanup = False
        room_entered_at = None
        try:
            token, user_id = self._execute_trial_step(
                result,
                'login',
                '登录',
                lambda: self._login_business_account(base_url, phone, DEFAULT_BUSINESS_SMS_CODE, server_id),
            )
            result['user_id'] = user_id
            community_detail = self._execute_trial_step(
                result,
                'enter_server',
                '进入社区',
                lambda: self._enter_business_server_detail(base_url, token, server_id),
            )
            hall = self._extract_team_hall_context(community_detail)
            self._execute_trial_step(
                result,
                'follow_server',
                '关注社区',
                lambda: self._follow_business_server(base_url, token, server_id),
                required=False,
            )

            channel_id = str(plan.get('channel_id') or '').strip()
            if not channel_id or channel_id.upper() == 'AUTO':
                raise ValidationError('发布组队需要明确目标房间，请先选择语音房')
            room_detail = self._find_room_detail(base_url, token, server_id, channel_id) or {}
            result['channel_id'] = channel_id
            result['channel_name'] = room_detail.get('channel_name') or result['channel_name']
            result['room_type_label'] = room_detail.get('room_type_label') or result['room_type_label']

            rid = self._execute_trial_step(
                result,
                'enter_room',
                '进入房间',
                lambda: self._enter_business_room(base_url, token, server_id, channel_id),
            )
            room_entered_at = time.monotonic()
            result['rid'] = rid
            result['room_entry'] = {
                'account_no': result['account_no'],
                'phone': phone,
                'user_id': user_id,
                'server_id': server_id,
                'channel_id': channel_id,
                'channel_name': result['channel_name'],
                'room_type_label': result['room_type_label'],
                'rid': rid,
                'entered': True,
                'heartbeat': False,
                'heartbeat_rounds': 0,
                'team_published': False,
                'im_notification_sent': False,
                'team_closed': False,
                'left': False,
            }

            self._execute_trial_step(
                result,
                'heartbeat',
                '心跳保活',
                lambda: self._send_room_heartbeat(base_url, token, rid),
            )
            result['room_entry']['heartbeat'] = True

            team_context = self._execute_trial_step(
                result,
                'publish_team',
                '发布组队',
                lambda: self._publish_business_team(task, base_url, token, server_id, channel_id, plan, room_detail),
            )
            team_published = True
            result['team_context'] = self._sanitize_team_context(team_context)
            result['room_entry']['team_published'] = True
            self._persist_team_room_publish_progress(task.id, plan, result, '招募中')

            notification_payload = self._build_team_notification_payload(
                task=task,
                hall=hall,
                plan=plan,
                room_detail=room_detail,
                team_context=team_context,
                user_id=user_id,
            )
            notification_result = self._execute_trial_step(
                result,
                'im_send_notification',
                '发送组队大厅通知',
                lambda: self._run_team_notification_runner(task, base_url, phone, user_id, token, hall, notification_payload),
            )
            result['notification_result'] = {
                'send_attempts': notification_result.get('send_attempts') or 0,
                'send_request_success': notification_result.get('send_request_success') or 0,
                'target_id': hall.get('server_hall_id'),
            }
            result['room_entry']['im_notification_sent'] = True
            self._persist_team_room_publish_progress(task.id, plan, result, '通知成功')

            if defer_keepalive and config.get('team_keepalive_after_notify') is not False:
                interval = self._get_team_heartbeat_interval(config)
                duration_seconds = self._get_team_keepalive_duration(config, team_context)
                active_session = {
                    'base_url': base_url,
                    'server_id': server_id,
                    'plan': plan,
                    'result': result,
                    'token': token,
                    'rid': rid,
                    'team_context': team_context,
                    'channel_id': channel_id,
                    'channel_type': plan.get('channel_type') or room_detail.get('channel_type') or -98,
                    'account_started_at': account_started,
                    'entered_at': room_entered_at or time.monotonic(),
                    'next_heartbeat_at': (room_entered_at or time.monotonic()) + interval,
                    'deadline_at': (room_entered_at or time.monotonic()) + duration_seconds,
                    'rounds': 0,
                    'failed_heartbeats': 0,
                    'interrupted': False,
                }
                result['team_keepalive_rounds'] = 0
                result['team_keepalive_interrupted'] = False
                result['room_entry']['heartbeat_rounds'] = 0
                result['passed'] = all(step.get('success') or not step.get('required', True) for step in result['steps'])
                deferred_cleanup = True
                self._persist_team_room_publish_progress(task.id, plan, result, '保活中')
                result['_active_session'] = active_session
                return result

            keepalive_result = self._keep_team_alive_after_notification(
                task=task,
                result=result,
                token=token,
                rid=rid,
                team_context=team_context,
            )
            result['team_keepalive_rounds'] = keepalive_result['rounds']
            result['team_keepalive_interrupted'] = keepalive_result['interrupted']
            result['room_entry']['heartbeat_rounds'] = keepalive_result['rounds']
            self._persist_team_room_publish_progress(task.id, plan, result, '保活完成')

            self._execute_trial_step(
                result,
                'close_team',
                '关闭组队',
                lambda: self._close_business_team(base_url, token, server_id, channel_id),
            )
            team_published = False
            result['room_entry']['team_closed'] = True
            self._persist_team_room_publish_progress(task.id, plan, result, '已清理')
            self._execute_trial_step(
                result,
                'leave_room',
                '退出房间',
                lambda: self._leave_business_room(base_url, token, channel_id, plan.get('channel_type') or -98, rid),
            )
            result['room_entry']['left'] = True
            result['passed'] = all(step.get('success') or not step.get('required', True) for step in result['steps'])
        except Exception as exc:
            result['error'] = str(exc)
            result['passed'] = False
            self._persist_team_room_publish_progress(task.id, plan, result, '执行失败')
        finally:
            if deferred_cleanup:
                result['elapsed_ms'] = int((time.perf_counter() - account_started) * 1000)
                return result
            if token and team_published and result.get('channel_id'):
                try:
                    self._close_business_team(base_url, token, server_id, result['channel_id'])
                    if result.get('room_entry'):
                        result['room_entry']['team_closed'] = True
                except Exception:
                    logger.debug('Best-effort close team failed', exc_info=True)
            if token and rid and result.get('channel_id') and not self._step_success(result, 'leave_room'):
                try:
                    self._leave_business_room(base_url, token, result['channel_id'], plan.get('channel_type') or -98, rid)
                    if result.get('room_entry'):
                        result['room_entry']['left'] = True
                except Exception:
                    logger.debug('Best-effort leave room failed', exc_info=True)
            result['elapsed_ms'] = int((time.perf_counter() - account_started) * 1000)
            self._persist_team_room_publish_progress(task.id, plan, result, '完成' if result.get('passed') else '执行失败')
        return result

    def _persist_team_room_publish_progress(self, task_id, plan, result, stage):
        if not task_id or not result.get('channel_id'):
            return
        try:
            task = BusinessLoadTask.objects.get(id=task_id)
            metrics = dict(task.metrics or {})
            records = dict(metrics.get('team_room_publish_records') or {})
            channel_id = str(result.get('channel_id') or plan.get('channel_id') or '')
            current_record = dict(records.get(channel_id) or {})
            records[channel_id] = {
                **current_record,
                'channel_id': channel_id,
                'channel_name': result.get('channel_name') or plan.get('channel_name') or current_record.get('channel_name') or '',
                'room_type_label': result.get('room_type_label') or plan.get('room_type_label') or current_record.get('room_type_label') or '',
                'display_order': plan.get('display_order') or current_record.get('display_order'),
                'last_result': result,
                'last_published_at': current_record.get('last_published_at') or (timezone.now().isoformat() if self._step_success(result, 'publish_team') else ''),
                'passed': bool(result.get('passed')),
                'stage': stage,
                'updated_at': timezone.now().isoformat(),
            }
            metrics['team_room_publish_records'] = records
            metrics['last_team_room_progress'] = records[channel_id]
            task.metrics = metrics
            task.save(update_fields=['metrics', 'updated_at'])
        except Exception:
            logger.debug('Best-effort persist team room progress failed', exc_info=True)

    def _run_keepalive_trial_execution(self, task, base_url, server_id, account_plan, start_time, started_at):
        configured_duration = self._safe_int(task.config.get('duration_seconds'), 300)
        duration_seconds = min(max(configured_duration, 1), self.TRIAL_RUN_HARD_DURATION_LIMIT)
        heartbeat_interval = min(
            max(self._safe_int(task.config.get('heartbeat_interval_seconds'), 30), 5),
            60,
        )
        performance_samples = [self._capture_runner_performance_snapshot('start')]
        account_results = []
        room_entry_records = []

        for index, plan in enumerate(account_plan, start=1):
            result = self._prepare_keepalive_account(base_url, server_id, plan, index)
            account_results.append(result)
            if result.get('room_entry'):
                room_entry_records.append(result['room_entry'])
            performance_samples.append(self._capture_runner_performance_snapshot(f'enter_account_{index}'))

        keepalive_started = time.perf_counter()
        heartbeat_round = 0
        next_heartbeat_at = keepalive_started
        while time.perf_counter() - keepalive_started < duration_seconds:
            now = time.perf_counter()
            if now < next_heartbeat_at:
                time.sleep(min(next_heartbeat_at - now, 1))
                continue

            heartbeat_round += 1
            for result in account_results:
                if not result.get('rid') or not result.get('token'):
                    continue
                self._run_keepalive_heartbeat(base_url, result, heartbeat_round)
            performance_samples.append(self._capture_runner_performance_snapshot(f'heartbeat_round_{heartbeat_round}'))
            next_heartbeat_at += heartbeat_interval

        for result in account_results:
            if not result.get('rid') or not result.get('token'):
                continue
            self._run_keepalive_leave(base_url, result)
            if result.get('room_entry'):
                result['room_entry']['left'] = self._step_success(result, 'leave_room')

        for result in account_results:
            result['passed'] = all(step.get('success') or not step.get('required', True) for step in result['steps'])
            result['elapsed_ms'] = int((time.perf_counter() - result.get('_started_perf', start_time)) * 1000)
            result.pop('token', None)
            result.pop('_started_perf', None)

        performance_samples.append(self._capture_runner_performance_snapshot('finish'))
        summary = self._summarize_trial_account_results(account_results)
        performance = self._summarize_runner_performance(performance_samples)
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        message = (
            f'语音房在线保活试跑完成：账号 {summary["total_accounts"]} 个，'
            f'进房成功 {summary["enter_room_success"]} 个，心跳轮次 {heartbeat_round} 次，失败 {summary["failed_count"]} 个'
        )
        return {
            'mode': 'trial_run',
            'scenario_mode': 'keepalive',
            'passed': summary['failed_count'] == 0,
            'message': message,
            'started_at': started_at.isoformat(),
            'finished_at': timezone.now().isoformat(),
            'duration_ms': duration_ms,
            'safety': {
                'requested_accounts': task.account_count,
                'executed_accounts': len(account_results),
                'hard_account_limit': self.TRIAL_RUN_HARD_ACCOUNT_LIMIT,
                'configured_duration_seconds': configured_duration,
                'executed_duration_seconds': duration_seconds,
                'hard_duration_limit_seconds': self.TRIAL_RUN_HARD_DURATION_LIMIT,
                'heartbeat_interval_seconds': heartbeat_interval,
                'heartbeat_rounds': heartbeat_round,
                'leave_room_after_trial': True,
            },
            'summary': summary,
            'account_results': account_results,
            'room_entry_records': room_entry_records,
            'performance': performance,
        }

    def _run_community_activity_trial_execution(self, task, base_url, server_id, account_plan, start_time, started_at):
        config = task.config or {}
        configured_duration = self._safe_int(config.get('duration_seconds'), 300)
        duration_seconds = min(max(configured_duration, 1), self.TRIAL_RUN_HARD_DURATION_LIMIT)
        heartbeat_interval = min(max(self._safe_int(config.get('heartbeat_interval_seconds'), 30), 5), 60)
        resident_requested = max(0, self._safe_int(config.get('resident_user_count'), 0))
        transient_requested = max(0, self._safe_int(config.get('transient_user_count'), 0))
        switch_ratio = min(max(self._safe_int(config.get('transient_switch_ratio'), 55), 0), 100)
        transient_to_resident_ratio = min(max(self._safe_int(config.get('transient_to_resident_ratio'), 80), 0), 100)
        transient_stay_min_seconds = max(0, self._safe_int(config.get('transient_stay_min_seconds'), 3))
        transient_stay_max_seconds = max(transient_stay_min_seconds, self._safe_int(config.get('transient_stay_max_seconds'), 5))

        resident_plan = [item for item in account_plan if item.get('activity_role') == 'resident']
        transient_plan = [item for item in account_plan if item.get('activity_role') == 'transient']
        if not resident_plan and not transient_plan:
            resident_plan = account_plan[:resident_requested or len(account_plan)]
            transient_plan = account_plan[len(resident_plan):]
        if not transient_plan and transient_requested and len(resident_plan) > 1:
            transient_plan = resident_plan[-1:]
            resident_plan = resident_plan[:-1]

        room_pool = self._build_activity_room_pool(account_plan)
        resident_room_ids = {str(item.get('channel_id') or '') for item in resident_plan if item.get('channel_id')}
        performance_samples = [self._capture_runner_performance_snapshot('start')]
        account_results = []
        room_entry_records = []
        activity_events = []

        for index, plan in enumerate(resident_plan, start=1):
            result = self._prepare_keepalive_account(base_url, server_id, plan, index)
            result['activity_role'] = 'resident'
            result['activity_role_label'] = '固定用户'
            account_results.append(result)
            if result.get('room_entry'):
                result['room_entry']['activity_role'] = 'resident'
                result['room_entry']['activity_role_label'] = '固定用户'
                room_entry_records.append(result['room_entry'])
            performance_samples.append(self._capture_runner_performance_snapshot(f'resident_enter_{index}'))

        heartbeat_round = 0
        if resident_plan:
            heartbeat_round = 1
            for result in account_results:
                if result.get('activity_role') == 'resident' and result.get('rid') and result.get('token'):
                    self._run_keepalive_heartbeat(base_url, result, heartbeat_round)
            performance_samples.append(self._capture_runner_performance_snapshot('resident_heartbeat_1'))

        for offset, plan in enumerate(transient_plan, start=1):
            result = self._prepare_keepalive_account(base_url, server_id, plan, len(resident_plan) + offset)
            result['activity_role'] = 'transient'
            result['activity_role_label'] = '流动用户'
            switch_mode = 'leave_then_enter' if random.randint(1, 100) <= switch_ratio else 'direct_switch'
            result['transient_switch_mode'] = switch_mode
            if result.get('room_entry'):
                result['room_entry']['activity_role'] = 'transient'
                result['room_entry']['activity_role_label'] = '流动用户'
                result['room_entry']['switch_mode'] = switch_mode
                room_entry_records.append(result['room_entry'])
            self._run_transient_activity_once(
                base_url,
                server_id,
                result,
                room_pool,
                switch_mode,
                activity_events,
                resident_room_ids=resident_room_ids,
                transient_to_resident_ratio=transient_to_resident_ratio,
                transient_stay_min_seconds=transient_stay_min_seconds,
                transient_stay_max_seconds=transient_stay_max_seconds,
            )
            account_results.append(result)
            performance_samples.append(self._capture_runner_performance_snapshot(f'transient_switch_{offset}'))

        if duration_seconds > 1:
            time.sleep(min(duration_seconds, 3))

        if config.get('cleanup_after_stop') is not False:
            for result in account_results:
                if not result.get('rid') or not result.get('token'):
                    continue
                if self._step_success(result, 'leave_room') or self._step_success(result, 'transient_leave_final'):
                    continue
                self._execute_trial_step(
                    result,
                    'cleanup_leave_room',
                    '结束清场',
                    lambda result=result: self._leave_business_room(
                        base_url,
                        result['token'],
                        result.get('channel_id'),
                        result.get('channel_type') or -98,
                        result['rid'],
                    ),
                    required=False,
                )
                if result.get('room_entry'):
                    result['room_entry']['left'] = True

        for result in account_results:
            result['passed'] = all(step.get('success') or not step.get('required', True) for step in result.get('steps') or [])
            result['elapsed_ms'] = int((time.perf_counter() - result.get('_started_perf', start_time)) * 1000)
            result.pop('token', None)
            result.pop('_started_perf', None)

        performance_samples.append(self._capture_runner_performance_snapshot('finish'))
        summary = self._summarize_trial_account_results(account_results)
        summary.update({
            'resident_requested': resident_requested,
            'transient_requested': transient_requested,
            'resident_executed': len(resident_plan),
            'transient_executed': len(transient_plan),
            'resident_online': sum(1 for item in account_results if item.get('activity_role') == 'resident' and self._step_success(item, 'enter_room')),
            'transient_switches': len(activity_events),
            'occupied_room_count': len({item.get('channel_id') for item in room_entry_records if item.get('channel_id')}),
        })
        performance = self._summarize_runner_performance(performance_samples)
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        message = (
            f'社区活跃模拟试跑完成：固定用户 {summary["resident_executed"]} 个，'
            f'流动用户 {summary["transient_executed"]} 个，切房 {summary["transient_switches"]} 次，'
            f'失败 {summary["failed_count"]} 个'
        )
        return {
            'mode': 'trial_run',
            'scenario_mode': 'community_activity',
            'passed': summary['failed_count'] == 0,
            'message': message,
            'started_at': started_at.isoformat(),
            'finished_at': timezone.now().isoformat(),
            'duration_ms': duration_ms,
            'safety': {
                'requested_accounts': task.account_count,
                'executed_accounts': len(account_results),
                'hard_account_limit': self.TRIAL_RUN_HARD_ACCOUNT_LIMIT,
                'configured_duration_seconds': configured_duration,
                'executed_duration_seconds': min(duration_seconds, 3),
                'hard_duration_limit_seconds': self.TRIAL_RUN_HARD_DURATION_LIMIT,
                'heartbeat_interval_seconds': heartbeat_interval,
                'cleanup_after_stop': config.get('cleanup_after_stop') is not False,
                'transient_stay_min_seconds': transient_stay_min_seconds,
                'transient_stay_max_seconds': transient_stay_max_seconds,
            },
            'summary': summary,
            'account_results': account_results,
            'room_entry_records': room_entry_records,
            'activity_events': activity_events,
            'performance': performance,
        }

    def _build_activity_room_pool(self, account_plan):
        room_pool = []
        seen = set()
        for item in account_plan:
            channel_id = str(item.get('channel_id') or '').strip()
            if not channel_id or channel_id.upper() == 'AUTO' or channel_id in seen:
                continue
            room_pool.append({
                'channel_id': channel_id,
                'channel_name': item.get('channel_name') or f'房间 {channel_id}',
                'channel_type': item.get('channel_type') or -98,
                'room_type_label': item.get('room_type_label') or '',
            })
            seen.add(channel_id)
        return room_pool

    def _run_transient_activity_once(
        self,
        base_url,
        server_id,
        result,
        room_pool,
        switch_mode,
        activity_events,
        resident_room_ids=None,
        transient_to_resident_ratio=80,
        transient_stay_min_seconds=3,
        transient_stay_max_seconds=5,
    ):
        if not result.get('token') or not result.get('rid') or not room_pool:
            return
        current_channel_id = str(result.get('channel_id') or '')
        candidates = [room for room in room_pool if str(room.get('channel_id')) != current_channel_id]
        if not candidates:
            self._execute_trial_step(
                result,
                'transient_leave_final',
                '流动用户退房',
                lambda: self._leave_business_room(base_url, result['token'], result.get('channel_id'), result.get('channel_type') or -98, result['rid']),
                required=False,
            )
            return

        resident_room_ids = resident_room_ids or set()
        preferred_candidates = [
            room for room in candidates
            if str(room.get('channel_id') or '') in resident_room_ids
        ]
        if preferred_candidates and random.randint(1, 100) <= transient_to_resident_ratio:
            next_room = random.choice(preferred_candidates)
        else:
            next_room = random.choice(candidates)

        stay_seconds = random.randint(transient_stay_min_seconds, transient_stay_max_seconds)
        if stay_seconds:
            time.sleep(min(stay_seconds, 1))
        if switch_mode == 'leave_then_enter':
            self._execute_trial_step(
                result,
                'transient_leave_before_switch',
                '流动用户退房',
                lambda: self._leave_business_room(base_url, result['token'], result.get('channel_id'), result.get('channel_type') or -98, result['rid']),
                required=False,
            )

        new_rid = self._execute_trial_step(
            result,
            'transient_enter_next_room',
            '流动用户切房',
            lambda: self._enter_business_room(base_url, result['token'], server_id, next_room['channel_id']),
            required=False,
        )
        if new_rid:
            result['rid'] = new_rid
            result['channel_id'] = next_room['channel_id']
            result['channel_name'] = next_room.get('channel_name') or ''
            result['channel_type'] = next_room.get('channel_type') or -98
            activity_events.append({
                'account_no': result.get('account_no'),
                'phone': result.get('phone'),
                'mode': switch_mode,
                'from_channel_id': current_channel_id,
                'to_channel_id': next_room['channel_id'],
                'to_channel_name': next_room.get('channel_name') or '',
                'planned_stay_seconds': stay_seconds,
            })
            self._execute_trial_step(
                result,
                'transient_heartbeat',
                '流动用户心跳',
                lambda: self._send_room_heartbeat(base_url, result['token'], new_rid),
                required=False,
            )

    def _prepare_keepalive_account(self, base_url, server_id, plan, index):
        phone = str(plan.get('phone') or plan.get('account_no') or '').strip()
        result = {
            'index': index,
            'account_no': plan.get('account_no'),
            'phone': phone,
            'configured_user_id': plan.get('user_id'),
            'nickname': plan.get('nickname'),
            'server_id': server_id,
            'channel_id': plan.get('channel_id') or '',
            'channel_type': plan.get('channel_type') or -98,
            'channel_name': plan.get('channel_name') or '',
            'room_type_label': plan.get('room_type_label') or '',
            'rid': '',
            'steps': [],
            'error': '',
            'passed': False,
            '_started_perf': time.perf_counter(),
        }
        if not phone:
            result['error'] = '账号缺少手机号，无法登录'
            return result

        try:
            token, user_id = self._execute_trial_step(result, 'login', '登录', lambda: self._login_business_account(base_url, phone, DEFAULT_BUSINESS_SMS_CODE, server_id))
            result['token'] = token
            result['user_id'] = user_id
            channel_id = str(plan.get('channel_id') or '').strip()
            self._execute_trial_step(result, 'enter_server', '进入社区', lambda: self._enter_business_server(base_url, token, server_id))
            self._execute_trial_step(
                result,
                'follow_server',
                '关注社区',
                lambda: self._follow_business_server(base_url, token, server_id),
                required=False,
            )
            if not channel_id or channel_id.upper() == 'AUTO':
                raise ValidationError('在线保活场景需要明确的目标房间')

            rid = self._execute_trial_step(
                result,
                'enter_room',
                '进入房间',
                lambda: self._enter_business_room(base_url, token, server_id, channel_id),
            )
            result['rid'] = rid
            result['room_entry'] = {
                'account_no': result['account_no'],
                'phone': phone,
                'user_id': user_id,
                'server_id': server_id,
                'channel_id': channel_id,
                'channel_name': plan.get('channel_name') or '',
                'room_type_label': plan.get('room_type_label') or '',
                'rid': rid,
                'entered': True,
                'heartbeat': False,
                'left': False,
            }
        except Exception as exc:
            result['error'] = str(exc)
        return result

    def _run_keepalive_heartbeat(self, base_url, result, heartbeat_round):
        try:
            self._execute_trial_step(
                result,
                f'heartbeat_{heartbeat_round}',
                f'心跳#{heartbeat_round}',
                lambda: self._send_room_heartbeat(base_url, result['token'], result['rid']),
            )
            if result.get('room_entry'):
                result['room_entry']['heartbeat'] = True
                result['room_entry']['heartbeat_rounds'] = heartbeat_round
        except Exception as exc:
            result['error'] = str(exc)

    def _run_keepalive_leave(self, base_url, result):
        try:
            self._execute_trial_step(
                result,
                'leave_room',
                '离开房间',
                lambda: self._leave_business_room(base_url, result['token'], result.get('channel_id'), result.get('channel_type') or -98, result['rid']),
            )
        except Exception as exc:
            result['error'] = str(exc)

    def _safe_int(self, value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _step_success(self, result, key):
        return any(step.get('key') == key and step.get('success') for step in result.get('steps') or [])

    def _resolve_auto_trial_rooms(self, task, base_url, server_id, account_plan):
        if not any(str(item.get('channel_id') or '').upper() == 'AUTO' for item in account_plan):
            return account_plan

        probe_phone = ''
        for item in account_plan:
            probe_phone = item.get('phone') or item.get('account_no') or ''
            if probe_phone:
                break
        if not probe_phone:
            raise ValidationError('自动分配房间失败：没有可用账号手机号')

        token, _user_id = self._login_probe_account(base_url, probe_phone, DEFAULT_BUSINESS_SMS_CODE, server_id)
        rooms = self._fetch_room_preview(base_url, token, server_id, page_size=50, max_pages=2)
        if not rooms:
            raise ValidationError('自动分配房间失败：未获取到可进入的语音房')

        assignment_mode = task.config.get('room_assignment_mode', 'round_robin')
        users_per_room = max(1, int(task.config.get('users_per_room') or 1))
        resolved_plan = []
        for index, item in enumerate(account_plan):
            item = dict(item)
            if str(item.get('channel_id') or '').upper() == 'AUTO':
                if assignment_mode == 'fill_first':
                    room_index = min(index // users_per_room, len(rooms) - 1)
                else:
                    room_index = index % len(rooms)
                room = rooms[room_index]
                item.update({
                    'channel_id': room.get('channel_id'),
                    'channel_name': room.get('channel_name'),
                    'channel_type': room.get('channel_type'),
                    'channel_model': room.get('channel_model'),
                    'channel_template': room.get('channel_template'),
                    'room_type_label': room.get('room_type_label'),
                    'display_order': room.get('display_order'),
                    'sort_index_num': room.get('sort_index_num'),
                    'is_top_room': room.get('is_top_room'),
                    'room_source': room.get('room_source'),
                })
            resolved_plan.append(item)
        return resolved_plan

    def _run_trial_account(self, base_url, server_id, plan, index):
        account_started = time.perf_counter()
        phone = str(plan.get('phone') or plan.get('account_no') or '').strip()
        result = {
            'index': index,
            'account_no': plan.get('account_no'),
            'phone': phone,
            'configured_user_id': plan.get('user_id'),
            'nickname': plan.get('nickname'),
            'server_id': server_id,
            'channel_id': plan.get('channel_id') or '',
            'channel_name': plan.get('channel_name') or '',
            'room_type_label': plan.get('room_type_label') or '',
            'rid': '',
            'steps': [],
            'error': '',
            'passed': False,
        }
        if not phone:
            result['error'] = '账号缺少手机号，无法登录'
            result['elapsed_ms'] = 0
            return result

        token = ''
        rid = ''
        try:
            token, user_id = self._execute_trial_step(result, 'login', '登录', lambda: self._login_business_account(base_url, phone, DEFAULT_BUSINESS_SMS_CODE, server_id))
            result['user_id'] = user_id
            channel_id = str(plan.get('channel_id') or '').strip()
            self._execute_trial_step(result, 'enter_server', '进入社区', lambda: self._enter_business_server(base_url, token, server_id))
            self._execute_trial_step(
                result,
                'follow_server',
                '关注社区',
                lambda: self._follow_business_server(base_url, token, server_id),
                required=not bool(channel_id and channel_id.upper() != 'AUTO'),
            )

            if channel_id and channel_id.upper() != 'AUTO':
                rid = self._execute_trial_step(
                    result,
                    'enter_room',
                    '进入房间',
                    lambda: self._enter_business_room(base_url, token, server_id, channel_id),
                )
                result['rid'] = rid
                self._execute_trial_step(result, 'heartbeat', '发送心跳', lambda: self._send_room_heartbeat(base_url, token, rid))
                self._execute_trial_step(
                    result,
                    'leave_room',
                    '离开房间',
                    lambda: self._leave_business_room(base_url, token, channel_id, plan.get('channel_type') or -98, rid),
                )
                result['room_entry'] = {
                    'account_no': result['account_no'],
                    'phone': phone,
                    'user_id': user_id,
                    'server_id': server_id,
                    'channel_id': channel_id,
                    'channel_name': plan.get('channel_name') or '',
                    'room_type_label': plan.get('room_type_label') or '',
                    'rid': rid,
                    'entered': True,
                    'heartbeat': True,
                    'left': True,
                }
            else:
                self._execute_trial_step(result, 'fetch_room_list', '查询房间列表', lambda: self._fetch_room_preview(base_url, token, server_id, 20, 1))

            result['passed'] = all(step.get('success') or not step.get('required', True) for step in result['steps'])
        except Exception as exc:
            result['error'] = str(exc)
            result['passed'] = False
            if token and rid:
                try:
                    self._leave_business_room(base_url, token, result.get('channel_id'), plan.get('channel_type') or -98, rid)
                except Exception:
                    logger.debug('Best-effort trial leave room failed', exc_info=True)
        finally:
            result['elapsed_ms'] = int((time.perf_counter() - account_started) * 1000)
        return result

    def _execute_trial_step(self, result, key, label, handler, required=True):
        started = time.perf_counter()
        try:
            value = handler()
            result['steps'].append({
                'key': key,
                'label': label,
                'required': required,
                'success': True,
                'elapsed_ms': int((time.perf_counter() - started) * 1000),
            })
            return value
        except Exception as exc:
            result['steps'].append({
                'key': key,
                'label': label,
                'required': required,
                'success': False,
                'elapsed_ms': int((time.perf_counter() - started) * 1000),
                'error': str(exc),
            })
            if required:
                raise
            return None

    def _login_business_account(self, base_url, phone, sms_code, server_id=None):
        return self._login_probe_account(base_url, phone, sms_code, server_id)

    def _enter_business_server(self, base_url, token, server_id):
        response = requests.post(
            f'{base_url}/webapi/nchannel/channel/business/enterPersonalTopicServerByIdV2',
            json={'serverId': int(server_id), 'isCache': False},
            headers=self._build_business_headers(base_url, token=token, server_id=server_id),
            timeout=15,
        )
        result = self._response_json(response)
        if not result.get('success'):
            raise ValidationError(self._extract_business_error(result, '进入社区失败'))
        return True

    def _enter_business_server_detail(self, base_url, token, server_id):
        response = requests.post(
            f'{base_url}/webapi/nchannel/channel/business/enterPersonalTopicServerByIdV2',
            json={'serverId': int(server_id), 'isCache': False},
            headers=self._build_business_headers(base_url, token=token, server_id=server_id),
            timeout=15,
        )
        result = self._response_json(response)
        if not result.get('success'):
            raise ValidationError(self._extract_business_error(result, '进入社区失败'))
        return result.get('retData') or {}

    def _extract_team_hall_context(self, community_detail):
        plugin = (community_detail or {}).get('personalServerPluginGroupResp') or {}
        hall = plugin.get('personalServerChannelIndex') or {}
        server_hall_id = str(hall.get('channelId') or '').strip()
        if not server_hall_id:
            raise ValidationError('进入社区成功，但未获取到组队大厅 channelId，无法发送组队 IM 通知')
        return {
            'server_hall_id': server_hall_id,
            'hall_tx_channel_id': hall.get('txChannelId') or hall.get('txTopicId') or '',
            'server_name': community_detail.get('serverName') or community_detail.get('name') or '',
        }

    def _follow_business_server(self, base_url, token, server_id):
        current_time = int(time.time() * 1000)
        version_info = self._get_personal_server_versions(base_url, token, server_id)
        payload = {
            'serverId': int(server_id),
            'version': version_info.get('version') or current_time,
            'serverType': 1,
            'personalVersion': version_info.get('personalVersion') or current_time,
            'searchFollow': 1,
            'indexFlag': 1,
        }
        response = requests.put(
            f'{base_url}/webapi/nchannel/channel/business/joinPersonalServer',
            json=payload,
            headers=self._build_business_headers(base_url, token=token, server_id=server_id),
            timeout=15,
        )
        result = self._response_json(response)
        if result.get('success') or self._is_already_joined(self._extract_business_error(result, '')):
            return True
        raise ValidationError(self._extract_business_error(result, '关注社区失败'))

    def _get_personal_server_versions(self, base_url, token, server_id):
        try:
            response = requests.get(
                f'{base_url}/webapi/nchannel/channel/business/findMyPersonalServerMemberServer',
                params={'t': int(time.time() * 1000)},
                headers=self._build_business_headers(base_url, token=token, server_id=server_id),
                timeout=15,
            )
            result = self._response_json(response)
            if result.get('success'):
                ret_data = result.get('retData') or {}
                return {
                    'personalVersion': ret_data.get('personalVersion'),
                    'version': ret_data.get('version'),
                }
        except Exception:
            logger.debug('Fetch server versions failed, fallback to current timestamp', exc_info=True)
        return {'personalVersion': None, 'version': None}

    def _enter_business_room(self, base_url, token, server_id, channel_id):
        response = requests.get(
            f'{base_url}/webapi/nchannel/channel/business/enterPersonalTopicChannelValidate/{server_id}/{channel_id}',
            params={'timestamp': int(time.time() * 1000), 'isDirectEnter': 0, 'enterScene': 0},
            headers=self._build_business_headers(base_url, token=token, server_id=server_id),
            timeout=15,
        )
        result = self._response_json(response)
        if not result.get('success'):
            raise ValidationError(self._extract_business_error(result, '进入房间失败'))
        ret_data = result.get('retData') or {}
        heart_beat_ready = ret_data.get('heartBeatReady') or {}
        rid = heart_beat_ready.get('rId') or ret_data.get('rid')
        if not rid:
            raise ValidationError('进入房间成功但未返回 rid，无法发送心跳')
        return rid

    def _send_room_heartbeat(self, base_url, token, rid):
        response = requests.post(
            f'{base_url}/webapi/nn-status/client/channel/heartBeat',
            json={
                'rid': rid,
                'channelModel': 1,
                'casterVersion': 0,
                'roomLiveType': 'RTC',
                'extJson': '{"isMic":0,"isSpeak":1}',
            },
            headers=self._build_business_headers(base_url, token=token),
            timeout=15,
        )
        result = self._response_json(response)
        if not result.get('success'):
            raise ValidationError(self._extract_business_error(result, '心跳失败'))
        return True

    def _get_team_heartbeat_interval(self, config):
        return 30

    def _get_team_keepalive_duration(self, config, team_context):
        duration_seconds = self._safe_int((config or {}).get('duration_seconds'), 30)
        return max(1, min(duration_seconds, 86400))

    def _is_business_task_interrupted(self, task_id):
        if not task_id:
            return False
        return BusinessLoadTask.objects.filter(id=task_id, status='stopped').exists()

    def _keep_team_alive_after_notification(self, task, result, token, rid, team_context):
        config = task.config or {}
        if config.get('team_keepalive_after_notify') is False:
            result['steps'].append({
                'key': 'team_keepalive_skipped',
                'label': '通知后保活',
                'required': False,
                'success': True,
                'elapsed_ms': 0,
                'message': '已关闭通知后保活，发送通知后直接收尾',
            })
            return {'rounds': 0, 'interrupted': False}

        interval = self._get_team_heartbeat_interval(config)
        duration_seconds = self._get_team_keepalive_duration(config, team_context)
        deadline = time.time() + duration_seconds
        rounds = 0
        interrupted = False

        while time.time() < deadline:
            if self._is_business_task_interrupted(task.id):
                interrupted = True
                break

            sleep_seconds = min(interval, max(0, deadline - time.time()))
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

            if self._is_business_task_interrupted(task.id):
                interrupted = True
                break
            if time.time() > deadline:
                break

            rounds += 1
            self._execute_trial_step(
                result,
                f'team_keepalive_{rounds}',
                f'组队保活#{rounds}',
                lambda: self._send_room_heartbeat(token=token, rid=rid, base_url=(config.get('base_url') or DEFAULT_BUSINESS_BASE_URL).rstrip('/')),
            )

        if interrupted:
            result['steps'].append({
                'key': 'team_keepalive_interrupted',
                'label': '组队保活中断',
                'required': False,
                'success': True,
                'elapsed_ms': 0,
                'message': '任务已被手动中断，开始关闭组队并退房',
            })
        else:
            result['steps'].append({
                'key': 'team_keepalive_completed',
                'label': '组队保活完成',
                'required': False,
                'success': True,
                'elapsed_ms': duration_seconds * 1000,
                'message': f'已按有效期保活 {rounds} 轮',
            })

        return {'rounds': rounds, 'interrupted': interrupted}

    def _leave_business_room(self, base_url, token, channel_id, channel_type, rid):
        response = requests.post(
            f'{base_url}/webapi/nchannel/channel/business/leavePersonalServerTopicChannel',
            json={'channelType': channel_type or -98, 'channelId': channel_id, 'rid': rid},
            headers=self._build_business_headers(base_url, token=token),
            timeout=15,
        )
        result = self._response_json(response)
        if not result.get('success'):
            raise ValidationError(self._extract_business_error(result, '离开房间失败'))
        return True

    def _extract_business_error(self, result, default_message='接口返回失败'):
        message = result.get('retMsg') or result.get('message') or default_message
        if not isinstance(message, str):
            message = str(message)
        ret_code = result.get('retCode')
        return f'{message} (retCode={ret_code})' if ret_code else message

    def _publish_business_team(self, task, base_url, token, server_id, channel_id, plan, room_detail):
        config = task.config or {}
        duration_minutes = max(1, min(self._safe_int(config.get('team_duration_minutes'), 1), 60))
        expires_at = int(time.time()) + duration_minutes * 60
        message = self._render_team_message_template(
            config.get('team_message_template') or 'QAFlow_team_{{run_id}}_{{account_no}}_{{timestamp}}',
            {
                'run_id': f'task-{task.id or "new"}',
                'account_no': plan.get('account_no') or '',
                'user_id': plan.get('user_id') or '',
            },
        )
        max_members = max(1, min(self._safe_int(config.get('team_max_members_num'), 2), 99))
        payload = {
            'serverId': int(server_id),
            'channelId': int(channel_id),
            'teamDuration': expires_at,
            'teamUpMsg': message,
            'teamMaxMembersNum': max_members,
        }
        response = requests.post(
            f'{base_url}/webapi/nchannel/channel/business/addTeam',
            json=payload,
            headers=self._build_business_headers(base_url, token=token, server_id=server_id),
            timeout=15,
        )
        result = self._response_json(response)
        if not result.get('success'):
            raise ValidationError(self._extract_business_error(result, '发布组队失败'))
        ret_data = result.get('retData') or {}
        if ret_data.get('result') is not True:
            raise ValidationError('发布组队接口返回成功，但 result=false')
        return {
            'payload': payload,
            'message': message,
            'duration_minutes': duration_minutes,
            'expires_at': expires_at,
            'current_time': ret_data.get('currentTime'),
            'team_end_time': ret_data.get('teamEndTime'),
            'team_mode': config.get('team_mode') or '全部区服',
            'max_members': max_members,
            'room_detail': room_detail or {},
        }

    def _close_business_team(self, base_url, token, server_id, channel_id):
        payload = {'serverId': int(server_id), 'channelId': int(channel_id)}
        response = requests.post(
            f'{base_url}/webapi/nchannel/channel/business/closeTeam',
            json=payload,
            headers=self._build_business_headers(base_url, token=token, server_id=server_id),
            timeout=15,
        )
        result = self._response_json(response)
        if not result.get('success'):
            raise ValidationError(self._extract_business_error(result, '关闭组队失败'))
        return True

    def _find_room_detail(self, base_url, token, server_id, channel_id):
        rooms = self._fetch_room_preview(base_url, token, server_id, page_size=100, max_pages=2)
        for room in rooms:
            if str(room.get('channel_id')) == str(channel_id):
                return room
        return None

    def _render_team_message_template(self, template, context):
        values = {
            'run_id': context.get('run_id') or '',
            'account_no': context.get('account_no') or '',
            'user_id': context.get('user_id') or '',
            'timestamp': int(time.time() * 1000),
        }
        rendered = str(template or '')
        for key, value in values.items():
            rendered = rendered.replace('{{' + key + '}}', str(value))
        return rendered[:200]

    def _build_team_notification_payload(self, task, hall, plan, room_detail, team_context, user_id):
        config = task.config or {}
        raw_room = (room_detail or {}).get('raw') or {}
        channel_id = str(plan.get('channel_id') or (room_detail or {}).get('channel_id') or '')
        current_time = team_context.get('current_time') or int(time.time())
        team_card = {
            'type': 'teamRoomCard',
            'operateType': 1,
            'showMsg': 0,
            'serverId': str(plan.get('server_id') or config.get('server_id') or ''),
            'serverName': hall.get('server_name') or config.get('server_name') or '',
            'serverType': 0,
            'channelModel': (room_detail or {}).get('channel_model') or raw_room.get('channelModel') or 1,
            'channelId': int(channel_id),
            'channelType': (room_detail or {}).get('channel_type') or plan.get('channel_type') or -98,
            'txChannelId': raw_room.get('txChannelId') or raw_room.get('txTopicId') or '',
            'contentText': team_context.get('message') or '',
            'teamMode': team_context.get('team_mode') or '全部区服',
            'duration': team_context.get('expires_at'),
            'onlineMemberMax': team_context.get('max_members'),
            'teamMaxMembersNum': team_context.get('max_members'),
            'vTime': team_context.get('duration_minutes'),
            'upTime': int(time.time()),
            'tabList': [{'name': team_context.get('team_mode') or '全部区服'}],
            'userList': [],
            'currentTime': current_time,
            'refDuration': str(current_time),
            'conversationID': raw_room.get('txChannelId') or raw_room.get('txTopicId') or '',
            'teamType': 0,
        }
        return {
            'id': int(hall.get('server_hall_id')),
            'sessionId': str(hall.get('server_hall_id')),
            'bizType': 2,
            'msgType': 4,
            'notifyType': 1,
            'channelId': channel_id,
            'content': json.dumps(team_card, ensure_ascii=False),
            'needStore': False,
            'name': str(user_id or ''),
        }

    def _run_team_notification_runner(self, task, base_url, phone, user_id, token, hall, notification_payload):
        runner_path = str((task.config or {}).get('runner_path') or '').strip()
        if not runner_path:
            raise ValidationError('发布组队需要配置 IM runner 路径')
        runner = Path(runner_path)
        if not runner.exists():
            raise ValidationError(f'IM runner 不存在：{runner_path}')

        runner_config = {
            'host': base_url,
            'accounts': [{'phone': phone, 'user_id': int(user_id), 'token': token}],
            'account_count': 1,
            'target_id': int(hall.get('server_hall_id')),
            'target_type': 'group',
            'biz_type': 2,
            'message_kind': 'notification',
            'notification_payload': json.dumps(notification_payload, ensure_ascii=False),
            'notify_type': 2,
            'send_count': 1,
            'interval_ms': 500,
            'duration_seconds': 1,
            'login_interval_ms': 0,
            'join_target': True,
        }
        timeout_seconds = min(max(self._safe_int((task.config or {}).get('runner_timeout_seconds'), 120), 30), 300)
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as file:
            json.dump(runner_config, file, ensure_ascii=False)
            config_path = file.name
        try:
            completed = subprocess.run(
                [str(runner), '--qaflow-headless', config_path],
                cwd=str(runner.parent),
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                encoding='utf-8',
                errors='replace',
            )
        finally:
            try:
                os.remove(config_path)
            except OSError:
                logger.debug('Best-effort cleanup team notification config failed', exc_info=True)

        runner_result = self._parse_im_runner_result(completed.stdout, completed.stderr)
        if completed.returncode != 0 or not runner_result.get('success'):
            raise ValidationError(runner_result.get('message') or 'IM 组队通知发送失败')
        return runner_result

    def _sanitize_team_context(self, team_context):
        payload = dict((team_context or {}).get('payload') or {})
        return {
            'payload': payload,
            'message': (team_context or {}).get('message'),
            'duration_minutes': (team_context or {}).get('duration_minutes'),
            'expires_at': (team_context or {}).get('expires_at'),
            'current_time': (team_context or {}).get('current_time'),
            'team_end_time': (team_context or {}).get('team_end_time'),
            'team_mode': (team_context or {}).get('team_mode'),
            'max_members': (team_context or {}).get('max_members'),
        }

    def _is_already_joined(self, message):
        lowered = str(message or '').lower()
        keywords = ['already', '重复', '已加入', '已经加入', '已关注', '已经关注', '请勿重复']
        return any(keyword in lowered for keyword in keywords)

    def _capture_runner_performance_snapshot(self, label):
        snapshot = {
            'label': label,
            'time': timezone.now().isoformat(),
            'available': False,
        }
        if not psutil:
            snapshot['message'] = 'psutil 未安装，无法采集执行机性能'
            return snapshot
        try:
            process = psutil.Process(os.getpid())
            memory = psutil.virtual_memory()
            snapshot.update({
                'available': True,
                'cpu_percent': psutil.cpu_percent(interval=0.05),
                'memory_percent': memory.percent,
                'memory_used_mb': round(memory.used / 1024 / 1024, 2),
                'memory_available_mb': round(memory.available / 1024 / 1024, 2),
                'process_rss_mb': round(process.memory_info().rss / 1024 / 1024, 2),
            })
        except Exception as exc:
            snapshot['message'] = f'性能采集失败：{exc}'
        return snapshot

    def _summarize_runner_performance(self, samples):
        available_samples = [item for item in samples if item.get('available')]
        if not available_samples:
            return {
                'available': False,
                'samples': samples,
                'summary': {},
                'analysis': ['未采集到执行机性能数据，请确认 psutil 依赖是否可用。'],
            }

        cpu_values = [float(item.get('cpu_percent') or 0) for item in available_samples]
        memory_values = [float(item.get('memory_percent') or 0) for item in available_samples]
        rss_values = [float(item.get('process_rss_mb') or 0) for item in available_samples]
        summary = {
            'cpu_avg_percent': round(sum(cpu_values) / len(cpu_values), 2),
            'cpu_max_percent': round(max(cpu_values), 2),
            'memory_avg_percent': round(sum(memory_values) / len(memory_values), 2),
            'memory_max_percent': round(max(memory_values), 2),
            'process_rss_max_mb': round(max(rss_values), 2),
            'sample_count': len(available_samples),
        }
        analysis = []
        if summary['cpu_max_percent'] >= 85:
            analysis.append('执行期间 CPU 峰值偏高，后续放量前建议降低并发或改为异步队列执行。')
        else:
            analysis.append('执行期间 CPU 峰值处于可控范围，本次小流量试跑未观察到明显 CPU 压力。')
        if summary['memory_max_percent'] >= 85:
            analysis.append('执行机内存占用偏高，建议排查后台进程或降低账号规模。')
        else:
            analysis.append('执行机内存占用处于可控范围，当前试跑规模可以继续验证。')
        if summary['process_rss_max_mb'] >= 1024:
            analysis.append('Django 进程内存超过 1GB，建议关注长期运行后的内存回收。')
        return {
            'available': True,
            'samples': samples,
            'summary': summary,
            'analysis': analysis,
        }

    def _summarize_trial_account_results(self, account_results):
        total = len(account_results)
        counters = {
            'login_success': 0,
            'enter_server_success': 0,
            'follow_success': 0,
            'fetch_room_list_success': 0,
            'enter_room_success': 0,
            'heartbeat_success': 0,
            'leave_success': 0,
        }
        for result in account_results:
            step_map = {step.get('key'): step.get('success') for step in result.get('steps') or []}
            counters['login_success'] += 1 if step_map.get('login') else 0
            counters['enter_server_success'] += 1 if step_map.get('enter_server') else 0
            counters['follow_success'] += 1 if step_map.get('follow_server') else 0
            counters['fetch_room_list_success'] += 1 if step_map.get('fetch_room_list') else 0
            counters['enter_room_success'] += 1 if step_map.get('enter_room') else 0
            counters['heartbeat_success'] += 1 if (
                step_map.get('heartbeat')
                or any(step.get('key', '').startswith('heartbeat_') and step.get('success') for step in result.get('steps') or [])
            ) else 0
            counters['leave_success'] += 1 if step_map.get('leave_room') else 0
        passed_count = sum(1 for item in account_results if item.get('passed'))
        failed_count = total - passed_count
        return {
            'total_accounts': total,
            'passed_count': passed_count,
            'failed_count': failed_count,
            'success_rate': round((passed_count / total) * 100, 2) if total else 0,
            **counters,
        }

    def _fetch_room_preview(self, base_url, token, server_id, page_size=50, max_pages=2):
        url = f'{base_url}/webapi/nchannel/server/channel/pageQuery'
        rooms = []
        seen_channel_ids = set()
        # pageQuery only returns topList on the first page when lastSortIndex is -1.
        last_sort_index = -1

        for page_index in range(max_pages):
            payload = {
                'serverId': int(server_id),
                'lastSortIndex': last_sort_index,
                'pageSize': page_size,
            }
            response = requests.post(
                url,
                json=payload,
                headers=self._build_business_headers(base_url, token=token, server_id=server_id),
                timeout=15,
            )
            result = self._response_json(response)
            if not result.get('success'):
                message = result.get('retMsg') or result.get('message') or '房间列表接口返回失败'
                raise ValidationError(message)

            ret_data = result.get('retData') or {}
            page_rooms = self._merge_top_and_page_rooms(ret_data, page_index=page_index)
            if not page_rooms:
                break

            for raw_room in page_rooms:
                room = self._normalize_room_preview(raw_room)
                channel_id = room.get('channel_id')
                if not channel_id or channel_id in seen_channel_ids:
                    continue
                rooms.append(room)
                seen_channel_ids.add(channel_id)

            last_raw_room = page_rooms[-1]
            next_sort_index = last_raw_room.get('sortIndex') or last_raw_room.get('sortIndexNum') or last_sort_index
            if not next_sort_index or next_sort_index == last_sort_index:
                break
            last_sort_index = next_sort_index

        rooms.sort(key=lambda item: (
            0 if item.get('is_top_room') else 1,
            item.get('room_order') or 0,
        ))
        for display_index, room in enumerate(rooms, start=1):
            room['display_order'] = display_index
        return rooms

    def _find_exclusive_room_plugin(self, community_detail, raise_error=True):
        plugin_resp = (community_detail or {}).get('personalServerPluginGroupResp') or {}
        plugin_bos = plugin_resp.get('personalServerPluginBos') or {}
        groups = plugin_bos.get('personalServerPluginGroupBos') or []
        for group in groups:
            sub_plugins = group.get('subPluginInfoBos') or []
            for sub_plugin in sub_plugins:
                plugin_name = str(sub_plugin.get('pluginName') or '')
                if group.get('pluginId') == 5 or '专属房间' in plugin_name:
                    return {
                        'plugin_id': group.get('pluginId'),
                        'plugin_group_id': group.get('dbId'),
                        'plugin_group_name': group.get('name') or '',
                        'biz_id': sub_plugin.get('bizId'),
                        'plugin_name': plugin_name or '专属房间',
                    }
        if raise_error:
            raise ValidationError('该社区未配置专属房间插件，无法加载专属房列表')
        return None

    def _fetch_exclusive_room_preview(self, base_url, token, server_id, plugin, page_size=50, max_pages=2):
        biz_id = (plugin or {}).get('biz_id')
        if not biz_id:
            raise ValidationError('专属房插件信息缺少 bizId，无法加载专属房列表')

        url = f'{base_url}/webapi/nchannel/channel/business/getExclusiveRoomListV2'
        rooms = []
        seen_channel_ids = set()
        for page_no in range(1, max_pages + 1):
            payload = {
                'serverId': int(server_id),
                'pluginId': plugin.get('plugin_id') or 5,
                'dbId': plugin.get('plugin_group_id'),
                'pluginGroupId': plugin.get('plugin_group_id'),
                'bizId': biz_id,
                'no': page_no,
                'size': page_size,
                'pageNo': page_no,
                'pageSize': page_size,
            }
            response = requests.post(
                url,
                json=payload,
                headers=self._build_business_headers(base_url, token=token, server_id=server_id),
                timeout=15,
            )
            result = self._response_json(response)
            if not result.get('success'):
                message = result.get('retMsg') or result.get('message') or '专属房列表接口返回失败'
                raise ValidationError(message)

            ret_data = result.get('retData') or {}
            page_rooms = ret_data.get('list') or []
            if not page_rooms:
                break

            for source_index, raw_room in enumerate(page_rooms):
                raw_room = dict(raw_room)
                raw_room['_qaflow_room_source'] = 'exclusive'
                raw_room['_qaflow_is_exclusive_room'] = True
                raw_room['_qaflow_exclusive_plugin'] = plugin
                raw_room['_qaflow_room_order'] = (page_no - 1) * page_size + source_index + 1
                room = self._normalize_room_preview(raw_room)
                channel_id = room.get('channel_id')
                if not channel_id or channel_id in seen_channel_ids:
                    continue
                rooms.append(room)
                seen_channel_ids.add(channel_id)

            total_pages = self._safe_int(ret_data.get('pages'), 0)
            if total_pages and page_no >= total_pages:
                break

        for display_index, room in enumerate(rooms, start=1):
            room['display_order'] = display_index
        return rooms

    def _merge_top_and_page_rooms(self, ret_data, page_index=0):
        """Keep pinned rooms first, then append normal page rooms, de-duplicated by channelId."""
        merged_rooms = []
        seen_channel_ids = set()
        top_rooms = list(ret_data.get('topList') or [])
        page_rooms = list(ret_data.get('pageList') or ret_data.get('list') or [])
        room_sources = [
            *[(raw_room, True, index) for index, raw_room in enumerate(top_rooms)],
            *[(raw_room, False, index) for index, raw_room in enumerate(page_rooms)],
        ]
        for raw_room, is_top_room, source_index in room_sources:
            channel_id = raw_room.get('channelId') or raw_room.get('channel_id') or raw_room.get('id')
            channel_id_text = str(channel_id or '').strip()
            if not channel_id_text or channel_id_text in seen_channel_ids:
                continue
            raw_room = dict(raw_room)
            raw_room['_qaflow_is_top_room'] = is_top_room
            raw_room['_qaflow_room_source'] = 'topList' if is_top_room else 'pageList'
            raw_room['_qaflow_room_order'] = (
                page_index * 100000 + source_index
                if is_top_room
                else (page_index + 1) * 100000 + source_index
            )
            merged_rooms.append(raw_room)
            seen_channel_ids.add(channel_id_text)
        return merged_rooms

    def _response_json(self, response):
        response.raise_for_status()
        return json.loads(response.content.decode('utf-8'))

    def _normalize_room_preview(self, raw_room):
        channel_id = raw_room.get('channelId') or raw_room.get('channel_id') or raw_room.get('id')
        channel_name = raw_room.get('channelName') or raw_room.get('channel_name') or raw_room.get('name')
        channel_type = raw_room.get('channelType') or raw_room.get('channel_type') or -98
        channel_model = raw_room.get('channelModel') or raw_room.get('channel_model')
        channel_template = raw_room.get('channelTemplate') or raw_room.get('channel_template')
        online_count = (
            raw_room.get('voiceAudioPersonNum')
            or raw_room.get('memberNum')
            or raw_room.get('memberCount')
            or raw_room.get('onlineCount')
            or raw_room.get('currentMemberCount')
            or 0
        )
        capacity = (
            raw_room.get('onlineMemberMax')
            or raw_room.get('micNum')
            or raw_room.get('memberLimit')
            or raw_room.get('maxMemberCount')
            or raw_room.get('limitNum')
            or raw_room.get('capacity')
            or 0
        )
        return {
            'channel_id': str(channel_id or ''),
            'channel_name': channel_name or f'语音房 {channel_id}',
            # channelType is still needed by the enter-room flow, but it is not a human-friendly room category.
            'channel_type': channel_type,
            'channel_model': channel_model,
            'channel_template': channel_template,
            'room_type': channel_model or channel_template or channel_type,
            'room_type_label': self._build_room_type_label(channel_model, channel_template, channel_type),
            'online_count': online_count,
            'capacity': capacity,
            'sort_index_num': raw_room.get('sortIndexNum') or raw_room.get('sortIndex') or 0,
            'is_top_room': bool(raw_room.get('_qaflow_is_top_room')),
            'room_source': raw_room.get('_qaflow_room_source') or 'pageList',
            'room_order': raw_room.get('_qaflow_room_order') or 0,
            'raw': raw_room,
        }

    def _build_room_type_label(self, channel_model=None, channel_template=None, channel_type=None):
        model_labels = {
            1: '普通模式',
            2: '开黑模式',
            3: '麦序模式',
            '1': '普通模式',
            '2': '开黑模式',
            '3': '麦序模式',
        }
        channel_type_labels = {
            -97: '社区文字频道',
            -98: '社区语音频道',
            -99: '社区派对频道',
            '-97': '社区文字频道',
            '-98': '社区语音频道',
            '-99': '社区派对频道',
        }
        template_labels = {
            1: '派单厅模板：麦位',
            2: '派单厅模板：麦位+列表',
            '1': '派单厅模板：麦位',
            '2': '派单厅模板：麦位+列表',
        }

        parts = []
        if channel_model not in (None, ''):
            parts.append(model_labels.get(channel_model, f'模式 {channel_model}'))
        if channel_template not in (None, ''):
            parts.append(template_labels.get(channel_template, f'模板 {channel_template}'))
        if parts:
            return ' / '.join(parts)
        if channel_type not in (None, ''):
            return channel_type_labels.get(channel_type, f'频道类型 {channel_type}')
        return '未知'

    def _build_precheck_result(self, task):
        account_domains = self._get_reusable_account_domains(task.business_domain)
        queryset = BusinessAccount.objects.filter(
            environment=task.environment,
            business_domain__in=account_domains,
            status='available',
        )
        available_without_tags = queryset.count()
        for tag in task.account_tags or []:
            queryset = queryset.filter(tags__contains=[tag])
        available_count = queryset.count()
        missing_count = max(0, task.account_count - available_count)
        planned_accounts = list(queryset.order_by('last_used_at', 'id').values(
            'account_no', 'phone', 'user_id', 'nickname',
        )[:task.account_count])
        target_rooms = self._parse_target_rooms(task.config.get('target_rooms') or [])
        room_selection_mode = task.config.get('room_selection_mode', 'auto')
        plan_result = self._build_assignment_plan(task, planned_accounts, target_rooms, room_selection_mode)
        im_validation = self._validate_im_message_config(task) if task.scenario_type == 'im_message_flood' else None
        team_validation = self._validate_team_recruit_config(task, target_rooms) if task.scenario_type == 'team_recruit_publish' else None
        passed = (
            missing_count == 0
            and (im_validation is None or im_validation['passed'])
            and (team_validation is None or team_validation['passed'])
        )
        if task.scenario_type == 'im_message_flood' and im_validation and not im_validation['passed']:
            message = 'IM 参数预检查不通过：' + '；'.join(im_validation['errors'])
        elif task.scenario_type == 'team_recruit_publish' and team_validation and not team_validation['passed']:
            message = '发布组队预检查不通过：' + '；'.join(team_validation['errors'])
        elif passed:
            message = f'预检查通过：可用账号 {available_count} 个，计划使用 {task.account_count} 个'
        elif task.account_tags:
            message = (
                f'按标签 {", ".join(task.account_tags)} 筛选后账号不足，'
                f'需要 {task.account_count} 个，当前 {available_count} 个；不按标签筛选有 {available_without_tags} 个'
            )
        else:
            message = f'账号不足，需要 {task.account_count} 个，当前 {available_count} 个'

        return {
            'passed': passed,
            'message': message,
            'available_count': available_count,
            'available_without_tags': available_without_tags,
            'required_count': task.account_count,
            'missing_count': missing_count,
            'account_domains': account_domains,
            'capability_chain': task.capability_chain or [],
            'server_id': task.config.get('server_id'),
            'room_selection_mode': room_selection_mode,
            'target_rooms': target_rooms,
            'account_room_plan': plan_result['account_room_plan'],
            'plan_warnings': (
                plan_result['warnings']
                + ((im_validation or {}).get('warnings') or [])
                + ((team_validation or {}).get('warnings') or [])
            ),
            'im_target': (im_validation or {}).get('target'),
            'im_safety': (im_validation or {}).get('safety'),
            'im_errors': (im_validation or {}).get('errors') or [],
            'team_errors': (team_validation or {}).get('errors') or [],
            'team_safety': (team_validation or {}).get('safety'),
        }

    def _get_reusable_account_domains(self, business_domain):
        business_domain = business_domain or 'common'
        if business_domain == 'common':
            return ['common']
        return [business_domain, 'common']

    def _pick_available_business_account(self, task):
        account_domains = self._get_reusable_account_domains(task.business_domain)
        queryset = BusinessAccount.objects.filter(
            environment=task.environment,
            business_domain__in=account_domains,
            status='available',
        )
        for tag in task.account_tags or []:
            queryset = queryset.filter(tags__contains=[tag])
        return queryset.order_by('last_used_at', 'id').values(
            'account_no', 'phone', 'user_id', 'nickname',
        ).first()

    def _parse_target_rooms(self, raw_rooms):
        if isinstance(raw_rooms, str):
            items = []
            for line in raw_rooms.splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = [part.strip() for part in line.replace('\t', ',').split(',')]
                items.append({
                    'channel_id': parts[0] if len(parts) > 0 else '',
                    'channel_name': parts[1] if len(parts) > 1 else '',
                    'channel_type': parts[2] if len(parts) > 2 else '-98',
                })
            raw_rooms = items

        target_rooms = []
        for index, item in enumerate(raw_rooms or [], start=1):
            if isinstance(item, (str, int)):
                item = {'channel_id': str(item)}
            channel_id = str(item.get('channel_id') or item.get('channelId') or '').strip()
            if not channel_id:
                continue
            target_rooms.append({
                'channel_id': channel_id,
                'channel_name': item.get('channel_name') or item.get('channelName') or f'目标房间{index}',
                'channel_type': item.get('channel_type') or item.get('channelType') or -98,
                'channel_model': item.get('channel_model') or item.get('channelModel'),
                'channel_template': item.get('channel_template') or item.get('channelTemplate'),
                'room_type': item.get('room_type') or item.get('roomType') or item.get('channel_model') or item.get('channelModel'),
                'room_type_label': (
                    item.get('room_type_label')
                    or item.get('roomTypeLabel')
                    or self._build_room_type_label(
                        item.get('channel_model') or item.get('channelModel'),
                        item.get('channel_template') or item.get('channelTemplate'),
                        item.get('channel_type') or item.get('channelType') or -98,
                    )
                ),
                'display_order': item.get('display_order') or item.get('displayOrder') or index,
                'sort_index_num': item.get('sort_index_num') or item.get('sortIndexNum') or item.get('sortIndex') or 0,
                'is_top_room': bool(item.get('is_top_room') or item.get('isTopRoom')),
                'room_source': item.get('room_source') or item.get('roomSource') or '',
                'room_order': item.get('room_order') or item.get('roomOrder') or index,
            })
        return target_rooms

    def _build_assignment_plan(self, task, planned_accounts, target_rooms, room_selection_mode):
        if task.scenario_type == 'im_message_flood':
            return self._build_im_assignment_plan(task, planned_accounts)

        requires_room = any(item.get('key') == 'enter_room' for item in task.capability_chain or [])
        warnings = []
        if requires_room and room_selection_mode == 'manual' and not target_rooms:
            warnings.append('当前场景需要进房，但未指定目标房间；后续真实执行时会退回为自动拉取房间列表。')
        if requires_room and room_selection_mode == 'auto':
            warnings.append('目标房间为自动模式：真实执行时将通过 pageQuery 使用 sortIndexNum 游标拉取，并按 channelId 去重。')

        account_room_plan = []
        if not requires_room:
            for account in planned_accounts:
                account_room_plan.append({
                    'account_no': account.get('account_no'),
                    'phone': account.get('phone'),
                    'user_id': account.get('user_id'),
                    'nickname': account.get('nickname'),
                    'server_id': task.config.get('server_id'),
                    'channel_id': '',
                    'channel_name': '无需进房',
                    'status': 'planned',
                })
            account_room_plan = self._annotate_community_activity_roles(task, account_room_plan)
            return {'account_room_plan': account_room_plan, 'warnings': warnings}

        if not target_rooms:
            for account in planned_accounts:
                account_room_plan.append({
                    'account_no': account.get('account_no'),
                    'phone': account.get('phone'),
                    'user_id': account.get('user_id'),
                    'nickname': account.get('nickname'),
                    'server_id': task.config.get('server_id'),
                    'channel_id': 'AUTO',
                    'channel_name': '运行时自动分配',
                    'channel_type': -98,
                    'room_type_label': '运行时自动识别',
                    'status': 'planned',
                })
            account_room_plan = self._annotate_community_activity_roles(task, account_room_plan)
            return {'account_room_plan': account_room_plan, 'warnings': warnings}

        assignment_mode = task.config.get('room_assignment_mode', 'round_robin')
        users_per_room = max(1, int(task.config.get('users_per_room') or 1))
        for index, account in enumerate(planned_accounts):
            if assignment_mode == 'fill_first':
                room_index = min(index // users_per_room, len(target_rooms) - 1)
            else:
                room_index = index % len(target_rooms)
            room = target_rooms[room_index]
            account_room_plan.append({
                'account_no': account.get('account_no'),
                'phone': account.get('phone'),
                'user_id': account.get('user_id'),
                'nickname': account.get('nickname'),
                'server_id': task.config.get('server_id'),
                'channel_id': room['channel_id'],
                'channel_name': room['channel_name'],
                'channel_type': room['channel_type'],
                'channel_model': room.get('channel_model'),
                'channel_template': room.get('channel_template'),
                'room_type': room.get('room_type'),
                'room_type_label': room.get('room_type_label'),
                'display_order': room.get('display_order'),
                'sort_index_num': room.get('sort_index_num'),
                'is_top_room': room.get('is_top_room'),
                'room_source': room.get('room_source'),
                'room_order': room.get('room_order'),
                'status': 'planned',
            })
        account_room_plan = self._annotate_community_activity_roles(task, account_room_plan)
        return {'account_room_plan': account_room_plan, 'warnings': warnings}

    def _annotate_community_activity_roles(self, task, account_room_plan):
        if task.scenario_type != 'community_activity_simulation':
            return account_room_plan
        total_accounts = len(account_room_plan)
        configured_resident_count = max(0, self._safe_int(task.config.get('resident_user_count'), 0))
        configured_transient_count = max(0, self._safe_int(task.config.get('transient_user_count'), 0))
        configured_total = configured_resident_count + configured_transient_count
        if configured_total and configured_total > total_accounts:
            resident_count = round(total_accounts * configured_resident_count / configured_total)
            if configured_resident_count and resident_count == 0:
                resident_count = 1
            if configured_transient_count and resident_count >= total_accounts and total_accounts > 1:
                resident_count = total_accounts - 1
        else:
            resident_count = min(configured_resident_count, total_accounts)
        for index, item in enumerate(account_room_plan):
            role = 'resident' if index < resident_count else 'transient'
            item['activity_role'] = role
            item['activity_role_label'] = '固定用户' if role == 'resident' else '流动用户'
        return account_room_plan

    def _build_im_assignment_plan(self, task, planned_accounts):
        config = task.config or {}
        target = self._build_im_target(config)
        warnings = []
        if not config.get('real_traffic_enabled'):
            warnings.append('当前为 IM 预演模式：只生成账号、目标和消息计划，不会产生真实刷屏流量。')
        if self._requires_im_business_room_context(target):
            warnings.append('房间类 IM 目标会先执行真实业务入场：登录账号、进入社区、进入房间，然后再调用 IM runner 发送消息。')

        account_room_plan = []
        for index, account in enumerate(planned_accounts, start=1):
            account_no = account.get('account_no') or ''
            account_room_plan.append({
                'account_no': account_no,
                'phone': account.get('phone'),
                'user_id': account.get('user_id'),
                'nickname': account.get('nickname'),
                'server_id': config.get('server_id'),
                'channel_id': target['target_id'],
                'channel_name': target['target_name'],
                'channel_type': config.get('channel_type') or -98,
                'room_type_label': target['target_type_label'],
                'status': 'planned',
                'im_target_type': target['target_type'],
                'im_target_type_label': target['target_type_label'],
                'im_target_id': target['target_id'],
                'message_preview': self._render_im_message_template(
                    config.get('message_template'),
                    {
                        'run_id': f'task-{task.id or "new"}',
                        'account_no': account_no,
                        'user_id': account.get('user_id') or '',
                        'sequence': index,
                    },
                ),
                'interval_ms': self._safe_int(config.get('interval_ms'), 1000),
            })
        return {'account_room_plan': account_room_plan, 'warnings': warnings}

    def _build_im_target(self, config):
        target_type = str(config.get('target_type') or 'room').strip()
        target_def = self.IM_TARGET_TYPES.get(target_type) or self.IM_TARGET_TYPES['room']
        selected_room = None
        if target_type in ('room', 'party'):
            target_rooms = self._parse_target_rooms(config.get('target_rooms') or [])
            selected_room = target_rooms[0] if target_rooms else None
        target_id_value = config.get('target_id')
        if not target_id_value and selected_room:
            target_id_value = selected_room.get('channel_id')
        target_id = str(target_id_value or '').strip()
        target_name = str(config.get('target_name') or (selected_room or {}).get('channel_name') or '').strip() or (
            f'{target_def["label"]} {target_id}' if target_id else target_def['label']
        )
        return {
            'target_type': target_type if target_type in self.IM_TARGET_TYPES else 'room',
            'raw_target_type': target_type,
            'target_type_label': target_def['label'],
            'target_id': target_id,
            'target_name': target_name,
            'biz_type': self._safe_int(config.get('biz_type'), target_def['biz_type']),
        }

    def _validate_team_recruit_config(self, task, target_rooms):
        config = task.config or {}
        errors = []
        warnings = []
        duration_minutes = self._safe_int(config.get('team_duration_minutes'), 1)
        duration_seconds = self._safe_int(config.get('duration_seconds'), 30)
        max_members = self._safe_int(config.get('team_max_members_num'), 2)
        heartbeat_interval = self._get_team_heartbeat_interval(config)
        keepalive_after_notify = config.get('team_keepalive_after_notify') is not False

        if not config.get('server_id'):
            errors.append('请选择目标社区')
        if not target_rooms:
            errors.append('请选择发布组队所在的语音房')
        if duration_minutes < 1 or duration_minutes > 60:
            errors.append('组队有效期需要在 1-60 分钟之间')
        if max_members < 1 or max_members > 99:
            errors.append('组队人数上限需要在 1-99 人之间')
        if not str(config.get('team_message_template') or '').strip():
            errors.append('请填写组队文案模板')

        if not config.get('real_traffic_enabled'):
            warnings.append('真实发送未开启：当前只适合做配置检查，不会完整验证发布组队 IM 通知链路。')
        else:
            runner_path = str(config.get('runner_path') or '').strip()
            if not runner_path:
                errors.append('真实发送需要配置 IM runner 路径')
            elif not Path(runner_path).exists():
                errors.append(f'IM runner 不存在：{runner_path}')

        return {
            'passed': not errors,
            'errors': errors,
            'warnings': warnings,
            'safety': {
                'close_team_after_trial': True,
                'leave_room_after_trial': True,
                'keepalive_after_notify': keepalive_after_notify,
                'heartbeat_interval_seconds': heartbeat_interval,
                'max_accounts_per_trial': self.TRIAL_RUN_HARD_ACCOUNT_LIMIT,
                'duration_minutes': duration_minutes,
                'keepalive_duration_seconds': duration_seconds,
                'max_members': max_members,
            },
        }

    def _normalize_team_room_publish_overrides(self, data):
        overrides = {}
        message_template = str(data.get('team_message_template') or '').strip()
        team_mode = str(data.get('team_mode') or '').strip()
        duration = self._safe_int(data.get('team_duration_minutes'), None)
        max_members = self._safe_int(data.get('team_max_members_num'), None)

        if message_template:
            overrides['team_message_template'] = message_template
        if team_mode:
            overrides['team_mode'] = team_mode
        if 'team_keepalive_after_notify' in data:
            overrides['team_keepalive_after_notify'] = data.get('team_keepalive_after_notify') is not False
        if duration is not None:
            overrides['team_duration_minutes'] = max(1, min(duration, 60))
        if max_members is not None:
            overrides['team_max_members_num'] = max(1, min(max_members, 99))
        return overrides

    def _validate_im_message_config(self, task):
        config = task.config or {}
        target = self._build_im_target(config)
        errors = []
        warnings = []
        target_id = target['target_id']
        interval_ms = self._safe_int(config.get('interval_ms'), 1000)
        duration_seconds = self._safe_int(config.get('duration_seconds'), 30)

        if target.get('raw_target_type') not in self.IM_TARGET_TYPES:
            errors.append('IM 目标类型不支持，请选择单聊、群聊、语音房或派对房。')
        if not target_id and self._requires_im_business_room_context(target):
            errors.append('请选择 IM 刷屏目标房间，系统会自动使用房间 ID 作为 IM 目标。')
        elif not target_id:
            errors.append('请填写 IM 目标 ID，例如群 ID、房间 ID 或接收用户 ID。')
        elif not re.fullmatch(r'\d+', target_id):
            errors.append('IM 目标 ID 只能填写纯数字。')
        if interval_ms < self.IM_SAFE_MIN_INTERVAL_MS:
            errors.append(f'发送间隔不能低于 {self.IM_SAFE_MIN_INTERVAL_MS}ms，避免误刷过快。')
        if self._requires_im_business_room_context(target) and not config.get('server_id'):
            errors.append('房间类 IM 目标需要配置社区 serverId，否则无法按真实业务链路先进入社区和房间。')
        if task.account_count > self.IM_SAFE_ACCOUNT_WARN_LIMIT:
            warnings.append(
                f'账号数超过 {self.IM_SAFE_ACCOUNT_WARN_LIMIT} 个，建议先用 1-5 个账号完成小流量验证。'
            )
        if duration_seconds > self.IM_SAFE_DURATION_LIMIT:
            warnings.append(f'持续时间超过 {self.IM_SAFE_DURATION_LIMIT}s，真实执行时会被安全策略截断。')
        if not config.get('real_traffic_enabled'):
            warnings.append('真实发送开关未开启，开始试跑时只做计划预演和参数校验。')

        return {
            'passed': not errors,
            'errors': errors,
            'warnings': warnings,
            'target': target,
            'safety': {
                'min_interval_ms': self.IM_SAFE_MIN_INTERVAL_MS,
                'duration_limit_seconds': self.IM_SAFE_DURATION_LIMIT,
                'account_warn_limit': self.IM_SAFE_ACCOUNT_WARN_LIMIT,
                'runner_status': config.get('runner_status') or 'cli_adapter',
            },
        }

    def _render_im_message_template(self, template, context):
        template = template or 'QAFlow_IM_{{run_id}}_{{account_no}}_{{sequence}}_{{timestamp}}'
        values = {
            'run_id': context.get('run_id') or '',
            'account_no': context.get('account_no') or '',
            'user_id': context.get('user_id') or '',
            'sequence': context.get('sequence') or 1,
            'timestamp': int(time.time() * 1000),
        }
        rendered = str(template)
        for key, value in values.items():
            rendered = rendered.replace('{{' + key + '}}', str(value))
        return rendered[:500]

    def _run_im_message_trial_execution(self, task, precheck, account_limit, start_time, started_at):
        config = task.config or {}
        target = precheck.get('im_target') or self._build_im_target(config)
        account_plan = list(precheck.get('account_room_plan') or [])[:account_limit]
        if config.get('real_traffic_enabled'):
            return self._run_im_cli_trial_execution(task, config, target, account_plan, start_time, started_at)

        performance_samples = [self._capture_runner_performance_snapshot('start')]
        account_results = []

        for index, plan in enumerate(account_plan, start=1):
            started = time.perf_counter()
            message_preview = plan.get('message_preview') or self._render_im_message_template(
                config.get('message_template'),
                {
                    'run_id': f'task-{task.id or "new"}',
                    'account_no': plan.get('account_no') or '',
                    'user_id': plan.get('user_id') or '',
                    'sequence': index,
                },
            )
            account_results.append({
                'index': index,
                'account_no': plan.get('account_no'),
                'phone': plan.get('phone'),
                'configured_user_id': plan.get('user_id'),
                'nickname': plan.get('nickname'),
                'channel_id': target.get('target_id'),
                'channel_name': target.get('target_name'),
                'room_type_label': target.get('target_type_label'),
                'message_preview': message_preview,
                'steps': [
                    {
                        'key': 'im_plan_validate',
                        'label': 'IM 参数校验',
                        'required': True,
                        'success': True,
                        'elapsed_ms': int((time.perf_counter() - started) * 1000),
                    },
                    {
                        'key': 'im_plan_preview',
                        'label': '生成 IM 发送预演',
                        'required': False,
                        'success': True,
                        'elapsed_ms': 0,
                    },
                ],
                'error': '',
                'passed': True,
                'elapsed_ms': int((time.perf_counter() - started) * 1000),
            })
            performance_samples.append(self._capture_runner_performance_snapshot(f'im_plan_account_{index}'))

        performance_samples.append(self._capture_runner_performance_snapshot('finish'))
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        performance = self._summarize_runner_performance(performance_samples)
        return {
            'mode': 'trial_run',
            'scenario_mode': 'im_message_flood_plan',
            'passed': True,
            'message': (
                f'IM 刷屏试跑预演完成：账号 {len(account_results)} 个，'
                f'目标 {target.get("target_type_label")} {target.get("target_id")}；未产生真实 IM 流量'
            ),
            'started_at': started_at.isoformat(),
            'finished_at': timezone.now().isoformat(),
            'duration_ms': duration_ms,
            'safety': {
                'requested_accounts': task.account_count,
                'executed_accounts': len(account_results),
                'hard_account_limit': self.TRIAL_RUN_HARD_ACCOUNT_LIMIT,
                'real_traffic': False,
                'runner_status': config.get('runner_status') or 'cli_adapter',
                'interval_ms': self._safe_int(config.get('interval_ms'), 1000),
                'duration_seconds': self._safe_int(config.get('duration_seconds'), 30),
            },
            'summary': {
                'total_accounts': len(account_results),
                'enter_room_success': 0,
                'heartbeat_success': 0,
                'failed_count': 0,
                'success_rate': 100 if account_results else 0,
                'real_send_count': 0,
                'planned_message_count': len(account_results),
            },
            'account_results': account_results,
            'room_entry_records': [],
            'im_message_plan': account_plan,
            'im_target': target,
            'performance': performance,
        }

    def _run_im_cli_trial_execution(self, task, config, target, account_plan, start_time, started_at):
        runner_path = str(config.get('runner_path') or '').strip()
        if not runner_path:
            raise ValidationError('已开启真实 IM 发送，但未配置 runner_path')
        runner = Path(runner_path)
        if not runner.exists():
            raise ValidationError(f'IM runner 不存在：{runner_path}')

        phones = [
            str(item.get('phone') or item.get('account_no') or '').strip()
            for item in account_plan
            if str(item.get('phone') or item.get('account_no') or '').strip()
        ]
        if not phones:
            raise ValidationError('没有可用于 IM 发送的账号手机号')

        timeout_seconds = min(max(self._safe_int(config.get('runner_timeout_seconds'), 120), 30), 300)
        base_url = (config.get('base_url') or DEFAULT_BUSINESS_BASE_URL).rstrip('/')
        business_context_results = []
        room_entry_records = []
        requires_business_room_context = self._requires_im_business_room_context(target)
        if requires_business_room_context:
            business_context_results, room_entry_records = self._prepare_im_business_room_context(
                base_url=base_url,
                server_id=config.get('server_id'),
                target=target,
                account_plan=account_plan,
            )
            if any(not item.get('passed') for item in business_context_results):
                performance = self._summarize_runner_performance([
                    self._capture_runner_performance_snapshot('business_context_failed')
                ])
                account_results = self._scrub_business_context_results(business_context_results)
                summary = {
                    **self._summarize_trial_account_results(account_results),
                    'real_send_count': 0,
                    'send_attempts': 0,
                }
                return {
                    'mode': 'trial_run',
                    'scenario_mode': 'im_message_flood_business_context',
                    'passed': False,
                    'message': (
                        f'IM 真实小流量试跑失败：业务入场未完成，'
                        f'进房成功 {summary.get("enter_room_success", 0)}/{summary.get("total_accounts", 0)}'
                    ),
                    'started_at': started_at.isoformat(),
                    'finished_at': timezone.now().isoformat(),
                    'duration_ms': int((time.perf_counter() - start_time) * 1000),
                    'safety': {
                        'requested_accounts': task.account_count,
                        'executed_accounts': len(account_results),
                        'hard_account_limit': self.TRIAL_RUN_HARD_ACCOUNT_LIMIT,
                        'real_traffic': True,
                        'business_context_required': True,
                        'runner_called': False,
                    },
                    'summary': summary,
                    'account_results': account_results,
                    'room_entry_records': room_entry_records,
                    'im_message_plan': account_plan,
                    'im_target': target,
                    'performance': performance,
                }

        runner_config = {
            'host': base_url,
            'phones': phones,
            'accounts': self._build_im_runner_accounts(account_plan, business_context_results),
            'account_count': len(phones),
            'target_id': int(target.get('target_id')),
            'target_type': target.get('target_type') or 'room',
            'biz_type': int(target.get('biz_type') or 5),
            'message_template': config.get('message_template') or 'QAFlow_IM_{{run_id}}_{{account_no}}_{{sequence}}_{{timestamp}}',
            'interval_ms': self._safe_int(config.get('interval_ms'), 1000),
            'duration_seconds': self._safe_int(config.get('duration_seconds'), 10),
            'login_interval_ms': self._safe_int(config.get('login_interval_ms'), 100),
            'join_target': True,
        }
        runner_config_debug = self._sanitize_im_runner_config_for_debug(runner_config)
        logger.info(
            'Starting IM CLI trial task_id=%s runner=%s config=%s',
            task.id,
            runner_path,
            json.dumps(runner_config_debug, ensure_ascii=False),
        )

        performance_samples = [self._capture_runner_performance_snapshot('start')]
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as file:
            json.dump(runner_config, file, ensure_ascii=False)
            config_path = file.name

        try:
            completed = subprocess.run(
                [str(runner), '--qaflow-headless', config_path],
                cwd=str(runner.parent),
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                encoding='utf-8',
                errors='replace',
            )
        finally:
            try:
                os.remove(config_path)
            except OSError:
                logger.debug('Best-effort cleanup IM runner config failed', exc_info=True)
            if business_context_results:
                self._cleanup_im_business_room_context(base_url, business_context_results)

        performance_samples.append(self._capture_runner_performance_snapshot('finish'))
        logger.info(
            'Finished IM CLI trial task_id=%s returncode=%s stdout_tail=%s stderr_tail=%s',
            task.id,
            completed.returncode,
            (completed.stdout or '')[-1000:],
            (completed.stderr or '')[-1000:],
        )
        runner_result = self._parse_im_runner_result(completed.stdout, completed.stderr)
        runner_account_results = self._normalize_im_runner_accounts(runner_result.get('account_results') or [])
        account_results = self._merge_im_business_and_runner_results(
            business_context_results,
            runner_account_results,
        )
        business_summary = self._summarize_trial_account_results(account_results) if business_context_results else {}
        summary = {
            'total_accounts': runner_result.get('executed_accounts') or len(account_results),
            'enter_room_success': business_summary.get('enter_room_success', 0),
            'heartbeat_success': 0,
            'failed_count': sum(1 for item in account_results if not item.get('passed')),
            'success_rate': self._calculate_success_rate(
                runner_result.get('send_request_success') or 0,
                runner_result.get('send_attempts') or 0,
            ),
            'real_send_count': runner_result.get('send_request_success') or 0,
            'send_attempts': runner_result.get('send_attempts') or 0,
        }
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        passed = completed.returncode == 0 and bool(runner_result.get('success'))
        message = runner_result.get('message') or (
            f'IM 真实小流量试跑完成：发送请求成功 {summary["real_send_count"]}/{summary["send_attempts"]}'
        )
        return {
            'mode': 'trial_run',
            'scenario_mode': 'im_message_flood_cli',
            'passed': passed,
            'message': message,
            'started_at': started_at.isoformat(),
            'finished_at': timezone.now().isoformat(),
            'duration_ms': duration_ms,
            'safety': {
                'requested_accounts': task.account_count,
                'executed_accounts': len(account_results),
                'hard_account_limit': self.TRIAL_RUN_HARD_ACCOUNT_LIMIT,
                'real_traffic': True,
                'runner_path': runner_path,
                'runner_returncode': completed.returncode,
                'interval_ms': runner_config['interval_ms'],
                'duration_seconds': runner_config['duration_seconds'],
                'business_context_required': requires_business_room_context,
                'runner_called': True,
            },
            'summary': summary,
            'account_results': account_results,
            'room_entry_records': room_entry_records,
            'im_message_plan': account_plan,
            'im_target': target,
            'runner_config_debug': runner_config_debug,
            'runner_stdout_tail': (completed.stdout or '')[-4000:],
            'runner_stderr_tail': (completed.stderr or '')[-4000:],
            'runner_result': runner_result,
            'performance': self._summarize_runner_performance(performance_samples),
        }

    def _parse_im_runner_result(self, stdout, stderr):
        marker = 'QAFLOW_RESULT_JSON='
        for line in reversed((stdout or '').splitlines()):
            if line.startswith(marker):
                try:
                    return json.loads(line[len(marker):])
                except json.JSONDecodeError as exc:
                    raise ValidationError(f'IM runner 结果 JSON 解析失败：{exc}') from exc
        raise ValidationError(f'IM runner 未输出结构化结果：{(stderr or stdout or "")[-1000:]}')

    def _normalize_im_runner_accounts(self, raw_accounts):
        results = []
        for index, item in enumerate(raw_accounts, start=1):
            failed = bool(item.get('error')) or not bool(item.get('connected'))
            send_attempts = item.get('send_attempts') or 0
            send_success = item.get('send_request_success') or 0
            results.append({
                'index': index,
                'account_no': item.get('account_no') or item.get('phone') or '',
                'phone': item.get('phone') or '',
                'configured_user_id': item.get('user_id') or '',
                'user_id': item.get('user_id') or '',
                'channel_id': '',
                'channel_name': '',
                'room_type_label': 'IM',
                'message_preview': '',
                'steps': [
                    {
                        'key': 'im_connect_login',
                        'label': 'IM 登录建连',
                        'required': True,
                        'success': bool(item.get('connected')),
                        'elapsed_ms': 0,
                    },
                    {
                        'key': 'im_send_message',
                        'label': '发送 IM 消息',
                        'required': True,
                        'success': send_attempts > 0 and send_attempts == send_success,
                        'elapsed_ms': 0,
                    },
                ],
                'send_attempts': send_attempts,
                'send_request_success': send_success,
                'error': item.get('error') or '',
                'passed': not failed and send_attempts > 0 and send_attempts == send_success,
                'elapsed_ms': 0,
            })
        return results

    def _build_im_runner_accounts(self, account_plan, business_context_results):
        context_by_phone = {
            str(item.get('phone') or item.get('account_no') or ''): item
            for item in business_context_results or []
        }
        accounts = []
        for item in account_plan:
            phone = str(item.get('phone') or item.get('account_no') or '').strip()
            if not phone:
                continue
            context = context_by_phone.get(phone) or {}
            account = {'phone': phone}
            if context.get('user_id') and context.get('token'):
                account.update({
                    'user_id': context.get('user_id'),
                    'token': context.get('token'),
                })
            accounts.append(account)
        return accounts

    def _sanitize_im_runner_config_for_debug(self, runner_config):
        def mask_phone(value):
            value = str(value or '').strip()
            if len(value) <= 4:
                return '***' if value else ''
            return f'***{value[-4:]}'

        def mask_token(value):
            value = str(value or '').strip()
            if not value:
                return ''
            return f'{value[:8]}...len={len(value)}'

        debug_config = dict(runner_config or {})
        debug_config['phones'] = [mask_phone(item) for item in debug_config.get('phones') or []]
        debug_accounts = []
        for item in debug_config.get('accounts') or []:
            debug_accounts.append({
                'phone': mask_phone(item.get('phone')),
                'user_id': item.get('user_id') or '',
                'token': mask_token(item.get('token')),
                'has_token': bool(item.get('token')),
            })
        debug_config['accounts'] = debug_accounts
        return debug_config

    def _requires_im_business_room_context(self, target):
        return (target or {}).get('target_type') in ('room', 'party')

    def _prepare_im_business_room_context(self, base_url, server_id, target, account_plan):
        if not server_id:
            raise ValidationError('房间类 IM 目标缺少 server_id，无法进入社区')
        account_results = []
        room_entry_records = []
        channel_id = str(target.get('target_id') or '').strip()
        channel_name = target.get('target_name') or target.get('target_type_label') or 'IM 目标房间'
        for index, plan in enumerate(account_plan, start=1):
            result = {
                'index': index,
                'account_no': plan.get('account_no'),
                'phone': str(plan.get('phone') or plan.get('account_no') or '').strip(),
                'configured_user_id': plan.get('user_id'),
                'nickname': plan.get('nickname'),
                'server_id': server_id,
                'channel_id': channel_id,
                'channel_name': channel_name,
                'channel_type': plan.get('channel_type') or -98,
                'room_type_label': target.get('target_type_label') or 'IM',
                'rid': '',
                'steps': [],
                'error': '',
                'passed': False,
                '_started_perf': time.perf_counter(),
            }
            if not result['phone']:
                result['error'] = '账号缺少手机号，无法登录'
                result['elapsed_ms'] = 0
                account_results.append(result)
                continue

            try:
                token, user_id = self._execute_trial_step(
                    result,
                    'login',
                    '登录',
                    lambda phone=result['phone']: self._login_business_account(base_url, phone, DEFAULT_BUSINESS_SMS_CODE, server_id),
                )
                result['token'] = token
                result['user_id'] = user_id
                self._execute_trial_step(
                    result,
                    'enter_server',
                    '进入社区',
                    lambda token=token: self._enter_business_server(base_url, token, server_id),
                )
                self._execute_trial_step(
                    result,
                    'follow_server',
                    '关注社区',
                    lambda token=token: self._follow_business_server(base_url, token, server_id),
                    required=False,
                )
                rid = self._execute_trial_step(
                    result,
                    'enter_room',
                    '进入房间',
                    lambda token=token: self._enter_business_room(base_url, token, server_id, channel_id),
                )
                result['rid'] = rid
                result['room_entry'] = {
                    'account_no': result['account_no'],
                    'phone': result['phone'],
                    'user_id': user_id,
                    'server_id': server_id,
                    'channel_id': channel_id,
                    'channel_name': channel_name,
                    'room_type_label': target.get('target_type_label') or '',
                    'rid': rid,
                    'entered': True,
                    'heartbeat': False,
                    'left': False,
                }
                room_entry_records.append(result['room_entry'])
                result['passed'] = all(step.get('success') or not step.get('required', True) for step in result['steps'])
            except Exception as exc:
                result['error'] = str(exc)
                result['passed'] = False
            finally:
                result['elapsed_ms'] = int((time.perf_counter() - result.get('_started_perf', time.perf_counter())) * 1000)
            account_results.append(result)
        return account_results, room_entry_records

    def _cleanup_im_business_room_context(self, base_url, account_results):
        for result in account_results:
            token = result.get('token')
            rid = result.get('rid')
            if not token or not rid:
                continue
            try:
                self._leave_business_room(
                    base_url,
                    token,
                    result.get('channel_id'),
                    result.get('channel_type') or -98,
                    rid,
                )
                if result.get('room_entry'):
                    result['room_entry']['left'] = True
            except Exception:
                logger.debug('Best-effort IM business context leave room failed', exc_info=True)

    def _scrub_business_context_results(self, account_results):
        scrubbed = []
        for item in account_results:
            item = dict(item)
            item.pop('token', None)
            item.pop('_started_perf', None)
            scrubbed.append(item)
        return scrubbed

    def _merge_im_business_and_runner_results(self, business_results, runner_results):
        if not business_results:
            return runner_results
        runner_by_phone = {
            str(item.get('phone') or item.get('account_no') or ''): item
            for item in runner_results
        }
        merged = []
        for business in self._scrub_business_context_results(business_results):
            runner = runner_by_phone.get(str(business.get('phone') or business.get('account_no') or ''))
            if runner:
                business['steps'] = list(business.get('steps') or []) + list(runner.get('steps') or [])
                business['send_attempts'] = runner.get('send_attempts') or 0
                business['send_request_success'] = runner.get('send_request_success') or 0
                if runner.get('error'):
                    business['error'] = runner.get('error')
                business['passed'] = bool(business.get('passed')) and bool(runner.get('passed'))
            else:
                business['steps'] = list(business.get('steps') or []) + [{
                    'key': 'im_send_message',
                    'label': '发送 IM 消息',
                    'required': True,
                    'success': False,
                    'elapsed_ms': 0,
                    'error': 'IM runner 未返回该账号结果',
                }]
                business['send_attempts'] = 0
                business['send_request_success'] = 0
                business['passed'] = False
            merged.append(business)
        return merged

    def _calculate_success_rate(self, success_count, total_count):
        if not total_count:
            return 0
        return round(success_count * 100 / total_count, 2)

    def _append_task_log(self, task, message, payload):
        logs = list(task.logs or [])
        logs.append({
            'time': timezone.now().isoformat(),
            'message': message,
            'payload': payload,
        })
        return logs[-200:]


class DataFactoryViewSet(viewsets.ModelViewSet):
    """数据工厂视图集"""
    queryset = DataFactoryRecord.objects.all()
    serializer_class = DataFactoryRecordSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = DataFactoryPagination

    def get_queryset(self):
        """获取当前用户的记录"""
        return DataFactoryRecord.objects.filter(user=self.request.user).only(
            'id', 'user', 'tool_name', 'tool_category', 'tool_scenario',
            'input_data', 'output_data', 'is_saved', 'tags', 'created_at', 'updated_at'
        ).order_by('-created_at')

    def filter_queryset(self, queryset):
        """自定义过滤逻辑，支持JSONField的过滤"""
        # 支持tags字段的过滤（JSONField）
        tags_contains = self.request.query_params.get('tags__contains')
        if tags_contains:
            queryset = queryset.filter(tags__contains=tags_contains)

        # 支持tool_name的模糊查询
        tool_name_icontains = self.request.query_params.get('tool_name__icontains')
        if tool_name_icontains:
            queryset = queryset.filter(tool_name__icontains=tool_name_icontains)

        # 支持tool_category的精确过滤
        tool_category = self.request.query_params.get('tool_category')
        if tool_category:
            queryset = queryset.filter(tool_category=tool_category)

        return queryset

    def list(self, request, *args, **kwargs):
        """重写list方法以正确处理分页"""
        try:
            # 生成缓存键，忽略时间戳参数
            query_params = request.query_params.copy()
            query_params.pop('_t', None)  # 移除时间戳参数
            
            cache_key = f'data_factory_history_{request.user.id}_{query_params.get("page", 1)}_{query_params.get("page_size", 10)}_{query_params.get("tool_category", "")}_{query_params.get("tool_name__icontains", "")}_{query_params.get("tags__contains", "")}'
            
            # 检查缓存，但如果有时间戳参数则不使用缓存
            if '_t' not in request.query_params:
                cached_data = cache.get(cache_key)
                if cached_data:
                    return Response(cached_data)
            
            # 获取并过滤查询集
            queryset = self.get_queryset()
            queryset = self.filter_queryset(queryset)
            
            # 分页处理
            page = self.paginate_queryset(queryset)
            if page is not None:
                # 序列化数据
                serializer = self.get_serializer(page, many=True)
                serializer_data = serializer.data
                
                # 获取分页响应
                paginated_response = self.get_paginated_response(serializer_data)
                
                # 缓存结果，3分钟过期
                if '_t' not in request.query_params:
                    cache.set(cache_key, paginated_response.data, 180)
                
                return paginated_response
            
            serializer = self.get_serializer(queryset, many=True)
            serializer_data = serializer.data
            return Response(serializer_data)
        except Exception as e:
            logger.error(f'列表方法错误: {str(e)}', exc_info=True)
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create(self, request, *args, **kwargs):
        """执行工具并保存结果"""
        serializer = ToolExecuteSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            result = self.execute_tool(
                data['tool_name'],
                data['tool_category'],
                data['input_data']
            )

            if 'error' in result:
                return Response(result, status=status.HTTP_400_BAD_REQUEST)

            if data.get('is_saved', True):
                try:
                    # 创建记录
                    record = DataFactoryRecord.objects.create(
                        user=request.user,
                        tool_name=data['tool_name'],
                        tool_category=data['tool_category'],
                        tool_scenario=data['tool_scenario'],
                        input_data=data['input_data'],
                        output_data=result,
                        is_saved=data.get('is_saved', True),
                        tags=data.get('tags', None)
                    )
                    result['record_id'] = str(record.id)
                    result['created_at'] = record.created_at.isoformat()
                    
                    # 清除相关缓存
                    self.clear_user_cache(request.user.id)
                except Exception as e:
                    return Response({'error': f'保存记录失败: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            return Response(result, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        """删除数据工厂记录"""
        try:
            logger.info(f'开始删除记录: ID={kwargs.get("pk")}, 用户ID={request.user.id}')
            # 使用self.get_object()获取记录，它会自动处理权限过滤
            instance = self.get_object()
            logger.info(f'成功获取记录: ID={instance.id}, 用户ID={instance.user.id}')
            
            # 删除记录
            instance.delete()
            logger.info(f'成功删除记录: ID={kwargs.get("pk")}')
            
            # 清除相关缓存
            self.clear_user_cache(request.user.id)
            logger.info(f'成功清除缓存: 用户ID={request.user.id}')
            
            return Response({'message': '删除成功'}, status=status.HTTP_200_OK)
        except DataFactoryRecord.DoesNotExist:
            logger.error(f'记录不存在: ID={kwargs.get("pk")}, 用户ID={request.user.id}')
            return Response({'error': '记录不存在'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f'删除记录失败: {str(e)}, ID={kwargs.get("pk")}, 用户ID={request.user.id}', exc_info=True)
            return Response({'error': f'删除失败: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def clear_user_cache(self, user_id):
        """清除用户相关的缓存"""
        # 清除统计信息缓存
        cache.delete(f'data_factory_statistics_{user_id}')
        # 清除标签缓存
        cache.delete(f'data_factory_tags_{user_id}')
        # 清除历史记录缓存
        try:
            # 遍历所有缓存键，删除与当前用户相关的历史记录缓存
            if hasattr(cache, '_cache'):
                # 对于LocMemCache
                keys_to_delete = []
                for key in cache._cache:
                    # 匹配包含 data_factory_history 和用户ID的缓存键
                    if 'data_factory_history' in key and str(user_id) in key:
                        keys_to_delete.append(key)
                for key in keys_to_delete:
                    cache.delete(key)
            elif hasattr(cache, 'keys'):
                # 对于支持keys()方法的缓存后端
                for key in cache.keys():
                    # 匹配包含 data_factory_history 和用户ID的缓存键
                    if 'data_factory_history' in key and str(user_id) in key:
                        cache.delete(key)
        except Exception as e:
            logger.error(f'清除历史记录缓存失败: {str(e)}')
        # 历史记录缓存会在3分钟后自动过期（作为备份）

    def execute_tool(self, tool_name: str, tool_category: str, input_data: dict):
        """执行工具"""
        try:
            logger.info(f'开始执行工具: {tool_name}, 分类: {tool_category}, 输入数据: {input_data}')
            
            # 字符工具
            if tool_category == 'string':
                result = self.execute_string_tool(tool_name, input_data)
            # 编码工具
            elif tool_category == 'encoding':
                result = self.execute_encoding_tool(tool_name, input_data)
            # 随机工具
            elif tool_category == 'random':
                result = self.execute_random_tool(tool_name, input_data)
            # 加密工具
            elif tool_category == 'encryption':
                result = self.execute_encryption_tool(tool_name, input_data)
            # 测试数据（包含测试数据和Mock数据）
            elif tool_category == 'test_data':
                if tool_name.startswith('mock_'):
                    result = self.execute_mock_tool(tool_name, input_data)
                else:
                    result = self.execute_test_data_tool(tool_name, input_data)
            # JSON工具
            elif tool_category == 'json':
                result = self.execute_json_tool(tool_name, input_data)
            # Crontab工具
            elif tool_category == 'crontab':
                result = self.execute_crontab_tool(tool_name, input_data)
            else:
                error_msg = f'不支持的工具分类: {tool_category}'
                logger.error(error_msg)
                return {'error': error_msg}
            
            logger.info(f'工具执行完成: {tool_name}, 结果: {"成功" if "error" not in result else "失败"}')
            return result
        except Exception as e:
            error_msg = f'工具执行失败: {str(e)}'
            logger.error(error_msg, exc_info=True)
            return {'error': error_msg}

    def execute_string_tool(self, tool_name: str, input_data: dict | str):
        """执行字符工具"""
        tool_mapping = {
            'remove_whitespace': StringTools.remove_whitespace,
            'replace_string': StringTools.replace_string,
            'escape_string': StringTools.escape_string,
            'unescape_string': StringTools.unescape_string,
            'word_count': StringTools.word_count,
            'text_diff': StringTools.text_diff,
            'regex_test': StringTools.regex_test,
            'case_convert': StringTools.case_convert,
            'string_format': StringTools.string_format
        }

        if tool_name not in tool_mapping:
            return {'error': f'不支持的字符工具: {tool_name}'}
        # 如果 input_data 是字符串，包装为 {'text': input_data}
        if isinstance(input_data, str):
            if tool_name in ['remove_whitespace', 'word_count', 'text_diff', 'string_format']:
                input_data = {'text': input_data}
            elif tool_name == 'regex_test':
                # 需要pattern和text，尝试解析
                input_data = {'pattern': input_data, 'text': ''}
            elif tool_name in ['case_convert']:
                input_data = {'text': input_data, 'convert_type': 'upper'}
            else:
                input_data = {'text': input_data}

        return tool_mapping[tool_name](**input_data)

    def execute_encoding_tool(self, tool_name: str, input_data: dict | str):
        """执行编码工具"""
        tool_mapping = {
            'generate_barcode': EncodingTools.generate_barcode,
            'generate_qrcode': EncodingTools.generate_qrcode,
            'decode_qrcode': EncodingTools.decode_qrcode,
            'timestamp_convert': EncodingTools.timestamp_convert,
            'base_convert': EncodingTools.base_convert,
            'unicode_convert': EncodingTools.unicode_convert,
            'ascii_convert': EncodingTools.ascii_convert,
            'color_convert': EncodingTools.color_convert,
            'base64_encode': EncodingTools.base64_encode,
            'base64_decode': EncodingTools.base64_decode,
            'url_encode': EncodingTools.url_encode,
            'url_decode': EncodingTools.url_decode,
            'jwt_decode': EncodingTools.jwt_decode,
            'image_to_base64': ImageTools.image_to_base64,
            'base64_to_image': ImageTools.base64_to_image
        }

        if tool_name not in tool_mapping:
            return {'error': f'不支持的编码工具: {tool_name}'}

        # 处理字符串输入
        if isinstance(input_data, str):
            if tool_name == 'timestamp_convert':
                input_data = {'timestamp': input_data, 'convert_type': 'to_datetime'}
            elif tool_name in ['base_convert', 'unicode_convert', 'ascii_convert', 'color_convert']:
                input_data = {'text': input_data}
            elif tool_name in ['base64_encode', 'base64_decode']:
                input_data = {'text': input_data, 'encoding': 'utf-8'}
            elif tool_name in ['url_encode', 'url_decode']:
                input_data = {'data': input_data, 'encoding': 'utf-8'}
            elif tool_name == 'jwt_decode':
                input_data = {'token': input_data, 'verify': False}
            elif tool_name in ['generate_barcode', 'generate_qrcode']:
                input_data = {'data': input_data}
            elif tool_name == 'decode_qrcode':
                input_data = {'image_data': input_data, 'image_format': 'png'}
            elif tool_name == 'image_to_base64':
                input_data = {'image_data': input_data, 'image_format': 'png', 'include_prefix': True}
            elif tool_name == 'base64_to_image':
                input_data = {'base64_str': input_data}
            else:
                input_data = {'text': input_data}
        return tool_mapping[tool_name](**input_data)

    def execute_random_tool(self, tool_name: str, input_data: dict | str):
        """执行随机工具"""
        tool_mapping = {
            'random_int': RandomTools.random_int,
            'random_float': RandomTools.random_float,
            'random_string': RandomTools.random_string,
            'random_uuid': RandomTools.random_uuid,
            'random_mac_address': RandomTools.random_mac_address,
            'random_ip_address': RandomTools.random_ip_address,
            'random_date': RandomTools.random_date,
            'random_boolean': RandomTools.random_boolean,
            'random_color': RandomTools.random_color,
            'random_password': RandomTools.random_password,
            'random_sequence': RandomTools.random_sequence
        }

        if tool_name not in tool_mapping:
            return {'error': f'不支持的随机工具: {tool_name}'}
        # 处理字符串输入 - 大部分随机工具不需要输入，直接返回空字典
        if isinstance(input_data, str):
            if tool_name == 'random_int':
                input_data = {'min_val': 1, 'max_val': 100, 'count': 1}
            elif tool_name == 'random_float':
                input_data = {'min_val': 0.0, 'max_val': 1.0, 'precision': 2, 'count': 1}
            elif tool_name == 'random_string':
                input_data = {'length': 8, 'char_type': 'all', 'count': 1}
            elif tool_name == 'random_uuid':
                input_data = {'version': 4, 'count': 1}
            elif tool_name == 'random_mac_address':
                input_data = {'separator': ':', 'count': 1}
            elif tool_name == 'random_ip_address':
                input_data = {'ip_version': 4, 'count': 1}
            elif tool_name == 'random_date':
                input_data = {'start_date': '2024-01-01', 'end_date': '2024-12-31', 'count': 1}
            elif tool_name == 'random_boolean':
                input_data = {'count': 1}
            elif tool_name == 'random_color':
                input_data = {'format': 'hex', 'count': 1}
            elif tool_name == 'random_password':
                input_data = {'length': 12, 'include_uppercase': True, 'include_lowercase': True,
                              'include_digits': True, 'include_special': True}
            elif tool_name == 'random_sequence':
                input_data = {'sequence': [], 'count': 1, 'unique': False}
            else:
                input_data = {'count': 1}
        return tool_mapping[tool_name](**input_data)

    def execute_encryption_tool(self, tool_name: str, input_data: dict | str):
        """执行加密工具"""
        tool_mapping = {
            'md5_hash': EncryptionTools.md5_hash,
            'sha1_hash': EncryptionTools.sha1_hash,
            'sha256_hash': EncryptionTools.sha256_hash,
            'sha512_hash': EncryptionTools.sha512_hash,
            'hash_comparison': EncryptionTools.hash_comparison,
            'aes_encrypt': EncryptionTools.aes_encrypt,
            'aes_decrypt': EncryptionTools.aes_decrypt,
            'password_strength': EncryptionTools.password_strength,
            'generate_salt': EncryptionTools.generate_salt
        }

        if tool_name not in tool_mapping:
            return {'error': f'不支持的加密工具: {tool_name}'}
        # 处理字符串输入
        if isinstance(input_data, str):
            if tool_name in ['md5_hash', 'sha1_hash', 'sha256_hash', 'sha512_hash',
                             'password_strength', 'generate_salt']:
                input_data = {'text': input_data}
            elif tool_name == 'hash_comparison':
                input_data = {'text': input_data, 'hash_value': ''}
            elif tool_name in ['aes_encrypt', 'aes_decrypt']:
                input_data = {'text': input_data, 'password': 'default_password', 'mode': 'CBC'}
            else:
                input_data = {'text': input_data}
        return tool_mapping[tool_name](**input_data)

    def execute_test_data_tool(self, tool_name: str, input_data: dict | str):
        """执行测试数据工具"""
        tool_mapping = {
            'generate_chinese_name': TestDataTools.generate_chinese_name,
            'generate_chinese_phone': TestDataTools.generate_chinese_phone,
            'generate_chinese_email': TestDataTools.generate_chinese_email,
            'generate_chinese_address': TestDataTools.generate_chinese_address,
            'generate_id_card': TestDataTools.generate_id_card,
            'generate_company_name': TestDataTools.generate_company_name,
            'generate_bank_card': TestDataTools.generate_bank_card,
            'generate_user_profile': TestDataTools.generate_user_profile,
            'generate_hk_id_card': TestDataTools.generate_hk_id_card,
            'generate_business_license': TestDataTools.generate_business_license,
            'generate_coordinates': TestDataTools.generate_coordinates
        }

        if tool_name not in tool_mapping:
            return {'error': f'不支持的测试数据工具: {tool_name}'}
        # 处理字符串输入 - 测试数据工具大部分不需要输入参数
        if isinstance(input_data, str):
            if tool_name in ['generate_chinese_name', 'generate_chinese_phone', 'generate_chinese_email',
                             'generate_chinese_address', 'generate_id_card', 'generate_company_name',
                             'generate_bank_card', 'generate_hk_id_card', 'generate_business_license',
                             'generate_coordinates']:
                input_data = {'count': 1}
            elif tool_name == 'generate_user_profile':
                input_data = {'count': 1}
            else:
                input_data = {'count': 1}
        return tool_mapping[tool_name](**input_data)

    def execute_json_tool(self, tool_name: str, input_data: dict | str):
        """执行JSON工具"""
        tool_mapping = {
            'format_json': JsonTools.format_json,
            'validate_json': JsonTools.validate_json,
            'json_to_xml': JsonTools.json_to_xml,
            'xml_to_json': JsonTools.xml_to_json,
            'json_to_yaml': JsonTools.json_to_yaml,
            'yaml_to_json': JsonTools.yaml_to_json,
            'json_diff_enhanced': JsonTools.json_diff_enhanced,
            'jsonpath_query': JsonTools.jsonpath_query,
            'json_path_list': JsonTools.json_path_list,
            'json_flatten': JsonTools.json_flatten
        }

        if tool_name not in tool_mapping:
            return {'error': f'不支持的JSON工具: {tool_name}'}

        # 处理字符串输入
        if isinstance(input_data, str):
            if tool_name in ['format_json', 'validate_json', 'json_to_xml', 'json_to_yaml', 'json_path_list',
                             'json_flatten']:
                input_data = {'json_str': input_data}
            elif tool_name == 'xml_to_json':
                input_data = {'xml_str': input_data}
            elif tool_name == 'yaml_to_json':
                input_data = {'yaml_str': input_data}
            elif tool_name == 'json_diff_enhanced':
                input_data = {'json_str1': input_data, 'json_str2': ''}
            elif tool_name == 'jsonpath_query':
                input_data = {'json_str': input_data, 'jsonpath_expr': ''}
            else:
                input_data = {'json_str': input_data}
        return tool_mapping[tool_name](**input_data)

    def execute_mock_tool(self, tool_name: str, input_data: dict | str):
        """执行Mock数据工具"""
        tool_mapping = {
            'mock_string': JsonTools.mock_data,
            'mock_number': JsonTools.mock_data,
            'mock_boolean': JsonTools.mock_data,
            'mock_email': JsonTools.mock_data,
            'mock_phone': JsonTools.mock_data,
            'mock_date': JsonTools.mock_data,
            'mock_datetime': JsonTools.mock_data,
            'mock_name': JsonTools.mock_data,
            'mock_address': JsonTools.mock_data,
            'mock_url': JsonTools.mock_data,
            'mock_uuid': JsonTools.mock_data,
            'mock_ip': JsonTools.mock_data
        }

        if tool_name not in tool_mapping:
            return {'error': f'不支持的Mock工具: {tool_name}'}

        data_type = tool_name.replace('mock_', '')

        if isinstance(input_data, str):
            input_data = {'data_type': data_type, 'count': 1}
        else:
            input_data['data_type'] = data_type

        return tool_mapping[tool_name](**input_data)

    def execute_crontab_tool(self, tool_name: str, input_data: dict | str):
        """执行Crontab工具"""
        tool_mapping = {
            'generate_expression': CrontabTools.generate_expression,
            'parse_expression': CrontabTools.parse_expression,
            'get_next_runs': CrontabTools.get_next_runs,
            'validate_expression': CrontabTools.validate_expression
        }

        if tool_name not in tool_mapping:
            return {'error': f'不支持的Crontab工具: {tool_name}'}

        if isinstance(input_data, str):
            if tool_name == 'generate_expression':
                input_data = {'minute': '*', 'hour': '*', 'day': '*', 'month': '*', 'weekday': '*'}
            elif tool_name == 'parse_expression':
                input_data = {'expression': input_data}
            elif tool_name == 'get_next_runs':
                input_data = {'expression': input_data, 'count': 10}
            elif tool_name == 'validate_expression':
                input_data = {'expression': input_data}
            else:
                input_data = {'expression': input_data}
        return tool_mapping[tool_name](**input_data)

    @action(detail=False, methods=['get'])
    def categories(self, request):
        """获取所有工具分类"""
        try:
            # 生成缓存键（分类数据是静态的，不需要用户ID）
            cache_key = 'data_factory_categories'
            
            # 检查缓存
            cached_categories = cache.get(cache_key)
            if cached_categories:
                return Response(cached_categories)
            
            # 获取分类数据
            categories = get_categories()
            
            # 为每个分类添加工具列表
            tool_list = get_tool_list()
            for category in categories:
                category['tools'] = [tool for tool in tool_list if tool['scenario'] == category['scenario']]
            
            categories_data = {
                'categories': categories,
                'total_tools': sum(len(cat['tools']) for cat in categories)
            }
            
            # 缓存结果，30分钟过期（分类数据很少变化）
            cache.set(cache_key, categories_data, 1800)
            
            return Response(categories_data)
        except Exception as e:
            logger.error(f'获取分类列表失败: {str(e)}', exc_info=True)
            return Response(
                {'error': f'获取分类列表失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def tags(self, request):
        """获取所有标签列表"""
        try:
            # 生成缓存键
            cache_key = f'data_factory_tags_{request.user.id}'
            
            # 检查缓存
            cached_tags = cache.get(cache_key)
            if cached_tags:
                return Response(cached_tags)
            
            # 同步获取标签，获取当前用户的所有记录
            queryset = DataFactoryRecord.objects.filter(user=request.user)
            
            # 获取所有唯一的标签
            tag_set = set()
            for record in queryset:
                if record.tags and isinstance(record.tags, list):
                    tag_set.update(record.tags)
            
            tags = sorted(list(tag_set))
            
            # 缓存结果，5分钟过期
            cache_data = {
                'tags': tags,
                'count': len(tags)
            }
            cache.set(cache_key, cache_data, 300)

            return Response(cache_data)
        except Exception as e:
            return Response(
                {'error': f'获取标签列表失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def batch_generate(self, request):
        """批量生成数据"""
        tool_name = request.data.get('tool_name')
        tool_category = request.data.get('tool_category')
        tool_scenario = request.data.get('tool_scenario')
        count = request.data.get('count', 10)
        input_data = request.data.get('input_data', {})

        if not tool_name or not tool_category:
            return Response(
                {'error': '缺少必要参数: tool_name 或 tool_category'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 检查是否适合缓存（如随机工具不适合缓存）
        import hashlib
        import json
        non_cacheable_tools = ['random_', 'mock_']
        is_cacheable = not any(tool_name.startswith(prefix) for prefix in non_cacheable_tools)
        
        if is_cacheable:
            # 生成缓存键
            cache_key = f'data_factory_batch_{tool_name}_{tool_category}_{count}_{hashlib.md5(json.dumps(input_data, sort_keys=True).encode()).hexdigest()}'
            
            # 检查缓存
            cached_result = cache.get(cache_key)
            if cached_result:
                # 如果需要保存记录
                if request.data.get('is_saved', True):
                    try:
                        # 创建记录
                        record = DataFactoryRecord.objects.create(
                            user=request.user,
                            tool_name=tool_name,
                            tool_category=tool_category,
                            tool_scenario=tool_scenario,
                            input_data=input_data,
                            output_data={'results': cached_result['results'], 'count': len(cached_result['results'])},
                            is_saved=True
                        )
                        # 清除相关缓存
                        self.clear_user_cache(request.user.id)
                    except Exception as e:
                        logger.error(f'保存记录失败: {str(e)}', exc_info=True)
                        pass  # 保存失败不影响返回结果
                return Response(cached_result)

        # 批量生成
        results = []
        for i in range(count):
            result = self.execute_tool(tool_name, tool_category, input_data)
            if 'error' not in result:
                results.append(result)

        # 构建响应数据
        response_data = {
            'results': results,
            'count': len(results),
            'total_requested': count
        }

        # 缓存结果（如果适合缓存）
        if is_cacheable:
            # 设置缓存，5分钟过期
            cache.set(cache_key, response_data, 300)

        # 保存记录
        if request.data.get('is_saved', True):
            # 创建记录
            record = DataFactoryRecord.objects.create(
                user=request.user,
                tool_name=tool_name,
                tool_category=tool_category,
                tool_scenario=tool_scenario,
                input_data=input_data,
                output_data={'results': results, 'count': len(results)},
                is_saved=True
            )
            # 清除相关缓存
            self.clear_user_cache(request.user.id)

        return Response(response_data)

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """获取使用统计"""
        # 生成缓存键
        cache_key = f'data_factory_statistics_{request.user.id}'
        
        # 检查缓存
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)
        
        # 预计算映射
        category_map = dict(DataFactoryRecord.TOOL_CATEGORIES)
        scenario_map = dict(DataFactoryRecord.TOOL_SCENARIOS)
        
        # 1. 计算总记录数（使用聚合查询）
        total_records = DataFactoryRecord.objects.filter(
            user=request.user
        ).count()
        
        # 2. 按分类统计（使用聚合查询）
        category_stats = {}
        category_counts = DataFactoryRecord.objects.filter(
            user=request.user
        ).values('tool_category').annotate(count=Count('tool_category')).order_by()
        
        for item in category_counts:
            cat_name = item['tool_category']
            cat_display = category_map.get(cat_name, cat_name)
            category_stats[cat_display] = item['count']
        
        # 确保所有分类都有统计数据
        for cat_name, cat_display in DataFactoryRecord.TOOL_CATEGORIES:
            if cat_display not in category_stats:
                category_stats[cat_display] = 0
        
        # 3. 按场景统计（使用聚合查询）
        scenario_stats = {}
        scenario_counts = DataFactoryRecord.objects.filter(
            user=request.user
        ).values('tool_scenario').annotate(count=Count('tool_scenario')).order_by()
        
        for item in scenario_counts:
            sce_name = item['tool_scenario']
            sce_display = scenario_map.get(sce_name, sce_name)
            scenario_stats[sce_display] = item['count']
        
        # 确保所有场景都有统计数据
        for sce_name, sce_display in DataFactoryRecord.TOOL_SCENARIOS:
            if sce_display not in scenario_stats:
                scenario_stats[sce_display] = 0
        
        # 4. 获取最近使用的工具（只选择需要的字段）
        recent_tools = []
        recent_records = DataFactoryRecord.objects.filter(
            user=request.user
        ).only(
            'tool_name', 'tool_category', 'tool_scenario', 'created_at'
        ).order_by('-created_at')[:10]
        
        for record in recent_records:
            recent_tools.append({
                'tool_name': record.tool_name,
                'tool_category_display': record.get_tool_category_display(),
                'tool_scenario_display': record.get_tool_scenario_display(),
                'created_at': record.created_at
            })
        
        # 构建响应数据
        stats_data = {
            'total_records': total_records,
            'category_stats': category_stats,
            'scenario_stats': scenario_stats,
            'recent_tools': recent_tools
        }
        
        # 缓存结果，5分钟过期
        cache.set(cache_key, stats_data, 300)
        
        return Response(stats_data)

    @action(detail=False, methods=['get'])
    def download_static_file(self, request):
        """
        下载static_files/img目录下的文件
        用于条形码和二维码的下载和预览
        """
        filename = request.query_params.get('filename')

        if not filename:
            return Response(
                {'error': '缺少必要参数: filename'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 调用工具类验证文件
        result = EncodingTools.download_static_file(filename)

        if 'error' in result:
            return Response(
                {'error': result['error']},
                status=status.HTTP_404_NOT_FOUND
            )

        # 读取文件内容
        file_path = Path(result['file_path'])

        try:
            # 同步读取文件
            with open(file_path, 'rb') as f:
                file_content = f.read()

            # 根据文件扩展名确定MIME类型
            mime_types = {
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.gif': 'image/gif',
                '.svg': 'image/svg+xml',
                '.bmp': 'image/bmp',
                '.webp': 'image/webp'
            }

            file_ext = file_path.suffix.lower()
            content_type = mime_types.get(file_ext, 'application/octet-stream')

            # 返回文件内容
            response = HttpResponse(file_content, content_type=content_type)
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response['Content-Length'] = str(len(file_content))

            return response
        except Exception as e:
            return Response(
                {'error': f'文件读取失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def variable_functions(self, request):
        """获取所有变量函数列表（用于变量助手）
        
        返回格式：
        [
            {
                'name': 'random_int',
                'syntax': '${random_int(min, max, count)}',
                'desc': '生成随机整数',
                'example': '${random_int(100, 999, 1)}'
                'category': '随机数'
            },
            ...
        ]
        """
        # 生成缓存键（变量函数列表是静态的）
        cache_key = 'data_factory_variable_functions'
        
        # 检查缓存
        cached_functions = cache.get(cache_key)
        if cached_functions:
            return Response(cached_functions)
        
        # 获取变量函数列表
        tool_list = get_tool_list()
        logger.info(f'获取到工具列表，共 {len(tool_list)} 个工具')
        
        # 定义工具函数的语法模板
        syntax_templates = {
            # 随机工具
            'random_int': '${random_int(min, max, count)}',
            'random_float': '${random_float(min, max, precision, count)}',
            'random_digits': '${random_digits(length, count)}',
            'random_string': '${random_string(length, char_type, count)}',
            'random_letters': '${random_letters(length, count)}',
            'random_chinese': '${random_chinese(length, count)}',
            'random_uuid': '${random_uuid(version, count)}',
            'random_guid': '${random_guid(version, count)}',
            'random_mac': '${random_mac(separator, count)}',
            'random_mac_address': '${random_mac_address(separator, count)}',
            'random_ip': '${random_ip(ip_version, count)}',
            'random_ip_address': '${random_ip_address(ip_version, count)}',
            'random_boolean': '${random_boolean(count)}',
            'random_color': '${random_color(format, count)}',
            'random_password': '${random_password(length, count)}',
            'random_sequence': '${random_sequence(sequence, count, unique)}',
            'random_date': '${random_date(start_date, end_date, count, date_format)}',
            
            # 测试数据工具
            'random_phone': '${random_phone(count)}',
            'random_email': '${random_email(count)}',
            'random_id_card': '${random_id_card(count)}',
            'random_name': '${random_name(count)}',
            'random_company': '${random_company(count)}',
            'random_address': '${random_address(count)}',
            'generate_chinese_name': '${generate_chinese_name(gender, count)}',
            'generate_chinese_phone': '${generate_chinese_phone(count)}',
            'generate_chinese_email': '${generate_chinese_email(count)}',
            'generate_chinese_address': '${generate_chinese_address(full_address, count)}',
            'generate_id_card': '${generate_id_card(count)}',
            'generate_company_name': '${generate_company_name(count)}',
            'generate_bank_card': '${generate_bank_card(count)}',
            'generate_hk_id_card': '${generate_hk_id_card(count)}',
            'generate_business_license': '${generate_business_license(count)}',
            'generate_user_profile': '${generate_user_profile(count)}',
            'generate_coordinates': '${generate_coordinates(count)}',
            
            # 字符工具
            'remove_whitespace': '${remove_whitespace(text, type)}',
            'replace_string': '${replace_string(text, old, new, count)}',
            'word_count': '${word_count(text)}',
            'regex_test': '${regex_test(pattern, text, flags)}',
            'case_convert': '${case_convert(text, case_type)}',
            
            # 编码工具
            'timestamp_convert': '${timestamp_convert(timestamp, convert_type)}',
            'base64_encode': '${base64_encode(text, encoding)}',
            'base64_decode': '${base64_decode(text, encoding)}',
            'url_encode': '${url_encode(data, encoding)}',
            'url_decode': '${url_decode(data, encoding)}',
            'unicode_convert': '${unicode_convert(text, convert_type)}',
            'ascii_convert': '${ascii_convert(text, convert_type)}',
            'color_convert': '${color_convert(color, from_type, to_type)}',
            'base_convert': '${base_convert(number, from_base, to_base)}',
            'generate_barcode': '${generate_barcode(data, format)}',
            'generate_qrcode': '${generate_qrcode(data)}',
            'decode_qrcode': '${decode_qrcode(image_path)}',
            'image_to_base64': '${image_to_base64(image_path)}',
            'base64_to_image': '${base64_to_image(base64_data, output_path)}',
            
            # 加密工具
            'md5': '${md5(text)}',
            'sha1': '${sha1(text)}',
            'sha256': '${sha256(text)}',
            'md5_hash': '${md5_hash(text)}',
            'sha1_hash': '${sha1_hash(text)}',
            'sha256_hash': '${sha256_hash(text)}',
            'sha512_hash': '${sha512_hash(text)}',
            'hash_comparison': '${hash_comparison(hash1, hash2)}',
            'aes_encrypt': '${aes_encrypt(text, password, mode)}',
            'aes_decrypt': '${aes_decrypt(encrypted_text, password, mode)}',
            'jwt_decode': '${jwt_decode(token, verify, secret)}',
            'password_strength': '${password_strength(password)}',
            'generate_salt': '${generate_salt(length)}',
            
            # Crontab工具
            'generate_expression': '${generate_expression(minute, hour, day, month, weekday)}',
            'parse_expression': '${parse_expression(expression)}',
            'get_next_runs': '${get_next_runs(expression, count)}',
            'validate_expression': '${validate_expression(expression)}',
            
            # 时间日期函数
            'timestamp': '${timestamp()}',
            'timestamp_sec': '${timestamp_sec()}',
            'datetime': '${datetime(format_str)}',
            'date': '${date(format_str)}',
            'time': '${time(format_str)}',
            'date_offset': '${date_offset(days, hours, minutes, format_str)}',
        }
        
        # 定义示例模板
        example_templates = {
            # 随机工具
            'random_int': '${random_int(100, 999, 1)}',
            'random_float': '${random_float(0, 1, 2, 1)}',
            'random_digits': '${random_digits(6, 1)}',
            'random_string': '${random_string(8, all, 1)}',
            'random_letters': '${random_letters(8, 1)}',
            'random_chinese': '${random_chinese(2, 1)}',
            'random_uuid': '${random_uuid(4, 1)}',
            'random_guid': '${random_guid(4, 1)}',
            'random_mac': '${random_mac(:, 1)}',
            'random_mac_address': '${random_mac_address(:, 1)}',
            'random_ip': '${random_ip(4, 1)}',
            'random_ip_address': '${random_ip_address(4, 1)}',
            'random_boolean': '${random_boolean(1)}',
            'random_color': '${random_color(hex, 1)}',
            'random_password': '${random_password(12, 1)}',
            'random_sequence': '${random_sequence([a,b,c], 1, false)}',
            'random_date': '${random_date(2024-01-01, 2024-12-31, 1, %Y-%m-%d)}',
            
            # 测试数据工具
            'random_phone': '${random_phone(1)}',
            'random_email': '${random_email(1)}',
            'random_id_card': '${random_id_card(1)}',
            'random_name': '${random_name(1)}',
            'random_company': '${random_company(1)}',
            'random_address': '${random_address(1)}',
            'generate_chinese_name': '${generate_chinese_name(random, 1)}',
            'generate_chinese_phone': '${generate_chinese_phone(1)}',
            'generate_chinese_email': '${generate_chinese_email(1)}',
            'generate_chinese_address': '${generate_chinese_address(true, 1)}',
            'generate_id_card': '${generate_id_card(1)}',
            'generate_company_name': '${generate_company_name(1)}',
            'generate_bank_card': '${generate_bank_card(1)}',
            'generate_hk_id_card': '${generate_hk_id_card(1)}',
            'generate_business_license': '${generate_business_license(1)}',
            'generate_user_profile': '${generate_user_profile(1)}',
            'generate_coordinates': '${generate_coordinates(1)}',
            
            # 字符工具
            'remove_whitespace': '${remove_whitespace(hello world, all)}',
            'replace_string': '${replace_string(hello world, world, test, 1)}',
            'word_count': '${word_count(hello world)}',
            'regex_test': '${regex_test(hello123, ^[a-z]+\\d+$, gi)}',
            'case_convert': '${case_convert(hello, upper)}',
            
            # 编码工具
            'timestamp_convert': '${timestamp_convert(1234567890, to_datetime)}',
            'base64_encode': '${base64_encode(123456, utf-8)}',
            'base64_decode': '${base64_decode(MTIzNDU2, utf-8)}',
            'url_encode': '${url_encode(hello world, utf-8)}',
            'url_decode': '${url_decode(hello%20world, utf-8)}',
            'unicode_convert': '${unicode_convert(你好, to_unicode)}',
            'ascii_convert': '${ascii_convert(ABC, to_ascii)}',
            'color_convert': '${color_convert(#ff0000, hex, rgb)}',
            'base_convert': '${base_convert(10, 10, 16)}',
            'generate_barcode': '${generate_barcode(123456, code128)}',
            'generate_qrcode': '${generate_qrcode(https://example.com)}',
            'decode_qrcode': '${decode_qrcode(/path/to/qrcode.png)}',
            'image_to_base64': '${image_to_base64(/path/to/image.png)}',
            'base64_to_image': '${base64_to_image(data:image/png;base64,..., /path/to/output.png)}',
            
            # 加密工具
            'md5': '${md5(123456)}',
            'sha1': '${sha1(123456)}',
            'sha256': '${sha256(123456)}',
            'md5_hash': '${md5_hash(123456)}',
            'sha1_hash': '${sha1_hash(123456)}',
            'sha256_hash': '${sha256_hash(123456)}',
            'sha512_hash': '${sha512_hash(123456)}',
            'hash_comparison': '${hash_comparison(hash1, hash2)}',
            'aes_encrypt': '${aes_encrypt(hello, password, CBC)}',
            'aes_decrypt': '${aes_decrypt(encrypted, password, CBC)}',
            'jwt_decode': '${jwt_decode(token, false, secret)}',
            'password_strength': '${password_strength(myPassword123)}',
            'generate_salt': '${generate_salt(16)}',
            
            # Crontab工具
            'generate_expression': '${generate_expression(*, *, *, *, *)}',
            'parse_expression': '${parse_expression(0 0 * * *)}',
            'get_next_runs': '${get_next_runs(0 0 * * *, 5)}',
            'validate_expression': '${validate_expression(0 0 * * *)}',
            
            # 时间日期函数
            'timestamp': '${timestamp()}',
            'timestamp_sec': '${timestamp_sec()}',
            'datetime': '${datetime(%Y-%m-%d %H:%M:%S)}',
            'date': '${date(%Y-%m-%d)}',
            'time': '${time(%H:%M:%S)}',
            'date_offset': '${date_offset(1, 0, 0, %Y-%m-%d)}',
        }
        
        # 定义分类映射
        category_map = {
            'random_int': '随机数',
            'random_float': '随机数',
            'random_digits': '随机数',
            'random_string': '随机数',
            'random_letters': '随机数',
            'random_chinese': '随机数',
            'random_uuid': '随机数',
            'random_guid': '随机数',
            'random_mac': '随机数',
            'random_mac_address': '随机数',
            'random_ip': '随机数',
            'random_ip_address': '随机数',
            'random_boolean': '随机数',
            'random_color': '随机数',
            'random_password': '随机数',
            'random_sequence': '随机数',
            'random_date': '随机数',
            'random_phone': '测试数据',
            'random_email': '测试数据',
            'random_id_card': '测试数据',
            'random_name': '测试数据',
            'random_company': '测试数据',
            'random_address': '测试数据',
            'generate_chinese_name': '测试数据',
            'generate_chinese_phone': '测试数据',
            'generate_chinese_email': '测试数据',
            'generate_chinese_address': '测试数据',
            'generate_id_card': '测试数据',
            'generate_company_name': '测试数据',
            'generate_bank_card': '测试数据',
            'generate_hk_id_card': '测试数据',
            'generate_business_license': '测试数据',
            'generate_user_profile': '测试数据',
            'generate_coordinates': '测试数据',
            'remove_whitespace': '字符串',
            'replace_string': '字符串',
            'word_count': '字符串',
            'regex_test': '字符串',
            'case_convert': '字符串',
            'timestamp_convert': '编码转换',
            'base64_encode': '编码转换',
            'base64_decode': '编码转换',
            'url_encode': '编码转换',
            'url_decode': '编码转换',
            'unicode_convert': '编码转换',
            'ascii_convert': '编码转换',
            'color_convert': '编码转换',
            'base_convert': '编码转换',
            'generate_barcode': '编码转换',
            'generate_qrcode': '编码转换',
            'decode_qrcode': '编码转换',
            'image_to_base64': '编码转换',
            'base64_to_image': '编码转换',
            'md5': '加密',
            'sha1': '加密',
            'sha256': '加密',
            'md5_hash': '加密',
            'sha1_hash': '加密',
            'sha256_hash': '加密',
            'sha512_hash': '加密',
            'hash_comparison': '加密',
            'aes_encrypt': '加密',
            'aes_decrypt': '加密',
            'jwt_decode': '加密',
            'password_strength': '加密',
            'generate_salt': '加密',
            'generate_expression': 'Crontab',
            'parse_expression': 'Crontab',
            'get_next_runs': 'Crontab',
            'validate_expression': 'Crontab',
            'timestamp': '时间日期',
            'timestamp_sec': '时间日期',
            'datetime': '时间日期',
            'date': '时间日期',
            'time': '时间日期',
            'date_offset': '时间日期',
        }
        
        # 生成变量函数列表
        variable_functions = []
        
        # 从工具列表生成函数信息
        for tool in tool_list:
            tool_name = tool['name']
            if tool_name in syntax_templates:
                variable_functions.append({
                    'name': tool_name,
                    'syntax': syntax_templates[tool_name],
                    'desc': tool.get('description', '无描述'),
                    'example': example_templates.get(tool_name, syntax_templates[tool_name]),
                    'category': category_map.get(tool_name, '其他')
                })
        
        # 添加时间日期函数
        time_functions = ['timestamp', 'timestamp_sec', 'datetime', 'date', 'time', 'date_offset']
        time_function_descriptions = {
            'timestamp': '获取当前时间戳（毫秒）',
            'timestamp_sec': '获取当前时间戳（秒）',
            'datetime': '获取当前日期时间，支持自定义格式',
            'date': '获取当前日期，支持自定义格式',
            'time': '获取当前时间，支持自定义格式',
            'date_offset': '获取偏移后的日期时间，支持自定义格式'
        }
        for func_name in time_functions:
            if func_name not in [f['name'] for f in variable_functions]:
                variable_functions.append({
                    'name': func_name,
                    'syntax': syntax_templates[func_name],
                    'desc': time_function_descriptions[func_name],
                    'example': example_templates.get(func_name, syntax_templates[func_name]),
                    'category': '时间日期'
                })
        
        # 缓存结果，30分钟过期（静态数据）
        cache.set(cache_key, variable_functions, 1800)

        return Response(variable_functions)
