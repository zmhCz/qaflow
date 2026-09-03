# -*- coding: utf-8 -*-
"""App element management views."""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.http import FileResponse
from django.conf import settings
from django.utils import timezone
from django.db import models
from pathlib import Path
from .test_case_views import AppPagination
from .device_views import (
    capture_page_state_payload,
    find_best_candidate_for_selector,
    find_candidate_by_point,
    get_adb_path,
    is_generic_container_candidate,
    run_adb_command,
)
import base64
import hashlib
import io
import re
import time
import logging

from ..models import AppDevice, AppElement, AppProject, AppSemanticDictionary, AppTestExecution
from ..serializers import AppElementSerializer
from ..utils.android_source_inspector import list_source_semantic_candidates

logger = logging.getLogger(__name__)


SEMANTIC_STATUS_LABELS = {
    'pending': '待验证',
    'verified': '已验证',
    'needs_update': '需调整',
}
SEMANTIC_STATUS_TAGS = set(SEMANTIC_STATUS_LABELS.values())


def normalize_semantic_status(raw_status):
    status_text = str(raw_status or '').strip()
    return SEMANTIC_STATUS_LABELS.get(status_text, status_text)


def update_element_semantic_status(element, status_text, user=None, source='manual', extra=None):
    config = dict(element.config or {})
    now = timezone.now().isoformat()

    config['semantic_status'] = status_text
    config['semantic_status_updated_at'] = now
    config['semantic_status_source'] = source
    if user and getattr(user, 'is_authenticated', False):
        config['semantic_status_updated_by'] = user.username

    if status_text == '已验证':
        config['verified_at'] = now
        config['verified_source'] = source
        if user and getattr(user, 'is_authenticated', False):
            config['verified_by'] = user.username

    if extra:
        config.update(extra)

    tags = [tag for tag in list(element.tags or []) if tag not in SEMANTIC_STATUS_TAGS]
    if status_text not in tags:
        tags.append(status_text)

    element.config = config
    element.tags = tags
    element.save(update_fields=['config', 'tags', 'updated_at'])
    return element


def collect_element_ids(payload):
    element_ids = set()

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.endswith('element_id') and item not in (None, ''):
                    try:
                        element_ids.add(int(item))
                    except (TypeError, ValueError):
                        pass
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    return element_ids


def is_semantic_v2_element(element):
    config = element.config or {}
    tags = element.tags or []
    return (
        'semantic_v2' in tags
        or str(element.name or '').startswith('semantic_v2.')
        or str(config.get('semantic_version') or '') == 'v2'
    )


def parse_bounds_text(bounds_text):
    match = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', str(bounds_text or ''))
    if not match:
        return None
    x1, y1, x2, y2 = [int(item) for item in match.groups()]
    return {
        'x1': min(x1, x2),
        'y1': min(y1, y2),
        'x2': max(x1, x2),
        'y2': max(y1, y2),
    }


def parse_bounds_payload(raw_bounds):
    if isinstance(raw_bounds, str):
        return parse_bounds_text(raw_bounds)
    if not isinstance(raw_bounds, dict):
        return None
    try:
        x1 = int(raw_bounds.get('x1'))
        y1 = int(raw_bounds.get('y1'))
        x2 = int(raw_bounds.get('x2'))
        y2 = int(raw_bounds.get('y2'))
        return {
            'x1': min(x1, x2),
            'y1': min(y1, y2),
            'x2': max(x1, x2),
            'y2': max(y1, y2),
        }
    except (TypeError, ValueError):
        return None


def format_bounds_text(bounds):
    return f"[{bounds['x1']},{bounds['y1']}][{bounds['x2']},{bounds['y2']}]"


def is_manual_bounds_element(element):
    config = element.config or {}
    tags = element.tags or []
    class_name = str(config.get('class') or '').strip()
    strategy = str(config.get('strategy') or '').strip()

    return (
        strategy == 'manual_bounds'
        or class_name == 'manual.bounds'
        or bool(config.get('preview_image_path'))
        or bool(config.get('bounds_rect'))
        or '人工框选' in tags
    )


def is_page_map_selector_element(element):
    config = element.config or {}
    return str(config.get('strategy') or '').strip() == 'page_map_selector' or bool(config.get('page_map_element_id'))


def resolve_page_map_bounds(config, current_size):
    if current_size:
        normalized = config.get('normalized_bounds') or {}
        if isinstance(normalized, dict):
            try:
                x1 = float(normalized.get('x1'))
                y1 = float(normalized.get('y1'))
                x2 = float(normalized.get('x2'))
                y2 = float(normalized.get('y2'))
                width, height = current_size
                if 0 <= x1 <= 1 and 0 <= y1 <= 1 and 0 <= x2 <= 1 and 0 <= y2 <= 1 and x2 > x1 and y2 > y1:
                    return {
                        'x1': round(x1 * width),
                        'y1': round(y1 * height),
                        'x2': round(x2 * width),
                        'y2': round(y2 * height),
                    }, {
                        'scaled': True,
                        'source': 'normalized_bounds',
                        'current_width': width,
                        'current_height': height,
                    }
            except (TypeError, ValueError):
                pass

    bounds = parse_bounds_text(config.get('bounds') or '')
    if bounds:
        return bounds, {
            'scaled': False,
            'source': 'raw_bounds',
            'current_width': current_size[0] if current_size else None,
            'current_height': current_size[1] if current_size else None,
        }
    return None, {}


def build_page_map_semantic_text_selector(config):
    text = str(
        config.get('text')
        or config.get('content_desc')
        or config.get('semantic_object')
        or config.get('description')
        or ''
    ).strip()
    if not text:
        return None
    return {
        'resource_id': '',
        'text': text,
        'content_desc': '',
        'hint': '',
        'class': '',
    }


def build_page_map_bounds_candidate(element, config, bounds, source='page_map_bounds', ui_candidate=None):
    candidate = {
        'name': config.get('semantic_object') or config.get('description') or element.name,
        'class_name': 'page_map.bounds',
        'resource_id': config.get('resource_id') or '',
        'text': config.get('text') or config.get('semantic_object') or config.get('description') or '',
        'content_desc': config.get('content_desc') or '',
        'bounds': bounds,
        'raw_bounds': format_bounds_text(bounds),
        'source': source,
    }
    if ui_candidate:
        candidate['ui_candidate'] = {
            'resource_id': ui_candidate.get('resource_id') or '',
            'text': ui_candidate.get('text') or '',
            'content_desc': ui_candidate.get('content_desc') or '',
            'class_name': ui_candidate.get('class_name') or ui_candidate.get('class') or '',
            'raw_bounds': ui_candidate.get('raw_bounds') or format_bounds_text(ui_candidate.get('bounds')) if ui_candidate.get('bounds') else '',
            'source': ui_candidate.get('source') or '',
        }
    return candidate


def resolve_page_map_bounds_target(element, config, current_size, candidates):
    page_map_bounds, bounds_meta = resolve_page_map_bounds(config, current_size)
    if not page_map_bounds:
        return {
            'target_bounds': None,
            'tap_point': None,
            'matched_candidate': None,
            'score': -1,
            'confidence': 'none',
            'reason': '页面地图元素缺少入库 bounds，无法区域验证',
            'bounds_meta': bounds_meta,
        }

    validation_bounds = clamp_bounds_to_screen(page_map_bounds, current_size)
    center_x = int((validation_bounds['x1'] + validation_bounds['x2']) / 2)
    center_y = int((validation_bounds['y1'] + validation_bounds['y2']) / 2)
    ui_candidate = find_candidate_by_point(candidates, center_x, center_y)
    result = {
        'target_bounds': validation_bounds,
        'tap_point': {'x': center_x, 'y': center_y},
        'matched_candidate': None,
        'score': -1,
        'confidence': 'none',
        'reason': '',
        'bounds_meta': bounds_meta,
    }

    if ui_candidate and not is_generic_container_candidate(ui_candidate):
        result.update({
            'matched_candidate': ui_candidate,
            'score': 0.85,
            'confidence': 'medium',
            'reason': '已按页面地图入库框选区域还原目标，并在区域中心命中实时 UI 节点',
        })
    elif bounds_overlap_screen(validation_bounds, current_size):
        result.update({
            'matched_candidate': build_page_map_bounds_candidate(
                element,
                config,
                validation_bounds,
                source='page_map_bounds',
                ui_candidate=ui_candidate,
            ),
            'score': 0.7,
            'confidence': 'medium' if ui_candidate else 'weak',
            'reason': (
                '已按页面地图入库框选区域还原目标；实时 UI 树仅命中整页/容器节点，'
                '不再用容器 bounds 覆盖框选区域'
            ) if ui_candidate else '已按页面地图入库框选区域还原目标，当前区域在截图范围内',
        })
    else:
        result['reason'] = '页面地图入库区域不在当前截图范围内，请确认是否在同一页面或元素需重新框选'

    if bounds_meta.get('scaled'):
        result['reason'] = f"{result['reason']}；已按设备分辨率比例换算 bounds"
    return result


