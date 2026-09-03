# -*- coding: utf-8 -*-
"""Utilities for turning exploration traces into reusable QA assets."""

from __future__ import annotations

import re
from typing import Any

from django.utils import timezone

from ..models import AppExplorationTask, AppTestCase
from .exploration_risk_guard import assess_risk_values

UNREADABLE_LABEL_RE = re.compile(r'[\u25a0-\u25a1\ufffd\ue000-\uf8ff]')
CAMEL_RE = re.compile(r'(?<!^)(?=[A-Z])')
INVALID_COVERAGE_KEYWORD_MARKERS = (
    '观察', '确认', '复核', '包括', '是否', '文案', '目标', '路径', '修正',
    '建议', '检查', '进入', '再进入', '点击', '打开', '查看', '验证', '测试',
    '人工复现', '至第', '第', '步骤', '网络请求', '权限提示', 'Toast', 'toast',
)


CONTROL_NAME_MAP = {
    'btnServerList': '服务器列表按钮',
    'serverList': '服务器列表',
    'createNewLayout': '创建入口',
    'btnCreateServer': '创建社区按钮',
    'createServer': '创建社区',
    'btnLogin': '登录按钮',
    'btn_login': '登录按钮',
    'btnLogout': '退出登录按钮',
    'logout': '退出登录',
    'ivBack': '返回按钮',
    'ifvBack': '返回按钮',
    'back': '返回',
    'll_search_layout': '搜索区域',
    'search': '搜索',
    'tabHome': '首页 Tab',
    'tabMessage': '消息 Tab',
    'tabMine': '我的 Tab',
    'drawerLayout': '侧边栏区域',
    'content': '页面内容区',
}

TOKEN_NAME_MAP = {
    'btn': '按钮',
    'button': '按钮',
    'iv': '图片',
    'ifv': '图片按钮',
    'img': '图片',
    'image': '图片',
    'tv': '文本',
    'text': '文本',
    'txt': '文本',
    'et': '输入框',
    'edit': '输入框',
    'input': '输入框',
    'layout': '区域',
    'container': '容器',
    'list': '列表',
    'item': '条目',
    'tab': 'Tab',
    'home': '首页',
    'message': '消息',
    'mine': '我的',
    'community': '社区',
    'server': '社区',
    'create': '创建',
    'new': '新建',
    'search': '搜索',
    'login': '登录',
    'logout': '退出登录',
    'cancel': '取消',
    'confirm': '确认',
    'ok': '确认',
    'save': '保存',
    'submit': '提交',
    'back': '返回',
}


