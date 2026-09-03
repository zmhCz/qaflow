# -*- coding: utf-8 -*-
"""LLM advisor for APP exploration reports.

The advisor does not control the device. It only reads the deterministic
exploration report and returns a human-reviewable analysis.
"""

from __future__ import annotations

import json
import re
from typing import Any

from asgiref.sync import async_to_sync
from django.utils import timezone

from apps.requirement_analysis.models import AIModelConfig, AIModelService, PromptConfig

from ..models import AppExplorationTask
from .exploration_assets import build_exploration_insights, readable_step_action, readable_step_target


MODEL_ROLE_PRIORITY = ('app_exploration', 'browser_use_text', 'reviewer', 'writer')
AI_CONTROLLED_SOURCE_TYPES = {'ai_next_round', 'ai_adjusted_retry'}
AI_ALLOWED_START_ACTION_TYPES = {'tap_text', 'swipe', 'wait', 'back'}
AI_ALLOWED_SWIPE_DIRECTIONS = {'up', 'down', 'left', 'right'}
STABLE_START_TARGETS = {
    '首页', '消息', '社区', '我的', '发现', '搜索', '设置', '登录', '注册',
    '通知', '会话', '聊天', '联系人', '好友', '返回首页',
}
PROCESS_KEYWORD_MARKERS = (
    '观察', '确认', '复核', '包括', '是否', '文案', '目标', '路径', '修正',
    '建议', '检查', '进入', '再进入', '点击', '打开', '查看', '验证', '测试',
    '人工复现', '至第', '第', '步骤', '网络请求', '权限提示', 'Toast', 'toast',
)
DYNAMIC_TARGET_MARKERS = (
    '条目', '列表项', '第一个', '第二个', '某个', '任意', '指定', '目标数据',
    '消息条目', '用户条目', '商品', '订单', '卡片', 'item',
)
CONDITIONAL_TARGET_MARKERS = (
    '取消', '关闭', '我知道了', '稍后', '暂不', '以后再说', '允许', '拒绝',
    '确定', '确认', '继续',
)
BLOCKED_ACTION_KEYWORDS = ('删除', '支付', '购买', '充值', '注销', '退出登录', '解散', '清空', '解绑')
ENTRY_KEYWORD_CANDIDATES = (
    '首页', '消息', '私信', '聊天', '会话', '好友设置', '好友', '社区', '创建',
    '我的', '设置', '搜索', '列表', '通知', '联系人', '登录', '注册',
)


