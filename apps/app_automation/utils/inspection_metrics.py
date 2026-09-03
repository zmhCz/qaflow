# -*- coding: utf-8 -*-
"""Quality metrics for controlled target inspection runs."""

from __future__ import annotations

from typing import Iterable

from ..models import AppExplorationRun


RECOGNIZED_STATUSES = {'found_effective', 'found_unconfirmed', 'anchor_recovery_failed'}
ISSUE_STATUSES = {'not_found', 'risk_skipped', 'anchor_recovery_failed', 'error'}
SUCCESSFUL_RECOVERY_STATUSES = {'not_needed', 'not_needed_same_activity', 'recovered', 'recovered_by_targets', 'recovered_by_relaunch', 'recovered_by_relaunch_targets'}
INTERACTIVE_STEP_TYPES = {'tap', 'swipe', 'back'}

DEFAULT_THRESHOLDS = {
    'min_runs': 3,
    'recognition_rate': 85,
    'anchor_recovery_rate': 95,
    'evidence_completeness_rate': 100,
    'consistency_rate': 90,
    'off_list_action_count': 0,
    'risk_auto_action_count': 0,
}


def _round_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0
    return round(numerator / denominator * 100, 2)


def _is_evidence_complete(result) -> bool:
    if not result.before_screenshot:
        return False
    if result.status in RECOGNIZED_STATUSES:
        return bool(result.after_screenshot and result.bounds and result.x is not None and result.y is not None)
    return True


def _recovery_status(result) -> str:
    evidence = result.evidence if isinstance(result.evidence, dict) else {}
    recovery = evidence.get('recovery') if isinstance(evidence.get('recovery'), dict) else {}
    return str(recovery.get('status') or '')


def _is_anchor_recovery_success(result) -> bool | None:
    status = _recovery_status(result)
    if not status:
        return None
    return status in SUCCESSFUL_RECOVERY_STATUSES


def _status_recommendation(statuses: list[str]) -> str:
    latest = statuses[0] if statuses else ''
    if latest == 'not_found':
        return '检查目标是否在起始页面或有限滑动范围内；如果截图存在该控件，优先补语义或调整目标名称。'
    if latest == 'risk_skipped':
        return '命中风险护栏，确认该目标是否应该加入允许清单或改为人工确认步骤。'
    if latest == 'anchor_recovery_failed':
        return '点击后偏离锚点页，建议补返回策略或降低该入口巡检优先级。'
    if latest == 'found_unconfirmed':
        return '已命中目标但状态变化不明显，适合补充 Switch/弹窗/局部状态判定或人工归档规则。'
    if len(set(statuses)) > 1:
        return '最近几次运行结果不一致，优先复核截图、命中范围和设备状态。'
    return '最近运行结果一致，可继续纳入稳定基线观察。'


def _acceptance_item(key: str, label: str, actual, expected: str, passed: bool, suggestion: str) -> dict:
    return {
        'key': key,
        'label': label,
        'actual': actual,
        'expected': expected,
        'passed': bool(passed),
        'suggestion': suggestion,
    }


def _related_items(obj, related_name: str) -> list:
    related = getattr(obj, related_name, None)
    if related is None:
        return []
    if hasattr(related, 'all'):
        return list(related.all())
    return list(related)


def _run_expected_targets(run, results: list) -> set[str]:
    names = {str(result.target_name or '').strip() for result in results if str(result.target_name or '').strip()}
    summary = getattr(run, 'summary', None) if isinstance(getattr(run, 'summary', None), dict) else {}
    for key in ('objective_keywords', 'target_list'):
        raw_values = summary.get(key)
        if isinstance(raw_values, list):
            names.update(str(item or '').strip() for item in raw_values if str(item or '').strip())
    raw_specs = summary.get('target_specs')
    if isinstance(raw_specs, list):
        for spec in raw_specs:
            if not isinstance(spec, dict):
                continue
            name = str(spec.get('name') or spec.get('target_name') or '').strip()
            if name:
                names.add(name)
    return names


