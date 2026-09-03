# -*- coding: utf-8 -*-
"""APP exploratory testing task views."""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.conf import settings
from django.db import close_old_connections
from django.http import HttpResponse
from django.utils.dateparse import parse_datetime
import io
import json
import logging
import os
import subprocess
import sys
import threading
import uuid
import zipfile

from .test_case_views import AppPagination
from ..models import (
    AppExplorationRun,
    AppExplorationTask,
    AppInspectionReviewRule,
    AppInspectionTargetResult,
    AppPageNode,
    AppPageTransition,
)
from ..serializers import AppExplorationTaskSerializer, AppTestCaseSerializer
from ..utils.exploration_ai_advisor import analyze_exploration_with_ai, sanitize_ai_controlled_task_overrides
from ..utils.exploration_assets import build_exploration_insights, convert_exploration_to_test_case
from ..utils.execution_precheck import build_precheck_error_message, run_execution_precheck


logger = logging.getLogger(__name__)


def _run_exploration_task_locally(task_id: int, run_id: int) -> None:
    """Execute exploration in the Django dev process when Celery/Redis is unavailable."""
    close_old_connections()
    try:
        from ..tasks import execute_app_exploration_task

        logger.info('Starting local APP exploration task: task=%s run=%s', task_id, run_id)
        execute_app_exploration_task.run(task_id, run_id)
    except Exception as exc:
        logger.exception(
            'Local APP exploration task failed before task handler captured it: task=%s run=%s',
            task_id,
            run_id,
        )
        try:
            task = AppExplorationTask.objects.filter(id=task_id).first()
            run = AppExplorationRun.objects.filter(id=run_id).first()
            if task:
                task.status = 'error'
                task.result = 'failed'
                task.error_message = str(exc)
                task.finished_at = timezone.now()
                task.save(update_fields=['status', 'result', 'error_message', 'finished_at', 'updated_at'])
            if run:
                run.status = 'error'
                run.result = 'failed'
                run.error_message = str(exc)
                run.finished_at = timezone.now()
                run.save(update_fields=['status', 'result', 'error_message', 'finished_at', 'updated_at'])
        except Exception:
            logger.exception('Failed to persist local APP exploration failure: task=%s run=%s', task_id, run_id)
    finally:
        close_old_connections()


def _run_exploration_consistency_locally(task_id: int, run_ids: list[int]) -> None:
    """Execute a controlled inspection task multiple times for consistency checks."""
    close_old_connections()
    try:
        from ..tasks import execute_app_exploration_task

        total = len(run_ids)
        for index, run_id in enumerate(run_ids, 1):
            task = AppExplorationTask.objects.filter(id=task_id).first()
            if not task or task.status == 'stopped':
                break
            summary = dict(task.summary or {})
            summary.update({
                'current_stage': f'三次一致性验证 {index}/{total}：等待执行',
                'consistency_batch_total': total,
                'consistency_batch_index': index,
                'consistency_batch_run_ids': run_ids,
            })
            task.summary = summary
            task.save(update_fields=['summary', 'updated_at'])
            logger.info('Starting local APP exploration consistency run: task=%s run=%s index=%s/%s', task_id, run_id, index, total)
            result = execute_app_exploration_task.run(task_id, run_id)
            if isinstance(result, dict) and result.get('success') is False:
                break
    except Exception as exc:
        logger.exception('Local APP exploration consistency batch failed: task=%s runs=%s', task_id, run_ids)
        _mark_consistency_batch_failed(task_id, run_ids, str(exc))
    finally:
        close_old_connections()


def _mark_consistency_batch_failed(task_id: int, run_ids: list[int], error_message: str) -> None:
    """Persist a visible failure instead of leaving consistency runs pending forever."""
    finished_at = timezone.now()
    task = AppExplorationTask.objects.filter(id=task_id).first()
    if task:
        summary = dict(task.summary or {})
        summary.update({
            'current_stage': '三次一致性验证执行失败',
            'consistency_batch_run_ids': run_ids,
            'consistency_batch_error': error_message,
        })
        task.status = 'error'
        task.result = 'failed'
        task.error_message = error_message
        task.finished_at = finished_at
        if task.started_at:
            task.duration = (finished_at - task.started_at).total_seconds()
        task.summary = summary
        task.save(update_fields=['status', 'result', 'error_message', 'finished_at', 'duration', 'summary', 'updated_at'])

    for run in AppExplorationRun.objects.filter(id__in=run_ids, status__in=['pending', 'running']):
        run.status = 'error'
        run.result = 'failed'
        run.error_message = error_message
        run.finished_at = finished_at
        if run.started_at:
            run.duration = (finished_at - run.started_at).total_seconds()
        summary = dict(run.summary or {})
        summary.update({
            'current_stage': '三次一致性验证执行失败',
            'consistency_batch_error': error_message,
        })
        run.summary = summary
        run.save(update_fields=['status', 'result', 'error_message', 'finished_at', 'duration', 'summary', 'updated_at'])


