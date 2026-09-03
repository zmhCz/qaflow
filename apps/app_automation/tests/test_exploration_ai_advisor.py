# -*- coding: utf-8 -*-
"""Tests for AI exploration advisory normalization."""

from apps.app_automation.utils.exploration_ai_advisor import (
    BLOCKED_ACTION_KEYWORDS,
    _build_next_round_draft,
    _normalize_analysis,
    sanitize_ai_controlled_task_overrides,
)


def test_next_round_draft_defaults_to_controlled_target_inspection():
    draft = _build_next_round_draft(
        targets=['消息 Tab', '社区入口'],
        entry_keywords=['消息', '社区'],
        action_proposals=[
            {
                'layer': 'start_navigation',
                'action_type': 'tap_text',
                'target': '消息',
                'risk': 'low',
            },
            {
                'layer': 'blocked',
                'action_type': 'tap_text',
                'target': '退出登录',
                'risk': 'high',
            },
        ],
    )

    assert draft['strategy'] == 'target_inspection'
    assert draft['targets'] == ['消息 Tab', '社区入口']
    assert draft['entry_keywords'] == ['消息', '社区']
    assert draft['start_actions'] == [{'type': 'tap_text', 'value': '消息'}]
    assert draft['blocked_actions'][0]['target'] == '退出登录'


def test_normalize_analysis_builds_l1_controlled_inspection_plan():
    analysis = _normalize_analysis({
        'conclusion': '建议补充消息和社区入口巡检',
        'risk_level': 'low',
        'inspection_plan': {
            'summary': '下一轮优先覆盖一级入口',
            'coverage_gaps': ['消息入口未覆盖'],
            'recommended_targets': [
                {
                    'target_name': '消息',
                    'page_name': '首页',
                    'semantic_role': 'TAB',
                    'priority': 'P0',
                    'reason': '本轮未覆盖消息入口',
                    'risk': 'low',
                },
                {
                    'target_name': '退出登录',
                    'page_name': '我的',
                    'semantic_role': '按钮',
                    'priority': 'P0',
                    'reason': '危险动作必须人工确认',
                    'risk': 'low',
                },
            ],
            'start_actions': [
                {'action_type': 'tap_text', 'target': '首页', 'risk': 'low', 'reason': '回到稳定入口'},
            ],
            'risk_controls': ['不执行退出登录'],
        },
        'semantic_suggestions': [
            {'page_name': '首页', 'target_name': '消息', 'semantic_role': 'TAB', 'suggestion': '沉淀为底部 TAB'},
        ],
    }, raw_text='{}')

    plan = analysis['inspection_plan']
    draft = analysis['next_round_draft']

    assert plan['schema_version'] == 'ai_l1_controlled_inspection_v1'
    assert plan['strategy'] == 'target_inspection'
    assert plan['device_controlled_by_ai'] is False
    assert plan['recommended_targets'][0]['target_name'] == '消息'
    assert plan['recommended_targets'][1]['risk'] == 'high'
    assert draft['strategy'] == 'target_inspection'
    assert draft['targets'] == ['消息']
    assert draft['start_actions'] == [{'type': 'tap_text', 'value': '首页'}]
    assert analysis['semantic_suggestions'][0]['target_name'] == '消息'

def test_sanitize_ai_controlled_task_overrides_rejects_high_risk_start_actions():
    overrides = sanitize_ai_controlled_task_overrides({
        'source_type': 'ai_next_round',
        'strategy': 'free_exploration',
        'entry_keywords': ['home', BLOCKED_ACTION_KEYWORDS[0]],
        'start_actions': [
            {'type': 'tap_text', 'value': 'home', 'risk': 'low'},
            {'type': 'tap_text', 'value': BLOCKED_ACTION_KEYWORDS[0], 'risk': 'low'},
            {'type': 'tap_pos', 'x': 10, 'y': 20, 'risk': 'low'},
            {'type': 'wait', 'seconds': 30, 'risk': 'low'},
        ],
        'source_summary': {'from': 'unit-test'},
    })

    assert overrides['strategy'] == 'target_inspection'
    assert overrides['entry_keywords'] == ['home']
    assert overrides['start_actions'] == [
        {'type': 'tap_text', 'value': 'home', 'after_wait': 0.6},
        {'type': 'wait', 'seconds': 5, 'after_wait': 0.6},
    ]
    assert overrides['source_summary']['from'] == 'unit-test'
    assert overrides['source_summary']['server_guardrails']['coordinate_click_allowed'] is False
    assert overrides['source_summary']['server_guardrails']['rejected_start_action_count'] == 2
