# -*- coding: utf-8 -*-
"""APP自动化定时任务视图"""
import json
import logging

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone

from .test_case_views import AppPagination
from ..models import (
    AppScheduledTask, AppNotificationLog,
    AppTestSuite, AppTestCase, AppDevice,
)
from ..serializers import (
    AppScheduledTaskSerializer,
    AppNotificationLogSerializer,
)
from ..utils.execution_precheck import build_precheck_error_message, run_execution_precheck
from ..utils.task_dispatcher import dispatch_app_task

logger = logging.getLogger(__name__)


class AppScheduledTaskViewSet(viewsets.ModelViewSet):
    """APP定时任务视图集"""
    queryset = AppScheduledTask.objects.all()
    serializer_class = AppScheduledTaskSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = AppPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['task_type', 'status', 'trigger_type', 'project']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'next_run_time', 'last_run_time']
    ordering = ['-created_at']

    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        task = self.get_object()
        task.status = 'PAUSED'
        task.save(update_fields=['status'])
        return Response({'success': True, 'message': '任务已暂停'})

    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        task = self.get_object()
        task.status = 'ACTIVE'
        task.next_run_time = task.calculate_next_run()
        task.save(update_fields=['status', 'next_run_time'])
        return Response({'success': True, 'message': '任务已恢复'})

    @action(detail=True, methods=['post'])
    def run_now(self, request, pk=None):
        """立即运行任务"""
        task = self.get_object()

        try:
            if not task.device:
                return Response({'success': False, 'message': '该任务未配置执行设备'},
                                status=status.HTTP_400_BAD_REQUEST)

            device = task.device
            if device.status == 'locked' and device.locked_by != request.user:
                return Response({'success': False, 'message': '设备已被其他用户锁定'},
                                status=status.HTTP_400_BAD_REQUEST)

            package_name = task.app_package.package_name if task.app_package else ''
            if not package_name and task.test_case:
                package_name = (
                    task.test_case.app_package.package_name if task.test_case.app_package else ''
                ) or (
                    task.test_case.project.android_app_package.package_name
                    if task.test_case.project and task.test_case.project.android_app_package else ''
                )
            if not package_name and task.test_suite:
                package_name = (
                    task.test_suite.project.android_app_package.package_name
                    if task.test_suite.project and task.test_suite.project.android_app_package else ''
                )
                if not package_name:
                    first_suite_case = task.test_suite.suite_cases.select_related(
                        'test_case',
                        'test_case__app_package',
                        'test_case__project__android_app_package',
                    ).first()
                    if first_suite_case and first_suite_case.test_case:
                        first_case = first_suite_case.test_case
                        package_name = (
                            first_case.app_package.package_name if first_case.app_package else ''
                        ) or (
                            first_case.project.android_app_package.package_name
                            if first_case.project and first_case.project.android_app_package else ''
                        )
            precheck = run_execution_precheck(device, package_name=package_name)
            if not precheck.get('can_submit'):
                return Response({
                    'success': False,
                    'message': build_precheck_error_message(precheck),
                    'precheck': precheck,
                }, status=status.HTTP_400_BAD_REQUEST)

            # 更新统计
            task.last_run_time = timezone.now()
            task.total_runs += 1
            task.next_run_time = task.calculate_next_run()
            task.save()

            if task.task_type == 'TEST_SUITE':
                if not task.test_suite:
                    return Response({'success': False, 'message': '该任务未配置测试套件'},
                                    status=status.HTTP_400_BAD_REQUEST)

                suite_cases = task.test_suite.suite_cases.select_related('test_case').all()
                if not suite_cases.exists():
                    return Response({'success': False, 'message': '测试套件没有用例'},
                                    status=status.HTTP_400_BAD_REQUEST)

                # 创建执行记录并调用 Celery
                from ..models import AppTestExecution
                from ..tasks import execute_app_suite_task

                executions = []
                for sc in suite_cases:
                    execution = AppTestExecution.objects.create(
                        test_case=sc.test_case,
                        test_suite=task.test_suite,
                        device=device,
                        user=request.user,
                        status='pending'
                    )
                    executions.append(execution)

                task.test_suite.execution_status = 'running'
                task.test_suite.save(update_fields=['execution_status'])

                execution_ids = [e.id for e in executions]
                celery_task = dispatch_app_task(
                    execute_app_suite_task,
                    suite_id=task.test_suite.id,
                    execution_ids=execution_ids,
                    package_name=package_name,
                    scheduled_task_id=task.id,
                    mark_execution_ids=execution_ids,
                )

                return Response({
                    'success': True,
                    'message': (
                        f'测试套件开始执行，共 {len(executions)} 个用例'
                        if not celery_task.fallback_used
                        else f'队列不可用，已切换本机执行，共 {len(executions)} 个用例'
                    ),
                    'data': {'task_id': celery_task.id, 'test_case_count': len(executions)}
                })

            elif task.task_type == 'TEST_CASE':
                if not task.test_case:
                    return Response({'success': False, 'message': '该任务未配置测试用例'},
                                    status=status.HTTP_400_BAD_REQUEST)

                from ..models import AppTestExecution
                from ..tasks import execute_app_test_task

                execution = AppTestExecution.objects.create(
                    test_case=task.test_case,
                    device=device,
                    user=request.user,
                    status='pending'
                )
                celery_task = dispatch_app_task(
                    execute_app_test_task,
                    execution.id,
                    package_name=package_name,
                    scheduled_task_id=task.id,
                    mark_execution_ids=[execution.id],
                )
                execution.task_id = celery_task.id
                execution.save(update_fields=['task_id'])

                return Response({
                    'success': True,
                    'message': '测试用例开始执行' if not celery_task.fallback_used else '队列不可用，已切换本机执行',
                    'data': {'task_id': celery_task.id}
                })

            return Response({'success': False, 'message': '不支持的任务类型'},
                            status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f'执行定时任务失败: {str(e)}', exc_info=True)
            return Response({'success': False, 'message': f'执行失败: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AppNotificationLogViewSet(viewsets.ReadOnlyModelViewSet):
    """APP通知日志视图集（只读）"""
    queryset = AppNotificationLog.objects.all()
    serializer_class = AppNotificationLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = AppPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'notification_type']
    search_fields = ['task_name', 'notification_content']
    ordering_fields = ['created_at', 'sent_at']
    ordering = ['-created_at']

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        log = self.get_object()
        if log.status == 'failed':
            log.retry_count += 1
            log.is_retried = True
            log.save(update_fields=['retry_count', 'is_retried'])
            return Response({'success': True, 'message': '通知已加入重试队列'})
        return Response({'success': False, 'message': '只能重试失败的通知'},
                        status=status.HTTP_400_BAD_REQUEST)