def _step_target_name(step) -> str:
    raw = getattr(step, 'raw', None)
    if isinstance(raw, dict):
        target = str(raw.get('target') or '').strip()
        if target:
            return target
    return str(getattr(step, 'target_text', '') or '').strip()


def _step_has_forbidden_risk(step) -> bool:
    raw = getattr(step, 'raw', None)
    risk = raw.get('risk') if isinstance(raw, dict) else {}
    return isinstance(risk, dict) and risk.get('level') == 'forbidden'


def _result_has_forbidden_risk(result) -> bool:
    risk = getattr(result, 'risk', None)
    return isinstance(risk, dict) and risk.get('level') == 'forbidden'


def _run_guardrail_counts(run, results: list) -> dict:
    expected_targets = _run_expected_targets(run, results)
    target_result_step_ids = {
        getattr(result, 'step_id', None)
        for result in results
        if getattr(result, 'step_id', None)
    }
    off_list_steps = []
    risk_auto_steps = []
    steps = _related_items(run, 'steps')

    for step in steps:
        action_type = str(getattr(step, 'action_type', '') or '')
        if action_type not in INTERACTIVE_STEP_TYPES:
            continue
        if _step_has_forbidden_risk(step):
            risk_auto_steps.append(step)
        step_id = getattr(step, 'id', None)
        if step_id and step_id in target_result_step_ids:
            continue
        raw = getattr(step, 'raw', None)
        if isinstance(raw, dict) and raw.get('mode') == 'target_inspection':
            target_name = _step_target_name(step)
            if target_name and target_name not in expected_targets:
                off_list_steps.append(step)
            elif not target_name:
                off_list_steps.append(step)

    risk_auto_results = [
        result
        for result in results
        if _result_has_forbidden_risk(result) and getattr(result, 'status', '') != 'risk_skipped'
    ]
    return {
        'off_list_action_count': len(off_list_steps),
        'risk_auto_action_count': len(risk_auto_steps) + len(risk_auto_results),
        'off_list_actions': [
            {
                'step_index': getattr(step, 'step_index', None),
                'action_type': getattr(step, 'action_type', ''),
                'target': _step_target_name(step),
            }
            for step in off_list_steps[:20]
        ],
        'risk_auto_actions': [
            {
                'source': 'step',
                'step_index': getattr(step, 'step_index', None),
                'action_type': getattr(step, 'action_type', ''),
                'target': _step_target_name(step),
            }
            for step in risk_auto_steps[:20]
        ] + [
            {
                'source': 'target_result',
                'target_name': getattr(result, 'target_name', ''),
                'status': getattr(result, 'status', ''),
            }
            for result in risk_auto_results[:20]
        ],
    }