def analyze_exploration_with_ai(task: AppExplorationTask) -> dict[str, Any]:
    """Analyze an exploration task with the active configured LLM."""
    config = _select_model_config()
    if not config:
        return {
            'status': 'not_configured',
            'message': '未找到可用的大模型配置，请先在配置中心的 AI 探索模型配置中启用 app_exploration 配置。',
        }

    prompt_config = PromptConfig.get_active_config('app_exploration')
    payload = _build_analysis_payload(task)
    messages = [
        {
            'role': 'system',
            'content': (
                '你是 QAFlow 的 APP 自动化探索测试分析助手。'
                '你只负责分析报告，不控制设备，不编造日志，不夸大风险。'
                '请基于输入 JSON 输出严格 JSON，不要输出 Markdown。'
            ),
        },
        {
            'role': 'user',
            'content': _build_prompt_config_header(prompt_config) + (
                '请分析以下 APP AI 探索测试报告，输出 JSON：\n'
                '{\n'
                '  "conclusion": "一句话结论",\n'
                '  "risk_level": "low|medium|high",\n'
                '  "defect_candidates": [{"title": "疑似缺陷标题", "reason": "判断依据", "step_index": 1}],\n'
                '  "false_positive_candidates": [{"title": "可能误报标题", "reason": "为什么可能是正常业务行为", "step_index": 1, "suggested_archive_type": "normal_behavior|rule_exception|needs_assertion|ignore"}],\n'
                '  "root_cause_hypotheses": ["可能原因"],\n'
                '  "next_exploration_targets": ["下一轮建议探索目标"],\n'
                '  "inspection_plan": {\n'
                '    "summary": "下一轮受控巡检计划摘要",\n'
                '    "coverage_gaps": ["本轮没有覆盖或需要复核的业务缺口"],\n'
                '    "recommended_targets": [\n'
                '      {"target_name": "稳定可见的控件名称", "page_name": "业务页面", "semantic_role": "TAB|按钮|输入框|页面入口|列表项", "priority": "P0|P1|P2", "reason": "推荐原因", "risk": "low|medium|high"}\n'
                '    ],\n'
                '    "start_actions": [\n'
                '      {"action_type": "tap_text", "target": "稳定入口短词", "reason": "为什么可作为起始导航", "risk": "low|medium|high"}\n'
                '    ],\n'
                '    "risk_controls": ["本轮需要避开的动作或人工确认项"]\n'
                '  },\n'
                '  "semantic_suggestions": [\n'
                '    {"page_name": "页面名称", "target_name": "控件名称", "semantic_role": "控件角色", "suggestion": "语义库维护建议", "reason": "证据依据"}\n'
                '  ],\n'
                '  "action_proposals": [\n'
                '    {"action_type": "tap_text|swipe|wait|back", "target": "可见中文按钮或入口文字", "direction": "up|down|left|right", "seconds": 1, "reason": "建议原因", "risk": "low|medium|high", "confidence": 0.8}\n'
                '  ],\n'
                '  "case_suggestions": ["适合沉淀为回归用例的建议"],\n'
                '  "manual_review_points": ["需要人工确认的点"]\n'
                '}\n\n'
                'inspection_plan 是最重要的输出：它必须是下一轮 target_inspection 受控巡检计划，不是自由探索计划。\n'
                '动作建议只允许低风险导航动作；不要输出坐标点击，不要建议删除、支付、注销、退出登录、解散、清空、解绑等危险动作。\n'
                '如果建议点击文字，优先输出稳定入口短词，例如“首页”“消息”“社区”“我的”“设置”；不要把“消息条目”“第一个商品”“某个用户”等动态列表项作为起始导航建议。\n\n'
                '如果输入里包含 iteration_context，请结合历史迭代判断：避免重复已经跑空的方向，优先给出可验证、可人工复核的下一轮探索建议。\n\n'
                f'输入报告 JSON：\n{json.dumps(payload, ensure_ascii=False)}'
            ),
        },
    ]

    response = async_to_sync(AIModelService.call_openai_compatible_api)(
        config,
        messages,
        max_tokens=min(int(config.max_tokens or 4096), 2048),
    )
    content = _extract_message_content(response)
    parsed = _parse_json_response(content)
    parsed = _attach_evidence_traces(parsed, task)
    parsed.update({
        'status': 'success',
        'model_config_id': config.id,
        'model_name': config.model_name,
        'model_role': config.role,
        'prompt_config_id': prompt_config.id if prompt_config else None,
        'prompt_config_name': prompt_config.name if prompt_config else None,
        'prompt_type': prompt_config.prompt_type if prompt_config else 'builtin_default',
        'audit': _build_analysis_audit(task, payload, config, prompt_config),
    })
    return parsed


def _attach_evidence_traces(analysis: dict[str, Any], task: AppExplorationTask) -> dict[str, Any]:
    steps = {step.step_index: step for step in task.steps.order_by('step_index')}
    if not steps:
        analysis['evidence_summary'] = {
            'traceable_item_count': 0,
            'total_evidence_steps': 0,
            'has_logcat_excerpt': False,
        }
        return analysis

    traceable_count = 0
    for field in ('defect_candidates', 'false_positive_candidates', 'manual_review_points'):
        enriched_items = []
        for item in _ensure_list(analysis.get(field)):
            enriched = _enrich_analysis_item(item, steps)
            if enriched.get('evidence'):
                traceable_count += 1
            enriched_items.append(enriched)
        analysis[field] = enriched_items

    analysis['evidence_summary'] = {
        'traceable_item_count': traceable_count,
        'total_evidence_steps': len(steps),
        'has_logcat_excerpt': any(bool(step.logcat_excerpt) for step in steps.values()),
    }
    return analysis


def _ensure_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ''):
        return []
    return [value]


def _enrich_analysis_item(item: Any, steps: dict[int, Any]) -> dict[str, Any]:
    if isinstance(item, dict):
        data = dict(item)
    else:
        data = {'title': str(item)}

    step_index = _coerce_step_index(data.get('step_index'))
    if step_index is None:
        step_index = _infer_step_index_from_text(data, steps)
    if step_index is None or step_index not in steps:
        data.setdefault('step_index', None)
        return data

    step = steps[step_index]
    data['step_index'] = step_index
    data['evidence'] = {
        'step_index': step_index,
        'action': readable_step_action(step),
        'target': readable_step_target(step),
        'changed': bool(step.changed),
        'before_activity': step.before_activity,
        'after_activity': step.after_activity,
        'activity': step.after_activity or step.before_activity,
        'before_screenshot': step.before_screenshot,
        'after_screenshot': step.after_screenshot,
        'screenshot': step.after_screenshot or step.before_screenshot,
        'issue_type': step.issue_type,
        'issue_message': step.issue_message,
        'logcat_excerpt': (step.logcat_excerpt or '')[:1000],
        'bounds': step.bounds,
        'x': step.x,
        'y': step.y,
    }
    return data