def decode_data_uri_image(data_uri):
    if not data_uri:
        return None
    try:
        from PIL import Image

        raw_data = str(data_uri)
        if ',' in raw_data:
            raw_data = raw_data.split(',', 1)[1]
        image_bytes = base64.b64decode(raw_data)
        return Image.open(io.BytesIO(image_bytes)).convert('RGB')
    except Exception as exc:
        logger.warning("解析实时截图失败: %s", exc)
        return None


def scale_bounds_for_current_screen(bounds, config, current_size):
    if not bounds or not current_size:
        return bounds, {
            'scaled': False,
            'current_width': current_size[0] if current_size else None,
            'current_height': current_size[1] if current_size else None,
        }

    screenshot = config.get('screenshot') or {}
    source_width = int(screenshot.get('natural_width') or 0)
    source_height = int(screenshot.get('natural_height') or 0)
    current_width, current_height = current_size

    if source_width <= 0 or source_height <= 0:
        return bounds, {
            'scaled': False,
            'current_width': current_width,
            'current_height': current_height,
        }

    scale_x = current_width / source_width
    scale_y = current_height / source_height
    scaled = abs(scale_x - 1) > 0.01 or abs(scale_y - 1) > 0.01
    if not scaled:
        return bounds, {
            'scaled': False,
            'source_width': source_width,
            'source_height': source_height,
            'current_width': current_width,
            'current_height': current_height,
        }

    scaled_bounds = {
        'x1': round(bounds['x1'] * scale_x),
        'y1': round(bounds['y1'] * scale_y),
        'x2': round(bounds['x2'] * scale_x),
        'y2': round(bounds['y2'] * scale_y),
    }
    return scaled_bounds, {
        'scaled': True,
        'scale_x': round(scale_x, 4),
        'scale_y': round(scale_y, 4),
        'source_width': source_width,
        'source_height': source_height,
        'current_width': current_width,
        'current_height': current_height,
    }


def clamp_bounds_to_screen(bounds, current_size):
    if not bounds or not current_size:
        return bounds
    width, height = current_size
    return {
        'x1': max(0, min(bounds['x1'], width - 1)),
        'y1': max(0, min(bounds['y1'], height - 1)),
        'x2': max(0, min(bounds['x2'], width)),
        'y2': max(0, min(bounds['y2'], height)),
    }


def bounds_overlap_screen(bounds, current_size):
    if not bounds or not current_size:
        return False
    width, height = current_size
    return bounds['x2'] > 0 and bounds['y2'] > 0 and bounds['x1'] < width and bounds['y1'] < height


def compare_manual_bounds_preview(template_base, config, current_image, bounds):
    preview_image_path = config.get('preview_image_path') or config.get('image_path')
    if not preview_image_path or current_image is None or not bounds:
        return None

    preview_path = template_base / str(preview_image_path)
    if not preview_path.exists():
        return {
            'available': False,
            'error': '预览图文件不存在',
            'preview_image_path': str(preview_image_path),
        }

    try:
        from PIL import Image

        crop_box = (
            max(0, bounds['x1']),
            max(0, bounds['y1']),
            max(0, bounds['x2']),
            max(0, bounds['y2']),
        )
        if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
            return {
                'available': False,
                'error': '当前截图裁剪区域无效',
                'preview_image_path': str(preview_image_path),
            }

        template_image = Image.open(preview_path).convert('L').resize((48, 48))
        current_crop = current_image.crop(crop_box).convert('L').resize((48, 48))
        template_pixels = list(template_image.getdata())
        current_pixels = list(current_crop.getdata())
        diff = sum(abs(a - b) for a, b in zip(template_pixels, current_pixels)) / len(template_pixels)
        similarity = max(0, min(1, 1 - diff / 255))
        threshold = 0.58
        return {
            'available': True,
            'matched': similarity >= threshold,
            'similarity': round(similarity, 4),
            'threshold': threshold,
            'preview_image_path': str(preview_image_path),
        }
    except Exception as exc:
        logger.warning("人工框选预览图比对失败: %s", exc)
        return {
            'available': False,
            'error': str(exc),
            'preview_image_path': str(preview_image_path),
        }


def build_screenshot_only_payload(adb_path, device_id, include_focus=False, screenshot_timeout=8):
    from .device_views import capture_screenshot_bytes, get_current_focus_info

    screenshot_bytes = capture_screenshot_bytes(adb_path, device_id, timeout=screenshot_timeout)
    event_timestamp = int(timezone.now().timestamp())
    image_base64 = base64.b64encode(screenshot_bytes).decode('utf-8') if screenshot_bytes else ''
    page_info = get_current_focus_info(adb_path, device_id, timeout=4) if include_focus else {}
    return {
        'filename': f"page_state_{device_id}_{event_timestamp}.png",
        'content': f"data:image/png;base64,{image_base64}" if image_base64 else '',
        'device_id': device_id,
        'timestamp': event_timestamp,
        'package_name': page_info.get('package_name', ''),
        'activity': page_info.get('activity', ''),
        'ui_xml': '',
        'node_count': 0,
        'candidate_count': 0,
        'hotzone_count': 0,
        'candidates': [],
        'fast_path': True,
    }


def build_selector_from_element(element):
    config = element.config or {}
    return {
        'package': config.get('package') or '',
        'activity': config.get('activity') or '',
        'resource_id': config.get('resource_id') or '',
        'text': config.get('text') or '',
        'content_desc': config.get('content_desc') or '',
        'hint': config.get('hint') or '',
        'class': config.get('class') or '',
        'bounds': config.get('bounds') or '',
        'clickable': config.get('clickable'),
        'focusable': config.get('focusable'),
        'enabled': config.get('enabled'),
    }