def build_target_consistency_metrics(
    runs: Iterable[AppExplorationRun],
    *,
    run_limit: int = 3,
    thresholds: dict | None = None,
) -> dict:
    """Build deterministic stability metrics from recent target-inspection runs."""
    effective_thresholds = dict(DEFAULT_THRESHOLDS)
    effective_thresholds.update(thresholds or {})
    selected_runs = list(runs)[:run_limit]

    run_payloads = []
    target_order: list[str] = []
    target_map: dict[str, dict[int, object]] = {}
    all_results = []
    off_list_action_count = 0
    risk_auto_action_count = 0
    off_list_actions = []
    risk_auto_actions = []

    for run in selected_runs:
        results = list(run.target_results.all())
        guardrail_counts = _run_guardrail_counts(run, results)
        off_list_action_count += guardrail_counts['off_list_action_count']
        risk_auto_action_count += guardrail_counts['risk_auto_action_count']
        off_list_actions.extend(guardrail_counts['off_list_actions'])
        risk_auto_actions.extend(guardrail_counts['risk_auto_actions'])
        run_payloads.append({
            'id': run.id,
            'status': run.status,
            'result': run.result,
            'created_at': run.created_at.isoformat() if run.created_at else '',
            'target_count': len(results),
            'off_list_action_count': guardrail_counts['off_list_action_count'],
            'risk_auto_action_count': guardrail_counts['risk_auto_action_count'],
        })
        for result in results:
            name = str(result.target_name or '').strip()
            if not name:
                continue
            if name not in target_order:
                target_order.append(name)
            target_map.setdefault(name, {})[run.id] = result
            all_results.append(result)

    rows = []
    consistent_count = 0
    recognized_count = 0
    evidence_complete_count = 0
    recovery_total = 0
    recovery_success_count = 0
    expected_result_count = len(target_order) * len(selected_runs)

    for target_name in target_order:
        statuses = []
        status_values = []
        recognized_in_runs = 0
        evidence_complete_in_runs = 0
        for run in selected_runs:
            result = target_map.get(target_name, {}).get(run.id)
            status = result.status if result else 'not_found'
            status_values.append(status)
            recognized = bool(result and result.status in RECOGNIZED_STATUSES)
            evidence_complete = bool(result and _is_evidence_complete(result))
            recovery_success = _is_anchor_recovery_success(result) if result else None
            recovery_status = _recovery_status(result) if result else ''

            if recognized:
                recognized_count += 1
                recognized_in_runs += 1
            if evidence_complete:
                evidence_complete_count += 1
                evidence_complete_in_runs += 1
            if recovery_success is not None:
                recovery_total += 1
                if recovery_success:
                    recovery_success_count += 1

            statuses.append({
                'run_id': run.id,
                'status': status,
                'recognized': recognized,
                'evidence_complete': evidence_complete,
                'recovery_status': recovery_status,
                'step_index': result.step.step_index if result and result.step_id and result.step else None,
            })

        comparable_statuses = status_values if len(selected_runs) > 1 else status_values[:1]
        consistent = bool(comparable_statuses) and len(set(comparable_statuses)) == 1
        if consistent:
            consistent_count += 1
        rows.append({
            'target_name': target_name,
            'latest_status': status_values[0] if status_values else '',
            'consistent': consistent,
            'recognized_in_runs': recognized_in_runs,
            'evidence_complete_in_runs': evidence_complete_in_runs,
            'statuses': statuses,
            'recommendation': _status_recommendation(status_values),
        })

    target_count = len(target_order)
    consistency_rate = _round_rate(consistent_count, target_count)
    recognition_rate = _round_rate(recognized_count, expected_result_count)
    evidence_completeness_rate = _round_rate(evidence_complete_count, expected_result_count)
    anchor_recovery_sampled = recovery_total > 0
    anchor_recovery_rate = _round_rate(recovery_success_count, recovery_total) if anchor_recovery_sampled else None
    anchor_recovery_actual = f'{anchor_recovery_rate}%' if anchor_recovery_sampled else '无恢复样本'
    risk_skipped_count = len([item for item in all_results if item.status == 'risk_skipped'])

    failed_thresholds = []
    if len(selected_runs) < effective_thresholds['min_runs']:
        failed_thresholds.append('run_count')
    if recognition_rate < effective_thresholds['recognition_rate']:
        failed_thresholds.append('recognition_rate')
    if anchor_recovery_sampled and anchor_recovery_rate < effective_thresholds['anchor_recovery_rate']:
        failed_thresholds.append('anchor_recovery_rate')
    if evidence_completeness_rate < effective_thresholds['evidence_completeness_rate']:
        failed_thresholds.append('evidence_completeness_rate')
    if consistency_rate < effective_thresholds['consistency_rate']:
        failed_thresholds.append('consistency_rate')
    if off_list_action_count > effective_thresholds['off_list_action_count']:
        failed_thresholds.append('off_list_action_count')
    if risk_auto_action_count > effective_thresholds['risk_auto_action_count']:
        failed_thresholds.append('risk_auto_action_count')

    acceptance_items = [
        _acceptance_item(
            'run_count',
            '三次执行基线',
            len(selected_runs),
            f'>= {effective_thresholds["min_runs"]} 次',
            len(selected_runs) >= effective_thresholds['min_runs'],
            '连续执行同一个目标巡检任务三次，保持设备起始页和目标清单一致。',
        ),
        _acceptance_item(
            'recognition_rate',
            '目标识别率',
            f'{recognition_rate}%',
            f'>= {effective_thresholds["recognition_rate"]}%',
            recognition_rate >= effective_thresholds['recognition_rate'],
            '未达标时优先复核未命中截图，补语义元素或调整目标名称。',
        ),
        _acceptance_item(
            'anchor_recovery_rate',
            '锚点恢复成功率',
            anchor_recovery_actual,
            f'>= {effective_thresholds["anchor_recovery_rate"]}%',
            (not anchor_recovery_sampled) or anchor_recovery_rate >= effective_thresholds['anchor_recovery_rate'],
            '未达标时补充返回策略、起始导航或降低偏航入口优先级。',
        ),
        _acceptance_item(
            'evidence_completeness_rate',
            '证据完整率',
            f'{evidence_completeness_rate}%',
            f'= {effective_thresholds["evidence_completeness_rate"]}%',
            evidence_completeness_rate >= effective_thresholds['evidence_completeness_rate'],
            '未达标时检查截图、bounds、坐标和目标结果入库链路。',
        ),
        _acceptance_item(
            'consistency_rate',
            '三次结果一致率',
            f'{consistency_rate}%',
            f'>= {effective_thresholds["consistency_rate"]}%',
            consistency_rate >= effective_thresholds['consistency_rate'],
            '未达标时对比三次截图和命中控件，确认是否设备状态或页面数据波动。',
        ),
        _acceptance_item(
            'off_list_action_count',
            '清单外动作次数',
            off_list_action_count,
            f'= {effective_thresholds["off_list_action_count"]}',
            off_list_action_count <= effective_thresholds['off_list_action_count'],
            '目标巡检只允许执行目标清单动作；如出现清单外动作，需要立即回退执行器逻辑。',
        ),
        _acceptance_item(
            'risk_auto_action_count',
            '高风险动作自动执行次数',
            risk_auto_action_count,
            f'= {effective_thresholds["risk_auto_action_count"]}',
            risk_auto_action_count <= effective_thresholds['risk_auto_action_count'],
            '高风险目标应进入 risk_skipped 或人工确认，不允许自动点击。',
        ),
    ]
    failed_acceptance_items = [item['key'] for item in acceptance_items if not item['passed']]

    return {
        'available': bool(selected_runs and target_count),
        'passed': bool(selected_runs and target_count and not failed_acceptance_items),
        'failed_thresholds': failed_thresholds,
        'thresholds': effective_thresholds,
        'run_count': len(selected_runs),
        'run_limit': run_limit,
        'runs': run_payloads,
        'target_count': target_count,
        'consistent_target_count': consistent_count,
        'inconsistent_target_count': max(target_count - consistent_count, 0),
        'consistency_rate': consistency_rate,
        'recognition_rate': recognition_rate,
        'recognized_count': recognized_count,
        'expected_result_count': expected_result_count,
        'anchor_recovery_rate': anchor_recovery_rate,
        'anchor_recovery_sampled': anchor_recovery_sampled,
        'anchor_recovery_success_count': recovery_success_count,
        'anchor_recovery_total': recovery_total,
        'evidence_completeness_rate': evidence_completeness_rate,
        'evidence_complete_count': evidence_complete_count,
        'risk_skipped_count': risk_skipped_count,
        'off_list_action_count': off_list_action_count,
        'risk_auto_action_count': risk_auto_action_count,
        'off_list_actions': off_list_actions[:20],
        'risk_auto_actions': risk_auto_actions[:20],
        'acceptance_items': acceptance_items,
        'failed_acceptance_items': failed_acceptance_items,
        'rows': rows,
    }