def _coerce_step_index(value: Any) -> int | None:
    if value in (None, ''):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _infer_step_index_from_text(item: Any, steps: dict[int, Any]) -> int | None:
    text = json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else str(item or '')
    for pattern in (r'step[_\s-]*index["\']?\s*[:=]\s*(\d+)', r'第\s*(\d+)\s*步', r'step\s*(\d+)'):
        match = re.search(pattern, text, re.I)
        if match:
            step_index = _coerce_step_index(match.group(1))
            if step_index in steps:
                return step_index
    return None


def _build_prompt_config_header(prompt_config: PromptConfig | None) -> str:
    if not prompt_config or not prompt_config.content:
        return ''
    return (
        '本次 AI 探索分析请优先遵循以下可配置提示词。'
        '如果它和输出 JSON 结构要求冲突，请保留 JSON 结构要求。\n'
        f'{prompt_config.content.strip()}\n\n'
    )


def _select_model_config() -> AIModelConfig | None:
    for role in MODEL_ROLE_PRIORITY:
        config = AIModelConfig.objects.filter(role=role, is_active=True).order_by('-updated_at').first()
        if config:
            return config
    return None


def _build_analysis_payload(task: AppExplorationTask) -> dict[str, Any]:
    insights = build_exploration_insights(task)
    steps = list(task.steps.order_by('step_index'))
    latest_run = task.latest_run()
    target_results = list(latest_run.target_results.select_related('step').order_by('id')) if latest_run else []
    summary = task.summary if isinstance(task.summary, dict) else {}
    return {
        'task': {
            'id': task.id,
            'name': task.name,
            'status': task.status,
            'result': task.result,
            'objective': task.objective,
            'package_name': task.package_name,
            'device_name': task.device_name,
            'total_steps': task.total_steps,
            'explored_pages': task.explored_pages,
            'issue_count': task.issue_count,
            'duration': task.duration,
            'error_message': task.error_message,
        },
        'rule_insights': {
            'conclusion': insights.get('conclusion'),
            'risk_level': insights.get('risk_level'),
            'issues': insights.get('issues', [])[:10],
            'target_coverage': insights.get('target_coverage', {}),
            'page_coverage': insights.get('page_coverage', {}),
            'exploration_guard': insights.get('exploration_guard', {}),
            'conversion_summary': insights.get('conversion_summary', {}),
            'skipped_risks': insights.get('skipped_risks', [])[:10],
            'entry_navigation': insights.get('entry_navigation', [])[:10],
        },
        'target_results': [
            {
                'target_name': result.target_name,
                'status': result.status,
                'changed': result.changed,
                'action_type': result.action_type,
                'step_index': result.step.step_index if result.step_id and result.step else None,
                'error_message': result.error_message,
                'review_resolution': result.review_resolution,
                'review_note': result.review_note,
                'risk': result.risk if isinstance(result.risk, dict) else {},
                'evidence': {
                    'bounds': result.bounds,
                    'activity': result.after_activity or result.before_activity,
                    'has_before_screenshot': bool(result.before_screenshot),
                    'has_after_screenshot': bool(result.after_screenshot),
                    'match_reason': _compact_match_reason(result.evidence),
                },
            }
            for result in target_results[:30]
        ],
        'page_map': _compact_page_map(summary.get('page_map', [])),
        'review_memory': {
            'issue_reviews': summary.get('issue_reviews') if isinstance(summary.get('issue_reviews'), dict) else {},
            'issue_review_rules': insights.get('issue_review_rules', [])[:20],
            'target_review_rules': insights.get('target_review_rules', [])[:20],
        },
        'iteration_context': _build_iteration_context(task),
        'steps': [
            {
                'step_index': step.step_index,
                'action_type': step.action_type,
                'action': readable_step_action(step),
                'target': readable_step_target(step),
                'changed': step.changed,
                'issue_type': step.issue_type,
                'issue_message': step.issue_message,
                'before_activity': step.before_activity,
                'after_activity': step.after_activity,
                'raw': {
                    'objective_hits': (step.raw or {}).get('objective_hits', []),
                    'score_reasons': (step.raw or {}).get('score_reasons', []),
                    'risk': (step.raw or {}).get('risk', {}),
                },
            }
            for step in steps[:60]
        ],
    }


