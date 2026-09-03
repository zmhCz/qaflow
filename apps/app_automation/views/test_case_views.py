# -*- coding: utf-8 -*-
"""APP测试用例管理视图"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.filters import SearchFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction
from django.db.models import Count, OuterRef, Q, Subquery
import logging

from ..models import (
    AppPackage,
    AppTestCase,
    AppTestCaseFolder,
    AppTestCaseTag,
    AppDevice,
    AppTestExecution,
    AppTestSuite,
    AppTestSuiteCase,
)
from ..serializers import (
    AppPackageSerializer,
    AppTestCaseSerializer,
    AppTestCaseFolderSerializer,
    AppTestCaseTagSerializer,
    AppTestExecutionSerializer,
)
from ..utils.execution_precheck import build_precheck_error_message, run_execution_precheck
from ..utils.task_dispatcher import dispatch_app_task

logger = logging.getLogger(__name__)


class AppPagination(PageNumberPagination):
    """APP自动化模块通用分页"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class AppPackageViewSet(viewsets.ModelViewSet):
    """APP应用包名管理 ViewSet"""
    queryset = AppPackage.objects.all()
    serializer_class = AppPackageSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = AppPagination
    search_fields = ['name', 'package_name']
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class AppTestCaseFolderViewSet(viewsets.ModelViewSet):
    """APP用例业务目录 ViewSet"""
    queryset = AppTestCaseFolder.objects.all()
    serializer_class = AppTestCaseFolderSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['project', 'parent']
    search_fields = ['name', 'description']

    def get_queryset(self):
        queryset = super().get_queryset().select_related('project', 'parent').annotate(total_cases=Count('test_cases'))
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return queryset.order_by('project_id', 'parent_id', 'order', 'id')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        folder = self.get_object()
        if folder.is_system:
            return Response({'success': False, 'message': '系统目录不允许删除'}, status=status.HTTP_400_BAD_REQUEST)
        if folder.children.exists():
            return Response({'success': False, 'message': '该目录下还有子目录，请先迁移或删除子目录'}, status=status.HTTP_400_BAD_REQUEST)
        if folder.test_cases.exists():
            return Response({'success': False, 'message': '该目录下还有用例，请先迁移用例后再删除'}, status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['get'], url_path='tree')
    def tree(self, request):
        project_id = request.query_params.get('project')
        folders = list(self.get_queryset())
        if project_id:
            folders = [item for item in folders if str(item.project_id) == str(project_id)]
        serialized = AppTestCaseFolderSerializer(folders, many=True, context=self.get_serializer_context()).data
        node_map = {item['id']: {**item, 'children': []} for item in serialized}
        roots = []
        for item in serialized:
            node = node_map[item['id']]
            parent_id = item.get('parent')
            if parent_id and parent_id in node_map:
                node_map[parent_id]['children'].append(node)
            else:
                roots.append(node)
        return Response({'success': True, 'data': roots})