class AppElementViewSet(viewsets.ModelViewSet):
    """APP閸忓啰绀岀粻锛勬倞 ViewSet"""
    queryset = AppElement.objects.filter(is_active=True)
    serializer_class = AppElementSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = AppPagination
    # 閳跨媴绗?缁夊娅?SearchFilter閿涘奔濞囬悽銊ㄥ殰鐎规矮绠熼幖婊呭偍闁槒绶?
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['element_type', 'is_active', 'project']
    
    def perform_create(self, serializer):
        element = serializer.save(created_by=self.request.user)
        self.sync_semantic_candidates(element)

    def perform_update(self, serializer):
        element = serializer.save()
        self.sync_semantic_candidates(element)

    def sync_semantic_candidates(self, element):
        """Keep page/object candidate pools easy to grow without blocking entry."""
        config = element.config or {}
        project = element.project
        candidates = [
            ('page', config.get('semantic_page') or config.get('page_name')),
            ('object', config.get('semantic_object') or config.get('description')),
        ]

        for category, raw_value in candidates:
            value = str(raw_value or '').strip()
            if not value:
                continue

            exists = AppSemanticDictionary.objects.filter(
                models.Q(project=project) | models.Q(project__isnull=True),
                category=category,
                value=value,
            ).exists()
            if exists:
                continue

            AppSemanticDictionary.objects.create(
                project=project,
                category=category,
                value=value,
                label=value,
                governance_status='pending',
                source='element_entry',
                description=f'Auto-created from element {element.name}',
                created_by=self.request.user,
            )
    
    def perform_destroy(self, instance):
        """
        閸掔娀娅庨崗鍐閺冭泛鎮撻弮璺哄灩闂勩倗澧块悶鍡樻瀮娴?
        """
        # 婵″倹鐏夐弰顖氭禈閻楀洨琚崹瀣剁礉閸掔娀娅庨悧鈺冩倞閺傚洣娆?
        if instance.element_type == 'image' and instance.config:
            image_path = instance.config.get('image_path')
            if image_path:
                try:
                    # 閺嬪嫰鈧姴鐣弫瀛樻瀮娴犳儼鐭惧?
                    template_base = self.get_template_base_path()
                    file_path = template_base / image_path
                    
                    # 閸掔娀娅庨弬鍥︽
                    if file_path.exists():
                        file_path.unlink()
                        logger.info(f"閸掔娀娅庨崶鍓у閺傚洣娆? {file_path}")
                    else:
                        logger.warning(f"閸ュ墽澧栭弬鍥︽娑撳秴鐡ㄩ崷? {file_path}")
                except Exception as e:
                    logger.error(f"閸掔娀娅庨崶鍓у閺傚洣娆㈡径杈Е: {str(e)}")
                    # 缂佈呯敾閸掔娀娅庨弫鐗堝祦鎼存捁顔囪ぐ鏇礉閸楀厖濞囬弬鍥︽閸掔娀娅庢径杈Е
        
        # 閸掔娀娅庨弫鐗堝祦鎼存捁顔囪ぐ?
        instance.delete()
    
    def get_queryset(self):
        """
        鑷畾涔夋煡璇㈤泦锛屾敮鎸佸悕绉板拰瀹氫綅淇℃伅鎼滅储銆?
        """
        queryset = super().get_queryset()

        search = (
            self.request.query_params.get('search', '').strip()
            or self.request.query_params.get('keyword', '').strip()
        )
        if search:
            from django.db.models import Q

            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(config__resource_id__icontains=search)
                | Q(config__locator_key__icontains=search)
                | Q(config__description__icontains=search)
                | Q(config__manual_note__icontains=search)
                | Q(config__hint__icontains=search)
                | Q(config__text__icontains=search)
                | Q(config__content_desc__icontains=search)
            )

        return queryset
    
    def get_template_base_path(self):
        """
        閼惧嘲褰囧Ο鈩冩緲閸╄櫣顢呯捄顖氱窞
        閸欏倽鈧?Smart AI Test 閻ㄥ嫬鐤勯悳甯窗閸ュ墽澧栫€涙ɑ鏂侀崷?app 閻╊喖缍嶆稉瀣畱 Template 閺傚洣娆㈡径?
        
        鏉╂柨娲? apps/app_automation/Template/
        """
        # __file__ = .../views/element_views.py
        # .parent = .../views/
        # .parent.parent = .../app_automation/
        return Path(__file__).resolve().parent.parent / "Template"

    @action(detail=False, methods=['get'], url_path='source-semantic-candidates')
    def source_semantic_candidates(self, request):
        """Return AI-assisted semantic element candidates from the read-only APP source."""
        try:
            payload = list_source_semantic_candidates(
                keyword=request.query_params.get('keyword', ''),
                role=request.query_params.get('role', ''),
                limit=int(request.query_params.get('limit', 200) or 200),
                include_static=str(request.query_params.get('include_static', '')).lower() in {'1', 'true', 'yes'},
            )
            return Response({
                'code': 0,
                'msg': '源码语义候选生成成功',
                'success': True,
                'data': payload,
            })
        except Exception as exc:
            logger.error("源码语义候选生成失败: %s", exc, exc_info=True)
            return Response({
                'code': 500,
                'msg': f'源码语义候选生成失败: {exc}',
                'success': False,
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'], url_path='semantic-status')
    def semantic_status(self, request, pk=None):
        """Update the human-facing semantic validation status for one element."""
        element = self.get_object()
        status_text = normalize_semantic_status(request.data.get('status') or request.data.get('semantic_status'))
        if status_text not in SEMANTIC_STATUS_TAGS:
            return Response({
                'code': 400,
                'msg': 'Unsupported semantic status',
                'success': False,
                'data': {'allowed': sorted(SEMANTIC_STATUS_TAGS)},
            }, status=status.HTTP_400_BAD_REQUEST)

        note = str(request.data.get('note') or '').strip()
        extra = {}
        if note:
            extra['semantic_status_note'] = note

        update_element_semantic_status(
            element,
            status_text,
            user=request.user,
            source='manual',
            extra=extra,
        )
        return Response({
            'code': 0,
            'msg': '元素状态已更新',
            'success': True,
            'data': AppElementSerializer(element).data,
        })

    @action(detail=True, methods=['post'], url_path='validate')
    def validate(self, request, pk=None):
        """Validate whether this semantic element can hit something on the current device page."""
        element = self.get_object()
        device_id = request.data.get('device') or request.data.get('device_id')
        if not device_id:
            return Response({
                'code': 400,
                'msg': '请选择验证设备',
                'success': False,
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            device = AppDevice.objects.get(pk=device_id)
        except AppDevice.DoesNotExist:
            return Response({
                'code': 404,
                'msg': '验证设备不存在',
                'success': False,
            }, status=status.HTTP_404_NOT_FOUND)

        if device.status == 'offline':
            return Response({
                'code': 400,
                'msg': '设备离线，无法验证元素',
                'success': False,
            }, status=status.HTTP_400_BAD_REQUEST)

        selector = build_selector_from_element(element)
        config = element.config or {}
        matched_candidate = None
        score = 0
        strategy = 'selector'
        reason = ''
        confidence = 'none'
        target_bounds = None
        tap_point = None
        bounds_meta = {}

        try:
            adb_path = get_adb_path()
            manual_bounds_mode = is_manual_bounds_element(element)
            page_payload = (
                build_screenshot_only_payload(adb_path, device.device_id)
                if manual_bounds_mode
                else capture_page_state_payload(adb_path, device.device_id, include_screenshot=True)
            )
            candidates = page_payload.get('candidates', [])
            current_image = decode_data_uri_image(page_payload.get('content', ''))
            current_size = current_image.size if current_image else None

            if manual_bounds_mode:
                strategy = 'manual_bounds'
                bounds = parse_bounds_text(config.get('bounds') or '')
                if bounds:
                    scaled_bounds, bounds_meta = scale_bounds_for_current_screen(bounds, config, current_size)
                    validation_bounds = clamp_bounds_to_screen(scaled_bounds, current_size)
                    center_x = int((validation_bounds['x1'] + validation_bounds['x2']) / 2)
                    center_y = int((validation_bounds['y1'] + validation_bounds['y2']) / 2)
                    target_bounds = validation_bounds
                    tap_point = {'x': center_x, 'y': center_y}
                    matched_candidate = find_candidate_by_point(candidates, center_x, center_y)
                    preview_match = compare_manual_bounds_preview(
                        self.get_template_base_path(),
                        config,
                        current_image,
                        validation_bounds,
                    )

                    if matched_candidate:
                        score = 1
                        confidence = 'strong'
                        reason = '人工框选中心点命中当前 UI 候选'
                    elif preview_match and preview_match.get('available') and preview_match.get('matched'):
                        score = preview_match.get('similarity', 0)
                        confidence = 'medium'
                        reason = '人工框选区域与入库预览图相似，按截图区域验证通过'
                        matched_candidate = {
                            'name': config.get('semantic_object') or config.get('description') or element.name,
                            'class_name': 'manual.bounds',
                            'resource_id': '',
                            'text': config.get('semantic_object') or config.get('description') or '',
                            'content_desc': '',
                            'bounds': validation_bounds,
                            'raw_bounds': format_bounds_text(validation_bounds),
                            'source': 'manual_bounds_preview',
                            'preview_match': preview_match,
                        }
                    elif bounds_overlap_screen(validation_bounds, current_size):
                        score = 0.5
                        confidence = 'weak'
                        reason = '人工框选元素：当前截图可用且 bounds 在屏幕内，UI 树不可见，按区域兜底通过'
                        matched_candidate = {
                            'name': config.get('semantic_object') or config.get('description') or element.name,
                            'class_name': 'manual.bounds',
                            'resource_id': '',
                            'text': config.get('semantic_object') or config.get('description') or '',
                            'content_desc': '',
                            'bounds': validation_bounds,
                            'raw_bounds': format_bounds_text(validation_bounds),
                            'source': 'manual_bounds_fallback',
                            'preview_match': preview_match,
                        }
                    else:
                        score = -1
                        reason = '人工框选 bounds 超出当前截图范围，请确认是否换了页面或元素需重新框选'

                    if bounds_meta.get('scaled'):
                        reason = f"{reason}；已按设备分辨率比例换算 bounds"
                else:
                    score = -1
                    reason = '人工框选元素缺少 bounds，无法实时验证'
            else:
                page_map_mode = is_page_map_selector_element(element)
                if page_map_mode:
                    page_map_result = resolve_page_map_bounds_target(element, config, current_size, candidates)
                    strategy = 'page_map_bounds'
                    target_bounds = page_map_result['target_bounds']
                    tap_point = page_map_result['tap_point']
                    matched_candidate = page_map_result['matched_candidate']
                    score = page_map_result['score']
                    confidence = page_map_result['confidence']
                    reason = page_map_result['reason']
                    bounds_meta = page_map_result['bounds_meta']

                    if not matched_candidate:
                        semantic_selector = build_page_map_semantic_text_selector(config)
                        if semantic_selector:
                            semantic_candidate, semantic_score = find_best_candidate_for_selector(candidates, semantic_selector)
                            if semantic_candidate and semantic_candidate.get('bounds') and not is_generic_container_candidate(semantic_candidate):
                                matched_candidate = semantic_candidate
                                score = max(semantic_score, 0.8)
                                confidence = 'medium'
                                strategy = 'page_map_semantic_text'
                                reason = '页面地图 bounds 不可用，已按业务对象文案匹配当前节点'
                                target_bounds = matched_candidate.get('bounds')
                                tap_point = {
                                    'x': int((target_bounds['x1'] + target_bounds['x2']) / 2),
                                    'y': int((target_bounds['y1'] + target_bounds['y2']) / 2),
                                }

                    if not matched_candidate:
                        selector_fields = ('resource_id', 'text', 'content_desc', 'hint')
                        has_selector_field = any(selector.get(key) for key in selector_fields)
                        class_name = str(selector.get('class') or '').strip()
                        if class_name and class_name != 'manual.bounds':
                            has_selector_field = True
                        if has_selector_field:
                            selector_candidate, selector_score = find_best_candidate_for_selector(candidates, selector)
                            if selector_candidate and selector_candidate.get('bounds') and not is_generic_container_candidate(selector_candidate):
                                matched_candidate = selector_candidate
                                score = selector_score
                                confidence = 'medium'
                                strategy = 'selector'
                                reason = '页面地图 bounds 不可用，已通过实时 UI 树语义字段匹配'
                                target_bounds = matched_candidate.get('bounds')
                                tap_point = {
                                    'x': int((target_bounds['x1'] + target_bounds['x2']) / 2),
                                    'y': int((target_bounds['y1'] + target_bounds['y2']) / 2),
                                }
                else:
                    selector_fields = ('resource_id', 'text', 'content_desc', 'hint')
                    has_selector_field = any(selector.get(key) for key in selector_fields)
                    class_name = str(selector.get('class') or '').strip()
                    if class_name and class_name != 'manual.bounds':
                        has_selector_field = True

                    if has_selector_field:
                        matched_candidate, score = find_best_candidate_for_selector(candidates, selector)
                        confidence = 'strong' if matched_candidate else 'none'
                        reason = '通过实时 UI 树语义字段匹配'
                        if matched_candidate and matched_candidate.get('bounds'):
                            target_bounds = matched_candidate.get('bounds')
                            tap_point = {
                                'x': int((target_bounds['x1'] + target_bounds['x2']) / 2),
                                'y': int((target_bounds['y1'] + target_bounds['y2']) / 2),
                            }
                    else:
                        strategy = 'bounds_center'
                        bounds = parse_bounds_text(config.get('bounds') or '')
                        if bounds:
                            center_x = int((bounds['x1'] + bounds['x2']) / 2)
                            center_y = int((bounds['y1'] + bounds['y2']) / 2)
                            target_bounds = bounds
                            tap_point = {'x': center_x, 'y': center_y}
                            matched_candidate = find_candidate_by_point(candidates, center_x, center_y)
                            score = 1 if matched_candidate else 0
                            confidence = 'strong' if matched_candidate else 'none'
                            reason = '通过框选区域中心点匹配当前 UI 候选'
                        else:
                            score = -1
                            reason = '元素缺少可验证的定位字段或 bounds'

            matched = matched_candidate is not None and score >= 0
            status_text = '已验证' if matched else '需调整'
            validation_result = {
                'matched': matched,
                'score': score,
                'strategy': strategy,
                'reason': reason,
                'confidence': confidence,
                'validated_device': device.device_id,
                'validated_at': timezone.now().isoformat(),
                'page_package': page_payload.get('package_name', ''),
                'page_activity': page_payload.get('activity', ''),
                'matched_candidate': matched_candidate,
                'target_bounds': target_bounds,
                'target_raw_bounds': format_bounds_text(target_bounds) if target_bounds else '',
                'tap_point': tap_point,
                'bounds_meta': bounds_meta,
            }

            update_element_semantic_status(
                element,
                status_text,
                user=request.user,
                source='live_validate',
                extra={
                    'last_validation': validation_result,
                },
            )

            return Response({
                'code': 0,
                'msg': '元素验证完成',
                'success': True,
                'data': {
                    **validation_result,
                    'semantic_status': status_text,
                    'page_state': {
                        'content': page_payload.get('content', ''),
                        'package_name': page_payload.get('package_name', ''),
                        'activity': page_payload.get('activity', ''),
                        'candidate_count': page_payload.get('candidate_count', 0),
                        'node_count': page_payload.get('node_count', 0),
                        'image_width': current_size[0] if current_size else None,
                        'image_height': current_size[1] if current_size else None,
                    },
                    'element': AppElementSerializer(element).data,
                },
            })
        except Exception as exc:
            logger.error("元素 %s 实时验证失败: %s", element.id, exc, exc_info=True)
            return Response({
                'code': 500,
                'msg': f'元素验证失败: {exc}',
                'success': False,
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'], url_path='click-test')
    def click_test(self, request, pk=None):
        """Tap the element target area and return before/after screenshots for human confirmation."""
        element = self.get_object()
        device_id = request.data.get('device') or request.data.get('device_id')
        if not device_id:
            return Response({
                'code': 400,
                'msg': '请选择验证设备',
                'success': False,
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            device = AppDevice.objects.get(pk=device_id)
        except AppDevice.DoesNotExist:
            return Response({
                'code': 404,
                'msg': '验证设备不存在',
                'success': False,
            }, status=status.HTTP_404_NOT_FOUND)

        if device.status == 'offline':
            return Response({
                'code': 400,
                'msg': '设备离线，无法点击试验',
                'success': False,
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            adb_path = get_adb_path()
            config = element.config or {}
            manual_bounds_mode = is_manual_bounds_element(element)
            page_map_mode = is_page_map_selector_element(element)
            before_payload = (
                build_screenshot_only_payload(adb_path, device.device_id)
                if manual_bounds_mode
                else capture_page_state_payload(adb_path, device.device_id, include_screenshot=True)
            )
            current_image = decode_data_uri_image(before_payload.get('content', ''))
            current_size = current_image.size if current_image else None
            candidates = before_payload.get('candidates', [])
            target_bounds = None
            matched_candidate = None
            strategy = 'selector'

            if manual_bounds_mode:
                strategy = 'manual_bounds'
                bounds = parse_bounds_text(config.get('bounds') or '')
                if bounds:
                    scaled_bounds, _ = scale_bounds_for_current_screen(bounds, config, current_size)
                    target_bounds = clamp_bounds_to_screen(scaled_bounds, current_size)
                    center_x = int((target_bounds['x1'] + target_bounds['x2']) / 2)
                    center_y = int((target_bounds['y1'] + target_bounds['y2']) / 2)
                    matched_candidate = find_candidate_by_point(candidates, center_x, center_y)
            else:
                if page_map_mode:
                    page_map_result = resolve_page_map_bounds_target(element, config, current_size, candidates)
                    strategy = 'page_map_bounds'
                    target_bounds = page_map_result['target_bounds']
                    matched_candidate = page_map_result['matched_candidate']
                else:
                    selector = build_selector_from_element(element)
                    matched_candidate, _ = find_best_candidate_for_selector(candidates, selector)
                    if matched_candidate and matched_candidate.get('bounds'):
                        target_bounds = matched_candidate.get('bounds')

            if not target_bounds:
                return Response({
                    'code': 400,
                    'msg': '未找到可点击的目标区域，请先完成定位验证或重新框选元素',
                    'success': False,
                }, status=status.HTTP_400_BAD_REQUEST)

            tap_point = {
                'x': int((target_bounds['x1'] + target_bounds['x2']) / 2),
                'y': int((target_bounds['y1'] + target_bounds['y2']) / 2),
            }
            run_adb_command(
                adb_path,
                device.device_id,
                ['shell', 'input', 'tap', str(tap_point['x']), str(tap_point['y'])],
                timeout=8,
            )

            delay_ms = int(request.data.get('delay_ms') or 800)
            time.sleep(max(0, min(delay_ms, 3000)) / 1000)
            after_payload = (
                build_screenshot_only_payload(adb_path, device.device_id)
                if manual_bounds_mode
                else capture_page_state_payload(adb_path, device.device_id, include_screenshot=True)
            )
            after_image = decode_data_uri_image(after_payload.get('content', ''))
            after_size = after_image.size if after_image else None

            result = {
                'clicked': True,
                'strategy': strategy,
                'reason': '已点击目标区域，请根据点击后截图或真机页面确认业务是否生效',
                'validated_device': device.device_id,
                'validated_at': timezone.now().isoformat(),
                'target_bounds': target_bounds,
                'target_raw_bounds': format_bounds_text(target_bounds),
                'tap_point': tap_point,
                'matched_candidate': matched_candidate,
                'manual_confirm_required': True,
            }

            return Response({
                'code': 0,
                'msg': '点击试验完成',
                'success': True,
                'data': {
                    **result,
                    'before': {
                        'content': before_payload.get('content', ''),
                        'package_name': before_payload.get('package_name', ''),
                        'activity': before_payload.get('activity', ''),
                        'candidate_count': before_payload.get('candidate_count', 0),
                        'image_width': current_size[0] if current_size else None,
                        'image_height': current_size[1] if current_size else None,
                    },
                    'after': {
                        'content': after_payload.get('content', ''),
                        'package_name': after_payload.get('package_name', ''),
                        'activity': after_payload.get('activity', ''),
                        'candidate_count': after_payload.get('candidate_count', 0),
                        'image_width': after_size[0] if after_size else None,
                        'image_height': after_size[1] if after_size else None,
                    },
                    'element': AppElementSerializer(element).data,
                },
            })
        except Exception as exc:
            logger.error("元素 %s 点击试验失败: %s", element.id, exc, exc_info=True)
            return Response({
                'code': 500,
                'msg': f'点击试验失败: {exc}',
                'success': False,
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], url_path='click-test-selection')
    def click_test_selection(self, request):
        """Tap a freshly selected bounds before saving it into the semantic library."""
        device_id = request.data.get('device') or request.data.get('device_id')
        if not device_id:
            return Response({
                'code': 400,
                'msg': '请选择验证设备',
                'success': False,
            }, status=status.HTTP_400_BAD_REQUEST)

        bounds = parse_bounds_payload(request.data.get('bounds'))
        if not bounds:
            return Response({
                'code': 400,
                'msg': '缺少有效框选区域',
                'success': False,
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            device = AppDevice.objects.get(pk=device_id)
        except AppDevice.DoesNotExist:
            return Response({
                'code': 404,
                'msg': '验证设备不存在',
                'success': False,
            }, status=status.HTTP_404_NOT_FOUND)

        if device.status == 'offline':
            return Response({
                'code': 400,
                'msg': '设备离线，无法点击验证',
                'success': False,
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            adb_path = get_adb_path()
            before_payload = build_screenshot_only_payload(adb_path, device.device_id)
            before_image = decode_data_uri_image(before_payload.get('content', ''))
            current_size = before_image.size if before_image else None

            screenshot_meta = request.data.get('screenshot') or {}
            config = {'screenshot': screenshot_meta}
            scaled_bounds, bounds_meta = scale_bounds_for_current_screen(bounds, config, current_size)
            target_bounds = clamp_bounds_to_screen(scaled_bounds, current_size)
            if not bounds_overlap_screen(target_bounds, current_size):
                return Response({
                    'code': 400,
                    'msg': '框选区域超出当前手机截图范围，请确认手机是否仍停留在刚才页面',
                    'success': False,
                }, status=status.HTTP_400_BAD_REQUEST)

            tap_point = {
                'x': int((target_bounds['x1'] + target_bounds['x2']) / 2),
                'y': int((target_bounds['y1'] + target_bounds['y2']) / 2),
            }
            run_adb_command(
                adb_path,
                device.device_id,
                ['shell', 'input', 'tap', str(tap_point['x']), str(tap_point['y'])],
                timeout=8,
            )

            delay_ms = int(request.data.get('delay_ms') or 500)
            time.sleep(max(0, min(delay_ms, 3000)) / 1000)
            after_payload = build_screenshot_only_payload(adb_path, device.device_id)
            after_image = decode_data_uri_image(after_payload.get('content', ''))
            after_size = after_image.size if after_image else None

            return Response({
                'code': 0,
                'msg': '点击验证完成',
                'success': True,
                'data': {
                    'clicked': True,
                    'strategy': 'selection_bounds',
                    'reason': '已点击当前框选区域，请确认点击后页面是否符合预期',
                    'validated_device': device.device_id,
                    'validated_at': timezone.now().isoformat(),
                    'target_bounds': target_bounds,
                    'target_raw_bounds': format_bounds_text(target_bounds),
                    'tap_point': tap_point,
                    'bounds_meta': bounds_meta,
                    'manual_confirm_required': True,
                    'before': {
                        'content': before_payload.get('content', ''),
                        'candidate_count': 0,
                        'image_width': current_size[0] if current_size else None,
                        'image_height': current_size[1] if current_size else None,
                    },
                    'after': {
                        'content': after_payload.get('content', ''),
                        'candidate_count': 0,
                        'image_width': after_size[0] if after_size else None,
                        'image_height': after_size[1] if after_size else None,
                    },
                },
            })
        except Exception as exc:
            logger.error("框选区域点击验证失败: %s", exc, exc_info=True)
            return Response({
                'code': 500,
                'msg': f'点击验证失败: {exc}',
                'success': False,
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], url_path='sync-verified-from-history')
    def sync_verified_from_history(self, request):
        """Mark semantic_v2 elements as verified when they appear in passed executions."""
        project_id = request.data.get('project') or request.query_params.get('project')
        execution_limit = int(request.data.get('execution_limit') or request.query_params.get('execution_limit') or 200)
        execution_limit = max(1, min(execution_limit, 1000))

        executions = AppTestExecution.objects.filter(
            status='completed',
            result='passed',
            test_case__isnull=False,
        ).select_related('test_case').order_by('-finished_at', '-created_at')[:execution_limit]

        element_execution_map = {}
        scanned_executions = 0
        for execution in executions:
            test_case = execution.test_case
            if not test_case:
                continue
            if project_id and str(test_case.project_id or '') != str(project_id):
                continue

            scanned_executions += 1
            ui_flow = test_case.ui_flow or {}
            ids = collect_element_ids(ui_flow)
            for element_id in ids:
                element_execution_map.setdefault(element_id, set()).add(execution.id)

        if not element_execution_map:
            return Response({
                'code': 0,
                'msg': '没有从历史通过用例中找到绑定元素',
                'success': True,
                'data': {
                    'updated_count': 0,
                    'scanned_executions': scanned_executions,
                    'elements': [],
                },
            })

        elements = AppElement.objects.filter(id__in=element_execution_map.keys(), is_active=True)
        updated_elements = []
        skipped = []
        for element in elements:
            if not is_semantic_v2_element(element):
                skipped.append({'id': element.id, 'name': element.name, 'reason': 'not_semantic_v2'})
                continue

            execution_ids = sorted(element_execution_map.get(element.id, []), reverse=True)
            update_element_semantic_status(
                element,
                '已验证',
                user=request.user,
                source='passed_execution_history',
                extra={
                    'verified_execution_ids': execution_ids[:20],
                    'last_verified_execution_id': execution_ids[0] if execution_ids else None,
                },
            )
            updated_elements.append(element)

        return Response({
            'code': 0,
            'msg': f'已同步 {len(updated_elements)} 个已验证元素',
            'success': True,
            'data': {
                'updated_count': len(updated_elements),
                'scanned_executions': scanned_executions,
                'skipped': skipped,
                'elements': AppElementSerializer(updated_elements, many=True).data,
            },
        })

    @action(detail=False, methods=['post'], url_path='import-source-semantics')
    def import_source_semantics(self, request):
        """Import selected source candidates as selector elements."""
        candidates = request.data.get('candidates') or []
        project_id = request.data.get('project')
        project = None
        if project_id:
            project = AppProject.objects.filter(id=project_id).first()
            if not project:
                return Response({
                    'code': 400,
                    'msg': '项目不存在',
                    'success': False,
                }, status=status.HTTP_400_BAD_REQUEST)

        if not isinstance(candidates, list) or not candidates:
            return Response({
                'code': 400,
                'msg': '请选择要导入的语义元素',
                'success': False,
            }, status=status.HTTP_400_BAD_REQUEST)

        created = []
        updated = []
        skipped = []

        for item in candidates:
            if not isinstance(item, dict):
                continue
            locator_key = str(item.get('locator_key') or item.get('key') or '').strip()
            resource_id = str(item.get('resource_id') or '').strip()
            text = str(item.get('text') or '').strip()
            content_desc = str(item.get('content_desc') or '').strip()
            hint = str(item.get('hint') or '').strip()
            bounds = str(item.get('bounds') or item.get('raw_bounds') or '').strip()
            if not locator_key:
                locator_key = str(
                    resource_id.rsplit('/', 1)[-1]
                    or text
                    or content_desc
                    or hint
                    or f"runtime_{len(created) + len(updated) + len(skipped) + 1}"
                ).strip()
            if not any([resource_id, text, content_desc, hint, bounds]):
                skipped.append({'candidate': item, 'reason': '缺少可用定位信息'})
                continue

            name = str(item.get('name') or f'semantic.{locator_key}').strip()
            config = {
                'strategy': 'semantic',
                'ai_managed': True,
                'semantic_status': 'ai_suggested',
                'needs_human_confirm': True,
                'description': str(item.get('description') or item.get('display_name') or locator_key).strip(),
                'manual_note': str(item.get('manual_note') or 'AI 根据 APP 源码生成，建议首次使用时由人工确认业务含义。').strip(),
                'resource_id': resource_id,
                'class': str(item.get('class') or item.get('class_name') or '').strip(),
                'text': text,
                'content_desc': content_desc,
                'hint': hint,
                'bounds': bounds,
                'locator_key': locator_key,
                'interaction_role': str(item.get('role') or '').strip(),
                'interaction_role_label': str(item.get('role_label') or '').strip(),
                'source_confidence': str(item.get('confidence') or 'medium').strip(),
                'source_layout_file': str(item.get('source_layout_file') or '').strip(),
                'source_code_file': str(item.get('source_code_file') or '').strip(),
                'source_summary': str(item.get('source_summary') or '').strip(),
                'source_refs': item.get('source_refs') or [],
                'source_click_refs': item.get('source_click_refs') or [],
                'source_movement_refs': item.get('source_movement_refs') or [],
                'runtime_match': item.get('runtime_match') or {},
            }
            tags = ['AI语义元素', config['interaction_role'] or 'semantic']

            element = AppElement.objects.filter(name=name, is_active=True).first()
            if element:
                element.project = project or element.project
                element.element_type = 'selector'
                element.config = {**(element.config or {}), **config}
                element.tags = sorted(set(list(element.tags or []) + tags))
                element.save()
                updated.append(AppElementSerializer(element).data)
                continue

            element = AppElement.objects.create(
                project=project,
                name=name,
                element_type='selector',
                tags=tags,
                config=config,
                created_by=request.user,
            )
            created.append(AppElementSerializer(element).data)

        return Response({
            'code': 0,
            'msg': f'导入完成，新增 {len(created)} 个，更新 {len(updated)} 个，跳过 {len(skipped)} 个',
            'success': True,
            'data': {
                'created': created,
                'updated': updated,
                'skipped': skipped,
            },
        })
    
    @action(detail=False, methods=['post'], url_path='upload')
    def upload_image(self, request):
        """
        娑撳﹣绱堕崗鍐閸ュ墽澧?
        
        閸旂喕鍏橀敍?
        1. 閹恒儲鏁归崶鍓у閺傚洣娆㈡稉濠佺炊
        2. 鐠侊紕鐣婚弬鍥︽閸濆牆绗?
        3. 濡偓濞村妲搁崥锕傚櫢婢?
        4. 娣囨繂鐡ㄩ崚鐗堝瘹鐎规艾鍨庣猾鑽ゆ窗瑜?
        5. 鏉╂柨娲栭崶鍓у鐠侯垰绶為崪灞芥惐鐢苯鈧?
        """
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({
                'code': 400,
                'msg': 'No file uploaded',
                'success': False
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # 閼惧嘲褰囬崣鍌涙殶
        category = request.data.get('category', 'common')
        element_id = request.data.get('element_id')  # 缂傛牞绶Ο鈥崇础閺冩湹绱堕柅鎺炵礉閻劋绨幒鎺楁珟閼奉亣闊?
        
        try:
            # 閴?娑撴艾濮熼柅鏄忕帆閸愬懓浠堥敍姘愁吀缁犳鏋冩禒璺烘惐鐢?
            file_obj.seek(0)
            hasher = hashlib.md5()
            for chunk in file_obj.chunks():
                hasher.update(chunk)
            file_hash = hasher.hexdigest()
            file_obj.seek(0)
            
            # 閴?娑撴艾濮熼柅鏄忕帆閸愬懓浠堥敍姘梾閺屻儲妲搁崥锕傚櫢婢跺稄绱欓幒鎺楁珟瑜版挸澧犻崗鍐閿?
            query = AppElement.objects.filter(
                config__file_hash=file_hash,
                is_active=True
            )
            if element_id:
                query = query.exclude(id=element_id)
            
            existing = query.first()
            
            if existing:
                return Response({
                    'code': 400,
                    'msg': 'Image already exists',
                    'success': False,
                    'detail': f'Duplicate image hash: {file_hash}',
                    'suggestion': '瀵ら缚顔呮径宥呭煑閻滅増婀侀崗鍐閹存牔绗傛导鐘辩瑝閸氬瞼娈戦崶鍓у',
                    'data': {
                        'existing_element': {
                            'id': existing.id,
                            'name': existing.name,
                            'image_path': existing.config.get('image_path')
                        }
                    }
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # 閴?娑撴艾濮熼柅鏄忕帆閸愬懓浠堥敍姘箽鐎涙ê娴橀悧鍥у煂 Template 閻╊喖缍?
            template_base = self.get_template_base_path()
            category_path = template_base / category
            category_path.mkdir(parents=True, exist_ok=True)
            
            # 娴ｈ法鏁ら崢鐔奉潗閺傚洣娆㈤崥?
            file_path = category_path / file_obj.name
            
            # 娣囨繂鐡ㄩ弬鍥︽
            with open(file_path, 'wb+') as destination:
                for chunk in file_obj.chunks():
                    destination.write(chunk)
            
            # 閺嬪嫬缂撻惄绋款嚠鐠侯垰绶為敍鍫㈡纯閹恒儴绻戦崶?category/filename.png閿?
            relative_path = f"{category}/{file_obj.name}"
            
            logger.info(f"閻劍鍩?{request.user.username} 娑撳﹣绱堕崶鍓у: {relative_path}, 閸濆牆绗? {file_hash}")
            
            return Response({
                'code': 0,
                'msg': '娑撳﹣绱堕幋鎰',
                'success': True,
                'data': {
                    'image_path': relative_path,
                    'file_hash': file_hash,
                    'url': f"/app-automation-templates/{relative_path}"
                }
            })
        
        except Exception as e:
            logger.error(f"娑撳﹣绱堕崶鍓у婢惰精瑙? {str(e)}")
            return Response({
                'code': 500,
                'msg': f'娑撳﹣绱舵径杈Е: {str(e)}',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'], url_path='image-categories')
    def image_categories(self, request):
        """
        閼惧嘲褰囬崶鍓у閸掑棛琚崚妤勩€?
        
        鏉╂柨娲栭幍鈧張澶婂讲閻劎娈戦崶鍓у閸掑棛琚惄顔肩秿
        """
        try:
            # 閴?娑撴艾濮熼柅鏄忕帆閸愬懓浠堥敍姘矤 Template 閻╊喖缍嶉懢宄板絿閸掑棛琚崚妤勩€?
            template_base = self.get_template_base_path()
            
            if not template_base.exists():
                return Response({
                    'code': 0,
                    'msg': '閼惧嘲褰囬幋鎰',
                    'success': True,
                    'data': []
                })
            
            categories = []
            for item in template_base.iterdir():
                if item.is_dir():
                    # 鐠侊紕鐣婚惄顔肩秿娑撳娈戦崶鍓у閺佷即鍣?
                    image_count = sum(1 for f in item.iterdir() if f.is_file() and f.suffix.lower() in ['.png', '.jpg', '.jpeg'])
                    
                    categories.append({
                        'name': item.name,
                        'count': image_count,
                        'path': str(item.relative_to(template_base))
                    })
            
            # 閹稿鎮曠粔鐗堝笓鎼?
            categories.sort(key=lambda x: x['name'])
            
            return Response({
                'code': 0,
                'msg': '閼惧嘲褰囬幋鎰',
                'success': True,
                'data': categories
            })
        except Exception as e:
            logger.error(f"閼惧嘲褰囬崚鍡欒閸掓銆冩径杈Е: {str(e)}")
            return Response({
                'code': 500,
                'msg': f'閼惧嘲褰囨径杈Е: {str(e)}',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'], url_path='image-categories/create')
    def create_image_category(self, request):
        """
        閸掓稑缂撻弬鎵畱閸ュ墽澧栭崚鍡欒
        
        閸欏倹鏆熼敍?
        - name: 閸掑棛琚崥宥囆為敍鍫濆涧閼宠棄瀵橀崥顐㈢摟濮ｅ秲鈧焦鏆熺€涙ぜ鈧椒绗呴崚鎺斿殠閵嗕椒鑵戦崚鎺斿殠閿?
        """
        category_name = request.data.get('name', '').strip()
        
        if not category_name:
            return Response({
                'code': 400,
                'msg': 'Category name is required',
                'success': False
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # 閴?娑撴艾濮熼柅鏄忕帆閸愬懓浠堥敍姘剁崣鐠囦礁鍨庣猾璇叉倳缁?
        if not re.match(r'^[a-zA-Z0-9_\-\u4e00-\u9fa5]+$', category_name):
            return Response({
                'code': 400,
                'msg': 'Category name may contain letters, numbers, underscores, hyphens, and Chinese characters only',
                'success': False
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # 閴?娑撴艾濮熼柅鏄忕帆閸愬懓浠堥敍姘躬 Template 閻╊喖缍嶉崚娑樼紦閸掑棛琚?
            template_base = self.get_template_base_path()
            category_path = template_base / category_name
            
            if category_path.exists():
                return Response({
                    'code': 400,
                    'msg': 'Category already exists',
                    'success': False
                }, status=status.HTTP_400_BAD_REQUEST)
            
            category_path.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"閻劍鍩?{request.user.username} 閸掓稑缂撻崶鍓у閸掑棛琚? {category_name}")
            
            return Response({
                'code': 0,
                'msg': '閸掓稑缂撻幋鎰',
                'success': True,
                'data': {
                    'name': category_name
                }
            })
        except Exception as e:
            logger.error(f"閸掓稑缂撻崚鍡欒婢惰精瑙? {str(e)}")
            return Response({
                'code': 500,
                'msg': f'閸掓稑缂撴径杈Е: {str(e)}',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['delete'], url_path='image-categories/(?P<name>[^/.]+)')
    def delete_image_category(self, request, name=None):
        """
        閸掔娀娅庨崶鍓у閸掑棛琚敍鍫滅矌閸掔娀娅庣粚铏规窗瑜版洩绱?
        
        閸欏倹鏆熼敍?
        - name: 閸掑棛琚崥宥囆?
        """
        if not name:
            return Response({
                'code': 400,
                'msg': 'Category name is required',
                'success': False
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # 閴?娑撴艾濮熼柅鏄忕帆閸愬懓浠堥敍姘矤 Template 閻╊喖缍嶉崚鐘绘珟閸掑棛琚?
            template_base = self.get_template_base_path()
            category_path = template_base / name
            
            if not category_path.exists():
                return Response({
                    'code': 404,
                    'msg': 'Category not found',
                    'success': False
                }, status=status.HTTP_404_NOT_FOUND)
            
            # 濡偓閺屻儲妲搁崥锔胯礋缁岃櫣娲拌ぐ?
            if any(category_path.iterdir()):
                return Response({
                    'code': 400,
                    'msg': 'Category is not empty. Delete images in this category first',
                    'success': False
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # 閸掔娀娅庣粚铏规窗瑜?
            category_path.rmdir()
            
            logger.info(f"閻劍鍩?{request.user.username} 閸掔娀娅庨崶鍓у閸掑棛琚? {name}")
            
            return Response({
                'code': 0,
                'msg': '閸掔娀娅庨幋鎰',
                'success': True
            })
        except Exception as e:
            logger.error(f"閸掔娀娅庨崚鍡欒婢惰精瑙? {str(e)}")
            return Response({
                'code': 500,
                'msg': f'閸掔娀娅庢径杈Е: {str(e)}',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'], url_path='preview')
    def preview(self, request, pk=None):
        """
        閼惧嘲褰囬崗鍐閸ュ墽澧栨０鍕潔
        
        鏉╂柨娲栭崶鍓у閺傚洣娆㈤敍鍫㈡暏娴滃骸澧犵粩顖涙▔缁€鐚寸礆
        """
        element = self.get_object()
        
        if element.element_type != 'image':
            return Response({
                'code': 400,
                'msg': 'Element is not an image type',
                'success': False
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # 閼惧嘲褰囬崶鍓у鐠侯垰绶?
        image_path = element.config.get('image_path')
        
        if not image_path:
            return Response({
                'code': 404,
                'msg': 'Image path is missing',
                'success': False
            }, status=status.HTTP_404_NOT_FOUND)
        
        # 閴?娑撴艾濮熼柅鏄忕帆閸愬懓浠堥敍姘矤 Template 閻╊喖缍嶉弸鍕偓鐘茬暚閺佸瓨鏋冩禒鎯扮熅瀵?
        template_base = self.get_template_base_path()
        file_path = template_base / image_path
        
        if not file_path.exists():
            return Response({
                'code': 404,
                'msg': 'Image file not found',
                'success': False
            }, status=status.HTTP_404_NOT_FOUND)
        
        try:
            return FileResponse(open(file_path, 'rb'), content_type='image/png')
        except Exception as e:
            logger.error(f"鐠囪褰囬崶鍓у婢惰精瑙? {str(e)}")
            return Response({
                'code': 500,
                'msg': f'鐠囪褰囬崶鍓у婢惰精瑙? {str(e)}',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'], url_path='crop-image')
    def crop_image(self, request):
        """
        鐟佷礁澹€閸ュ墽澧栭獮鏈电箽鐎?
        
        閸欏倹鏆熼敍?
        - image_data: Base64 閸ュ墽澧栭弫鐗堝祦
        - x, y, width, height: 鐟佷礁澹€閸栧搫鐓欓崸鎰垼
        - element_name: 閸忓啰绀岄崥宥囆?
        - category: 閸ュ墽澧栭崚鍡欒
        - element_type: 閸忓啰绀岀猾璇茬€烽敍鍧昺age/pos/region閿?
        
        鏉╂柨娲栭敍?
        - 鐟佷礁澹€閸氬海娈戦崶鍓у鐠侯垰绶?
        - 閺傚洣娆㈤崫鍫濈瑖
        - 閸ф劖鐖ｆ穱鈩冧紖
        """
        try:
            from PIL import Image
            import io
            import base64
            import time
            
            # 閼惧嘲褰囬崣鍌涙殶
            image_data = request.data.get('image_data', '')
            x = int(request.data.get('x', 0))
            y = int(request.data.get('y', 0))
            width = int(request.data.get('width', 100))
            height = int(request.data.get('height', 100))
            element_name = request.data.get('element_name', 'captured_element')
            category = request.data.get('category', 'common')
            element_type = request.data.get('element_type', 'image')  # image/pos/region
            
            # 鐟欙絿鐖?Base64 閸ュ墽澧?
            if image_data.startswith('data:image'):
                image_data = image_data.split(',')[1]
            
            image_bytes = base64.b64decode(image_data)
            image = Image.open(io.BytesIO(image_bytes))
            
            # 鐟佷礁澹€閸ュ墽澧?
            cropped = image.crop((x, y, x + width, y + height))
            
            # 娣囨繂鐡ㄩ崚棰佸閺冨墎绱﹂崘鎻掑隘
            buffer = io.BytesIO()
            cropped.save(buffer, format='PNG')
            buffer.seek(0)
            
            # 鐠侊紕鐣婚崫鍫濈瑖
            file_hash = hashlib.md5(buffer.getvalue()).hexdigest()
            buffer.seek(0)
            
            # 濡偓閺屻儵鍣告径?
            existing = AppElement.objects.filter(
                config__file_hash=file_hash,
                is_active=True
            ).first()
            
            if existing:
                return Response({
                    'code': 400,
                    'msg': 'Cropped image already exists',
                    'success': False,
                    'data': {
                        'existing_element': {
                            'id': existing.id,
                            'name': existing.name,
                            'image_path': existing.config.get('image_path')
                        }
                    }
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # 娣囨繂鐡ㄩ弬鍥︽閿涘牏绮烘稉鈧担璺ㄦ暏 Template 閻╊喖缍嶉敍?
            base_path = self.get_template_base_path()
            category_path = base_path / category
            category_path.mkdir(parents=True, exist_ok=True)
            
            # 娴ｈ法鏁ら崗鍐閸氬秶袨 + 閺冨爼妫块幋鍏呯稊娑撶儤鏋冩禒璺烘倳
            filename = f"{element_name}_{int(time.time())}.png"
            file_path = category_path / filename
            
            with open(file_path, 'wb') as f:
                f.write(buffer.getvalue())
            
            # 閺嬪嫬缂撻惄绋款嚠鐠侯垰绶?
            relative_path = f"{category}/{filename}"
            
            logger.info(f"閻劍鍩?{request.user.username} 鐟佷礁澹€閸ュ墽澧? {relative_path}, 閸濆牆绗? {file_hash}")
            
            return Response({
                'code': 0,
                'msg': 'Image cropped successfully',
                'success': True,
                'data': {
                    'image_path': relative_path,
                    'file_hash': file_hash,
                    'url': f"/app-automation-templates/{relative_path}",
                    'coordinates': {
                        'x': x,
                        'y': y,
                        'width': width,
                        'height': height
                    },
                    'element_type': element_type
                }
            })

        except Exception as e:
            logger.error(f"鐟佷礁澹€閸ュ墽澧栨径杈Е: {str(e)}")
            return Response({
                'code': 500,
                'msg': f'鐟佷礁澹€婢惰精瑙? {str(e)}',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], url_path='create-from-picker')
    def create_from_picker(self, request):
        """Create an element from the visual picker."""
        from ..utils.element_picker import ElementPicker, analyze_element_for_picker

        try:
            project_id = request.data.get('project_id')
            name = request.data.get('name', '').strip()
            element_data = request.data.get('element_data')
            preferred_locator_type = request.data.get('preferred_locator_type')
            description = request.data.get('description', '').strip()

            if not project_id:
                return Response({'code': 400, 'msg': '缂哄皯蹇呴渶鍙傛暟锛歱roject_id', 'success': False}, status=status.HTTP_400_BAD_REQUEST)
            if not name:
                return Response({'code': 400, 'msg': '鍏冪礌鍚嶇О涓嶈兘涓虹┖', 'success': False}, status=status.HTTP_400_BAD_REQUEST)
            if not element_data or not isinstance(element_data, dict):
                return Response({'code': 400, 'msg': 'Missing valid element_data', 'success': False}, status=status.HTTP_400_BAD_REQUEST)

            picker = ElementPicker()
            analysis = analyze_element_for_picker(element_data)

            if not analysis['strategies']:
                return Response({'code': 400, 'msg': 'No usable locator strategy found', 'success': False, 'data': {'element': element_data}}, status=status.HTTP_400_BAD_REQUEST)

            try:
                config = picker.generate_selector_config(element_data, preferred_locator_type)
            except ValueError as e:
                return Response({'code': 400, 'msg': str(e), 'success': False}, status=status.HTTP_400_BAD_REQUEST)

            element = AppElement.objects.create(
                project_id=project_id, name=name, element_type='selector',
                config=config, description=description or analysis['display_name'], created_by=request.user
            )

            logger.info(f"User {request.user.username} created picker element {name} (ID={element.id}, locator_type={config['selector_type']})")

            serializer = AppElementSerializer(element)
            return Response({
                'code': 0, 'msg': '鍏冪礌鍒涘缓鎴愬姛', 'success': True,
                'data': {'element': serializer.data, 'analysis': analysis, 'used_locator': {'type': config['selector_type'], 'value': config.get(config['selector_type'])}}
            })
        except Exception as e:
            logger.error(f"浠庢嬀鍙栧櫒鍒涘缓鍏冪礌澶辫触: {str(e)}", exc_info=True)
            return Response({'code': 500, 'msg': f'鍒涘缓鍏冪礌澶辫触: {str(e)}', 'success': False}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], url_path='analyze-for-picker')
    def analyze_for_picker(self, request):
        """Analyze a picked element and return locator suggestions without saving."""
        from ..utils.element_picker import analyze_element_for_picker

        try:
            element_data = request.data.get('element_data')
            if not element_data or not isinstance(element_data, dict):
                return Response(
                    {'code': 400, 'msg': 'Invalid element_data payload', 'success': False},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            analysis = analyze_element_for_picker(element_data)
            return Response({'code': 0, 'msg': 'Analysis completed', 'success': True, 'data': analysis})
        except Exception as e:
            logger.error(f"Analyze element for picker failed: {str(e)}", exc_info=True)
            return Response(
                {'code': 500, 'msg': f'Analyze failed: {str(e)}', 'success': False},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