def _build_iteration_context(task: AppExplorationTask) -> dict[str, Any]:
    chain = []
    current = task
    seen_ids = set()
    max_depth = 12

    while current and current.id not in seen_ids and len(chain) < max_depth:
        seen_ids.add(current.id)
        source_summary = current.source_summary or {}
        selected_actions = source_summary.get('selected_action_proposals') or source_summary.get('action_proposals') or []
        metrics = {
            'total_steps': int(current.total_steps or 0),
            'explored_pages': int(current.explored_pages or 0),
            'issue_count': int(current.issue_count or 0),
            'duration': round(float(current.duration or 0), 1),
        }
        chain.append({
            'id': current.id,
            'name': current.name,
            'status': current.status,
            'result': current.result,
            'source_type': current.source_type or '',
            'effective': metrics['total_steps'] > 0 or metrics['explored_pages'] > 0,
            'metrics': metrics,
            'targets': source_summary.get('targets') or [],
            'selected_actions': selected_actions[:8] if isinstance(selected_actions, list) else [],
            'rejected_action_count': source_summary.get('rejected_action_count') or 0,
            'reason': source_summary.get('reason') or '',
        })
        current = current.source_task

    chain.reverse()
    for index, item in enumerate(chain, start=1):
        item['round'] = index

    ineffective_count = sum(1 for item in chain if not item.get('effective'))
    effective_count = len(chain) - ineffective_count
    issue_count = sum(1 for item in chain if int(item.get('metrics', {}).get('issue_count') or 0) > 0)
    return {
        'has_history': len(chain) > 1,
        'current_round': len(chain),
        'effective_attempts': effective_count,
        'ineffective_attempts': ineffective_count,
        'issue_attempts': issue_count,
        'chain': chain,
    }


def _compact_match_reason(evidence: Any) -> str:
    if not isinstance(evidence, dict):
        return ''
    reasons = evidence.get('match_reasons')
    if isinstance(reasons, list):
        return '、'.join(str(item) for item in reasons[:3] if str(item).strip())[:200]
    return str(evidence.get('match_reason') or '')[:200]


def _compact_page_map(page_map: Any) -> list[dict[str, Any]]:
    if not isinstance(page_map, list):
        return []

    compact_pages = []
    for page in page_map[:20]:
        if not isinstance(page, dict):
            continue
        controls = page.get('clicked_controls') if isinstance(page.get('clicked_controls'), list) else []
        issues = page.get('issues') if isinstance(page.get('issues'), list) else []
        compact_pages.append({
            'title': str(page.get('title') or '')[:80],
            'activity': str(page.get('activity') or '')[:160],
            'semantic_signature': str(page.get('semantic_signature') or '')[:80],
            'first_step': page.get('first_step'),
            'step_count': page.get('step_count'),
            'controls': [
                {
                    'text': str(control.get('text') or control.get('action') or '')[:80],
                    'resource_id': str(control.get('resource_id') or '')[-120:],
                    'class_name': str(control.get('class_name') or '')[-80:],
                    'step_index': control.get('step_index'),
                }
                for control in controls[:12]
                if isinstance(control, dict)
            ],
            'issues': [
                {
                    'step_index': issue.get('step_index'),
                    'issue_type': issue.get('issue_type'),
                    'issue_message': str(issue.get('issue_message') or '')[:160],
                }
                for issue in issues[:6]
                if isinstance(issue, dict)
            ],
        })
    return compact_pages


def _build_analysis_audit(
    task: AppExplorationTask,
    payload: dict[str, Any],
    config: AIModelConfig,
    prompt_config: PromptConfig | None,
) -> dict[str, Any]:
    iteration_context = payload.get('iteration_context') or {}
    rule_insights = payload.get('rule_insights') or {}
    target_coverage = rule_insights.get('target_coverage') or {}
    page_coverage = rule_insights.get('page_coverage') or {}
    steps = payload.get('steps') or []
    issues = rule_insights.get('issues') or []

    return {
        'analyzed_at': timezone.now().isoformat(),
        'model_role': config.role,
        'model_name': config.model_name,
        'prompt': {
            'type': prompt_config.prompt_type if prompt_config else 'builtin_default',
            'name': prompt_config.name if prompt_config else '内置默认提示词',
            'config_id': prompt_config.id if prompt_config else None,
        },
        'task_id': task.id,
        'task_status': task.status,
        'task_result': task.result,
        'input_summary': {
            'objective': task.objective[:200],
            'step_count_sent': len(steps),
            'total_steps': int(task.total_steps or 0),
            'explored_pages': int(task.explored_pages or 0),
            'issue_count': int(task.issue_count or 0),
            'target_coverage_rate': target_coverage.get('rate') or 0,
            'page_count': page_coverage.get('page_count') or 0,
            'rule_issue_count_sent': len(issues),
        },
        'iteration_summary': {
            'has_history': bool(iteration_context.get('has_history')),
            'current_round': iteration_context.get('current_round') or 1,
            'effective_attempts': iteration_context.get('effective_attempts') or 0,
            'ineffective_attempts': iteration_context.get('ineffective_attempts') or 0,
            'issue_attempts': iteration_context.get('issue_attempts') or 0,
        },
        'safety': {
            'device_controlled_by_ai': False,
            'coordinate_click_allowed': False,
            'high_risk_actions_auto_adopted': False,
            'action_allowlist': ['tap_text', 'swipe', 'wait', 'back'],
        },
    }