class AppTestCaseTagViewSet(viewsets.ModelViewSet):
    """APP用例受控标签 ViewSet"""
    queryset = AppTestCaseTag.objects.all()
    serializer_class = AppTestCaseTagSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['project', 'is_active']
    search_fields = ['name', 'description']

    def get_queryset(self):
        queryset = super().get_queryset().select_related('project').annotate(total_cases=Count('test_cases'))
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return queryset.order_by('project_id', 'name')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class AppTestCaseViewSet(viewsets.ModelViewSet):
    """APP测试用例 ViewSet"""
    queryset = AppTestCase.objects.all()
    serializer_class = AppTestCaseSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = AppPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['project', 'app_package', 'case_type', 'priority', 'lifecycle_status', 'data_impact', 'source', 'maintainer']
    search_fields = ['name', 'description']

    def get_queryset(self):
        latest_execution = AppTestExecution.objects.filter(test_case=OuterRef('pk')).order_by('-created_at')
        queryset = (
            AppTestCase.objects.all()
            .select_related('project', 'app_package', 'folder', 'created_by', 'maintainer')
            .prefetch_related('tags', 'suite_memberships__test_suite')
            .annotate(
                latest_execution_status=Subquery(latest_execution.values('status')[:1]),
                latest_execution_result=Subquery(latest_execution.values('result')[:1]),
                latest_execution_finished_at=Subquery(latest_execution.values('finished_at')[:1]),
            )
        )

        params = self.request.query_params
        include_deprecated = params.get('include_deprecated') in {'1', 'true', 'yes'}
        if not include_deprecated:
            queryset = queryset.exclude(lifecycle_status='deprecated')

        folder_id = params.get('folder')
        include_children = params.get('include_children', '1') not in {'0', 'false', 'no'}
        if folder_id and include_children:
            folder_ids = self._folder_descendant_ids(folder_id)
            queryset = queryset.filter(folder_id__in=folder_ids)

        tag_ids = [item for item in str(params.get('tags') or '').split(',') if item.strip().isdigit()]
        if tag_ids:
            queryset = queryset.filter(tags__id__in=tag_ids).distinct()

        latest_result = params.get('latest_result')
        if latest_result:
            if latest_result == 'not_run':
                queryset = queryset.filter(latest_execution_status__isnull=True)
            elif latest_result in {'passed', 'failed', 'skipped'}:
                queryset = queryset.filter(latest_execution_result=latest_result)
            else:
                queryset = queryset.filter(latest_execution_status=latest_result)

        q = params.get('q') or ''
        if q:
            queryset = queryset.filter(Q(name__icontains=q) | Q(description__icontains=q) | Q(tags__name__icontains=q)).distinct()

        return queryset

    def _folder_descendant_ids(self, folder_id):
        try:
            root_id = int(folder_id)
        except (TypeError, ValueError):
            return []
        ids = {root_id}
        pending = [root_id]
        while pending:
            child_ids = list(AppTestCaseFolder.objects.filter(parent_id__in=pending).values_list('id', flat=True))
            child_ids = [item for item in child_ids if item not in ids]
            ids.update(child_ids)
            pending = child_ids
        return list(ids)
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, maintainer=serializer.validated_data.get('maintainer') or self.request.user)

    @action(detail=False, methods=['post'], url_path='batch-governance')
    def batch_governance(self, request):
        """批量治理用例资产属性。"""
        case_ids = request.data.get('case_ids') or []
        if not isinstance(case_ids, list) or not case_ids:
            return Response({'success': False, 'message': '请选择需要治理的用例'}, status=status.HTTP_400_BAD_REQUEST)
        if len(case_ids) > 500:
            return Response({'success': False, 'message': '单次最多处理 500 条用例'}, status=status.HTTP_400_BAD_REQUEST)

        allowed_fields = {'folder', 'case_type', 'priority', 'lifecycle_status', 'data_impact', 'source', 'maintainer'}
        updates = {field: request.data[field] for field in allowed_fields if field in request.data}
        tag_ids = request.data.get('tag_ids')
        tag_mode = request.data.get('tag_mode', 'replace')
        suite_id = request.data.get('suite_id')

        queryset = AppTestCase.objects.filter(id__in=case_ids)
        if not queryset.exists():
            return Response({'success': False, 'message': '未找到可处理的用例'}, status=status.HTTP_404_NOT_FOUND)

        project_ids = set(queryset.values_list('project_id', flat=True))
        if len(project_ids) > 1 and ('folder' in updates or isinstance(tag_ids, list) or suite_id):
            return Response({'success': False, 'message': '跨项目批量治理时不允许移动目录、处理标签或加入套件'}, status=status.HTTP_400_BAD_REQUEST)
        project_id = next(iter(project_ids)) if len(project_ids) == 1 else None

        if 'folder' in updates and updates['folder']:
            folder_exists = AppTestCaseFolder.objects.filter(id=updates['folder'], project_id=project_id).exists()
            if not folder_exists:
                return Response({'success': False, 'message': '目标目录不属于所选用例项目'}, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(tag_ids, list) and project_id:
            matched_count = AppTestCaseTag.objects.filter(id__in=tag_ids, project_id=project_id).count()
            if matched_count != len(set(tag_ids)):
                return Response({'success': False, 'message': '标签必须属于所选用例项目'}, status=status.HTTP_400_BAD_REQUEST)

        if suite_id:
            suite = AppTestSuite.objects.filter(id=suite_id).first()
            if not suite:
                return Response({'success': False, 'message': '目标套件不存在'}, status=status.HTTP_404_NOT_FOUND)
            if suite.project_id and project_id and suite.project_id != project_id:
                return Response({'success': False, 'message': '目标套件不属于所选用例项目'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            if updates:
                queryset.update(**updates)
            if isinstance(tag_ids, list):
                tags = list(AppTestCaseTag.objects.filter(id__in=tag_ids))
                for case in queryset.prefetch_related('tags'):
                    if tag_mode == 'append':
                        case.tags.add(*tags)
                    elif tag_mode == 'remove':
                        case.tags.remove(*tags)
                    else:
                        case.tags.set(tags)
            if suite_id:
                max_order = (
                    AppTestSuiteCase.objects.filter(test_suite=suite)
                    .order_by('-order')
                    .values_list('order', flat=True)
                    .first()
                )
                order = int(max_order if max_order is not None else -1) + 1
                for case in queryset.order_by('id'):
                    _, created = AppTestSuiteCase.objects.get_or_create(
                        test_suite=suite,
                        test_case=case,
                        defaults={'order': order},
                    )
                    if created:
                        order += 1

        return Response({'success': True, 'message': f'已处理 {queryset.count()} 条用例', 'updated_count': queryset.count()})

    @action(detail=False, methods=['get'], url_path='governance-options')
    def governance_options(self, request):
        def choices(values):
            return [{'value': value, 'label': label} for value, label in values]
        return Response({
            'success': True,
            'data': {
                'case_types': choices(AppTestCase.CASE_TYPE_CHOICES),
                'priorities': choices(AppTestCase.PRIORITY_CHOICES),
                'lifecycles': choices(AppTestCase.LIFECYCLE_CHOICES),
                'data_impacts': choices(AppTestCase.DATA_IMPACT_CHOICES),
                'sources': choices(AppTestCase.SOURCE_CHOICES),
            }
        })
    
    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        """执行测试用例"""
        test_case = self.get_object()
        device_id = request.data.get('device_id')
        execution_mode = request.data.get('execution_mode') or 'server'
        package_name = request.data.get('package_name') or (
            test_case.app_package.package_name if test_case.app_package else ''
        ) or (
            test_case.project.android_app_package.package_name
            if test_case.project and test_case.project.android_app_package else ''
        )
        
        if not device_id:
            return Response({
                'success': False,
                'message': '请选择执行设备'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # 检查设备是否可用
            device = AppDevice.objects.get(device_id=device_id)
            if device.status == 'locked' and device.locked_by != request.user:
                return Response({
                    'success': False,
                    'message': '设备已被其他用户锁定'
                }, status=status.HTTP_400_BAD_REQUEST)

            if execution_mode not in ('server', 'agent'):
                return Response({
                    'success': False,
                    'message': '执行模式不正确'
                }, status=status.HTTP_400_BAD_REQUEST)

            if execution_mode == 'server':
                precheck = run_execution_precheck(device, package_name=package_name)
                if not precheck.get('can_submit'):
                    return Response({
                        'success': False,
                        'message': build_precheck_error_message(precheck),
                        'precheck': precheck,
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # 创建执行记录
            execution = AppTestExecution.objects.create(
                test_case=test_case,
                device=device,
                user=request.user,
                status='pending',
                execution_mode=execution_mode,
            )

            if execution_mode == 'agent':
                execution.task_id = f'agent-pending-{execution.id}'
                execution.save(update_fields=['task_id'])
                return Response({
                    'success': True,
                    'message': '测试已提交到本地 Agent 队列，等待执行机领取',
                    'execution': AppTestExecutionSerializer(execution).data
                })
            
            # 调用 Celery 任务异步执行
            from ..tasks import execute_app_test_task
            task = dispatch_app_task(
                execute_app_test_task,
                execution.id,
                package_name=package_name,
                mark_execution_ids=[execution.id],
            )
            execution.task_id = task.id
            execution.save()
            
            logger.info(
                "测试已提交执行: execution_id=%s, task_id=%s, mode=%s",
                execution.id,
                task.id,
                task.mode,
            )
            
            return Response({
                'success': True,
                'message': '测试已提交执行' if not task.fallback_used else '队列不可用，已切换本机执行',
                'execution': AppTestExecutionSerializer(execution).data
            })
            
        except AppDevice.DoesNotExist:
            return Response({
                'success': False,
                'message': '设备不存在'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"执行测试失败: {str(e)}")
            return Response({
                'success': False,
                'message': f'执行测试失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
