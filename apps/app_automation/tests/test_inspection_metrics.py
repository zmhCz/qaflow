# -*- coding: utf-8 -*-
"""Tests for controlled inspection stability metrics."""

from datetime import datetime
from types import SimpleNamespace

from apps.app_automation.utils.inspection_metrics import build_target_consistency_metrics


class _ResultList(list):
    def all(self):
        return self


def _step(index):
    return SimpleNamespace(step_index=index)


def _result(
    target_name,
    status,
    *,
    step_index=1,
    before='before.png',
    after='after.png',
    bounds='[10,10][100,100]',
    x=55,
    y=55,
    recovery_status='not_needed',
    risk=None,
):
    return SimpleNamespace(
        target_name=target_name,
        status=status,
        before_screenshot=before,
        after_screenshot=after,
        bounds=bounds,
        x=x,
        y=y,
        evidence={'recovery': {'status': recovery_status}} if recovery_status else {},
        risk=risk or {},
        step_id=step_index,
        step=_step(step_index),
    )


def _run(run_id, results, *, steps=None, summary=None):
    return SimpleNamespace(
        id=run_id,
        status='completed',
        result='passed',
        created_at=datetime(2026, 7, 20, 10, run_id, 0),
        target_results=_ResultList(results),
        steps=_ResultList(steps or []),
        summary=summary or {},
    )


def _action_step(step_id, step_index, action_type, target='', *, raw=None):
    return SimpleNamespace(
        id=step_id,
        step_index=step_index,
        action_type=action_type,
        target_text=target,
        raw=raw or {},
    )


def test_target_consistency_metrics_pass_for_three_consistent_runs():
    runs = [
        _run(3, [_result('消息', 'found_effective'), _result('社区', 'found_effective')]),
        _run(2, [_result('消息', 'found_effective'), _result('社区', 'found_effective')]),
        _run(1, [_result('消息', 'found_effective'), _result('社区', 'found_effective')]),
    ]

    metrics = build_target_consistency_metrics(runs)

    assert metrics['passed'] is True
    assert metrics['run_count'] == 3
    assert metrics['target_count'] == 2
    assert metrics['recognition_rate'] == 100
    assert metrics['consistency_rate'] == 100
    assert metrics['evidence_completeness_rate'] == 100
    assert metrics['anchor_recovery_rate'] == 100
    assert metrics['failed_thresholds'] == []
    assert metrics['failed_acceptance_items'] == []
    assert metrics['off_list_action_count'] == 0
    assert metrics['risk_auto_action_count'] == 0
    assert metrics['risk_skipped_count'] == 0
    assert all(item['passed'] for item in metrics['acceptance_items'])


def test_target_consistency_metrics_marks_inconsistent_statuses():
    runs = [
        _run(3, [_result('消息', 'found_effective'), _result('社区', 'not_found', after='', bounds='', x=None, y=None, recovery_status='')]),
        _run(2, [_result('消息', 'found_effective'), _result('社区', 'found_effective')]),
        _run(1, [_result('消息', 'found_effective'), _result('社区', 'found_effective')]),
    ]

    metrics = build_target_consistency_metrics(runs)

    community = next(item for item in metrics['rows'] if item['target_name'] == '社区')
    assert metrics['passed'] is False
    assert metrics['recognition_rate'] == 83.33
    assert metrics['consistency_rate'] == 50
    assert 'recognition_rate' in metrics['failed_thresholds']
    assert 'consistency_rate' in metrics['failed_thresholds']
    assert community['consistent'] is False
    assert community['latest_status'] == 'not_found'
    assert '起始页面' in community['recommendation']


def test_target_consistency_metrics_requires_three_runs_for_baseline():
    runs = [
        _run(2, [_result('消息', 'found_effective')]),
        _run(1, [_result('消息', 'found_effective')]),
    ]

    metrics = build_target_consistency_metrics(runs)

    assert metrics['available'] is True
    assert metrics['passed'] is False
    assert metrics['run_count'] == 2
    assert 'run_count' in metrics['failed_thresholds']
    assert 'run_count' in metrics['failed_acceptance_items']


def test_target_consistency_metrics_tracks_anchor_recovery_failures():
    runs = [
        _run(3, [_result('消息', 'anchor_recovery_failed', recovery_status='failed')]),
        _run(2, [_result('消息', 'anchor_recovery_failed', recovery_status='failed')]),
        _run(1, [_result('消息', 'anchor_recovery_failed', recovery_status='failed')]),
    ]

    metrics = build_target_consistency_metrics(runs)

    assert metrics['recognition_rate'] == 100
    assert metrics['anchor_recovery_rate'] == 0
    assert 'anchor_recovery_rate' in metrics['failed_thresholds']
    assert metrics['rows'][0]['recommendation'].startswith('点击后偏离锚点页')