def _extract_message_content(response: dict[str, Any]) -> str:
    choices = response.get('choices') or []
    if not choices:
        return ''
    message = choices[0].get('message') or {}
    return str(message.get('content') or choices[0].get('text') or '').strip()


def _parse_json_response(content: str) -> dict[str, Any]:
    if not content:
        raise ValueError('大模型返回为空')

    text = content.strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', text, re.S)
        if not match:
            raise ValueError(f'大模型未返回有效 JSON：{content[:200]}')
        parsed = json.loads(match.group(0))

    if not isinstance(parsed, dict):
        raise ValueError('大模型返回 JSON 不是对象')

    return _normalize_analysis(parsed, raw_text=content)


def sanitize_ai_controlled_task_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """Return safe field overrides for AI-derived controlled inspection tasks."""
    source_type = str(data.get('source_type') or '').strip()
    if source_type not in AI_CONTROLLED_SOURCE_TYPES:
        return {}

    source_summary = data.get('source_summary') if isinstance(data.get('source_summary'), dict) else {}
    safe_actions, rejected_actions = _sanitize_ai_start_actions(data.get('start_actions'))
    safe_keywords = _sanitize_ai_entry_keywords(data.get('entry_keywords'))
    guarded_summary = {
        **source_summary,
        'server_guardrails': {
            'strategy_forced': 'target_inspection',
            'device_controlled_by_ai': False,
            'coordinate_click_allowed': False,
            'allowed_start_action_types': sorted(AI_ALLOWED_START_ACTION_TYPES),
            'rejected_start_action_count': len(rejected_actions),
        },
        'server_rejected_start_actions': rejected_actions,
        'admitted_start_actions': safe_actions,
    }

    return {
        'strategy': 'target_inspection',
        'entry_keywords': safe_keywords,
        'start_actions': safe_actions,
        'source_summary': guarded_summary,
    }


def _normalize_analysis(data: dict[str, Any], raw_text: str) -> dict[str, Any]:
    def as_list(value):
        if isinstance(value, list):
            return value
        if value in (None, ''):
            return []
        return [str(value)]

    targets = [str(item).strip() for item in as_list(data.get('next_exploration_targets')) if str(item).strip()]
    action_proposals = _normalize_action_proposals(data.get('action_proposals'))
    inspection_plan = _normalize_inspection_plan(data.get('inspection_plan'), targets, action_proposals)
    plan_target_names = [
        item['target_name']
        for item in inspection_plan.get('recommended_targets', [])
        if item.get('risk') != 'high'
    ]
    if not targets:
        targets = plan_target_names
    entry_keywords = _derive_entry_keyword_candidates(targets)
    inspection_plan['entry_keywords'] = entry_keywords
    semantic_suggestions = _normalize_semantic_suggestions(
        data.get('semantic_suggestions'),
        inspection_plan.get('recommended_targets', []),
    )
    return {
        'conclusion': str(data.get('conclusion') or '').strip() or '大模型未给出明确结论',
        'risk_level': data.get('risk_level') if data.get('risk_level') in {'low', 'medium', 'high'} else 'medium',
        'defect_candidates': as_list(data.get('defect_candidates')),
        'false_positive_candidates': as_list(data.get('false_positive_candidates')),
        'root_cause_hypotheses': as_list(data.get('root_cause_hypotheses')),
        'next_exploration_targets': targets,
        'entry_keyword_candidates': entry_keywords,
        'action_proposals': action_proposals,
        'inspection_plan': inspection_plan,
        'semantic_suggestions': semantic_suggestions,
        'next_round_draft': _build_next_round_draft(plan_target_names or targets, entry_keywords, action_proposals, inspection_plan),
        'case_suggestions': as_list(data.get('case_suggestions')),
        'manual_review_points': as_list(data.get('manual_review_points')),
        'raw_text': raw_text[:4000],
    }


def _clean_keyword_text(value: Any) -> str:
    text = str(value or '').strip()
    text = re.sub(r'^[在再去到从往]+', '', text)
    if text in STABLE_START_TARGETS:
        return text
    text = re.sub(r'(页面|页|模块|区域|入口)$', '', text)
    text = re.sub(r'[“”"\'`（）()\[\]【】<>《》]', '', text)
    return text.strip(' \t\r\n,，。；;、：:!?！？')


