# -*- coding: utf-8 -*-
"""Semantic dictionary management for APP automation."""
import csv
import io
import json

from django.db import models
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .test_case_views import AppPagination
from ..models import AppProject, AppSemanticDictionary
from ..serializers import AppSemanticDictionarySerializer


DEFAULT_SEMANTIC_DICTIONARY = {
    'page': ['登录页', '验证码登录页', '创建社区页', '社区详情页', '关注列表页', '个人中心页', '设置页', '公共弹窗', '公共顶部栏', '公共Toast'],
    'object': ['手机号', '验证码', '登录', '退出登录', '取消', '确认', '返回', '社区名称', '社区介绍', '创建社区', '关注社区', '关注列表', '社区头像', '个人头像', '昵称', '搜索', '设置'],
    'role': ['按钮', '输入框', '文本', '列表项', '图片', '开关', '勾选框', '弹窗', 'Tab', 'Toast', '容器'],
    'purpose': ['点击', '输入', '展示', '断言', '选择', '返回', '确认', '取消'],
}


def normalize_dictionary_row(row):
    category = str(row.get('category') or row.get('type') or '').strip()
    value = str(row.get('value') or row.get('name') or row.get('label') or '').strip()
    label = str(row.get('label') or value).strip()
    description = str(row.get('description') or row.get('remark') or row.get('note') or '').strip()
    governance_status = str(row.get('governance_status') or row.get('status') or 'approved').strip()
    source = str(row.get('source') or 'import').strip()
    sort_order = row.get('sort_order', row.get('order', 0))
    is_active = row.get('is_active', row.get('enabled', True))

    try:
        sort_order = int(sort_order or 0)
    except (TypeError, ValueError):
        sort_order = 0

    if isinstance(is_active, str):
        is_active = is_active.strip().lower() not in {'false', '0', 'no', '否', '禁用'}

    return {
        'category': category,
        'value': value,
        'label': label,
        'description': description,
        'governance_status': governance_status,
        'source': source,
        'sort_order': sort_order,
        'is_active': bool(is_active),
    }


def parse_import_payload(request):
    upload = request.FILES.get('file')
    raw_text = request.data.get('content') or request.data.get('text') or ''

    if upload:
        raw_text = upload.read().decode('utf-8-sig')

    if not raw_text and isinstance(request.data.get('items'), list):
        return request.data.get('items')

    raw_text = str(raw_text or '').strip()
    if not raw_text:
        return []

    if raw_text.startswith('['):
        return json.loads(raw_text)

    reader = csv.DictReader(io.StringIO(raw_text))
    return list(reader)


class AppSemanticDictionaryViewSet(viewsets.ModelViewSet):
    """APP semantic naming dictionary ViewSet."""

    serializer_class = AppSemanticDictionarySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = AppPagination
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'is_active', 'governance_status']
    search_fields = ['value', 'label', 'description']
    ordering_fields = ['category', 'sort_order', 'updated_at', 'value']
    ordering = ['category', 'sort_order', 'value']

    def get_queryset(self):
        user = self.request.user
        project_id = self.request.query_params.get('project')
        scope = self.request.query_params.get('scope')
        queryset = AppSemanticDictionary.objects.all()

        accessible_projects = AppProject.objects.filter(
            models.Q(owner=user) | models.Q(members=user)
        ).distinct()

        if scope == 'global':
            queryset = queryset.filter(project__isnull=True)
        elif project_id:
            queryset = queryset.filter(models.Q(project_id=project_id) | models.Q(project__isnull=True))
        else:
            queryset = queryset.filter(models.Q(project__in=accessible_projects) | models.Q(project__isnull=True))

        return queryset.distinct()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=['get'], url_path='options')
    def options(self, request):
        project_id = request.query_params.get('project')
        queryset = self.filter_queryset(self.get_queryset()).filter(is_active=True)

        if project_id:
            # Project words should override the same global word in UI options.
            queryset = queryset.order_by('category', 'sort_order', 'project_id', 'value')

        grouped = {key: [] for key in DEFAULT_SEMANTIC_DICTIONARY.keys()}
        seen = {key: set() for key in DEFAULT_SEMANTIC_DICTIONARY.keys()}

        for item in queryset:
            if item.category not in grouped or item.value in seen[item.category]:
                continue
            grouped[item.category].append({
                'id': item.id,
                'value': item.value,
                'label': item.label or item.value,
                'description': item.description,
                'governance_status': item.governance_status,
                'project': item.project_id,
            })
            seen[item.category].add(item.value)

        for category, values in DEFAULT_SEMANTIC_DICTIONARY.items():
            for value in values:
                if value in seen[category]:
                    continue
                grouped[category].append({
                    'id': None,
                    'value': value,
                    'label': value,
                    'description': 'built-in fallback',
                    'governance_status': 'approved',
                    'project': None,
                })
                seen[category].add(value)

        return Response({'success': True, 'data': grouped})

    @action(detail=False, methods=['post'], url_path='import')
    def import_items(self, request):
        project_id = request.data.get('project') or request.query_params.get('project')
        project = None
        if project_id not in (None, ''):
            project = AppProject.objects.filter(id=project_id).first()
            if not project:
                return Response({'success': False, 'message': 'Project not found.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            rows = parse_import_payload(request)
        except Exception as exc:
            return Response({'success': False, 'message': f'Import payload parse failed: {exc}'}, status=status.HTTP_400_BAD_REQUEST)

        created_count = 0
        updated_count = 0
        skipped = []

        allowed_categories = {choice[0] for choice in AppSemanticDictionary.CATEGORY_CHOICES}
        allowed_statuses = {choice[0] for choice in AppSemanticDictionary.GOVERNANCE_STATUS_CHOICES}
        for index, raw_row in enumerate(rows, start=1):
            row = normalize_dictionary_row(raw_row)
            if row['category'] not in allowed_categories or not row['value']:
                skipped.append({'row': index, 'reason': 'category/value required', 'data': raw_row})
                continue
            if row['governance_status'] not in allowed_statuses:
                row['governance_status'] = 'approved'

            item, created = AppSemanticDictionary.objects.update_or_create(
                project=project,
                category=row['category'],
                value=row['value'],
                defaults={
                    'label': row['label'],
                    'description': row['description'],
                    'governance_status': row['governance_status'],
                    'source': row['source'],
                    'sort_order': row['sort_order'],
                    'is_active': row['is_active'],
                    'created_by': request.user,
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        return Response({
            'success': True,
            'data': {
                'created': created_count,
                'updated': updated_count,
                'skipped': skipped,
            },
        })
