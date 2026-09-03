# -*- coding: utf-8 -*-
"""APP测试执行管理视图"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.filters import SearchFilter
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.http import FileResponse, Http404, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import logging
import os
import io
import json
import zipfile

from ..models import AppTestExecution
from ..serializers import AppTestExecutionSerializer
from ..tasks import send_execution_update
from ..utils.report_summary import build_execution_report_summary
from .test_case_views import AppPagination

logger = logging.getLogger(__name__)


class AppTestExecutionViewSet(viewsets.ModelViewSet):
    """APP测试执行记录 ViewSet"""
    queryset = AppTestExecution.objects.all()
    serializer_class = AppTestExecutionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['status', 'test_case', 'device']
    search_fields = ['test_case__name', 'device__name', 'device__device_id', 'user__username']
    pagination_class = AppPagination
    
    def get_queryset(self):
        queryset = super().get_queryset()

        # 支持 test_suite__isnull 过滤，用于区分单独执行和套件执行
        suite_isnull = self.request.query_params.get('test_suite__isnull')
        if suite_isnull is not None:
            queryset = queryset.filter(test_suite__isnull=(suite_isnull.lower() in ('true', '1')))

        # 支持按项目间接过滤（通过 test_case.project）
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(test_case__project_id=project_id)

        search_value = (self.request.query_params.get('search') or '').strip()
        if not search_value:
            return queryset
        return queryset.filter(
            Q(test_case__name__icontains=search_value) |
            Q(device__name__icontains=search_value) |
            Q(device__device_id__icontains=search_value) |
            Q(user__username__icontains=search_value)
        )
    
    @action(detail=False, methods=['get'])
    def ws_status(self, request):
        """检查 WebSocket 是否可用"""
        try:
            import daphne
            from channels.layers import get_channel_layer
            channel_layer = get_channel_layer()
            ws_available = channel_layer is not None and not isinstance(
                channel_layer, type(None)
            )
            # 检查是否通过 ASGI 服务器运行（非 runserver）
            server_type = request.META.get('SERVER_SOFTWARE', '')
            is_asgi = 'daphne' in server_type.lower() or request.META.get('asgi', False)
            return Response({'websocket': ws_available and is_asgi})
        except (ImportError, Exception):
            return Response({'websocket': False})

    @action(detail=True, methods=['get'], url_path='report-summary')
    def report_summary(self, request, pk=None):
        """返回团队可读报告摘要，并预生成企微机器人 Markdown。"""
        execution = self.get_object()
        summary = build_execution_report_summary(execution, request=request)
        return Response({
            'code': 0,
            'success': True,
            'data': summary,
        })

    @action(detail=True, methods=['get'], url_path='download-logcat')
    def download_logcat(self, request, pk=None):
        """导出执行期间采集的 logcat，方便提交缺陷给开发排查。"""
        execution = self.get_object()
        files = _find_logcat_files(execution.id)
        if not files:
            return Response({
                'success': False,
                'message': '该执行记录暂无 logcat 文件，可能执行时未采集或日志已被清理。'
            }, status=status.HTTP_404_NOT_FOUND)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            manifest = {
                'execution_id': execution.id,
                'case_name': execution.case_name,
                'device_name': execution.device_name,
                'status': execution.status,
                'result': execution.result,
                'started_at': execution.started_at.isoformat() if execution.started_at else '',
                'finished_at': execution.finished_at.isoformat() if execution.finished_at else '',
                'duration': execution.duration,
                'file_count': len(files),
                'note': 'logcat_summary 为崩溃/异常关键日志摘要，logcat 为完整日志。',
            }
            archive.writestr(
                'manifest.json',
                json.dumps(manifest, ensure_ascii=False, indent=2),
            )
            for path in files:
                arcname = os.path.basename(path)
                archive.write(path, arcname=arcname)

        buffer.seek(0)
        filename = f"qaflow_execution_{execution.id}_logcat.zip"
        response = HttpResponse(buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = str(buffer.getbuffer().nbytes)
        return response

    @action(detail=True, methods=['get'], url_path='download-evidence')
    def download_evidence(self, request, pk=None):
        """导出执行排障附件：Allure 原始结果、截图/XML/logcat 附件和 manifest。"""
        execution = self.get_object()
        files = _find_evidence_files(execution.id)
        if not files:
            return Response({
                'success': False,
                'message': '该执行记录暂无可导出的排障附件。'
            }, status=status.HTTP_404_NOT_FOUND)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            manifest = {
                'execution_id': execution.id,
                'case_name': execution.case_name,
                'device_name': execution.device_name,
                'status': execution.status,
                'result': execution.result,
                'started_at': execution.started_at.isoformat() if execution.started_at else '',
                'finished_at': execution.finished_at.isoformat() if execution.finished_at else '',
                'duration': execution.duration,
                'file_count': len(files),
                'note': '该压缩包用于失败排障，包含 Allure 原始结果和执行附件。logcat 可单独通过 download-logcat 导出。',
            }
            archive.writestr(
                'manifest.json',
                json.dumps(manifest, ensure_ascii=False, indent=2),
            )
            for path in files:
                archive.write(path, arcname=os.path.basename(path))

        buffer.seek(0)
        filename = f"qaflow_execution_{execution.id}_evidence.zip"
        response = HttpResponse(buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = str(buffer.getbuffer().nbytes)
        return response

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        """停止执行"""
        execution = self.get_object()
        
        if execution.status not in ['pending', 'running']:
            return Response({
                'success': False,
                'message': '只能停止待执行或执行中的任务'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # 停止 Celery 任务
            if execution.task_id:
                from celery import current_app
                current_app.control.revoke(execution.task_id, terminate=True, signal='SIGTERM')
                logger.info(f"Celery任务已终止: task_id={execution.task_id}")
            
            execution.status = 'stopped'
            execution.finished_at = timezone.now()
            if execution.started_at:
                execution.duration = (execution.finished_at - execution.started_at).total_seconds()
            execution.save()
            send_execution_update(
                execution.id,
                status='stopped',
                progress=execution.progress,
                message='任务已停止',
                report_path=execution.report_path,
                finished_at=execution.finished_at
            )
            
            return Response({
                'success': True,
                'message': '任务已停止'
            })
        except Exception as e:
            logger.error(f"停止任务失败: {str(e)}")
            return Response({
                'success': False,
                'message': f'停止任务失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
def serve_report_file(request, execution_id, file_path=''):
    """提供 Allure 报告文件访问"""
    try:
        execution = AppTestExecution.objects.get(id=execution_id)
        if not execution.report_path:
            raise Http404("报告路径不存在")

        if not file_path:
            file_path = 'index.html'

        report_dir = execution.report_path
        full_path = os.path.join(report_dir, file_path)

        report_dir_abs = os.path.abspath(report_dir)
        full_path_abs = os.path.abspath(full_path)
        if not full_path_abs.startswith(report_dir_abs):
            raise Http404("无效的文件路径")

        if not os.path.exists(full_path_abs) or not os.path.isfile(full_path_abs):
            raise Http404("文件不存在")

        return FileResponse(open(full_path_abs, 'rb'), content_type=_get_content_type(file_path))
    except AppTestExecution.DoesNotExist:
        raise Http404("执行记录不存在")


def _get_content_type(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    content_types = {
        '.html': 'text/html',
        '.js': 'application/javascript',
        '.css': 'text/css',
        '.json': 'application/json',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.svg': 'image/svg+xml',
        '.ico': 'image/x-icon',
        '.woff': 'font/woff',
        '.woff2': 'font/woff2',
        '.ttf': 'font/ttf',
        '.eot': 'application/vnd.ms-fontobject',
        '.txt': 'text/plain',
    }
    return content_types.get(ext, 'application/octet-stream')


def _find_logcat_files(execution_id):
    results_dir = os.path.join(
        settings.MEDIA_ROOT,
        'app-automation',
        'allure-results',
        f'execution_{execution_id}',
    )
    if not os.path.isdir(results_dir):
        return []

    candidates = []
    for name in os.listdir(results_dir):
        lower_name = name.lower()
        if 'logcat' not in lower_name or not lower_name.endswith('.txt'):
            continue
        path = os.path.abspath(os.path.join(results_dir, name))
        if os.path.isfile(path) and path.startswith(os.path.abspath(results_dir)):
            candidates.append(path)

    return sorted(candidates, key=lambda item: (0 if 'summary' in os.path.basename(item).lower() else 1, item))


def _find_evidence_files(execution_id):
    results_dir = os.path.join(
        settings.MEDIA_ROOT,
        'app-automation',
        'allure-results',
        f'execution_{execution_id}',
    )
    if not os.path.isdir(results_dir):
        return []

    candidates = []
    allowed_suffixes = (
        '.json', '.txt', '.log', '.xml', '.png', '.jpg', '.jpeg',
        '.html', '.csv'
    )
    for name in os.listdir(results_dir):
        lower_name = name.lower()
        if not lower_name.endswith(allowed_suffixes):
            continue
        path = os.path.abspath(os.path.join(results_dir, name))
        if os.path.isfile(path) and path.startswith(os.path.abspath(results_dir)):
            candidates.append(path)

    return sorted(candidates)