def _start_consistency_subprocess(task_id: int, run_ids: list[int], task_identifier: str) -> None:
    """Start consistency execution outside the request thread in local debug mode."""
    log_path = os.path.join(settings.BASE_DIR, 'django-app-exploration-consistency.log')
    err_path = os.path.join(settings.BASE_DIR, 'django-app-exploration-consistency.err.log')
    command = [
        sys.executable,
        'manage.py',
        'run_app_exploration_consistency',
        str(task_id),
        ','.join(str(item) for item in run_ids),
        '--task-identifier',
        task_identifier,
    ]
    try:
        stdout_handle = open(log_path, 'a', encoding='utf-8')
        stderr_handle = open(err_path, 'a', encoding='utf-8')
        subprocess.Popen(
            command,
            cwd=settings.BASE_DIR,
            stdout=stdout_handle,
            stderr=stderr_handle,
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
    except Exception as exc:
        logger.exception('Failed to start local APP exploration consistency subprocess: task=%s runs=%s', task_id, run_ids)
        _mark_consistency_batch_failed(task_id, run_ids, str(exc))


def _run_ai_analysis_locally(task_id: int, force: bool = False) -> None:
    """Run AI report analysis in the Django dev process when Celery/Redis is unavailable."""
    close_old_connections()
    try:
        from ..tasks import analyze_app_exploration_task

        logger.info('Starting local APP exploration AI analysis: task=%s force=%s', task_id, force)
        analyze_app_exploration_task.run(task_id, force)
    except Exception as exc:
        logger.exception('Local APP exploration AI analysis failed: task=%s', task_id)
        try:
            task = AppExplorationTask.objects.filter(id=task_id).first()
            if task:
                summary = dict(task.summary or {})
                summary.update({
                    'ai_analysis_status': 'failed',
                    'ai_analysis_stage': '分析失败',
                    'ai_analysis_message': 'AI 分析失败',
                    'ai_analysis_error': str(exc),
                    'ai_analysis_finished_at': timezone.now().isoformat(),
                })
                task.summary = summary
                task.save(update_fields=['summary', 'updated_at'])
        except Exception:
            logger.exception('Failed to persist local APP exploration AI analysis failure: task=%s', task_id)
    finally:
        close_old_connections()


def _is_stale_ai_analysis(summary: dict, timeout_seconds: int = 120) -> bool:
    status_value = summary.get('ai_analysis_status')
    if status_value not in ('queued', 'running'):
        return False
    raw_started_at = summary.get('ai_analysis_started_at') or ''
    started_at = parse_datetime(str(raw_started_at)) if raw_started_at else None
    if not started_at:
        return True
    if timezone.is_naive(started_at):
        started_at = timezone.make_aware(started_at, timezone.get_current_timezone())
    return (timezone.now() - started_at).total_seconds() > timeout_seconds


class AppExplorationTaskViewSet(viewsets.ModelViewSet):
    """Manage rule-based exploratory testing tasks."""

    queryset = AppExplorationTask.objects.select_related(
        'project',
        'app_package',
        'device',
        'created_by',
        'source_task',
    ).prefetch_related('steps')
    serializer_class = AppExplorationTaskSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = AppPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['status', 'result', 'project', 'app_package', 'device']
    search_fields = ['name', 'objective', 'device__device_id', 'device__name', 'app_package__name', 'app_package__package_name']

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_superuser:
            return queryset
        return queryset.filter(created_by=user)

    def perform_create(self, serializer):
        overrides = sanitize_ai_controlled_task_overrides(serializer.validated_data)
        serializer.save(created_by=self.request.user, **overrides)

    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        task = self.get_object()
        if task.status == 'running':
            return Response({'success': False, 'message': '任务正在执行中'}, status=status.HTTP_400_BAD_REQUEST)
        if not task.device:
            return Response({'success': False, 'message': '请先选择执行设备'}, status=status.HTTP_400_BAD_REQUEST)
        if task.device.status == 'locked' and task.device.locked_by != request.user:
            return Response({'success': False, 'message': '设备已被其他用户锁定'}, status=status.HTTP_400_BAD_REQUEST)

        package_name = task.app_package.package_name if task.app_package else ''
        precheck = run_execution_precheck(task.device, package_name=package_name)
        if not precheck.get('can_submit'):
            return Response({
                'success': False,
                'message': build_precheck_error_message(precheck),
                'precheck': precheck,
            }, status=status.HTTP_400_BAD_REQUEST)

        task.status = 'pending'
        task.result = None
        task.progress = 0
        task.total_steps = 0
        task.explored_pages = 0
        task.issue_count = 0
        task.summary = {'current_stage': '任务已提交，等待执行批次启动'}
        task.error_message = ''
        task.started_at = None
        task.finished_at = None
        task.duration = 0
        task.save()

        run = AppExplorationRun.objects.create(
            task=task,
            device=task.device,
            app_package=task.app_package,
            status='pending',
            strategy=task.strategy or 'rule_mvp',
            summary={'current_stage': '任务已提交，等待执行批次启动'},
        )

        from ..tasks import execute_app_exploration_task
        task_identifier = ''
        if settings.DEBUG:
            task_identifier = f'local-thread-{uuid.uuid4().hex}'
            thread = threading.Thread(
                target=_run_exploration_task_locally,
                args=(task.id, run.id),
                name=f'app-exploration-{task.id}-{run.id}',
                daemon=False,
            )
            thread.start()
        else:
            celery_task = execute_app_exploration_task.delay(task.id, run.id)
            task_identifier = celery_task.id
        task.task_id = task_identifier
        run.celery_task_id = task_identifier
        task.save(update_fields=['task_id', 'updated_at'])
        run.save(update_fields=['celery_task_id', 'updated_at'])

        return Response({
            'success': True,
            'message': '探索任务已提交',
            'data': AppExplorationTaskSerializer(task, context={'request': request}).data,
            'run_id': run.id,
        })

    @action(detail=True, methods=['post'], url_path='run-consistency')
    def run_consistency(self, request, pk=None):
        """Run the same target-inspection task three times to build a stability baseline."""
        task = self.get_object()
        if task.strategy != 'target_inspection':
            return Response({'success': False, 'message': '三次一致性验证只支持目标巡检任务'}, status=status.HTTP_400_BAD_REQUEST)
        if task.status in ('pending', 'running'):
            return Response({'success': False, 'message': '任务正在执行中，请完成或停止后再发起一致性验证'}, status=status.HTTP_400_BAD_REQUEST)
        if not task.device:
            return Response({'success': False, 'message': '请先选择执行设备'}, status=status.HTTP_400_BAD_REQUEST)
        if task.device.status == 'locked' and task.device.locked_by != request.user:
            return Response({'success': False, 'message': '设备已被其他用户锁定'}, status=status.HTTP_400_BAD_REQUEST)

        package_name = task.app_package.package_name if task.app_package else ''
        precheck = run_execution_precheck(task.device, package_name=package_name)
        if not precheck.get('can_submit'):
            return Response({
                'success': False,
                'message': build_precheck_error_message(precheck),
                'precheck': precheck,
            }, status=status.HTTP_400_BAD_REQUEST)

        requested_count = request.data.get('run_count') or 3
        try:
            run_count = max(2, min(int(requested_count), 5))
        except (TypeError, ValueError):
            run_count = 3

        task.status = 'pending'
        task.result = None
        task.progress = 0
        task.total_steps = 0
        task.explored_pages = 0
        task.issue_count = 0
        task.error_message = ''
        task.started_at = None
        task.finished_at = None
        task.duration = 0
        task.summary = {
            'current_stage': f'三次一致性验证已提交，准备执行 1/{run_count}',
            'consistency_batch_total': run_count,
            'consistency_batch_index': 0,
        }
        task.save()

        runs = [
            AppExplorationRun.objects.create(
                task=task,
                device=task.device,
                app_package=task.app_package,
                status='pending',
                strategy=task.strategy or 'target_inspection',
                summary={
                    'current_stage': f'三次一致性验证排队中：{index}/{run_count}',
                    'consistency_batch_total': run_count,
                    'consistency_batch_index': index,
                },
            )
            for index in range(1, run_count + 1)
        ]
        run_ids = [run.id for run in runs]

        task_identifier = ''
        if settings.DEBUG:
            task_identifier = f'local-consistency-{uuid.uuid4().hex}'
        else:
            from ..tasks import execute_app_exploration_task
            from celery import chain
            celery_task = chain(
                *[execute_app_exploration_task.si(task.id, run.id) for run in runs]
            ).apply_async()
            task_identifier = celery_task.id
            for run in runs:
                run.celery_task_id = task_identifier
                run.save(update_fields=['celery_task_id', 'updated_at'])

        task.task_id = task_identifier
        task.summary = {
            **(task.summary or {}),
            'consistency_batch_run_ids': run_ids,
        }
        task.save(update_fields=['task_id', 'summary', 'updated_at'])
        for run in runs:
            if not run.celery_task_id:
                run.celery_task_id = task_identifier
                run.save(update_fields=['celery_task_id', 'updated_at'])

        if settings.DEBUG:
            _start_consistency_subprocess(task.id, run_ids, task_identifier)

        return Response({
            'success': True,
            'message': f'三次一致性验证已提交，将连续执行 {run_count} 轮',
            'data': AppExplorationTaskSerializer(task, context={'request': request}).data,
            'run_ids': run_ids,
        })

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        task = self.get_object()
        if task.status not in ('pending', 'running'):
            return Response({'success': False, 'message': '只能停止等待中或执行中的任务'}, status=status.HTTP_400_BAD_REQUEST)

        if task.task_id:
            try:
                from celery import current_app
                current_app.control.revoke(task.task_id, terminate=True, signal='SIGTERM')
            except Exception:
                # The runner also checks task.status before each step, so revoke
                # failure should not block a user-requested stop.
                pass

        task.status = 'stopped'
        task.finished_at = timezone.now()
        if task.started_at:
            task.duration = (task.finished_at - task.started_at).total_seconds()
        task.save(update_fields=['status', 'finished_at', 'duration', 'updated_at'])
        latest_run = task.latest_run()
        if latest_run and latest_run.status in ('pending', 'running'):
            latest_run.status = 'stopped'
            latest_run.finished_at = task.finished_at
            if latest_run.started_at:
                latest_run.duration = (latest_run.finished_at - latest_run.started_at).total_seconds()
            latest_run.save(update_fields=['status', 'finished_at', 'duration', 'updated_at'])
        return Response({'success': True, 'message': '探索任务已停止'})

    @action(detail=True, methods=['get'])
    def report(self, request, pk=None):
        task = self.get_object()
        data = AppExplorationTaskSerializer(task, context={'request': request}).data
        data['insights'] = build_exploration_insights(task)
        data['logcat'] = _exploration_logcat_summary(task, request)
        data['iteration'] = _build_exploration_iteration(task)
        data['page_map_assets'] = _build_page_map_assets(task)
        return Response({'success': True, 'data': data})

    @action(detail=True, methods=['get'], url_path='page-map-assets')
    def page_map_assets(self, request, pk=None):
        """Return persisted page-map assets for this exploration task."""
        task = self.get_object()
        return Response({'success': True, 'data': _build_page_map_assets(task)})

    @action(detail=True, methods=['post'], url_path='ai-analyze')
    def ai_analyze(self, request, pk=None):
        """Use the configured LLM to analyze an existing exploration report."""
        task = self.get_object()
        if task.status in ('pending', 'running'):
            return Response({
                'success': False,
                'message': '探索任务尚未结束，请执行完成后再进行 AI 分析',
            }, status=status.HTTP_400_BAD_REQUEST)

        force = bool(request.data.get('force'))
        summary = task.summary or {}
        if summary.get('ai_analysis') and not force:
            return Response({
                'success': True,
                'message': '已返回缓存的 AI 分析结果',
                'data': summary['ai_analysis'],
            })
        if summary.get('ai_analysis_status') in ('queued', 'running') and not force and not _is_stale_ai_analysis(summary):
            return Response({
                'success': True,
                'message': summary.get('ai_analysis_message') or 'AI 分析任务正在执行中',
                'data': {
                    'status': summary.get('ai_analysis_status'),
                    'stage': summary.get('ai_analysis_stage') or '等待分析',
                    'message': summary.get('ai_analysis_message') or '',
                },
            }, status=status.HTTP_202_ACCEPTED)

        summary = dict(summary)
        if force:
            summary.pop('ai_analysis', None)
        initial_stage = '构建报告上下文' if settings.DEBUG else '等待分析'
        initial_message = '正在本地后台整理探索报告、步骤和页面证据' if settings.DEBUG else 'AI 分析任务已提交，正在排队处理'
        summary.update({
            'ai_analysis_status': 'running' if settings.DEBUG else 'queued',
            'ai_analysis_stage': initial_stage,
            'ai_analysis_message': initial_message,
            'ai_analysis_error': '',
            'ai_analysis_started_at': timezone.now().isoformat(),
            'ai_analysis_finished_at': '',
        })
        task.summary = summary
        task.save(update_fields=['summary', 'updated_at'])

        task_identifier = ''
        if settings.DEBUG:
            task_identifier = f'local-ai-analysis-{uuid.uuid4().hex}'
            thread = threading.Thread(
                target=_run_ai_analysis_locally,
                args=(task.id, force),
                name=f'app-exploration-ai-{task.id}',
                daemon=True,
            )
            thread.start()
        else:
            try:
                from ..tasks import analyze_app_exploration_task
                celery_task = analyze_app_exploration_task.delay(task.id, force)
                task_identifier = celery_task.id
            except Exception as exc:
                logger.exception('APP探索 AI 分析提交 Celery 失败，改为本地线程执行: task=%s', task.id)
                summary = dict(task.summary or {})
                summary.update({
                    'ai_analysis_status': 'queued',
                    'ai_analysis_stage': '本地兜底执行',
                    'ai_analysis_message': '队列服务不可用，已改为本地后台执行 AI 分析',
                    'ai_analysis_error': '',
                })
                task.summary = summary
                task.save(update_fields=['summary', 'updated_at'])
                task_identifier = f'local-ai-analysis-{uuid.uuid4().hex}'
                thread = threading.Thread(
                    target=_run_ai_analysis_locally,
                    args=(task.id, force),
                    name=f'app-exploration-ai-{task.id}',
                    daemon=True,
                )
                thread.start()

        return Response({
            'success': True,
            'message': 'AI 分析任务已提交，可以先查看报告其他内容，完成后会自动刷新',
            'data': {
                'status': 'running' if settings.DEBUG else 'queued',
                'stage': initial_stage,
                'message': initial_message,
                'task_id': task_identifier,
            },
        }, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=['post'], url_path='review-issue')
    def review_issue(self, request, pk=None):
        """Persist human review result for an exploration issue."""
        task = self.get_object()
        step_index = int(request.data.get('step_index') or 0)
        resolution = str(request.data.get('resolution') or '').strip()
        note = str(request.data.get('note') or '').strip()
        allowed = {'valid_issue', 'normal_behavior', 'rule_exception', 'needs_assertion', 'ignore'}
        if step_index <= 0:
            return Response({'success': False, 'message': '缺少有效步骤序号'}, status=status.HTTP_400_BAD_REQUEST)
        if resolution not in allowed:
            return Response({'success': False, 'message': '不支持的复核结果'}, status=status.HTTP_400_BAD_REQUEST)

        latest_run = task.latest_run()
        step_queryset = task.steps.filter(run=latest_run) if latest_run else task.steps.filter(run__isnull=True)
        step = step_queryset.filter(step_index=step_index).first()
        if not step:
            return Response({'success': False, 'message': '未找到对应步骤'}, status=status.HTTP_404_NOT_FOUND)

        summary = dict(task.summary or {})
        reviews = summary.get('issue_reviews') if isinstance(summary.get('issue_reviews'), dict) else {}
        reviews[str(step_index)] = {
            'step_index': step_index,
            'resolution': resolution,
            'note': note or _default_issue_review_note(resolution),
            'reviewed_at': timezone.now().isoformat(),
            'reviewed_by': request.user.username,
            'target': {
                'text': step.target_text,
                'resource_id': step.target_resource_id,
                'class_name': step.target_class,
                'bounds': step.bounds,
            },
        }
        summary['issue_reviews'] = reviews

        if resolution in {'normal_behavior', 'rule_exception', 'needs_assertion'}:
            rules = summary.get('issue_review_rules') if isinstance(summary.get('issue_review_rules'), list) else []
            rule = _build_issue_review_rule(step, resolution, note)
            key = (rule.get('issue_type'), rule.get('target_type'), rule.get('target_value'))
            if key[2] and not any((item.get('issue_type'), item.get('target_type'), item.get('target_value')) == key for item in rules if isinstance(item, dict)):
                rules.append(rule)
            summary['issue_review_rules'] = rules

        task.summary = summary
        task.save(update_fields=['summary', 'updated_at'])
        return Response({
            'success': True,
            'message': '问题复核结果已保存',
            'data': build_exploration_insights(task),
        })

    @action(detail=True, methods=['post'], url_path='review-target')
    def review_target(self, request, pk=None):
        """Persist human review result for one controlled-inspection target."""
        task = self.get_object()
        resolution = str(request.data.get('resolution') or '').strip()
        note = str(request.data.get('note') or '').strip()
        allowed = {
            'valid_issue',
            'normal_behavior',
            'element_needs_update',
            'target_should_remove',
            'wrong_start_page',
            'rule_exception',
        }
        if resolution not in allowed:
            return Response({'success': False, 'message': '不支持的目标复核结果'}, status=status.HTTP_400_BAD_REQUEST)

        target_result = _find_review_target_result(task, request.data)
        if not target_result:
            return Response({'success': False, 'message': '未找到对应目标结果'}, status=status.HTTP_404_NOT_FOUND)

        default_note = _default_target_review_note(resolution)
        target_result.review_resolution = resolution
        target_result.review_note = note or default_note
        target_result.review_context = {
            'status': target_result.status,
            'target_name': target_result.target_name,
            'step_index': target_result.step.step_index if target_result.step_id and target_result.step else None,
            'bounds': target_result.bounds,
            'review_source': 'target_inspection_matrix',
        }
        target_result.reviewed_by = request.user
        target_result.reviewed_at = timezone.now()
        target_result.save(update_fields=[
            'review_resolution',
            'review_note',
            'review_context',
            'reviewed_by',
            'reviewed_at',
            'updated_at',
        ])

        if resolution in {'normal_behavior', 'rule_exception', 'target_should_remove'}:
            rule = AppInspectionReviewRule.objects.filter(
                task=task,
                target_name=target_result.target_name,
                status=target_result.status,
            ).order_by('-updated_at').first()
            if rule:
                rule.resolution = resolution
                rule.note = note or default_note
                rule.enabled = True
                rule.created_from_result = target_result
                rule.created_by = request.user
                rule.save(update_fields=[
                    'resolution',
                    'note',
                    'enabled',
                    'created_from_result',
                    'created_by',
                    'updated_at',
                ])
            else:
                AppInspectionReviewRule.objects.create(
                    task=task,
                    target_name=target_result.target_name,
                    status=target_result.status,
                    resolution=resolution,
                    note=note or default_note,
                    enabled=True,
                    created_from_result=target_result,
                    created_by=request.user,
                )

        return Response({
            'success': True,
            'message': '目标复核结果已保存',
            'data': AppExplorationTaskSerializer(task, context={'request': request}).data,
        })

    @action(detail=True, methods=['get'], url_path='download-logcat')
    def download_logcat(self, request, pk=None):
        task = self.get_object()
        files = _find_exploration_logcat_files(task.id)
        if not files:
            return Response({
                'success': False,
                'message': '该探索任务暂无 logcat 文件，可能任务执行时未采集或日志已被清理。'
            }, status=status.HTTP_404_NOT_FOUND)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                'manifest.json',
                json.dumps({
                    'task_id': task.id,
                    'task_name': task.name,
                    'status': task.status,
                    'result': task.result,
                    'device_name': task.device_name,
                    'started_at': task.started_at.isoformat() if task.started_at else '',
                    'finished_at': task.finished_at.isoformat() if task.finished_at else '',
                    'note': 'logcat_summary 为崩溃/异常关键日志摘要，logcat 为完整日志。',
                }, ensure_ascii=False, indent=2),
            )
            for path in files:
                archive.write(path, os.path.basename(path))

        buffer.seek(0)
        filename = f"qaflow_exploration_{task.id}_logcat.zip"
        response = HttpResponse(buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = str(buffer.getbuffer().nbytes)
        return response

    @action(detail=True, methods=['post'], url_path='convert-to-case')
    def convert_to_case(self, request, pk=None):
        """Convert an exploration path to a normal APP UI Flow test case draft."""
        task = self.get_object()
        if task.status == 'running':
            return Response({'success': False, 'message': '任务执行中，结束后再转为用例草稿'}, status=status.HTTP_400_BAD_REQUEST)

        name = str(request.data.get('name') or '').strip()
        description = str(request.data.get('description') or '').strip()
        try:
            test_case, ui_flow = convert_exploration_to_test_case(
                task=task,
                user=request.user,
                name=name,
                description=description,
            )
            return Response({
                'success': True,
                'message': '已生成用例草稿',
                'data': {
                    'test_case': AppTestCaseSerializer(test_case).data,
                    'step_count': len(ui_flow),
                    'ui_flow': ui_flow,
                },
            })
        except ValueError as exc:
            return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


def _find_exploration_logcat_files(task_id):
    results_dir = os.path.join(
        settings.MEDIA_ROOT,
        'app-automation',
        'explorations',
        f'task_{task_id}',
    )
    if not os.path.isdir(results_dir):
        return []

    files = []
    for name in os.listdir(results_dir):
        lower_name = name.lower()
        if 'logcat' not in lower_name or not lower_name.endswith('.txt'):
            continue
        path = os.path.abspath(os.path.join(results_dir, name))
        if os.path.isfile(path) and path.startswith(os.path.abspath(results_dir)):
            files.append(path)
    return sorted(files)


def _build_page_map_assets(task):
    summary = task.summary or {}
    page_map = summary.get('page_map') if isinstance(summary.get('page_map'), list) else []
    signatures = [
        str(item.get('signature') or '').strip()
        for item in page_map
        if isinstance(item, dict) and str(item.get('signature') or '').strip()
    ]
    if not signatures:
        return {
            'stats': summary.get('page_map_persistence') or {},
            'nodes': [],
            'transitions': [],
        }

    nodes = list(
        AppPageNode.objects
        .filter(
            project=task.project,
            app_package=task.app_package,
            platform='android',
            page_signature__in=signatures,
        )
        .prefetch_related('elements')
        .order_by('-updated_at')
    )
    node_by_id = {node.id: node for node in nodes}
    node_payload = []
    for node in nodes:
        elements = list(node.elements.order_by('-clickable', 'role', 'id')[:20])
        node_payload.append({
            'id': node.id,
            'title': node.business_name or node.title,
            'activity': node.activity,
            'page_signature': node.page_signature,
            'semantic_signature': node.semantic_signature,
            'representative_screenshot': node.representative_screenshot,
            'visit_count': node.visit_count,
            'element_count': node.elements.count(),
            'elements': [
                {
                    'id': element.id,
                    'text': element.text,
                    'content_desc': element.content_desc,
                    'resource_id': element.resource_id,
                    'class_name': element.class_name,
                    'role': element.role,
                    'bounds': element.bounds,
                    'normalized_bounds': element.normalized_bounds,
                    'clickable': element.clickable,
                    'risk_level': element.risk_level,
                    'seen_count': element.seen_count,
                }
                for element in elements
            ],
        })

    transitions = []
    transition_queryset = AppPageTransition.objects.filter(
        from_page_id__in=node_by_id.keys(),
        to_page_id__in=node_by_id.keys(),
    ).select_related('from_page', 'to_page').order_by('-confidence', '-updated_at')[:80]
    for transition in transition_queryset:
        transitions.append({
            'id': transition.id,
            'from_page': transition.from_page.business_name or transition.from_page.title,
            'to_page': transition.to_page.business_name or transition.to_page.title,
            'action_type': transition.action_type,
            'trigger_text': transition.trigger_text,
            'trigger_resource_id': transition.trigger_resource_id,
            'trigger_bounds': transition.trigger_bounds,
            'success_count': transition.success_count,
            'failure_count': transition.failure_count,
            'confidence': transition.confidence,
        })

    return {
        'stats': summary.get('page_map_persistence') or {},
        'nodes': node_payload,
        'transitions': transitions,
    }


def _build_exploration_iteration(task):
    source_task = task.source_task
    current_insights = build_exploration_insights(task)
    insight_cache = {task.id: current_insights}
    chain = _build_exploration_chain(task, insight_cache)
    chain_summary = _summarize_exploration_chain(chain)
    if not source_task:
        return {
            'has_source': False,
            'source_type': task.source_type or '',
            'source_summary': task.source_summary or {},
            'chain': chain,
            'chain_summary': chain_summary,
        }

    source_insights = build_exploration_insights(source_task)
    insight_cache[source_task.id] = source_insights
    current_metrics = _exploration_iteration_metrics(task, current_insights)
    source_metrics = _exploration_iteration_metrics(source_task, source_insights)

    return {
        'has_source': True,
        'source_type': task.source_type or '',
        'source_summary': task.source_summary or {},
        'source_task': {
            'id': source_task.id,
            'name': source_task.name,
            'status': source_task.status,
            'result': source_task.result,
            'created_at': source_task.created_at.isoformat() if source_task.created_at else '',
        },
        'current_metrics': current_metrics,
        'source_metrics': source_metrics,
        'diff': _exploration_iteration_diff(current_metrics, source_metrics),
        'chain': chain,
        'chain_summary': chain_summary,
    }


def _build_exploration_chain(task, insight_cache=None):
    insight_cache = insight_cache or {}
    chain = []
    current = task
    seen_ids = set()
    max_depth = 20

    while current and current.id not in seen_ids and len(chain) < max_depth:
        seen_ids.add(current.id)
        insights = insight_cache.get(current.id)
        if insights is None:
            insights = build_exploration_insights(current)
            insight_cache[current.id] = insights
        metrics = _exploration_iteration_metrics(current, insights)
        iteration_state = _exploration_iteration_state(current, metrics)
        chain.append({
            'id': current.id,
            'name': current.name,
            'status': current.status,
            'result': current.result,
            'source_type': current.source_type or '',
            'source_summary': current.source_summary or {},
            'created_at': current.created_at.isoformat() if current.created_at else '',
            'finished_at': current.finished_at.isoformat() if current.finished_at else '',
            'is_current': current.id == task.id,
            'iteration_state': iteration_state,
            'effective': iteration_state == 'effective',
            'metrics': metrics,
        })
        current = current.source_task

    chain.reverse()
    for index, item in enumerate(chain, start=1):
        item['round'] = index
    return chain


def _summarize_exploration_chain(chain):
    effective_nodes = [item for item in chain if item.get('effective')]
    ineffective_nodes = [item for item in chain if item.get('iteration_state') == 'empty_run']
    pending_nodes = [item for item in chain if item.get('iteration_state') == 'pending']
    error_nodes = [item for item in chain if item.get('iteration_state') == 'error']
    issue_nodes = [
        item for item in chain
        if int((item.get('metrics') or {}).get('issue_count') or 0) > 0
    ]
    latest_effective = effective_nodes[-1] if effective_nodes else None
    return {
        'total_attempts': len(chain),
        'effective_attempts': len(effective_nodes),
        'ineffective_attempts': len(ineffective_nodes),
        'pending_attempts': len(pending_nodes),
        'error_attempts': len(error_nodes),
        'issue_attempts': len(issue_nodes),
        'current_round': len(chain),
        'latest_effective_task': {
            'id': latest_effective.get('id'),
            'name': latest_effective.get('name'),
            'round': latest_effective.get('round'),
        } if latest_effective else None,
    }


def _exploration_iteration_state(task, metrics):
    status_value = (task.status or '').lower()
    if status_value in ('pending', 'running'):
        return 'pending'
    if status_value in ('error', 'failed'):
        return 'error'
    if status_value == 'stopped':
        return 'stopped'
    if int(metrics.get('total_steps') or 0) > 0 or int(metrics.get('explored_pages') or 0) > 0:
        return 'effective'
    if status_value == 'completed':
        return 'empty_run'
    return 'unknown'


def _exploration_iteration_metrics(task, insights):
    target_coverage = insights.get('target_coverage') or {}
    ai_analysis = (task.summary or {}).get('ai_analysis') or {}
    return {
        'total_steps': int(task.total_steps or 0),
        'explored_pages': int(task.explored_pages or 0),
        'issue_count': int(task.issue_count or 0),
        'duration': round(float(task.duration or 0), 1),
        'risk_level': insights.get('risk_level') or ai_analysis.get('risk_level') or '',
        'target_coverage_rate': float(target_coverage.get('rate') or 0),
        'target_covered': int(target_coverage.get('covered') or 0),
        'target_total': int(target_coverage.get('total') or 0),
    }


def _exploration_iteration_diff(current_metrics, source_metrics):
    numeric_fields = (
        'total_steps',
        'explored_pages',
        'issue_count',
        'duration',
        'target_coverage_rate',
        'target_covered',
    )
    return {
        field: round(current_metrics.get(field, 0) - source_metrics.get(field, 0), 2)
        for field in numeric_fields
    }


def _default_issue_review_note(resolution):
    return {
        'valid_issue': '人工复核为有效问题',
        'normal_behavior': '人工复核为正常业务行为，后续同类控件自动归档',
        'rule_exception': '人工复核为规则例外',
        'needs_assertion': '人工复核为需补充状态断言',
        'ignore': '人工复核后暂不处理',
    }.get(resolution, '人工复核')


def _default_target_review_note(resolution):
    return {
        'valid_issue': '人工复核为有效问题，保留在目标巡检报告中。',
        'normal_behavior': '人工复核为正常业务行为，后续同类目标自动归档。',
        'element_needs_update': '人工复核为元素定位需维护，建议补充或更新语义元素。',
        'target_should_remove': '人工复核为低价值或不适合巡检目标，建议从目标清单移除。',
        'wrong_start_page': '人工复核为起始页面不正确，建议调整起始导航后重跑。',
        'rule_exception': '人工复核为规则例外，后续同类目标自动归档。',
    }.get(resolution, '人工复核')


def _find_review_target_result(task, payload):
    result_id = payload.get('target_result_id') or payload.get('result_id') or payload.get('id')
    queryset = AppInspectionTargetResult.objects.select_related('step', 'reviewed_by').filter(task=task)
    if result_id:
        try:
            return queryset.get(id=int(result_id))
        except (TypeError, ValueError, AppInspectionTargetResult.DoesNotExist):
            return None

    latest_run = task.latest_run()
    target_name = str(payload.get('target_name') or '').strip()
    step_index = payload.get('step_index')
    if latest_run:
        queryset = queryset.filter(run=latest_run)
    if target_name:
        queryset = queryset.filter(target_name=target_name)
    if step_index:
        try:
            queryset = queryset.filter(step__step_index=int(step_index))
        except (TypeError, ValueError):
            pass
    return queryset.order_by('-id').first()


def _build_issue_review_rule(step, resolution, note=''):
    if step.target_resource_id:
        target_type = 'resource_id'
        target_value = step.target_resource_id
    elif step.target_class:
        target_type = 'class_name'
        target_value = step.target_class
    else:
        target_type = 'text'
        target_value = step.target_text
    return {
        'enabled': True,
        'resolution': resolution,
        'issue_type': step.issue_type,
        'target_type': target_type,
        'target_value': target_value,
        'note': note or _default_issue_review_note(resolution),
        'created_at': timezone.now().isoformat(),
    }


def _normalize_ai_analysis_error(exc):
    raw_message = str(exc) or repr(exc)
    lower_message = raw_message.lower()

    auth_keywords = (
        '401',
        'invalid token',
        'unauthorized',
        'authentication',
        'api key',
        'api_key',
        'invalid key',
        'incorrect key',
    )
    if any(keyword in lower_message for keyword in auth_keywords):
        return {
            'success': False,
            'error_type': 'model_auth_error',
            'message': 'AI 模型认证失败，请到配置中心的 AI 探索模型配置中检查 API Key 是否有效。',
            'detail': _short_error_detail(raw_message),
        }, status.HTTP_400_BAD_REQUEST

    if '429' in lower_message or 'rate limit' in lower_message or 'too many requests' in lower_message:
        return {
            'success': False,
            'error_type': 'model_rate_limited',
            'message': 'AI 模型请求过于频繁或额度不足，请稍后重试，或检查模型服务额度。',
            'detail': _short_error_detail(raw_message),
        }, status.HTTP_400_BAD_REQUEST

    if 'timeout' in lower_message or 'timed out' in lower_message:
        return {
            'success': False,
            'error_type': 'model_timeout',
            'message': 'AI 模型响应超时，请稍后重试；如果频繁出现，建议检查模型服务地址或网络。',
            'detail': _short_error_detail(raw_message),
        }, status.HTTP_400_BAD_REQUEST

    if '404' in lower_message and 'model' in lower_message:
        return {
            'success': False,
            'error_type': 'model_not_found',
            'message': 'AI 模型不可用，请检查模型名称、Base URL 和当前启用的模型配置。',
            'detail': _short_error_detail(raw_message),
        }, status.HTTP_400_BAD_REQUEST

    return {
        'success': False,
        'error_type': 'model_service_error',
        'message': 'AI 分析失败，模型服务暂时不可用，请检查模型配置或稍后重试。',
        'detail': _short_error_detail(raw_message),
    }, status.HTTP_400_BAD_REQUEST


def _short_error_detail(message, limit=300):
    text = str(message or '').strip()
    if len(text) <= limit:
        return text
    return f'{text[:limit]}...'


def _exploration_logcat_summary(task, request=None):
    files = _find_exploration_logcat_files(task.id)
    download_url = ''
    if files:
        path = f'/api/app-automation/exploration-tasks/{task.id}/download-logcat/'
        download_url = request.build_absolute_uri(path) if request else path
    return {
        'available': bool(files),
        'file_count': len(files),
        'download_url': download_url,
    }