def clean_display_label(value: Any) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    text = UNREADABLE_LABEL_RE.sub('', text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return ''
    readable_chars = [char for char in text if char.isalnum() or '\u4e00' <= char <= '\u9fff']
    if not readable_chars:
        return ''
    return text


def normalize_control_name(value: Any) -> str:
    """Turn resource-id tails like btnServerList into a readable Chinese label."""
    raw = clean_display_label(value)
    if not raw:
        return ''
    tail = raw.split('/')[-1].strip()
    if not tail:
        return ''
    if tail in CONTROL_NAME_MAP:
        return CONTROL_NAME_MAP[tail]
    lower_tail = tail.lower()
    for key, label in CONTROL_NAME_MAP.items():
        if key.lower() == lower_tail:
            return label

    # Already contains Chinese, so it is usually more meaningful than a guessed label.
    if any('\u4e00' <= char <= '\u9fff' for char in tail):
        return tail

    words = _split_identifier(tail)
    translated = []
    for word in words:
        mapped = TOKEN_NAME_MAP.get(word.lower())
        if mapped and mapped not in translated:
            translated.append(mapped)

    if translated:
        # Keep short, business-facing names. "创建 社区 区域" is less useful than "创建社区入口".
        text = ''.join(translated)
        text = text.replace('创建社区区域', '创建社区入口')
        text = text.replace('服务器列表按钮', '服务器列表按钮')
        return text

    return tail


def readable_step_target(step) -> str:
    return (
        clean_display_label(step.target_text)
        or normalize_control_name(step.target_resource_id)
        or normalize_control_name(step.target_class)
        or '页面区域'
    )


def technical_step_target(step) -> str:
    parts = []
    if step.target_resource_id:
        parts.append(f'resource-id: {step.target_resource_id}')
    if step.target_text:
        parts.append(f'text: {step.target_text}')
    if step.target_class:
        parts.append(f'class: {step.target_class}')
    if step.bounds:
        parts.append(f'bounds: {step.bounds}')
    if step.x is not None and step.y is not None:
        parts.append(f'坐标: ({step.x}, {step.y})')
    return '；'.join(parts) or '-'


def _clean_coverage_keyword(value: Any) -> str:
    text = clean_display_label(str(value or ''))
    text = re.sub(r'^[在再去到从往]+', '', text)
    text = re.sub(r'(页面|页|模块|区域|入口)$', '', text)
    text = re.sub(r'[“”"\'`（）()\[\]【】<>《》]', '', text)
    return text.strip(' \t\r\n,，。；;、：:!?！？')


def _is_valid_coverage_keyword(value: Any) -> bool:
    text = _clean_coverage_keyword(value)
    if text.isdigit():
        return False
    if not (2 <= len(text) <= 8):
        return False
    return not any(marker in text for marker in INVALID_COVERAGE_KEYWORD_MARKERS)


def readable_step_action(step) -> str:
    raw_action = clean_display_label(step.action_label)
    target = readable_step_target(step)
    if step.action_type == 'tap':
        return f'点击 {target}'
    if step.action_type == 'swipe':
        return _readable_swipe_action(step)
    if step.action_type == 'back':
        return '返回上一页'
    if step.action_type == 'wait':
        return '等待页面稳定'
    if step.action_type == 'stop':
        return raw_action or '停止探索'
    return raw_action or f'探索步骤 {step.step_index}'


def build_exploration_insights(task: AppExplorationTask) -> dict[str, Any]:
    """Build a human-readable summary for an exploration task."""
    steps = list(task.report_steps())
    summary = task.summary or {}
    latest_run = task.latest_run()
    target_results = list(latest_run.target_results.all()) if latest_run else []
    target_review_rules = list(task.inspection_review_rules.filter(enabled=True)) if task.id else []
    target_review_stats = _build_target_review_stats(target_results, target_review_rules)
    issue_reviews = summary.get('issue_reviews') if isinstance(summary.get('issue_reviews'), dict) else {}
    issue_review_rules = summary.get('issue_review_rules') if isinstance(summary.get('issue_review_rules'), list) else []
    ignored_issues = []
    issues = []
    for step in steps:
        if not (step.issue_type or step.issue_message):
            continue
        issue = {
            'step_index': step.step_index,
            'issue_type': step.issue_type,
            'issue_message': step.issue_message,
            'action': readable_step_action(step),
            'activity': step.after_activity or step.before_activity,
            'screenshot': step.after_screenshot or step.before_screenshot,
            'target_text': step.target_text,
            'target_resource_id': step.target_resource_id,
            'target_class': step.target_class,
            'bounds': step.bounds,
            'review': issue_reviews.get(str(step.step_index)) or {},
        }
        ignore_reason = _issue_ignore_reason(step, issue.get('review'), issue_review_rules)
        if ignore_reason:
            issue['ignore_reason'] = ignore_reason
            ignored_issues.append(issue)
            continue
        issues.append(issue)

    path = [
        {
            'step_index': step.step_index,
            'action_type': step.action_type,
            'action': readable_step_action(step),
            'target': readable_step_target(step),
            'changed': step.changed,
            'activity': step.after_activity or step.before_activity,
        }
        for step in steps
        if step.action_type in ('tap', 'swipe', 'back')
    ]

    risk_skipped_count = int(summary.get('risk_skipped_count') or 0)

    failed_start_target = _extract_failed_start_action_target(task.error_message)
    if task.status == 'error' and failed_start_target:
        conclusion = f'本轮失败原因是起始导航目标不可达：{failed_start_target}。建议移除该动作，或改为人工确认后的条件动作。'
        risk_level = 'high'
    elif task.status == 'error':
        conclusion = '探索任务执行异常，建议先查看错误信息和日志，再判断是否为设备、ADB、APP 启动或执行器异常。'
        risk_level = 'high'
    elif issues:
        conclusion = f'本次探索发现 {len(issues)} 个疑似问题，建议按复现路径人工确认。'
        risk_level = 'medium'
    elif risk_skipped_count:
        conclusion = f'本次探索已自动跳过 {risk_skipped_count} 个高风险控件，路径可参考，但转用例前需要人工复核风险边界。'
        risk_level = 'medium'
    elif task.status == 'completed':
        conclusion = '本次探索未发现明显异常，可将有效路径沉淀为回归用例草稿。'
        risk_level = 'low'
    else:
        conclusion = '探索任务尚未完成，等待执行结束后再判断结论。'
        risk_level = 'info'

    return {
        'conclusion': conclusion,
        'risk_level': risk_level,
        'strategy': task.strategy or 'rule_mvp',
        'entry_navigation': summary.get('entry_navigation', []),
        'entry_failed_keywords': summary.get('entry_failed_keywords', []),
        'objective_keywords': summary.get('objective_keywords', []),
        'objective_hits': summary.get('objective_hits', {}),
        'objective_uncovered': summary.get('objective_uncovered', []),
        'target_coverage': _build_target_coverage(summary),
        'exploration_guard': _build_exploration_guard(summary),
        'risk_skipped_count': risk_skipped_count,
        'skipped_risks': summary.get('skipped_risks', []),
        'issue_type_counts': summary.get('issue_type_counts', {}),
        'page_map': summary.get('page_map', []),
        'page_coverage': _build_page_coverage(summary),
        'issue_count': len(issues),
        'issues': issues,
        'ignored_issues': ignored_issues,
        'issue_reviews': issue_reviews,
        'issue_review_rules': issue_review_rules,
        'target_review_stats': target_review_stats,
        'target_review_rules': [
            {
                'id': rule.id,
                'target_name': rule.target_name,
                'status': rule.status,
                'resolution': rule.resolution,
                'note': rule.note,
            }
            for rule in target_review_rules
        ],
        'reproduction_path': path,
        'conversion_summary': _build_conversion_summary(steps),
        'ai_analysis': summary.get('ai_analysis') or {},
        'suggestions': _build_suggestions(task, issues, path),
        'can_convert_to_case': bool(path) and task.status in ('completed', 'error', 'stopped'),
    }


def _build_target_review_stats(target_results, rules) -> dict[str, Any]:
    reviewed = 0
    suppressed = 0
    pending = 0
    rule_hits = 0
    resolution_counts: dict[str, int] = {}
    actionable_statuses = {'found_unconfirmed', 'not_found', 'risk_skipped', 'anchor_recovery_failed', 'error'}
    suppressing_resolutions = {'normal_behavior', 'rule_exception', 'target_should_remove'}

    for result in target_results:
        resolution = result.review_resolution
        source = 'manual' if resolution else ''
        if not resolution:
            rule = _matching_target_review_rule(result, rules)
            if rule:
                resolution = rule.resolution
                source = 'rule'
                rule_hits += 1
        if resolution:
            reviewed += 1
            resolution_counts[resolution] = resolution_counts.get(resolution, 0) + 1
            if resolution in suppressing_resolutions:
                suppressed += 1
            continue
        if result.status in actionable_statuses:
            pending += 1

    return {
        'reviewed_count': reviewed,
        'suppressed_count': suppressed,
        'pending_count': pending,
        'rule_hit_count': rule_hits,
        'resolution_counts': resolution_counts,
    }


def _matching_target_review_rule(result, rules):
    for rule in rules:
        if rule.target_name != result.target_name:
            continue
        if rule.status and rule.status != result.status:
            continue
        return rule
    return None


def _extract_failed_start_action_target(message: str) -> str:
    match = re.search(r'未找到起始导航目标[:：]\s*([^，。；;\n\r]+)', str(message or ''))
    return match.group(1).strip() if match else ''


def _issue_ignore_reason(step, review: dict[str, Any] | None, rules: list[dict[str, Any]]) -> str:
    review = review if isinstance(review, dict) else {}
    resolution = str(review.get('resolution') or '')
    if resolution in {'normal_behavior', 'rule_exception'}:
        return review.get('note') or '已人工复核为正常行为'
    if resolution == 'needs_assertion':
        return review.get('note') or '已转为需补充断言，不再作为疑似缺陷'

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if not rule.get('enabled', True):
            continue
        if _issue_review_rule_matches(step, rule):
            return rule.get('note') or '命中人工复核规则，已忽略该类问题'
    return ''


def _issue_review_rule_matches(step, rule: dict[str, Any]) -> bool:
    if rule.get('issue_type') and rule.get('issue_type') != step.issue_type:
        return False
    target_type = str(rule.get('target_type') or '')
    target_value = str(rule.get('target_value') or '')
    if not target_type or not target_value:
        return False
    actual = {
        'resource_id': step.target_resource_id,
        'class_name': step.target_class,
        'text': step.target_text,
    }.get(target_type, '')
    return bool(actual and target_value and target_value in actual)


def convert_exploration_to_test_case(task: AppExplorationTask, user, name: str = '', description: str = '') -> tuple[AppTestCase, list[dict[str, Any]]]:
    """Create a maintainable draft test case from exploration steps."""
    ui_flow = build_ui_flow_draft(task)
    if not ui_flow:
        raise ValueError('当前探索任务没有可转换的操作步骤')

    case_name = name.strip() if name else f'探索草稿 - {task.name}'
    case_description = description.strip() if description else _build_case_description_with_quality(task)
    test_case = AppTestCase.objects.create(
        project=task.project,
        app_package=task.app_package,
        name=case_name,
        description=case_description,
        ui_flow=ui_flow,
        created_by=user,
    )
    return test_case, ui_flow


def build_ui_flow_draft(task: AppExplorationTask) -> list[dict[str, Any]]:
    """Convert trace steps to the existing UI Flow schema."""
    ui_flow: list[dict[str, Any]] = []
    for step in task.report_steps():
        if _step_forbidden_risk(step):
            continue
        converted = _step_to_ui_flow(step)
        if converted:
            ui_flow.append(converted)
    return ui_flow


def _build_conversion_summary(steps: list[AppExplorationStep]) -> dict[str, Any]:
    convertible = [step for step in steps if step.action_type in ('tap', 'swipe', 'wait')]
    high = 0
    medium = 0
    low = 0
    needs_review = []
    coordinate_only = 0
    no_change_taps = 0
    issue_steps = 0
    forbidden_risk_steps = 0

    for step in convertible:
        stability = _step_stability(step)
        level = stability['level']
        forbidden_risk = _step_forbidden_risk(step)
        if forbidden_risk:
            forbidden_risk_steps += 1
        if level == 'high':
            high += 1
        elif level == 'medium':
            medium += 1
        else:
            low += 1

        selector_has_semantic = bool(step.target_resource_id or step.target_text)
        if step.action_type == 'tap' and not selector_has_semantic:
            coordinate_only += 1
        if step.action_type == 'tap' and not step.changed:
            no_change_taps += 1
        if step.issue_type or step.issue_message:
            issue_steps += 1
        if level != 'high':
            needs_review.append({
                'step_index': step.step_index,
                'action': readable_step_action(step),
                'target': readable_step_target(step),
                'stability': level,
                'reason': stability['reason'],
                'risk': forbidden_risk or {},
            })

    total = len(convertible)
    return {
        'total_steps': total,
        'high_confidence_steps': high,
        'medium_confidence_steps': medium,
        'low_confidence_steps': low,
        'needs_review_count': len(needs_review),
        'coordinate_only_count': coordinate_only,
        'no_change_tap_count': no_change_taps,
        'issue_step_count': issue_steps,
        'forbidden_risk_step_count': forbidden_risk_steps,
        'ready_rate': round(high / total * 100, 1) if total else 0,
        'needs_review': needs_review[:10],
    }


def _step_to_ui_flow(step) -> dict[str, Any] | None:
    if step.action_type == 'tap':
        return {
            'type': 'click',
            'name': readable_step_action(step) or f'点击探索步骤 {step.step_index}',
            'config': _selector_config_from_step(step),
            'meta': _step_meta(step),
        }
    if step.action_type == 'swipe':
        raw = step.raw or {}
        start = raw.get('start') or [step.x or 0, step.y or 0]
        end = raw.get('end') or [step.x or 0, max(int(step.y or 0) - 500, 0)]
        return {
            'type': 'swipe',
            'name': readable_step_action(step) or f'滑动探索步骤 {step.step_index}',
            'config': {
                'start': start,
                'end': end,
                'duration': raw.get('duration', 0.45),
            },
            'meta': _step_meta(step),
        }
    if step.action_type == 'wait':
        return {
            'type': 'wait',
            'name': readable_step_action(step) or '等待页面稳定',
            'config': {'duration': 1},
            'meta': _step_meta(step),
        }
    return None


def _selector_config_from_step(step) -> dict[str, Any]:
    selector = {
        key: value
        for key, value in {
            'resource_id': step.target_resource_id,
            'text': step.target_text,
            'class': step.target_class,
            'bounds': step.bounds,
        }.items()
        if value
    }
    fallback = [step.x or 0, step.y or 0]
    if any(selector.get(key) for key in ('resource_id', 'text', 'class')):
        return {
            'selector_type': 'selector',
            'selector': selector,
            'fallback_selector_type': 'pos',
            'fallback_selector': fallback,
        }
    return {
        'selector_type': 'pos',
        'selector': fallback,
    }


def _step_meta(step) -> dict[str, Any]:
    stability = _step_stability(step)
    forbidden_risk = _step_forbidden_risk(step)
    return {
        'source': 'exploration',
        'exploration_task_id': step.task_id,
        'exploration_step_index': step.step_index,
        'changed': step.changed,
        'stability': stability['level'],
        'stability_reason': stability['reason'],
        'needs_review': stability['level'] != 'high' or bool(forbidden_risk),
        'risk': forbidden_risk or (step.raw or {}).get('risk') or {},
        'before_activity': step.before_activity,
        'after_activity': step.after_activity,
        'issue_type': step.issue_type,
        'issue_message': step.issue_message,
    }


def _build_case_description(task: AppExplorationTask) -> str:
    created_at = timezone.localtime().strftime('%Y-%m-%d %H:%M:%S')
    return (
        f'由 AI 探索任务「{task.name}」生成的用例草稿。\n'
        f'生成时间：{created_at}\n'
        f'探索目标：{task.objective or "-"}\n'
        '说明：该草稿优先保留探索路径，部分步骤可能使用坐标兜底，建议进入用例编排后替换为语义元素。'
    )


def _build_case_description_with_quality(task: AppExplorationTask) -> str:
    created_at = timezone.localtime().strftime('%Y-%m-%d %H:%M:%S')
    conversion = _build_conversion_summary(list(task.report_steps()))
    review_lines = [
        f"- 第 {item.get('step_index') or '-'} 步：{item.get('reason') or '建议人工确认'}"
        for item in conversion.get('needs_review', [])[:5]
    ]
    review_text = '\n'.join(review_lines) if review_lines else '- 无'
    return (
        f'由 AI 探索任务《{task.name}》生成的用例草稿。\n'
        f'生成时间：{created_at}\n'
        f'探索目标：{task.objective or "-"}\n'
        f'质量预估：高可信 {conversion.get("high_confidence_steps", 0)} / '
        f'{conversion.get("total_steps", 0)} 步，可用率 {conversion.get("ready_rate", 0)}%，'
        f'需复核 {conversion.get("needs_review_count", 0)} 步，'
        f'坐标兜底 {conversion.get("coordinate_only_count", 0)} 步。\n'
        f'需复核步骤：\n{review_text}\n'
        '说明：该草稿优先保留探索路径，部分步骤可能使用坐标兜底，建议进入用例编排后替换为语义元素。'
    )


def _build_suggestions(task: AppExplorationTask, issues: list[dict[str, Any]], path: list[dict[str, Any]]) -> list[str]:
    suggestions = []
    summary = task.summary or {}
    if issues:
        suggestions.append('优先人工复现疑似问题，并结合截图、Activity、logcat 判断是否为真实缺陷。')
    if path:
        suggestions.append('可以将有效探索路径转成用例草稿，再把坐标步骤替换为语义元素。')
    failed_keywords = summary.get('entry_failed_keywords') or []
    if failed_keywords:
        suggestions.append(f'入口关键词未命中：{", ".join(failed_keywords)}。建议检查 APP 是否已登录、页面是否可达，或改用截图选点补一条起始导航。')
    uncovered = summary.get('objective_uncovered') or []
    if uncovered:
        suggestions.append(f'探索目标未完全覆盖：{", ".join(uncovered[:8])}。建议补充入口关键词或缩小探索目标。')
    if summary.get('risk_skipped_count', 0):
        suggestions.append('本次已自动跳过高风险控件，可在风险跳过明细中确认是否符合预期。')
    if task.strategy == 'rule_mvp':
        suggestions.append('后续可按场景选择冒烟、稳定性、表单或列表策略，减少无效探索。')
    if not issues and task.status == 'completed':
        suggestions.append('本次未发现明显异常，建议扩大探索步数或换页面入口继续覆盖。')
    return suggestions or ['任务信息不足，建议重新执行一次探索。']


def _split_identifier(value: str) -> list[str]:
    text = re.sub(r'[_\-.]+', ' ', value)
    text = CAMEL_RE.sub(' ', text)
    return [word for word in text.split() if word]


def _readable_swipe_action(step) -> str:
    raw = step.raw or {}
    start = raw.get('start') or []
    end = raw.get('end') or []
    if len(start) >= 2 and len(end) >= 2:
        try:
            dx = int(end[0]) - int(start[0])
            dy = int(end[1]) - int(start[1])
            if abs(dx) > abs(dy):
                return '向右滑动' if dx > 0 else '向左滑动'
            return '向下滑动' if dy > 0 else '向上滑动'
        except (TypeError, ValueError):
            pass
    return '滑动页面'


def _build_target_coverage(summary: dict[str, Any]) -> dict[str, Any]:
    keywords = []
    for item in summary.get('objective_keywords') or []:
        keyword = _clean_coverage_keyword(item)
        if keyword and _is_valid_coverage_keyword(keyword) and keyword not in keywords:
            keywords.append(keyword)
    hits = summary.get('objective_hits') or {}
    normalized_hits = {
        _clean_coverage_keyword(keyword): count
        for keyword, count in hits.items()
        if _is_valid_coverage_keyword(keyword)
    }
    for item in summary.get('entry_navigation') or []:
        keyword = _clean_coverage_keyword(item.get('keyword') if isinstance(item, dict) else '')
        if keyword and _is_valid_coverage_keyword(keyword) and keyword not in keywords:
            keywords.append(keyword)
        if keyword and item.get('status') == 'matched':
            normalized_hits[keyword] = max(int(normalized_hits.get(keyword, 0) or 0), 1)
    covered = [keyword for keyword in keywords if int(normalized_hits.get(keyword, 0) or 0) > 0]
    uncovered = [keyword for keyword in keywords if keyword not in covered]
    total = len(keywords)
    return {
        'total': total,
        'covered': len(covered),
        'uncovered': len(uncovered),
        'rate': round(len(covered) / total * 100, 1) if total else 0,
        'covered_keywords': covered,
        'uncovered_keywords': uncovered,
        'invalid_keywords_filtered': [
            str(item)
            for item in summary.get('objective_keywords') or []
            if not _is_valid_coverage_keyword(item)
        ],
    }


def _build_page_coverage(summary: dict[str, Any]) -> dict[str, Any]:
    pages = summary.get('page_map') or []
    issue_pages = [page for page in pages if page.get('issues')]
    repeated_pages = [page for page in pages if page.get('step_count', 0) > 2]
    clicked_count = sum(len(page.get('clicked_controls') or []) for page in pages)
    return {
        'page_count': len(pages),
        'issue_page_count': len(issue_pages),
        'repeated_page_count': len(repeated_pages),
        'clicked_control_count': clicked_count,
    }


def _build_exploration_guard(summary: dict[str, Any]) -> dict[str, Any]:
    stop_reason = str(summary.get('exploration_stop_reason') or '').strip()
    return {
        'stop_reason': stop_reason,
        'stopped_by_guard': bool(stop_reason),
        'empty_page_escape_count': int(summary.get('empty_page_escape_count') or 0),
        'unresponsive_target_count': int(summary.get('unresponsive_target_count') or 0),
        'stagnant_action_count': int(summary.get('stagnant_action_count') or 0),
        'low_value_action_count': int(summary.get('low_value_action_count') or 0),
        'repeated_semantic_hit_count': int(summary.get('repeated_semantic_hit_count') or 0),
        'explored_semantic_pages': int(summary.get('explored_semantic_pages') or 0),
    }


def _step_stability(step) -> dict[str, str]:
    raw = step.raw or {}
    selector_has_semantic = bool(step.target_resource_id or step.target_text)
    forbidden_risk = _step_forbidden_risk(step)
    if forbidden_risk:
        label = forbidden_risk.get('group') or forbidden_risk.get('keyword') or '高风险'
        return {'level': 'low', 'reason': f'命中高风险语义「{label}」，默认不建议沉淀'}
    if step.issue_type:
        return {'level': 'low', 'reason': f'该步骤产生疑似问题：{step.issue_type}'}
    if step.action_type == 'tap' and not step.changed:
        return {'level': 'medium', 'reason': '点击后页面无明显变化，建议人工确认是否有效'}
    if step.action_type == 'tap' and not selector_has_semantic:
        return {'level': 'low', 'reason': '缺少语义定位信息，主要依赖坐标兜底'}
    if raw.get('risk', {}).get('level') == 'caution':
        return {'level': 'medium', 'reason': '命中谨慎风险词，建议人工确认'}
    if raw.get('objective_hits'):
        return {'level': 'high', 'reason': '命中探索目标且具备可复用路径价值'}
    if selector_has_semantic:
        return {'level': 'high', 'reason': '具备 text 或 resource-id 等语义定位信息'}
    return {'level': 'medium', 'reason': '普通探索步骤，建议结合截图确认'}


def _step_forbidden_risk(step) -> dict[str, Any] | None:
    raw_risk = (step.raw or {}).get('risk') or {}
    if raw_risk.get('level') == 'forbidden':
        return raw_risk
    risk = assess_risk_values([
        step.target_text,
        step.target_resource_id,
        step.target_class,
        step.action_label,
        readable_step_target(step),
    ])
    if risk and risk.get('level') == 'forbidden':
        return risk
    return None