def _is_noise_keyword(value: str) -> bool:
    text = _clean_keyword_text(value)
    if text.isdigit():
        return True
    if not (2 <= len(text) <= 8):
        return True
    return any(marker in text for marker in PROCESS_KEYWORD_MARKERS)


def _derive_entry_keyword_candidates(targets: list[str]) -> list[str]:
    joined = ' '.join(targets)
    keywords: list[str] = []

    def add_keyword(value: Any) -> None:
        text = _clean_keyword_text(value)
        if text and text not in keywords and not _is_noise_keyword(text):
            keywords.append(text)

    for term in ENTRY_KEYWORD_CANDIDATES:
        if term in joined:
            add_keyword(term)

    for target in targets:
        for token in re.split(r'[\s,，。；;、/|｜：:!?！？]+', str(target or '')):
            add_keyword(token)

    return keywords[:8]


def _is_dynamic_target(target: str) -> bool:
    return any(marker.lower() in target.lower() for marker in DYNAMIC_TARGET_MARKERS)


def _is_conditional_target(target: str, reason: str = '') -> bool:
    text = f'{target} {reason}'
    return any(marker in text for marker in CONDITIONAL_TARGET_MARKERS)


def _is_stable_start_target(target: str) -> bool:
    text = _clean_keyword_text(target)
    if text in STABLE_START_TARGETS:
        return True
    if _is_dynamic_target(text) or _is_noise_keyword(text):
        return False
    return text in ENTRY_KEYWORD_CANDIDATES and len(text) <= 6


def _is_blocked_target(value: Any) -> bool:
    text = str(value or '')
    return any(keyword in text for keyword in BLOCKED_ACTION_KEYWORDS)


def _normalize_priority(value: Any) -> str:
    text = str(value or '').strip().upper()
    return text if text in {'P0', 'P1', 'P2'} else 'P1'


def _normalize_plan_targets(value: Any, fallback_targets: list[str]) -> list[dict[str, Any]]:
    raw_items = value if isinstance(value, list) else []
    if not raw_items:
        raw_items = fallback_targets

    targets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_items[:16]:
        if isinstance(item, dict):
            name = _clean_keyword_text(item.get('target_name') or item.get('target') or item.get('name') or '')
            page_name = str(item.get('page_name') or item.get('page') or '').strip()[:80]
            semantic_role = str(item.get('semantic_role') or item.get('role') or '按钮').strip()[:40]
            reason = str(item.get('reason') or item.get('candidate_reason') or 'AI 推荐下一轮覆盖该目标').strip()[:240]
            risk = str(item.get('risk') or 'medium').strip()
            priority = _normalize_priority(item.get('priority'))
            source = str(item.get('source') or 'llm').strip()[:40]
        else:
            name = _clean_keyword_text(item)
            page_name = ''
            semantic_role = '按钮'
            reason = 'AI 推荐下一轮覆盖该目标'
            risk = 'medium'
            priority = 'P1'
            source = 'llm'

        if not name or _is_noise_keyword(name):
            continue
        if _is_blocked_target(name):
            risk = 'high'
        if risk not in {'low', 'medium', 'high'}:
            risk = 'medium'
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        targets.append({
            'target_name': name[:80],
            'page_name': page_name,
            'semantic_role': semantic_role or '按钮',
            'priority': priority,
            'reason': reason,
            'risk': risk,
            'source': source,
        })
    return targets[:8]


def _normalize_inspection_plan(
    value: Any,
    fallback_targets: list[str],
    action_proposals: list[dict[str, Any]],
) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    targets = _normalize_plan_targets(data.get('recommended_targets'), fallback_targets)
    if not targets:
        targets = _normalize_plan_targets(fallback_targets, fallback_targets)

    start_actions = _normalize_action_proposals(data.get('start_actions'))
    if not start_actions:
        start_actions = [item for item in action_proposals if item.get('layer') == 'start_navigation']

    coverage_gaps = data.get('coverage_gaps') if isinstance(data.get('coverage_gaps'), list) else []
    risk_controls = data.get('risk_controls') if isinstance(data.get('risk_controls'), list) else []
    blocked_targets = [item['target_name'] for item in targets if item.get('risk') == 'high']
    if blocked_targets:
        risk_controls = [
            *[str(item).strip() for item in risk_controls if str(item).strip()],
            *[f'高风险目标「{name}」不会自动执行，需人工确认或移出目标清单' for name in blocked_targets],
        ]

    return {
        'schema_version': 'ai_l1_controlled_inspection_v1',
        'summary': str(data.get('summary') or 'AI 已生成下一轮受控目标巡检计划，保存前请人工确认。').strip()[:240],
        'strategy': 'target_inspection',
        'coverage_gaps': [str(item).strip()[:160] for item in coverage_gaps if str(item).strip()][:8],
        'recommended_targets': targets,
        'start_actions': [item for item in start_actions if item.get('risk') != 'high'][:5],
        'risk_controls': list(dict.fromkeys(str(item).strip()[:200] for item in risk_controls if str(item).strip()))[:8],
        'requires_human_confirmation': True,
        'device_controlled_by_ai': False,
    }