def test_target_consistency_metrics_tracks_missing_evidence_for_recognized_targets():
    runs = [
        _run(3, [_result('消息', 'found_effective', after='', bounds='', x=None, y=None)]),
        _run(2, [_result('消息', 'found_effective')]),
        _run(1, [_result('消息', 'found_effective')]),
    ]

    metrics = build_target_consistency_metrics(runs)

    assert metrics['evidence_completeness_rate'] == 66.67
    assert 'evidence_completeness_rate' in metrics['failed_thresholds']
    assert 'evidence_completeness_rate' in metrics['failed_acceptance_items']


def test_target_consistency_metrics_tracks_risk_skipped_as_guarded_not_auto_action():
    runs = [
        _run(3, [_result('退出登录', 'risk_skipped', after='', bounds='', x=None, y=None, recovery_status='')]),
        _run(2, [_result('退出登录', 'risk_skipped', after='', bounds='', x=None, y=None, recovery_status='')]),
        _run(1, [_result('退出登录', 'risk_skipped', after='', bounds='', x=None, y=None, recovery_status='')]),
    ]

    metrics = build_target_consistency_metrics(runs)

    assert metrics['risk_skipped_count'] == 3
    assert metrics['risk_auto_action_count'] == 0
    assert 'risk_auto_action_count' not in metrics['failed_acceptance_items']
    assert metrics['rows'][0]['recommendation'].startswith('命中风险护栏')


def test_target_consistency_metrics_does_not_fake_anchor_rate_without_samples():
    runs = [
        _run(3, [_result('退出登录', 'risk_skipped', after='', bounds='', x=None, y=None, recovery_status='')]),
        _run(2, [_result('退出登录', 'risk_skipped', after='', bounds='', x=None, y=None, recovery_status='')]),
        _run(1, [_result('退出登录', 'risk_skipped', after='', bounds='', x=None, y=None, recovery_status='')]),
    ]

    metrics = build_target_consistency_metrics(runs)
    anchor_item = next(item for item in metrics['acceptance_items'] if item['key'] == 'anchor_recovery_rate')

    assert metrics['anchor_recovery_rate'] is None
    assert metrics['anchor_recovery_sampled'] is False
    assert anchor_item['actual'] == '无恢复样本'
    assert anchor_item['passed'] is True


def test_target_consistency_metrics_tracks_off_list_target_inspection_actions():
    runs = [
        _run(
            3,
            [_result('消息', 'found_effective')],
            steps=[
                _action_step(1, 1, 'tap', '消息', raw={'mode': 'target_inspection', 'target': '消息'}),
                _action_step(99, 2, 'tap', '退出登录', raw={'mode': 'target_inspection', 'target': '退出登录'}),
            ],
            summary={'objective_keywords': ['消息']},
        ),
        _run(2, [_result('消息', 'found_effective')]),
        _run(1, [_result('消息', 'found_effective')]),
    ]

    metrics = build_target_consistency_metrics(runs)

    assert metrics['off_list_action_count'] == 1
    assert metrics['off_list_actions'][0]['target'] == '退出登录'
    assert 'off_list_action_count' in metrics['failed_thresholds']
    assert 'off_list_action_count' in metrics['failed_acceptance_items']


def test_target_consistency_metrics_tracks_forbidden_risk_auto_actions():
    runs = [
        _run(
            3,
            [_result('退出登录', 'found_effective', risk={'level': 'forbidden', 'keyword': '退出登录'})],
            steps=[
                _action_step(
                    1,
                    1,
                    'tap',
                    '退出登录',
                    raw={'mode': 'target_inspection', 'target': '退出登录', 'risk': {'level': 'forbidden'}},
                ),
            ],
            summary={'objective_keywords': ['退出登录']},
        ),
        _run(2, [_result('退出登录', 'risk_skipped', after='', bounds='', x=None, y=None, recovery_status='')]),
        _run(1, [_result('退出登录', 'risk_skipped', after='', bounds='', x=None, y=None, recovery_status='')]),
    ]

    metrics = build_target_consistency_metrics(runs)

    assert metrics['risk_auto_action_count'] == 2
    assert {item['source'] for item in metrics['risk_auto_actions']} == {'step', 'target_result'}
    assert 'risk_auto_action_count' in metrics['failed_thresholds']
    assert 'risk_auto_action_count' in metrics['failed_acceptance_items']
