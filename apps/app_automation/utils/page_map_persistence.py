# -*- coding: utf-8 -*-
"""Persist APP exploration page maps into reusable graph tables."""

from __future__ import annotations

import hashlib
import os
import re
import xml.etree.ElementTree as ET
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import (
    AppExplorationRun,
    AppExplorationStep,
    AppExplorationTask,
    AppPageElement,
    AppPageNode,
    AppPageTransition,
)
from .exploration_assets import clean_display_label
from .exploration_risk_guard import assess_risk_values


BOUNDS_PATTERN = re.compile(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]')


def persist_exploration_page_map(
    task: AppExplorationTask,
    run: AppExplorationRun | None,
    summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """Persist page nodes, control snapshots and transitions for one exploration run."""
    if not run or not isinstance(summary, dict):
        return _empty_stats('missing_run_or_summary')

    page_map = summary.get('page_map') or []
    if not isinstance(page_map, list):
        return _empty_stats('invalid_page_map')

    stats = _empty_stats('')
    page_nodes: dict[str, AppPageNode] = {}

    with transaction.atomic():
        for raw_page in page_map:
            if not isinstance(raw_page, dict):
                continue
            signature = str(raw_page.get('signature') or '').strip()
            if not signature:
                continue
            node, created = _upsert_page_node(task, run, raw_page)
            page_nodes[signature] = node
            stats['page_nodes_created' if created else 'page_nodes_updated'] += 1

        element_cache = _persist_page_elements(task, run, page_nodes, stats)
        _persist_page_transitions(task, run, page_nodes, element_cache, stats)

    stats['page_nodes_total'] = len(page_nodes)
    stats['persisted_at'] = timezone.now().isoformat()
    return stats


def _empty_stats(reason: str) -> dict[str, Any]:
    return {
        'status': 'skipped' if reason else 'completed',
        'reason': reason,
        'page_nodes_total': 0,
        'page_nodes_created': 0,
        'page_nodes_updated': 0,
        'page_elements_created': 0,
        'page_elements_updated': 0,
        'transitions_created': 0,
        'transitions_updated': 0,
    }


def _upsert_page_node(task: AppExplorationTask, run: AppExplorationRun, raw_page: dict[str, Any]) -> tuple[AppPageNode, bool]:
    package_name = ''
    if task.app_package:
        package_name = task.app_package.package_name
    package_name = str(raw_page.get('package') or package_name or '').strip()
    signature = str(raw_page.get('signature') or '').strip()
    defaults = {
        'activity': str(raw_page.get('activity') or '').strip(),
        'app_identifier': package_name,
        'semantic_signature': str(raw_page.get('semantic_signature') or signature).strip()[:64],
        'business_name': str(raw_page.get('business_name') or '').strip()[:255],
        'title': clean_display_label(raw_page.get('title') or '')[:255],
        'representative_screenshot': str(raw_page.get('screenshot') or '').strip(),
        'screen_size': raw_page.get('screen_size') if isinstance(raw_page.get('screen_size'), list) else [],
        'last_seen_run': run,
        'raw': _compact_page_raw(raw_page),
    }
    node, created = AppPageNode.objects.get_or_create(
        project=task.project,
        app_package=task.app_package,
        platform='android',
        page_signature=signature,
        defaults={
            **defaults,
            'first_seen_run': run,
            'visit_count': int(raw_page.get('step_count') or 0),
        },
    )
    if not created:
        node.visit_count = (node.visit_count or 0) + max(1, int(raw_page.get('step_count') or 1))
        for field, value in defaults.items():
            if field == 'representative_screenshot' and node.representative_screenshot:
                continue
            setattr(node, field, value)
        node.save(update_fields=[
            'activity',
            'app_identifier',
            'semantic_signature',
            'business_name',
            'title',
            'representative_screenshot',
            'screen_size',
            'last_seen_run',
            'visit_count',
            'raw',
            'updated_at',
        ])
    return node, created


def _compact_page_raw(raw_page: dict[str, Any]) -> dict[str, Any]:
    return {
        'first_step': raw_page.get('first_step'),
        'last_step': raw_page.get('last_step'),
        'step_count': raw_page.get('step_count'),
        'next_pages': raw_page.get('next_pages') if isinstance(raw_page.get('next_pages'), list) else [],
        'issues': raw_page.get('issues') if isinstance(raw_page.get('issues'), list) else [],
        'skipped_risks': raw_page.get('skipped_risks') if isinstance(raw_page.get('skipped_risks'), list) else [],
    }


def _persist_page_elements(
    task: AppExplorationTask,
    run: AppExplorationRun,
    page_nodes: dict[str, AppPageNode],
    stats: dict[str, Any],
) -> dict[tuple[int, str], AppPageElement]:
    cache: dict[tuple[int, str], AppPageElement] = {}
    seen_pages: set[str] = set()
    steps = run.steps.exclude(page_source_path='').order_by('step_index')
    for step in steps:
        signature = step.before_signature or ''
        page = page_nodes.get(signature)
        if not page or signature in seen_pages:
            continue
        seen_pages.add(signature)
        xml = _read_media_text(step.page_source_path)
        for raw_element in _extract_page_elements(xml, page.screen_size):
            element, created = _upsert_page_element(page, run, raw_element)
            cache[(page.id, element.element_signature)] = element
            stats['page_elements_created' if created else 'page_elements_updated'] += 1
    return cache


def _extract_page_elements(xml: str, screen_size: list[Any] | None, limit: int = 150) -> list[dict[str, Any]]:
    if not xml:
        return []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []

    elements: list[dict[str, Any]] = []
    for node in root.iter('node'):
        attrs = node.attrib
        text = clean_display_label(attrs.get('text', ''))
        content_desc = clean_display_label(attrs.get('content-desc', ''))
        resource_id = str(attrs.get('resource-id') or '').strip()
        class_name = str(attrs.get('class') or '').strip()
        bounds = str(attrs.get('bounds') or '').strip()
        clickable = attrs.get('clickable') == 'true'
        enabled = attrs.get('enabled') != 'false'
        if not enabled:
            continue
        if not any([text, content_desc, resource_id, clickable]):
            continue
        parsed_bounds = _parse_bounds(bounds)
        if not parsed_bounds:
            continue
        risk = assess_risk_values([text, content_desc, resource_id, class_name]) or {}
        element = {
            'text': text[:255],
            'content_desc': content_desc[:255],
            'resource_id': resource_id[:255],
            'class_name': class_name[:255],
            'role': _infer_role(class_name, clickable),
            'bounds': bounds,
            'normalized_bounds': _normalize_bounds(parsed_bounds, screen_size),
            'clickable': clickable,
            'enabled': enabled,
            'risk_level': str(risk.get('level') or '')[:30],
            'raw': {
                'index': attrs.get('index'),
                'selected': attrs.get('selected'),
                'checked': attrs.get('checked'),
                'focusable': attrs.get('focusable'),
            },
        }
        element['element_signature'] = _element_signature(element)
        elements.append(element)
        if len(elements) >= limit:
            break
    return elements


def _upsert_page_element(page: AppPageNode, run: AppExplorationRun, raw_element: dict[str, Any]) -> tuple[AppPageElement, bool]:
    signature = raw_element['element_signature']
    defaults = {
        'text': raw_element['text'],
        'content_desc': raw_element['content_desc'],
        'resource_id': raw_element['resource_id'],
        'class_name': raw_element['class_name'],
        'role': raw_element['role'],
        'bounds': raw_element['bounds'],
        'normalized_bounds': raw_element['normalized_bounds'],
        'clickable': raw_element['clickable'],
        'enabled': raw_element['enabled'],
        'risk_level': raw_element['risk_level'],
        'last_seen_run': run,
        'raw': raw_element['raw'],
    }
    element, created = AppPageElement.objects.get_or_create(
        page=page,
        element_signature=signature,
        defaults={
            **defaults,
            'first_seen_run': run,
            'seen_count': 1,
        },
    )
    if not created:
        element.seen_count = (element.seen_count or 0) + 1
        for field, value in defaults.items():
            setattr(element, field, value)
        element.save(update_fields=[
            'text',
            'content_desc',
            'resource_id',
            'class_name',
            'role',
            'bounds',
            'normalized_bounds',
            'clickable',
            'enabled',
            'risk_level',
            'last_seen_run',
            'seen_count',
            'raw',
            'updated_at',
        ])
    return element, created


def _persist_page_transitions(
    task: AppExplorationTask,
    run: AppExplorationRun,
    page_nodes: dict[str, AppPageNode],
    element_cache: dict[tuple[int, str], AppPageElement],
    stats: dict[str, Any],
) -> None:
    steps = run.steps.exclude(before_signature='').exclude(after_signature='').order_by('step_index')
    for step in steps:
        if step.before_signature == step.after_signature:
            continue
        from_page = page_nodes.get(step.before_signature)
        to_page = page_nodes.get(step.after_signature)
        if not from_page or not to_page:
            continue
        trigger_signature = _element_signature({
            'text': step.target_text or '',
            'content_desc': '',
            'resource_id': step.target_resource_id or '',
            'class_name': step.target_class or '',
            'bounds': step.bounds or '',
        })
        trigger_element = element_cache.get((from_page.id, trigger_signature))
        transition, created = AppPageTransition.objects.get_or_create(
            project=task.project,
            app_package=task.app_package,
            from_page=from_page,
            to_page=to_page,
            action_type=step.action_type or 'tap',
            trigger_text=(step.target_text or '')[:255],
            trigger_resource_id=(step.target_resource_id or '')[:255],
            trigger_bounds=(step.bounds or '')[:100],
            defaults={
                'trigger_element': trigger_element,
                'success_count': 1 if step.changed and not step.issue_type else 0,
                'failure_count': 0 if step.changed and not step.issue_type else 1,
                'confidence': 1.0 if step.changed and not step.issue_type else 0.0,
                'last_seen_run': run,
                'raw': {'step_index': step.step_index, 'issue_type': step.issue_type},
            },
        )
        if created:
            stats['transitions_created'] += 1
            continue
        if step.changed and not step.issue_type:
            transition.success_count = (transition.success_count or 0) + 1
        else:
            transition.failure_count = (transition.failure_count or 0) + 1
        total = transition.success_count + transition.failure_count
        transition.confidence = round(transition.success_count / total, 4) if total else 0
        transition.trigger_element = transition.trigger_element or trigger_element
        transition.last_seen_run = run
        transition.raw = {'step_index': step.step_index, 'issue_type': step.issue_type}
        transition.save(update_fields=[
            'trigger_element',
            'success_count',
            'failure_count',
            'confidence',
            'last_seen_run',
            'raw',
            'updated_at',
        ])
        stats['transitions_updated'] += 1


def _read_media_text(relative_path: str) -> str:
    if not relative_path:
        return ''
    safe_path = str(relative_path).replace('\\', '/').lstrip('/')
    if safe_path.startswith('media/'):
        safe_path = safe_path[len('media/'):]
    path = os.path.abspath(os.path.join(settings.MEDIA_ROOT, safe_path))
    media_root = os.path.abspath(settings.MEDIA_ROOT)
    if not path.startswith(media_root) or not os.path.exists(path):
        return ''
    with open(path, 'r', encoding='utf-8', errors='ignore') as file:
        return file.read()


def _parse_bounds(bounds: str) -> tuple[int, int, int, int] | None:
    match = BOUNDS_PATTERN.match(bounds or '')
    if not match:
        return None
    x1, y1, x2, y2 = (int(value) for value in match.groups())
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _normalize_bounds(bounds: tuple[int, int, int, int], screen_size: list[Any] | None) -> dict[str, float]:
    width = int(screen_size[0]) if screen_size and len(screen_size) >= 2 and screen_size[0] else 0
    height = int(screen_size[1]) if screen_size and len(screen_size) >= 2 and screen_size[1] else 0
    x1, y1, x2, y2 = bounds
    if width <= 0 or height <= 0:
        return {}
    return {
        'x1': round(x1 / width, 6),
        'y1': round(y1 / height, 6),
        'x2': round(x2 / width, 6),
        'y2': round(y2 / height, 6),
    }


def _infer_role(class_name: str, clickable: bool) -> str:
    lower = (class_name or '').lower()
    if 'button' in lower:
        return 'button'
    if 'edittext' in lower:
        return 'input'
    if 'checkbox' in lower or 'switch' in lower:
        return 'switch'
    if 'image' in lower:
        return 'image'
    if 'textview' in lower:
        return 'text'
    if clickable:
        return 'clickable'
    return 'view'


def _element_signature(element: dict[str, Any]) -> str:
    seed = '|'.join([
        str(element.get('resource_id') or ''),
        str(element.get('text') or ''),
        str(element.get('content_desc') or ''),
        str(element.get('class_name') or ''),
        str(element.get('bounds') or ''),
    ])
    return hashlib.sha1(seed.encode('utf-8', errors='ignore')).hexdigest()