def _normalize_semantic_suggestions(value: Any, plan_targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_items = value if isinstance(value, list) else []
    if not raw_items:
        raw_items = [
            {
                'target_name': item.get('target_name'),
                'page_name': item.get('page_name'),
                'semantic_role': item.get('semantic_role'),
                'suggestion': '建议在页面地图中确认该控件语义后，再沉淀为 semantic_v2 候选。',
                'reason': item.get('reason'),
            }
            for item in plan_targets[:5]
            if item.get('risk') != 'high'
        ]

    suggestions: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw_items[:12]:
        if isinstance(item, dict):
            target_name = _clean_keyword_text(item.get('target_name') or item.get('target') or item.get('name') or '')
            page_name = str(item.get('page_name') or item.get('page') or '').strip()[:80]
            semantic_role = str(item.get('semantic_role') or item.get('role') or '按钮').strip()[:40]
            suggestion = str(item.get('suggestion') or item.get('advice') or '建议人工确认语义命名和控件角色。').strip()[:240]
            reason = str(item.get('reason') or '').strip()[:200]
        else:
            target_name = _clean_keyword_text(item)
            page_name = ''
            semantic_role = '按钮'
            suggestion = '建议人工确认语义命名和控件角色。'
            reason = ''
        if not target_name or _is_blocked_target(target_name):
            continue
        key = (page_name, target_name)
        if key in seen:
            continue
        seen.add(key)
        suggestions.append({
            'page_name': page_name,
            'target_name': target_name[:80],
            'semantic_role': semantic_role,
            'suggestion': suggestion,
            'reason': reason,
        })
    return suggestions[:8]


def _sanitize_ai_entry_keywords(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    keywords: list[str] = []
    for item in value[:24]:
        text = _clean_keyword_text(item)
        if text and text not in keywords and not _is_noise_keyword(text) and not _is_blocked_target(text):
            keywords.append(text)
    return keywords[:12]


def _sanitize_ai_start_actions(value: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(value, list):
        return [], []

    safe_actions: list[dict[str, Any]] = []
    rejected_actions: list[dict[str, Any]] = []
    for item in value[:12]:
        if not isinstance(item, dict):
            continue

        action_type = str(item.get('type') or item.get('action_type') or '').strip()
        target = _clean_keyword_text(item.get('value') or item.get('target') or '')
        risk = str(item.get('risk') or '').strip()
        reject_reason = ''

        if action_type not in AI_ALLOWED_START_ACTION_TYPES:
            reject_reason = 'unsupported_action_type'
        elif risk == 'high' or _is_blocked_target(target):
            reject_reason = 'high_risk_action'
        elif action_type == 'tap_text' and not target:
            reject_reason = 'empty_tap_text_target'

        if reject_reason:
            rejected_actions.append({
                'type': action_type or str(item.get('action_type') or ''),
                'value': target,
                'reason': reject_reason,
            })
            continue

        if action_type == 'tap_text':
            safe_action = {'type': 'tap_text', 'value': target}
        elif action_type == 'swipe':
            direction = str(item.get('direction') or 'up').strip().lower()
            if direction not in AI_ALLOWED_SWIPE_DIRECTIONS:
                direction = 'up'
            safe_action = {'type': 'swipe', 'direction': direction}
        elif action_type == 'wait':
            try:
                seconds = float(item.get('seconds') or item.get('value') or 1)
            except (TypeError, ValueError):
                seconds = 1
            safe_action = {'type': 'wait', 'seconds': min(max(seconds, 0.2), 5)}
        else:
            safe_action = {'type': 'back'}

        try:
            after_wait = float(item.get('after_wait') or 0.6)
        except (TypeError, ValueError):
            after_wait = 0.6
        safe_action['after_wait'] = min(max(after_wait, 0.2), 3)
        safe_actions.append(safe_action)

    return safe_actions[:5], rejected_actions[:8]


def _build_next_round_draft(
    targets: list[str],
    entry_keywords: list[str],
    action_proposals: list[dict[str, Any]],
    inspection_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    action_layers = {
        'start_navigation': [],
        'conditional_fallback': [],
        'exploration_preference': [],
        'blocked': [],
    }
    for action in action_proposals:
        layer = action.get('layer') or 'exploration_preference'
        if layer not in action_layers:
            layer = 'exploration_preference'
        action_layers[layer].append(action)

    plan_start_actions = (inspection_plan or {}).get('start_actions') if isinstance(inspection_plan, dict) else []
    plan_start_actions = plan_start_actions if isinstance(plan_start_actions, list) else []
    admitted_start_actions = [
        {
            'type': 'tap_text',
            'value': action.get('target', ''),
        }
        for action in plan_start_actions
        if action.get('action_type') == 'tap_text' and action.get('target') and action.get('risk') != 'high'
    ][:5]

    if not admitted_start_actions:
        admitted_start_actions = [
            {
                'type': 'tap_text',
                'value': action.get('target', ''),
            }
            for action in action_layers['start_navigation']
            if action.get('action_type') == 'tap_text' and action.get('target')
        ][:5]

    exploration_preferences = [
        {
            'action_type': action.get('action_type'),
            'target': action.get('target', ''),
            'direction': action.get('direction', 'up'),
            'seconds': action.get('seconds', 1),
            'reason': action.get('reason', ''),
            'risk': action.get('risk', 'medium'),
            'confidence': action.get('confidence', 0),
        }
        for action in action_layers['exploration_preference']
    ][:8]

    confirmation_required = [
        action for action in action_layers['conditional_fallback']
        if action.get('risk') != 'high'
    ][:5]

    return {
        'targets': targets[:8],
        'entry_keywords': entry_keywords[:8],
        'strategy': 'target_inspection',
        'max_steps': 30,
        'max_duration': 300,
        'start_actions': admitted_start_actions,
        'inspection_plan': inspection_plan or {},
        'exploration_preferences': exploration_preferences,
        'confirmation_required_actions': confirmation_required,
        'blocked_actions': action_layers['blocked'][:8],
        'action_layers': action_layers,
        'rejected_action_count': len(action_layers['blocked']),
        'draft_note': 'AI 仅生成下一轮探索草稿；保存前仍需人工确认目标、入口和风险动作。',
    }


def _classify_action_layer(action_type: str, target: str, risk: str, reason: str) -> tuple[str, str]:
    if risk == 'high':
        return 'blocked', '高风险动作不会进入草稿执行'
    if action_type != 'tap_text':
        return 'exploration_preference', '返回/等待/滑动只作为探索偏好，不进入起始导航'
    if _is_conditional_target(target, reason):
        return 'conditional_fallback', '疑似弹窗或条件动作，需要人工确认后再使用'
    if _is_dynamic_target(target):
        return 'exploration_preference', '动态列表项不适合作为稳定起始导航'
    if _is_stable_start_target(target):
        return 'start_navigation', '命中稳定入口，可作为起始导航候选'
    return 'exploration_preference', '未命中稳定入口白名单，仅作为探索偏好'


def _normalize_action_proposals(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    allowed_types = {'tap_text', 'swipe', 'wait', 'back'}
    allowed_directions = {'up', 'down', 'left', 'right'}
    allowed_risks = {'low', 'medium', 'high'}
    normalized: list[dict[str, Any]] = []

    for item in value[:8]:
        if not isinstance(item, dict):
            continue

        action_type = str(item.get('action_type') or item.get('type') or '').strip()
        target = _clean_keyword_text(item.get('target') or item.get('value') or '')
        direction = str(item.get('direction') or 'up').strip()
        reason = str(item.get('reason') or '').strip()
        risk = str(item.get('risk') or 'medium').strip()

        if action_type not in allowed_types:
            continue
        if action_type == 'tap_text' and not target:
            continue
        if action_type == 'tap_text' and any(keyword in target for keyword in BLOCKED_ACTION_KEYWORDS):
            risk = 'high'
        if action_type == 'swipe' and direction not in allowed_directions:
            direction = 'up'
        if risk not in allowed_risks:
            risk = 'medium'
        layer, layer_reason = _classify_action_layer(action_type, target, risk, reason)

        try:
            seconds = float(item.get('seconds') or 1)
        except (TypeError, ValueError):
            seconds = 1
        seconds = min(max(seconds, 0.2), 5)

        try:
            confidence = float(item.get('confidence') or 0)
        except (TypeError, ValueError):
            confidence = 0
        confidence = min(max(confidence, 0), 1)

        normalized.append({
            'action_type': action_type,
            'target': target[:80],
            'direction': direction,
            'seconds': seconds,
            'reason': reason[:200],
            'risk': risk,
            'confidence': round(confidence, 2),
            'layer': layer,
            'layer_reason': layer_reason,
            'can_start_navigation': layer == 'start_navigation',
        })

    return normalized
