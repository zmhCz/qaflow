# -*- coding: utf-8 -*-
"""Rule-based exploratory runner for APP automation.

The first version deliberately avoids LLM control. It creates a reliable trace
of screenshots, XML snapshots, actions, and basic risks. AI can be plugged in
later as a decision advisor on top of this stable execution loop.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Iterable

from django.conf import settings
from django.utils import timezone

from ..models import AppExplorationRun, AppExplorationStep, AppExplorationTask, AppInspectionTargetResult, AppTestConfig
from .exploration_risk_guard import (
    assess_risk_values,
    contains_forbidden_risk,
)

OBJECTIVE_BUSINESS_TERMS = [
    '首页',
    '消息',
    '社区',
    '创建',
    '搜索',
    '列表',
    '详情',
    '关注',
    '登录',
    '注册',
    '我的',
    '设置',
    '昵称',
    '名称',
    '介绍',
    '返回',
    '入口',
    '导航',
    '主导航',
    'Tab',
    'tab',
]

HIGH_VALUE_CONTROL_KEYWORDS = (
    'tab', 'nav', 'navigation', 'bottom', 'menu', 'home', 'main', '入口', '导航', '首页', '消息',
    '社区', '我的', '设置', '搜索', '创建', '新增', '发布', '更多', '详情', '列表', 'item', 'card',
    'cell', '确定', '确认', '取消', '完成', '下一步',
)
LIST_CONTROL_KEYWORDS = (
    'recycler', 'recyclerview', 'list', 'listview', 'item', 'adapter', 'card', 'cell', '列表',
)
FORM_INPUT_KEYWORDS = (
    'edit', 'input', 'et', 'searchview', 'textfield', 'textarea', 'password', 'phone', 'mobile',
    'comment', 'content', 'desc', 'name', 'title', '输入', '编辑', '昵称', '名称', '介绍',
)
LOW_VALUE_CONTROL_KEYWORDS = (
    'background', 'bg', 'banner', 'avatar', 'logo', 'placeholder', 'divider', 'decor', 'cover',
    'image', 'photo', 'picture', 'ivbackground', 'iv_background', '背景', '头像', '图片', '封面',
)
INVALID_OBJECTIVE_KEYWORD_MARKERS = (
    '观察', '确认', '复核', '包括', '是否', '文案', '目标', '路径', '修正',
    '建议', '检查', '进入', '再进入', '点击', '打开', '查看', '验证', '测试',
    '人工复现', '至第', '第', '步骤', '网络请求', '权限提示', 'Toast', 'toast',
)

GENERIC_OBJECTIVE_KEYWORDS = {
    '入口', '列表', '控件', '页面', '当前', '主要', '重点', '覆盖', '遍历', '返回', '继续',
    '浅层', '检查', '状态', '变化', '详情', '按钮', '模块', '区域', '搜索', '搜索框', '搜索页',
    '顶部', '底部', '以及页面内容', '页面内容', '内容入口', '如果误入', '不要进入', '优先返回',
    'entry', 'list', 'page', 'button', 'search',
}

UNREADABLE_LABEL_RE = re.compile(r'[\u25a0-\u25a1\ufffd\ue000-\uf8ff]')


def clean_display_label(value: str) -> str:
    """Return a readable label for reports and generated draft steps."""
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


def clean_objective_keyword(value: str) -> str:
    text = clean_display_label(value)
    text = re.sub(r'^[在再去到从往]+', '', text)
    text = re.sub(r'(页面|页|模块|区域|入口)$', '', text)
    text = re.sub(r'[“”"\'`（）()\[\]【】<>《》]', '', text)
    return text.strip(' \t\r\n,，。；;、：:!?！？')


def is_valid_objective_keyword(value: str) -> bool:
    text = clean_objective_keyword(value)
    if text.isdigit():
        return False
    if not (2 <= len(text) <= 14):
        return False
    allowed_business_markers = {'测试', '验证'}
    return not any(
        marker in text
        for marker in INVALID_OBJECTIVE_KEYWORD_MARKERS
        if marker not in allowed_business_markers
    )


@dataclass
class UiCandidate:
    text: str
    resource_id: str
    content_desc: str
    class_name: str
    bounds: str
    x: int
    y: int
    width: int
    height: int
    score: float
    objective_hits: list[str]
    score_reasons: list[str]
    risk: dict | None = None

    @property
    def label(self) -> str:
        return (
            clean_display_label(self.text)
            or clean_display_label(self.content_desc)
            or clean_display_label(self.resource_id.split('/')[-1])
            or clean_display_label(self.class_name)
            or 'unknown target'
        )

    @property
    def key(self) -> str:
        semantic_key = '|'.join([self.resource_id, self.text, self.content_desc, self.class_name]).strip('|')
        if semantic_key:
            return semantic_key
        return '|'.join([self.class_name, self.bounds])


class RuleExplorationRunner:
    """Small deterministic exploration engine backed by ADB."""

    def __init__(self, task: AppExplorationTask, run: AppExplorationRun | None = None):
        self.task = task
        self.execution_run = run
        self.adb_path = self._get_adb_path()
        self.device_id = task.device.device_id if task.device else ''
        self.package_name = task.app_package.package_name if task.app_package else ''
        self.started_at = time.time()
        self.visited_targets: set[str] = set()
        self.unresponsive_targets: set[str] = set()
        self.visited_pages: set[str] = set()
        self.visited_semantic_pages: set[str] = set()
        self.no_change_count = 0
        self.no_candidate_signature = ''
        self.no_candidate_swipe_count = 0
        self.empty_page_escape_count = 0
        self.stagnant_action_count = 0
        self.low_value_action_count = 0
        self.repeated_semantic_hit_count = 0
        self.trap_page_escape_count = 0
        self.exploration_stop_reason = ''
        self.pending_anchor_return: dict | None = None
        self.anchor_return_count = 0
        self.shallow_entry_probe_count = 0
        self.anchor_page_signature = ''
        self.anchor_page_semantic_signature = ''
        self.anchor_page_keywords: set[str] = set()
        self.off_course_escape_count = 0
        self.entry_navigation_trace: list[dict] = []
        self.objective_keywords = self._extract_objective_keywords()
        self.target_keyword_hits: dict[str, int] = {keyword: 0 for keyword in self.objective_keywords}
        self.skipped_risks: list[dict] = []
        self.page_map: dict[str, dict] = {}
        self.reported_logcat_issue_keys: set[str] = set()
        self.logcat_collector = None
        self.current_stage = '初始化探索任务'
        self.output_dir = os.path.join(
            settings.MEDIA_ROOT,
            'app-automation',
            'explorations',
            f'task_{task.id}',
            f'run_{run.id}' if run else 'legacy',
        )
        os.makedirs(self.output_dir, exist_ok=True)

    def run(self) -> dict:
        if not self.device_id:
            raise RuntimeError('探索任务未绑定设备')

        self._set_stage('设备检查与 APP 启动中', progress=3)
        self._prepare_device()
        self._set_stage('准备采集 logcat 日志', progress=5)
        self._start_logcat_capture()
        try:
            self._set_stage('执行入口关键词导航', progress=8)
            self._run_entry_navigation()
            self._set_stage('执行起始导航动作', progress=12)
            self._run_start_actions()
        except Exception:
            self._save_logcat_artifacts()
            raise
        issues = []

        for step_index in range(1, self.task.max_steps + 1):
            self.task.refresh_from_db(fields=['status'])
            if self.task.status == 'stopped':
                break
            if time.time() - self.started_at > self.task.max_duration:
                self._create_stop_step(step_index, '达到最大探索时长，任务停止')
                break

            self._set_stage(f'第 {step_index} 步：采集页面结构', progress=min(95, int((step_index - 0.5) / max(self.task.max_steps, 1) * 95)))
            before = self._capture_state(step_index, 'before')
            self.visited_pages.add(before['signature'])
            before_semantic_signature = before.get('semantic_signature') or ''
            if before_semantic_signature:
                self.visited_semantic_pages.add(before_semantic_signature)
            self._register_page(before, step_index)
            self._maybe_set_anchor_page(before)
            candidate = None
            action_prepared = False
            trap_reason = self._trap_page_escape_reason(before)
            if trap_reason:
                self._set_stage(f'第 {step_index} 步：低价值页面脱困')
                self._press_back()
                self.trap_page_escape_count += 1
                if trap_reason == 'off_course_anchor_escape':
                    self.off_course_escape_count += 1
                action_type = 'back'
                action_label = '低价值页面脱困，返回上一页'
                target_data = {
                    'target_text': '',
                    'target_resource_id': '',
                    'target_class': '',
                    'bounds': '',
                    'x': None,
                    'y': None,
                    'raw': {
                        'reason': trap_reason,
                        'strategy': 'system_back',
                        'page_activity': before.get('activity', ''),
                        'page_signature': before.get('signature', ''),
                    },
                }
                action_prepared = True
            elif self.pending_anchor_return:
                anchor_return = self.pending_anchor_return
                self.pending_anchor_return = None
                self.anchor_return_count += 1
                self._set_stage(f'第 {step_index} 步：入口巡检返回锚点页')
                self._press_back()
                action_type = 'back'
                action_label = '入口巡检返回锚点页'
                target_data = {
                    'target_text': '',
                    'target_resource_id': '',
                    'target_class': '',
                    'bounds': '',
                    'x': None,
                    'y': None,
                    'raw': {
                        'reason': 'shallow_entry_anchor_return',
                        'strategy': 'system_back',
                        'anchor_signature': anchor_return.get('anchor_signature', ''),
                        'anchor_semantic_signature': anchor_return.get('anchor_semantic_signature', ''),
                        'probe_step': anchor_return.get('probe_step'),
                        'probe_keywords': anchor_return.get('probe_keywords', []),
                        'probe_target': anchor_return.get('probe_target', ''),
                    },
                }
                action_prepared = True
            else:
                candidates = self._select_candidates(before['xml'], before['screen_size'], before)
                candidate = self._choose_candidate(candidates)

            if not action_prepared and candidate:
                self._set_stage(f'第 {step_index} 步：点击 {candidate.label}')
                self._tap(candidate.x, candidate.y)
                action_type = 'tap'
                action_label = f'点击 {candidate.label}'
                for keyword in candidate.objective_hits:
                    self.target_keyword_hits[keyword] = self.target_keyword_hits.get(keyword, 0) + 1
                target_data = {
                    'target_text': candidate.text,
                    'target_resource_id': candidate.resource_id,
                    'target_class': candidate.class_name,
                    'bounds': candidate.bounds,
                    'x': candidate.x,
                    'y': candidate.y,
                    'raw': {
                        'candidate_key': candidate.key,
                        'candidate_score': candidate.score,
                        'score_reasons': candidate.score_reasons,
                        'objective_hits': candidate.objective_hits,
                        'risk': candidate.risk or {},
                    },
                }
            elif not action_prepared:
                width, height = before['screen_size']
                if self._should_escape_empty_page(before):
                    self._set_stage(f'第 {step_index} 步：空页面无有效内容，返回上一页')
                    self._press_back()
                    action_type = 'back'
                    action_label = '空页面连续滑动无变化，返回上一页'
                    self.empty_page_escape_count += 1
                    target_data = {
                        'target_text': '',
                        'target_resource_id': '',
                        'target_class': '',
                        'bounds': '',
                        'x': None,
                        'y': None,
                        'raw': {
                            'reason': 'empty_page_escape',
                            'strategy': 'system_back',
                            'previous_no_candidate_swipes': self.no_candidate_swipe_count,
                            'page_signature': before.get('signature', ''),
                        },
                    }
                else:
                    self._set_stage(f'第 {step_index} 步：未发现合适控件，滑动探索')
                    self._swipe(width // 2, int(height * 0.78), width // 2, int(height * 0.28))
                    action_type = 'swipe'
                    action_label = '未发现合适控件，向上滑动探索'
                    target_data = {
                        'target_text': '',
                        'target_resource_id': '',
                        'target_class': '',
                        'bounds': '',
                        'x': width // 2,
                        'y': int(height * 0.78),
                        'raw': {
                            'reason': 'no_clickable_candidate',
                            'start': [width // 2, int(height * 0.78)],
                            'end': [width // 2, int(height * 0.28)],
                            'duration': 0.45,
                        },
                    }

            time.sleep(1.0)
            after = self._capture_state(step_index, 'after')
            changed = before['signature'] != after['signature'] or before['activity'] != after['activity']
            semantic_changed = (
                before.get('semantic_signature') != after.get('semantic_signature')
                or before['activity'] != after['activity']
            )
            after_semantic_signature = after.get('semantic_signature') or ''
            new_semantic_page = bool(
                after_semantic_signature
                and after_semantic_signature not in self.visited_semantic_pages
            )
            self._register_page(after, step_index)
            if changed:
                self.no_change_count = 0
            else:
                self.no_change_count += 1
            self._update_empty_page_escape_state(before, action_type, target_data, semantic_changed)
            if action_type == 'tap' and candidate and not semantic_changed:
                self.unresponsive_targets.add(candidate.key)
            if action_type == 'tap' and candidate:
                self._maybe_schedule_anchor_return(
                    candidate,
                    before,
                    after,
                    step_index,
                    semantic_changed,
                    target_data,
                )
            self._update_exploration_progress_state(
                action_type,
                target_data,
                semantic_changed,
                new_semantic_page,
                after_semantic_signature,
            )

            issue_type, issue_message = self._detect_issue(before, after, action_type, candidate, changed)
            if issue_type:
                issues.append({
                    'step_index': step_index,
                    'issue_type': issue_type,
                    'issue_message': issue_message,
                    'action': action_label,
                })

            self._record_page_transition(before, after, step_index, action_label, target_data, issue_type)
            AppExplorationStep.objects.create(
                task=self.task,
                run=self.execution_run,
                step_index=step_index,
                action_type=action_type,
                action_label=action_label,
                before_activity=before['activity'],
                after_activity=after['activity'],
                before_signature=before['signature'],
                after_signature=after['signature'],
                changed=changed,
                before_screenshot=before['screenshot'],
                after_screenshot=after['screenshot'],
                page_source_path=before['xml_path'],
                issue_type=issue_type,
                issue_message=issue_message,
                logcat_excerpt=self._read_logcat_excerpt() if issue_type else '',
                **target_data,
            )

            self.visited_pages.add(after['signature'])
            if after_semantic_signature:
                self.visited_semantic_pages.add(after_semantic_signature)
            self.task.total_steps = step_index
            self.task.explored_pages = len(self.visited_pages)
            self.task.issue_count = len(issues)
            self.task.progress = min(95, int(step_index / max(self.task.max_steps, 1) * 95))
            self.task.summary = self._build_summary(issues)
            self.task.save(update_fields=['total_steps', 'explored_pages', 'issue_count', 'progress', 'summary', 'updated_at'])
            if self.execution_run:
                self.execution_run.total_steps = self.task.total_steps
                self.execution_run.explored_pages = self.task.explored_pages
                self.execution_run.issue_count = self.task.issue_count
                self.execution_run.summary = self.task.summary
                self.execution_run.save(update_fields=['total_steps', 'explored_pages', 'issue_count', 'summary', 'updated_at'])

            if self.no_change_count >= 3:
                self._press_back()
                self.no_change_count = 0

            stop_reason = self._low_value_stop_reason(step_index)
            if stop_reason:
                self.exploration_stop_reason = stop_reason
                if step_index < self.task.max_steps:
                    self._create_stop_step(step_index + 1, stop_reason)
                self.task.summary = self._build_summary(issues)
                self.task.save(update_fields=['summary', 'updated_at'])
                if self.execution_run:
                    self.execution_run.summary = self.task.summary
                    self.execution_run.save(update_fields=['summary', 'updated_at'])
                break

        self._set_stage('生成日志与探索报告', progress=98)
        self._save_logcat_artifacts()
        self.current_stage = '探索完成'
        return self._build_summary(issues)

    def _set_stage(self, stage: str, progress: int | None = None) -> None:
        self.current_stage = stage
        summary = dict(self.task.summary or {})
        summary['current_stage'] = stage
        self.task.summary = summary
        update_fields = ['summary', 'updated_at']
        if progress is not None:
            self.task.progress = max(int(self.task.progress or 0), min(int(progress), 99))
            update_fields.append('progress')
        try:
            self.task.save(update_fields=update_fields)
            if self.execution_run:
                self.execution_run.summary = summary
                self.execution_run.save(update_fields=['summary', 'updated_at'])
        except Exception:
            pass

    def _start_logcat_capture(self) -> None:
        try:
            from .logcat_helper import AppLogcatCollector

            self.logcat_collector = AppLogcatCollector(
                device_id=self.device_id,
                results_dir=self.output_dir,
                adb_path=self.adb_path,
            )
            self.logcat_collector.clear()
        except Exception:
            self.logcat_collector = None

    def _save_logcat_artifacts(self) -> None:
        if not self.logcat_collector:
            return
        try:
            self.logcat_collector.save_artifacts(f'exploration_{self.task.id}')
        except Exception:
            pass

    def _run_entry_navigation(self) -> None:
        """Best-effort navigation by business keywords before normal exploration."""
        keywords = self._normalize_keywords(self.task.entry_keywords or [])
        if not keywords:
            return

        for keyword in keywords:
            matched = False
            attempts = []
            for attempt in range(1, 4):
                self._set_stage(f'查找入口关键词：{keyword}（第 {attempt}/3 次）', progress=8)
                xml = self._dump_xml()
                center = self._find_start_target(xml, 'tap_text', keyword) or self._find_start_target(xml, 'tap_resource_id', keyword)
                if center:
                    self._set_stage(f'入口关键词已命中：{keyword}', progress=10)
                    before_focus = self._get_focus()
                    self._tap(center[0], center[1])
                    time.sleep(0.9)
                    after_focus = self._get_focus()
                    self.entry_navigation_trace.append({
                        'keyword': keyword,
                        'status': 'matched',
                        'mode': 'candidate_entry',
                        'stop_reason': 'matched_candidate_entry',
                        'attempt': attempt,
                        'x': center[0],
                        'y': center[1],
                        'before_activity': before_focus.get('activity', ''),
                        'after_activity': after_focus.get('activity', ''),
                    })
                    matched = True
                    break

                attempts.append({'attempt': attempt, 'status': 'not_found'})
                if attempt < 3:
                    self._set_stage(f'入口关键词未命中：{keyword}，滑动后继续查找', progress=8)
                    width, height = self._get_screen_size()
                    self._swipe(width // 2, int(height * 0.78), width // 2, int(height * 0.28))
                    time.sleep(0.6)

            if not matched:
                self._set_stage(f'入口关键词未找到：{keyword}，继续后续探索', progress=10)
                self.entry_navigation_trace.append({
                    'keyword': keyword,
                    'status': 'not_found',
                    'mode': 'candidate_entry',
                    'attempts': attempts,
                })
            else:
                self._set_stage(f'入口关键词已命中：{keyword}，开始正式探索', progress=10)
                return

    def _normalize_keywords(self, value: list[str]) -> list[str]:
        result = []
        for item in value:
            text = clean_objective_keyword(item)
            if (
                is_valid_objective_keyword(text)
                and not self._is_generic_objective_keyword(text)
                and text not in result
                and not self._is_blacklisted([text])
            ):
                result.append(text)
        return result[:8]

    def _is_generic_objective_keyword(self, value: str) -> bool:
        text = clean_objective_keyword(value)
        if not text or text.lower() in GENERIC_OBJECTIVE_KEYWORDS:
            return True
        generic_markers = (
            '重点覆盖',
            '优先返回',
            '不要进入',
            '如果误入',
            '当前社区首页',
            '输入键盘',
            '三级详情',
            '空结果',
            '状态有变化',
        )
        return any(marker in text for marker in generic_markers)

    def _extract_objective_keywords(self) -> list[str]:
        source = ' '.join([
            str(self.task.objective or ''),
            ' '.join(str(item) for item in (self.task.entry_keywords or [])),
        ])
        keywords: list[str] = []
        for term in OBJECTIVE_BUSINESS_TERMS:
            if (
                term.lower() in source.lower()
                and term not in keywords
                and is_valid_objective_keyword(term)
                and not self._is_generic_objective_keyword(term)
            ):
                keywords.append(term)
        for token in re.split(r'[\s,，、/|;；:：。.!！?？\[\]()（）]+', source):
            token = clean_objective_keyword(token)
            if (
                is_valid_objective_keyword(token)
                and not self._is_generic_objective_keyword(token)
                and token not in keywords
                and not self._is_blacklisted([token])
            ):
                keywords.append(token)
        return keywords[:24]

    def _run_start_actions(self) -> None:
        actions = self.task.start_actions or []
        if not isinstance(actions, list):
            return

        for index, action in enumerate(actions, 1):
            if not isinstance(action, dict) or not action.get('type'):
                continue
            action_type = str(action.get('type') or '').strip()
            try:
                self._set_stage(f'执行起始导航第 {index} 步：{self._describe_start_action(action_type, action)}', progress=12)
                self._run_start_action(action_type, action)
                time.sleep(float(action.get('after_wait') or 0.6))
            except Exception as exc:
                raise RuntimeError(f'起始导航第 {index} 步失败：{exc}') from exc

    def _describe_start_action(self, action_type: str, action: dict) -> str:
        if action_type == 'wait':
            return f"等待 {action.get('seconds') or action.get('value') or 1} 秒"
        if action_type == 'back':
            return '返回上一页'
        if action_type == 'tap_pos':
            return f"点击坐标 ({action.get('x') or 0}, {action.get('y') or 0})"
        if action_type == 'swipe':
            direction_text = {
                'up': '向上滑动',
                'down': '向下滑动',
                'left': '向左滑动',
                'right': '向右滑动',
            }
            return direction_text.get(str(action.get('direction') or 'up').lower(), '滑动页面')
        if action_type in ('tap_text', 'tap_resource_id'):
            return f"查找并点击 {action.get('value') or ''}".strip()
        return action_type or '未知动作'

    def _run_start_action(self, action_type: str, action: dict) -> None:
        if action_type == 'wait':
            time.sleep(float(action.get('seconds') or action.get('value') or 1))
            return
        if action_type == 'back':
            self._press_back()
            return
        if action_type == 'tap_pos':
            x = int(action.get('x') or 0)
            y = int(action.get('y') or 0)
            if x <= 0 or y <= 0:
                raise ValueError('点击坐标不能为空')
            self._tap(x, y)
            return
        if action_type == 'swipe':
            self._run_start_swipe(action)
            return
        if action_type in ('tap_text', 'tap_resource_id'):
            value = str(action.get('value') or '').strip()
            if not value:
                raise ValueError('点击目标不能为空')
            risk = self._assess_risk([value])
            if risk and risk.get('level') == 'forbidden':
                self._record_skipped_risk(risk, value, '', '', 'start_action', '', None)
                return
            xml = self._dump_xml()
            center = self._find_start_target(xml, action_type, value)
            if not center:
                raise ValueError(f'未找到起始导航目标：{value}')
            self._tap(center[0], center[1])
            return
        raise ValueError(f'不支持的起始导航动作：{action_type}')

    def _run_start_swipe(self, action: dict) -> None:
        width, height = self._get_screen_size()
        direction = str(action.get('direction') or 'up').lower()
        if isinstance(action.get('start'), list) and isinstance(action.get('end'), list):
            start = action['start']
            end = action['end']
            self._swipe(int(start[0]), int(start[1]), int(end[0]), int(end[1]))
            return
        if direction == 'down':
            self._swipe(width // 2, int(height * 0.28), width // 2, int(height * 0.78))
        elif direction == 'left':
            self._swipe(int(width * 0.82), height // 2, int(width * 0.18), height // 2)
        elif direction == 'right':
            self._swipe(int(width * 0.18), height // 2, int(width * 0.82), height // 2)
        else:
            self._swipe(width // 2, int(height * 0.78), width // 2, int(height * 0.28))

    def _find_start_target(self, xml: str, action_type: str, value: str) -> tuple[int, int] | None:
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            return None
        needle = value.lower()
        for node in root.iter():
            attrs = node.attrib
            if action_type == 'tap_text':
                candidates = [
                    attrs.get('text', ''),
                    attrs.get('content-desc', ''),
                ]
                matched = any(needle in str(item).lower() for item in candidates if item)
            else:
                resource_id = str(attrs.get('resource-id', '') or '')
                tail = resource_id.split('/')[-1]
                matched = resource_id == value or tail == value or needle in resource_id.lower()
            if not matched:
                continue
            bounds = self._parse_bounds(attrs.get('bounds', ''))
            if bounds:
                x1, y1, x2, y2 = bounds
                return (x1 + x2) // 2, (y1 + y2) // 2
        return None

    def _get_adb_path(self) -> str:
        config = AppTestConfig.objects.first()
        return config.adb_path if config and config.adb_path else 'adb'

    def _prepare_device(self) -> None:
        self._run_adb(['shell', 'logcat', '-c'], timeout=8, check=False)
        if self.package_name:
            self._run_adb(
                ['shell', 'monkey', '-p', self.package_name, '-c', 'android.intent.category.LAUNCHER', '1'],
                timeout=15,
                check=False,
            )
            time.sleep(1.5)

    def _capture_state(self, step_index: int, phase: str) -> dict:
        screenshot_rel = self._capture_screenshot(step_index, phase)
        xml = self._dump_xml()
        xml_rel = self._save_xml(step_index, phase, xml)
        focus = self._get_focus()
        screen_size = self._get_screen_size()
        return {
            'screenshot': screenshot_rel,
            'xml': xml,
            'xml_path': xml_rel,
            'activity': focus.get('activity', ''),
            'package': focus.get('package_name', ''),
            'signature': self._page_signature(focus, xml),
            'semantic_signature': self._semantic_page_signature(focus, xml),
            'screen_size': screen_size,
        }

    def _capture_screenshot(self, step_index: int, phase: str) -> str:
        path = os.path.join(self.output_dir, f'step_{step_index:03d}_{phase}.png')
        result = self._run_adb(['exec-out', 'screencap', '-p'], timeout=12)
        with open(path, 'wb') as image_file:
            image_file.write(result.stdout)
        return self._relative_media_path(path)

    def _dump_xml(self) -> str:
        command = (
            'rm -f /data/local/tmp/qaflow_uidump.xml >/dev/null 2>&1; '
            'uiautomator dump --compressed /data/local/tmp/qaflow_uidump.xml >/dev/null 2>&1; '
            'cat /data/local/tmp/qaflow_uidump.xml'
        )
        result = self._run_adb(['shell', 'sh', '-c', command], timeout=15)
        output = result.stdout.decode('utf-8', errors='ignore')
        start = output.find('<?xml')
        end = output.rfind('</hierarchy>')
        if start >= 0 and end >= 0:
            return output[start:end + len('</hierarchy>')]
        return output

    def _save_xml(self, step_index: int, phase: str, xml: str) -> str:
        path = os.path.join(self.output_dir, f'step_{step_index:03d}_{phase}.xml')
        with open(path, 'w', encoding='utf-8') as xml_file:
            xml_file.write(xml or '')
        return self._relative_media_path(path)

    def _get_focus(self) -> dict:
        result = self._run_adb(['shell', 'dumpsys', 'window'], timeout=10, check=False)
        output = result.stdout.decode('utf-8', errors='ignore') if result.stdout else ''
        patterns = [
            r'mCurrentFocus[^\n]*\s([A-Za-z0-9._$]+)/([A-Za-z0-9._$/]+)',
            r'mFocusedApp[^\n]*\s([A-Za-z0-9._$]+)/([A-Za-z0-9._$/]+)',
            r'mTopFullscreenOpaqueWindowState[^\n]*\s([A-Za-z0-9._$]+)/([A-Za-z0-9._$/]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, output)
            if match:
                return self._normalize_focus(match.group(1), match.group(2))
        activity_focus = self._get_activity_focus()
        if activity_focus.get('package_name') or activity_focus.get('activity'):
            return activity_focus
        return {'package_name': '', 'activity': ''}

    def _get_activity_focus(self) -> dict:
        result = self._run_adb(['shell', 'dumpsys', 'activity', 'top'], timeout=10, check=False)
        output = result.stdout.decode('utf-8', errors='ignore') if result.stdout else ''
        patterns = [
            r'ACTIVITY\s+([A-Za-z0-9._$]+)/([A-Za-z0-9._$/]+)',
            r'RealActivity=([A-Za-z0-9._$]+)/([A-Za-z0-9._$/]+)',
            r'topResumedActivity[^\n]*\s([A-Za-z0-9._$]+)/([A-Za-z0-9._$/]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, output)
            if match:
                return self._normalize_focus(match.group(1), match.group(2))
        return {'package_name': '', 'activity': ''}

    def _normalize_focus(self, package_name: str, activity: str) -> dict:
        package_name = (package_name or '').strip()
        activity = (activity or '').strip().rstrip('}')
        if activity.startswith('.') and package_name:
            activity = f'{package_name}{activity}'
        return {'package_name': package_name, 'activity': activity}

    def _get_screen_size(self) -> tuple[int, int]:
        result = self._run_adb(['shell', 'wm', 'size'], timeout=8, check=False)
        output = result.stdout.decode('utf-8', errors='ignore') if result.stdout else ''
        match = re.search(r'Physical size:\s*(\d+)x(\d+)', output)
        if match:
            return int(match.group(1)), int(match.group(2))
        return 1080, 1920

    def _select_candidates(self, xml: str, screen_size: tuple[int, int], page_state: dict | None = None) -> list[UiCandidate]:
        if not xml:
            return []
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            return []

        candidates = []
        screen_width, screen_height = screen_size
        for node in root.iter('node'):
            attrs = node.attrib
            if attrs.get('enabled') == 'false':
                continue
            if attrs.get('clickable') != 'true' and attrs.get('long-clickable') != 'true':
                continue
            bounds = attrs.get('bounds', '')
            parsed = self._parse_bounds(bounds)
            if not parsed:
                continue
            x1, y1, x2, y2 = parsed
            width = max(0, x2 - x1)
            height = max(0, y2 - y1)
            if width < 8 or height < 8:
                continue

            text = attrs.get('text', '').strip()
            resource_id = attrs.get('resource-id', '').strip()
            content_desc = attrs.get('content-desc', '').strip()
            class_name = attrs.get('class', '').strip()
            if not text and not content_desc:
                text = self._descendant_label(node)
            risk = self._assess_risk([text, resource_id, content_desc, class_name])
            if risk and risk.get('level') == 'forbidden':
                self._record_skipped_risk(risk, text, resource_id, content_desc, class_name, bounds, page_state)
                continue
            if self._is_container_noise(resource_id, class_name, text, content_desc, width, height, screen_width, screen_height):
                continue

            score, reasons, objective_hits = self._score_candidate(
                text,
                resource_id,
                content_desc,
                class_name,
                width,
                height,
                screen_width,
                screen_height,
                risk,
                (x1 + x2) // 2,
                (y1 + y2) // 2,
            )
            candidates.append(UiCandidate(
                text=text,
                resource_id=resource_id,
                content_desc=content_desc,
                class_name=class_name,
                bounds=bounds,
                x=(x1 + x2) // 2,
                y=(y1 + y2) // 2,
                width=width,
                height=height,
                score=score,
                objective_hits=objective_hits,
                score_reasons=reasons,
                risk=risk,
            ))

        return sorted(candidates, key=lambda item: item.score, reverse=True)

    def _descendant_label(self, node: ET.Element) -> str:
        labels: list[str] = []
        for child in node.iter('node'):
            if child is node:
                continue
            attrs = child.attrib
            label = clean_display_label(attrs.get('text', '')) or clean_display_label(attrs.get('content-desc', ''))
            if not label or label in labels:
                continue
            labels.append(label)
            if len(labels) >= 3:
                break
        text = ' '.join(labels).strip()
        return text[:80]

    def _choose_candidate(self, candidates: Iterable[UiCandidate]) -> UiCandidate | None:
        fallback = None
        for candidate in candidates:
            if candidate.key in self.unresponsive_targets:
                continue
            if candidate.score <= 0:
                continue
            if fallback is None:
                fallback = candidate
            if candidate.key not in self.visited_targets:
                self.visited_targets.add(candidate.key)
                return candidate
        if fallback and self.no_change_count >= 2 and fallback.score >= 8:
            self.visited_targets.add(fallback.key)
            return fallback
        return None

    def _maybe_schedule_anchor_return(
        self,
        candidate: UiCandidate,
        before: dict,
        after: dict,
        step_index: int,
        semantic_changed: bool,
        target_data: dict,
    ) -> None:
        """Return to the current anchor page after a shallow objective-entry probe."""
        if self.pending_anchor_return:
            return
        if not self.objective_keywords or not candidate.objective_hits:
            return
        if not semantic_changed:
            return
        if self._is_form_like_candidate(candidate):
            return
        max_returns = max(1, min(len(self.objective_keywords), 12))
        if self.anchor_return_count >= max_returns:
            return

        remaining_keywords = [
            keyword
            for keyword in self.objective_keywords
            if self.target_keyword_hits.get(keyword, 0) <= 0
        ]
        if not remaining_keywords:
            return

        after_visible_keywords = self._visible_objective_keywords(after.get('xml') or '')
        if any(keyword in after_visible_keywords for keyword in remaining_keywords):
            return

        raw = target_data.setdefault('raw', {})
        raw['reason'] = 'shallow_entry_probe'
        raw['probe_keywords'] = candidate.objective_hits
        raw['anchor_return_pending'] = True
        self.shallow_entry_probe_count += 1
        self.pending_anchor_return = {
            'anchor_signature': before.get('signature') or '',
            'anchor_semantic_signature': before.get('semantic_signature') or '',
            'probe_step': step_index,
            'probe_keywords': candidate.objective_hits,
            'probe_target': candidate.label,
            'after_signature': after.get('signature') or '',
            'after_semantic_signature': after.get('semantic_signature') or '',
        }

    def _visible_objective_keywords(self, xml: str) -> set[str]:
        if not xml or not self.objective_keywords:
            return set()
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            return set()

        visible_texts: list[str] = []
        for node in root.iter('node'):
            attrs = node.attrib
            visible_text = ' '.join(
                item
                for item in [
                    clean_display_label(attrs.get('text', '')),
                    clean_display_label(attrs.get('content-desc', '')),
                ]
                if item
            )
            if visible_text:
                visible_texts.append(visible_text.lower())
        joined = ' '.join(visible_texts)
        return {
            keyword
            for keyword in self.objective_keywords
            if keyword.lower() in joined
        }

    def _is_form_like_candidate(self, candidate: UiCandidate) -> bool:
        joined = ' '.join([
            candidate.text,
            candidate.resource_id,
            candidate.content_desc,
            candidate.class_name,
        ]).lower()
        return any(token in joined for token in ('edittext', 'input', 'search', 'textfield', '输入', '搜索'))

    def _is_current_page_traversal(self) -> bool:
        source_summary = self.task.source_summary if isinstance(self.task.source_summary, dict) else {}
        run_mode = str(source_summary.get('run_mode') or '').lower()
        return (
            self.task.source_type == 'manual_page_traversal'
            or run_mode in {'current_page_shallow_traversal', 'page_control_traversal'}
            or (
                bool(self.objective_keywords)
                and not (self.task.entry_keywords or [])
                and not (self.task.start_actions or [])
            )
        )

    def _maybe_set_anchor_page(self, state: dict) -> None:
        if self.anchor_page_signature or not self._is_current_page_traversal():
            return
        self.anchor_page_signature = state.get('signature') or ''
        self.anchor_page_semantic_signature = state.get('semantic_signature') or ''
        self.anchor_page_keywords = self._visible_objective_keywords(state.get('xml') or '')

    def _is_off_course_page(self, state: dict) -> bool:
        if not self.anchor_page_signature or not self._is_current_page_traversal():
            return False
        signature = state.get('signature') or ''
        semantic_signature = state.get('semantic_signature') or ''
        if signature == self.anchor_page_signature or semantic_signature == self.anchor_page_semantic_signature:
            return False

        remaining_keywords = {
            keyword
            for keyword in self.objective_keywords
            if self.target_keyword_hits.get(keyword, 0) <= 0
        }
        if not remaining_keywords:
            return False
        visible_keywords = self._visible_objective_keywords(state.get('xml') or '')
        if visible_keywords & remaining_keywords:
            return False

        if len(self.anchor_page_keywords & remaining_keywords) >= 2:
            return True

        text_blob = self._xml_text_blob(state.get('xml') or '')
        off_course_markers = ('请输入游戏名称搜索', '确定', '游戏名称', '绑定游戏', '选择游戏')
        return any(marker in text_blob for marker in off_course_markers)

    def _trap_page_escape_reason(self, state: dict) -> str:
        """Detect pages where swiping is low-value and a back action is safer."""
        activity = str(state.get('activity') or '').lower()
        xml = state.get('xml') or ''
        if not xml:
            return ''

        if self._is_off_course_page(state):
            return 'off_course_anchor_escape'

        text_blob = self._xml_text_blob(xml)
        lower_blob = text_blob.lower()
        is_search_page = (
            'search' in activity
            or 'globalsearch' in lower_blob
            or '搜索' in text_blob
            or 'search' in lower_blob
        )
        is_empty_result = any(marker in text_blob for marker in ('搜索结果为空', '暂无结果', '暂无数据', '没有找到'))
        has_keyboard = self._xml_has_soft_keyboard(xml)
        if is_search_page and (is_empty_result or has_keyboard):
            return 'search_empty_or_keyboard_escape'
        return ''

    def _xml_text_blob(self, xml: str) -> str:
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            return ''
        values: list[str] = []
        for node in root.iter('node'):
            attrs = node.attrib
            for key in ('text', 'content-desc', 'resource-id', 'class'):
                value = clean_display_label(attrs.get(key, ''))
                if value:
                    values.append(value)
        return ' '.join(values[:260])

    def _xml_has_soft_keyboard(self, xml: str) -> bool:
        text = self._xml_text_blob(xml).lower()
        keyboard_markers = (
            'inputmethod',
            'latinime',
            'keyboard',
            'com.google.android.inputmethod',
            'com.sohu.inputmethod',
            'com.baidu.input',
            '讯飞输入法',
            '搜狗输入法',
            '键盘',
        )
        return any(marker.lower() in text for marker in keyboard_markers)

    def _should_escape_empty_page(self, state: dict) -> bool:
        signature = state.get('semantic_signature') or state.get('signature') or ''
        if not signature:
            return False
        return self.no_candidate_signature == signature and self.no_candidate_swipe_count >= 1

    def _update_empty_page_escape_state(
        self,
        before: dict,
        action_type: str,
        target_data: dict,
        changed: bool,
    ) -> None:
        raw = target_data.get('raw') or {}
        reason = raw.get('reason')
        signature = before.get('semantic_signature') or before.get('signature') or ''
        if action_type == 'swipe' and reason == 'no_clickable_candidate':
            if changed:
                self.no_candidate_signature = ''
                self.no_candidate_swipe_count = 0
                return
            if self.no_candidate_signature == signature:
                self.no_candidate_swipe_count += 1
            else:
                self.no_candidate_signature = signature
                self.no_candidate_swipe_count = 1
            return
        if action_type == 'back' and reason == 'empty_page_escape':
            self.no_candidate_signature = ''
            self.no_candidate_swipe_count = 0
            return
        if changed:
            self.no_candidate_signature = ''
            self.no_candidate_swipe_count = 0

    def _update_exploration_progress_state(
        self,
        action_type: str,
        target_data: dict,
        semantic_changed: bool,
        new_semantic_page: bool,
        after_semantic_signature: str,
    ) -> None:
        raw = target_data.get('raw') or {}
        reason = raw.get('reason')
        if new_semantic_page:
            self.stagnant_action_count = 0
            self.low_value_action_count = 0
            self.repeated_semantic_hit_count = 0
            return

        if after_semantic_signature and after_semantic_signature in self.visited_semantic_pages:
            self.repeated_semantic_hit_count += 1
        else:
            self.repeated_semantic_hit_count = 0

        is_low_value_action = (
            reason in {'no_clickable_candidate', 'empty_page_escape'}
            or (action_type == 'tap' and not semantic_changed)
        )
        if is_low_value_action:
            self.low_value_action_count += 1
        elif semantic_changed:
            self.low_value_action_count = 0

        if semantic_changed and action_type != 'back':
            self.stagnant_action_count = 0
        elif action_type in {'tap', 'swipe', 'back'}:
            self.stagnant_action_count += 1

    def _low_value_stop_reason(self, step_index: int) -> str:
        if step_index < min(8, max(self.task.max_steps, 1)):
            return ''
        if self.stagnant_action_count >= 5:
            return '连续多步未发现新的有效页面或状态变化，提前结束探索'
        if self.low_value_action_count >= 6:
            return '连续低价值动作过多，提前结束探索'
        if self.repeated_semantic_hit_count >= 8:
            return '反复回到已探索页面，提前结束探索'
        if self.empty_page_escape_count >= 3 and self.low_value_action_count >= 4:
            return '多次触发空页面返回，提前结束探索'
        if len(self.unresponsive_targets) >= 8 and self.low_value_action_count >= 4:
            return '无响应控件累计过多，提前结束探索'
        return ''

    def _score_candidate(
        self,
        text: str,
        resource_id: str,
        content_desc: str,
        class_name: str,
        width: int,
        height: int,
        screen_width: int,
        screen_height: int,
        risk: dict | None = None,
        x: int | None = None,
        y: int | None = None,
    ) -> tuple[float, list[str], list[str]]:
        score = 0.0
        reasons: list[str] = []
        if text:
            score += 8
            reasons.append('有可读文本 +8')
        if content_desc:
            score += 6
            reasons.append('有 content-desc +6')
        if resource_id:
            score += 4
            reasons.append('有 resource-id +4')
        if any(token in class_name for token in ('Button', 'TextView', 'ImageButton', 'EditText')):
            score += 3
            reasons.append('控件类型可操作 +3')
        area_ratio = (width * height) / max(screen_width * screen_height, 1)
        if area_ratio < 0.12:
            score += 2
            reasons.append('控件面积合理 +2')
        elif area_ratio > 0.5:
            score -= 8
            reasons.append('疑似大容器 -8')
        strategy_boost = self._strategy_boost(text, resource_id, content_desc, class_name)
        if strategy_boost:
            score += strategy_boost
            reasons.append(f'策略加权 {strategy_boost:+g}')
        value_adjustment, value_reasons = self._exploration_value_adjustment(
            text,
            resource_id,
            content_desc,
            class_name,
            width,
            height,
            screen_width,
            screen_height,
            x,
            y,
        )
        if value_adjustment:
            score += value_adjustment
            reasons.extend(value_reasons)
        objective_boost, objective_hits = self._objective_boost(text, resource_id, content_desc, class_name)
        if objective_boost:
            score += objective_boost
            reasons.append(f'探索目标命中 {",".join(objective_hits)} {objective_boost:+g}')
        if risk and risk.get('level') == 'caution':
            score -= 4
            reasons.append(f'谨慎风险：{risk.get("keyword")} -4')
        return score, reasons, objective_hits

    def _exploration_value_adjustment(
        self,
        text: str,
        resource_id: str,
        content_desc: str,
        class_name: str,
        width: int,
        height: int,
        screen_width: int,
        screen_height: int,
        x: int | None,
        y: int | None,
    ) -> tuple[float, list[str]]:
        joined = ' '.join([text, resource_id, content_desc, class_name]).lower()
        class_tail = class_name.split('.')[-1] if class_name else ''
        area_ratio = (width * height) / max(screen_width * screen_height, 1)
        adjustment = 0.0
        reasons: list[str] = []

        if any(keyword in joined for keyword in HIGH_VALUE_CONTROL_KEYWORDS):
            adjustment += 8
            reasons.append('高价值入口/导航/按钮 +8')
        if any(keyword in joined for keyword in LIST_CONTROL_KEYWORDS):
            adjustment += 5
            reasons.append('列表/卡片项 +5')
        if class_tail in {'Button', 'ImageButton', 'CheckedTextView'}:
            adjustment += 5
            reasons.append('按钮类控件 +5')
        elif class_tail == 'TextView' and text:
            adjustment += 3
            reasons.append('可读文本控件 +3')

        if y is not None:
            vertical_ratio = y / max(screen_height, 1)
            if vertical_ratio >= 0.82:
                adjustment += 6
                reasons.append('疑似底部 Tab/主导航 +6')
            elif vertical_ratio <= 0.16:
                adjustment += 2
                reasons.append('疑似顶部入口/导航 +2')

        if any(keyword in joined for keyword in FORM_INPUT_KEYWORDS) or class_tail == 'EditText':
            adjustment -= 10
            reasons.append('表单输入类控件默认降权 -10')
        if str(self.task.strategy or '').lower() == 'smoke' and any(keyword in joined for keyword in ('search', 'searchview', '搜索')):
            adjustment -= 12
            reasons.append('冒烟探索默认避开搜索入口 -12')
        if any(keyword in joined for keyword in LOW_VALUE_CONTROL_KEYWORDS):
            adjustment -= 8
            reasons.append('图片/背景/装饰类控件降权 -8')
        if class_tail in {'ImageView'} and not (text or content_desc):
            adjustment -= 6
            reasons.append('无语义图片控件降权 -6')
        if area_ratio > 0.32 and not (text or content_desc):
            adjustment -= 6
            reasons.append('大面积弱语义区域降权 -6')
        if area_ratio < 0.002 and not text:
            adjustment -= 4
            reasons.append('过小弱语义控件降权 -4')

        if not text and not content_desc and width / max(screen_width, 1) < 0.12:
            adjustment -= 10
            reasons.append('边缘窄弱语义控件降权 -10')

        return adjustment, reasons

    def _objective_boost(self, text: str, resource_id: str, content_desc: str, class_name: str) -> tuple[float, list[str]]:
        if not self.objective_keywords:
            return 0.0, []
        visible_joined = ' '.join([text, content_desc]).lower()
        technical_joined = ' '.join([resource_id, class_name]).lower()
        visible_hits = [keyword for keyword in self.objective_keywords if keyword.lower() in visible_joined]
        technical_hits = [
            keyword
            for keyword in self.objective_keywords
            if keyword.lower() in technical_joined and keyword not in visible_hits
        ]
        hits = [*visible_hits, *technical_hits]
        if not hits:
            return 0.0, []
        boost = min(30.0, 14.0 * len(visible_hits) + 3.0 * len(technical_hits))
        return boost, hits[:5]

    def _strategy_boost(self, text: str, resource_id: str, content_desc: str, class_name: str) -> float:
        strategy = str(self.task.strategy or 'rule_mvp').lower()
        joined = ' '.join([text, resource_id, content_desc, class_name]).lower()
        if strategy == 'smoke':
            if any(keyword in joined for keyword in ('tab', 'home', 'main', '首页', '消息', '我的', '社区', '登录', '确定')):
                return 6
            if any(keyword in class_name for keyword in ('Button', 'TextView')):
                return 2
        if strategy == 'stability':
            if any(keyword in joined for keyword in ('设置', '详情', '更多', '列表', 'item', '入口')):
                return 4
            return 1
        if strategy == 'form':
            if any(keyword in joined for keyword in ('edit', 'input', 'search', 'name', 'title', 'content', 'desc', '输入', '搜索', '名称')):
                return 8
            if any(keyword in joined for keyword in ('提交', '保存', '确定', '下一步', '完成')):
                return 5
        if strategy == 'list':
            if any(keyword in joined for keyword in ('recycler', 'list', 'item', '列表', '更多', '详情')):
                return 6
            if not text and not content_desc:
                return -2
        return 0

    def _is_blacklisted(self, values: list[str]) -> bool:
        return contains_forbidden_risk(values, custom_keywords=self.task.blacklist_keywords or [])

    def _assess_risk(self, values: list[str]) -> dict | None:
        return assess_risk_values(values, custom_keywords=self.task.blacklist_keywords or [])

    def _record_skipped_risk(
        self,
        risk: dict,
        text: str,
        resource_id: str,
        content_desc: str,
        class_name: str,
        bounds: str,
        page_state: dict | None,
    ) -> None:
        item = {
            'level': risk.get('level', 'forbidden'),
            'keyword': risk.get('keyword', ''),
            'group': risk.get('group', ''),
            'reason': risk.get('reason', ''),
            'text': clean_display_label(text),
            'resource_id': resource_id,
            'content_desc': clean_display_label(content_desc),
            'class_name': class_name,
            'bounds': bounds,
            'activity': (page_state or {}).get('activity', ''),
            'page_signature': (page_state or {}).get('signature', ''),
        }
        key = '|'.join([item['keyword'], item['resource_id'], item['text'], item['bounds'], item['page_signature']])
        if any(existing.get('_key') == key for existing in self.skipped_risks):
            return
        item['_key'] = key
        self.skipped_risks.append(item)
        page_signature = item.get('page_signature')
        if page_signature and page_signature in self.page_map:
            self.page_map[page_signature]['skipped_risks'].append({k: v for k, v in item.items() if k != '_key'})

    def _is_container_noise(self, resource_id: str, class_name: str, text: str, content_desc: str, width: int, height: int, screen_width: int, screen_height: int) -> bool:
        tail = resource_id.split('/')[-1].lower() if resource_id else ''
        if tail in {'content', 'drawerlayout', 'root', 'rootview', 'container', 'main', 'layout'}:
            return True
        if any(marker in tail for marker in ('anim', 'guide', 'float', 'decor')) and (
            width / max(screen_width, 1) < 0.12 or 'ImageView' in class_name
        ):
            return True
        area_ratio = (width * height) / max(screen_width * screen_height, 1)
        has_semantic = bool(text or content_desc or resource_id)
        if area_ratio > 0.65 and not has_semantic:
            return True
        if 'Layout' in class_name and area_ratio > 0.45 and not (text or content_desc):
            return True
        return False

    def _detect_issue(self, before: dict, after: dict, action_type: str, candidate: UiCandidate | None, changed: bool) -> tuple[str, str]:
        if self.package_name and after.get('package') and after['package'] != self.package_name:
            return 'app_exit', f'动作后离开被测应用，当前包名：{after["package"]}'
        logcat_issue = self._detect_logcat_issue()
        if logcat_issue:
            return logcat_issue
        screen_issue = self._detect_screen_issue(after)
        if screen_issue:
            return screen_issue
        if action_type == 'tap' and candidate and not changed:
            if self.no_change_count >= 2:
                return 'no_response', '连续点击后页面无明显变化，疑似控件无响应或命中错误'
        if not after.get('xml'):
            return 'ui_dump_failed', '动作后未获取到有效 UI 层级，可能是页面异常或系统限制'
        return '', ''

    def _detect_logcat_issue(self) -> tuple[str, str] | None:
        logcat_text = self._read_recent_logcat()
        if not logcat_text:
            return None
        issue = self._extract_relevant_logcat_issue(logcat_text)
        if not issue:
            return None
        issue_key = hashlib.sha1(
            f'{issue["type"]}:{self.package_name}:{issue["excerpt"]}'.encode('utf-8', errors='ignore')
        ).hexdigest()
        if issue_key in self.reported_logcat_issue_keys:
            return None
        self.reported_logcat_issue_keys.add(issue_key)
        if issue['type'] == 'crash':
            return 'crash', f'logcat 检测到被测包崩溃关键日志：{issue["marker"]}'
        if issue['type'] == 'anr':
            return 'anr', f'logcat 检测到被测包 ANR 关键日志：{issue["marker"]}'
        return None

    def _extract_relevant_logcat_issue(self, logcat_text: str) -> dict | None:
        lines = logcat_text.splitlines()
        markers = [
            ('crash', 'FATAL EXCEPTION'),
            ('crash', 'SIGSEGV'),
            ('crash', 'SIGABRT'),
            ('crash', 'signal 11'),
            ('crash', 'signal 6'),
            ('anr', 'ANR in'),
            ('anr', 'Input dispatching timed out'),
        ]
        package_name = str(self.package_name or '').strip()
        for idx, line in enumerate(lines):
            for issue_type, marker in markers:
                if marker.lower() not in line.lower():
                    continue
                start = max(0, idx - 20)
                end = min(len(lines), idx + 36)
                block = '\n'.join(lines[start:end])
                if not self._is_relevant_fatal_block(issue_type, marker, block, package_name):
                    continue
                return {
                    'type': issue_type,
                    'marker': marker,
                    'excerpt': self._filter_logcat_excerpt(block),
                }
        return None

    def _is_relevant_fatal_block(self, issue_type: str, marker: str, block: str, package_name: str) -> bool:
        if not package_name:
            return False
        lower_block = block.lower()
        lower_package = package_name.lower()
        if issue_type == 'anr':
            return f'anr in {lower_package}' in lower_block or f'package {lower_package}' in lower_block
        if marker == 'FATAL EXCEPTION':
            return (
                f'process: {lower_package}' in lower_block
                or f'pid: ' in lower_block and lower_package in lower_block
            )
        if marker in ('SIGSEGV', 'SIGABRT', 'signal 11', 'signal 6'):
            return lower_package in lower_block and (
                'fatal signal' in lower_block
                or 'pid:' in lower_block
                or '>>> ' in lower_block
            )
        return False

    def _detect_screen_issue(self, state: dict) -> tuple[str, str] | None:
        xml = state.get('xml') or ''
        lower_xml = xml.lower()
        if any(keyword in xml for keyword in ('网络异常', '网络错误', '加载失败', '请求失败', '服务器异常', '重试')):
            return 'network_error', '页面出现网络或加载异常文案'
        if any(keyword in xml for keyword in ('允许', '权限', '始终允许', '仅使用期间允许')):
            package_name = state.get('package') or ''
            if package_name and package_name != self.package_name:
                return 'system_dialog', '检测到系统权限弹窗或系统级阻塞'
        if not xml or len(xml) < 120:
            return 'blank_or_black_screen', 'UI 层级过少，疑似白屏、黑屏或页面未渲染'
        if 'package="android"' in lower_xml and self.package_name and state.get('package') != self.package_name:
            return 'system_dialog', '检测到系统弹窗或外部系统页面'
        return None

    def _create_stop_step(self, step_index: int, message: str) -> None:
        AppExplorationStep.objects.create(
            task=self.task,
            run=self.execution_run,
            step_index=step_index,
            action_type='stop',
            action_label=message,
            issue_type='',
            issue_message='',
        )

    def _tap(self, x: int, y: int) -> None:
        self._run_adb(['shell', 'input', 'tap', str(x), str(y)], timeout=8)

    def _swipe(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self._run_adb(['shell', 'input', 'swipe', str(x1), str(y1), str(x2), str(y2), '450'], timeout=10)

    def _press_back(self) -> None:
        self._run_adb(['shell', 'input', 'keyevent', '4'], timeout=8, check=False)
        time.sleep(0.6)

    def _read_logcat_excerpt(self) -> str:
        text = self._read_recent_logcat()
        return self._filter_logcat_excerpt(text)

    def _read_recent_logcat(self) -> str:
        result = self._run_adb(['shell', 'logcat', '-d', '-t', '240'], timeout=12, check=False)
        return result.stdout.decode('utf-8', errors='ignore') if result.stdout else ''

    def _filter_logcat_excerpt(self, text: str) -> str:
        if not text:
            return ''
        keywords = ('FATAL EXCEPTION', 'ANR in', 'SIGSEGV', 'SIGABRT', 'fatal signal', 'Process:', 'pid:')
        lines = [line for line in text.splitlines() if any(keyword in line for keyword in keywords)]
        return '\n'.join(lines[-30:])

    def _register_page(self, state: dict, step_index: int) -> None:
        signature = state.get('signature') or ''
        if not signature:
            return
        if signature not in self.page_map:
            self.page_map[signature] = {
                'signature': signature,
                'title': self._infer_page_title(state),
                'activity': state.get('activity', ''),
                'package': state.get('package', ''),
                'first_step': step_index,
                'last_step': step_index,
                'step_count': 0,
                'screenshot': state.get('screenshot', ''),
                'screen_size': list(state.get('screen_size') or []),
                'clicked_controls': [],
                'skipped_risks': [],
                'next_pages': [],
                'issues': [],
            }
        self.page_map[signature]['last_step'] = step_index
        self.page_map[signature]['step_count'] += 1

    def _infer_page_title(self, state: dict) -> str:
        activity = state.get('activity') or ''
        xml = state.get('xml') or ''
        text_candidates = self._extract_page_text_candidates(xml)
        if text_candidates:
            return text_candidates[0]
        if activity:
            tail = activity.split('.')[-1].split('$')[-1]
            return tail or activity
        package_name = state.get('package') or ''
        if package_name:
            return package_name.split('.')[-1]
        return '未知页面'

    def _extract_page_text_candidates(self, xml: str) -> list[str]:
        if not xml:
            return []
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            return []
        candidates = []
        for node in root.iter('node'):
            attrs = node.attrib
            text = clean_display_label(attrs.get('text', '')) or clean_display_label(attrs.get('content-desc', ''))
            if not text or len(text) > 24:
                continue
            class_name = str(attrs.get('class') or '').lower()
            resource_id = str(attrs.get('resource-id') or '').lower()
            hint = clean_display_label(attrs.get('hint', ''))
            if 'edittext' in class_name or 'search' in resource_id or hint:
                continue
            if any(marker in text for marker in ('搜索', '请输入', '输入', '名称/ID')):
                continue
            bounds = self._parse_bounds(attrs.get('bounds', ''))
            if not bounds:
                continue
            x1, y1, x2, y2 = bounds
            if y1 > 360:
                continue
            if x2 - x1 < 12 or y2 - y1 < 8:
                continue
            if text not in candidates:
                candidates.append(text)
            if len(candidates) >= 5:
                break
        return candidates

    def _record_page_transition(self, before: dict, after: dict, step_index: int, action_label: str, target_data: dict, issue_type: str) -> None:
        before_signature = before.get('signature') or ''
        after_signature = after.get('signature') or ''
        page = self.page_map.get(before_signature)
        if not page:
            return
        control = {
            'step_index': step_index,
            'action': action_label,
            'text': target_data.get('target_text', ''),
            'resource_id': target_data.get('target_resource_id', ''),
            'class_name': target_data.get('target_class', ''),
            'bounds': target_data.get('bounds', ''),
            'x': target_data.get('x'),
            'y': target_data.get('y'),
            'raw': target_data.get('raw') or {},
            'objective_hits': (target_data.get('raw') or {}).get('objective_hits', []),
        }
        page['clicked_controls'].append(control)
        if after_signature and after_signature != before_signature and after_signature not in page['next_pages']:
            page['next_pages'].append(after_signature)
        if issue_type:
            page['issues'].append({
                'step_index': step_index,
                'issue_type': issue_type,
                'issue_message': self._issue_message(issue_type),
            })

    def _issue_message(self, issue_type: str) -> str:
        return {
            'app_exit': '动作后离开被测应用',
            'no_response': '连续点击后页面无明显变化',
            'ui_dump_failed': '未获取到有效 UI 层级',
            'crash': '检测到被测包崩溃日志',
            'anr': '检测到被测包 ANR 日志',
            'network_error': '页面出现网络或加载异常文案',
            'system_dialog': '检测到系统弹窗或权限弹窗',
            'blank_or_black_screen': '疑似白屏、黑屏或页面未渲染',
        }.get(issue_type, issue_type or '未知问题')

    def _page_signature(self, focus: dict, xml: str) -> str:
        seed = f'{focus.get("package_name", "")}/{focus.get("activity", "")}\n{xml or ""}'
        return hashlib.sha1(seed.encode('utf-8', errors='ignore')).hexdigest()

    def _semantic_page_signature(self, focus: dict, xml: str) -> str:
        tokens = [
            focus.get('package_name', ''),
            focus.get('activity', ''),
        ]
        if xml:
            try:
                root = ET.fromstring(xml)
            except ET.ParseError:
                root = None
            if root is not None:
                for node in root.iter('node'):
                    attrs = node.attrib
                    text = clean_display_label(attrs.get('text', ''))
                    content_desc = clean_display_label(attrs.get('content-desc', ''))
                    resource_id = attrs.get('resource-id', '').strip()
                    class_name = attrs.get('class', '').strip()
                    resource_tail = resource_id.split('/')[-1] if resource_id else ''
                    class_tail = class_name.split('.')[-1] if class_name else ''
                    state_bits = [
                        f'{key}={attrs.get(key)}'
                        for key in ('checked', 'selected')
                        if attrs.get(key) in {'true', 'false'}
                    ]
                    token = '|'.join(item for item in [text, content_desc, resource_tail, class_tail, *state_bits] if item)
                    if token:
                        tokens.append(token)
        seed = '\n'.join(tokens[:240])
        return hashlib.sha1(seed.encode('utf-8', errors='ignore')).hexdigest()

    def _parse_bounds(self, bounds: str) -> tuple[int, int, int, int] | None:
        match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds or '')
        if not match:
            return None
        return tuple(int(item) for item in match.groups())

    def _relative_media_path(self, path: str) -> str:
        return os.path.relpath(path, settings.MEDIA_ROOT).replace('\\', '/')

    def _run_adb(self, args: list[str], timeout: int = 15, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self.adb_path, '-s', self.device_id, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=check,
            timeout=timeout,
        )

    def _build_summary(self, issues: list[dict]) -> dict:
        step_queryset = self.task.steps.filter(run=self.execution_run) if self.execution_run else self.task.steps.filter(run__isnull=True)
        steps = list(step_queryset.order_by('step_index').values('step_index', 'action_type', 'action_label', 'changed', 'issue_type'))
        issue_type_counts: dict[str, int] = {}
        for issue in issues:
            issue_type = issue.get('issue_type') or 'unknown'
            issue_type_counts[issue_type] = issue_type_counts.get(issue_type, 0) + 1
        objective_uncovered = [
            keyword
            for keyword in self.objective_keywords
            if self.target_keyword_hits.get(keyword, 0) <= 0
        ]
        objective_total = len(self.objective_keywords)
        objective_covered = max(0, objective_total - len(objective_uncovered))
        objective_coverage_rate = round(objective_covered / objective_total * 100, 2) if objective_total else 100.0
        quality_warnings = []
        if objective_total and objective_coverage_rate < 50:
            quality_warnings.append('探索目标覆盖率不足，任务未充分遍历目标控件')
        if self.off_course_escape_count:
            quality_warnings.append('执行过程中出现偏航页面，已自动返回锚点页')
        exploration_success = not issues and objective_coverage_rate >= 50
        return {
            'strategy': self.task.strategy or 'rule_mvp',
            'current_stage': self.current_stage,
            'explored_pages': len(self.visited_pages),
            'explored_semantic_pages': len(self.visited_semantic_pages),
            'issue_count': len(issues),
            'issues': issues,
            'issue_type_counts': issue_type_counts,
            'objective_keywords': self.objective_keywords,
            'objective_hits': self.target_keyword_hits,
            'objective_uncovered': objective_uncovered,
            'objective_total': objective_total,
            'objective_covered': objective_covered,
            'objective_coverage_rate': objective_coverage_rate,
            'quality_warnings': quality_warnings,
            'exploration_success': exploration_success,
            'empty_page_escape_count': self.empty_page_escape_count,
            'unresponsive_target_count': len(self.unresponsive_targets),
            'stagnant_action_count': self.stagnant_action_count,
            'low_value_action_count': self.low_value_action_count,
            'repeated_semantic_hit_count': self.repeated_semantic_hit_count,
            'trap_page_escape_count': self.trap_page_escape_count,
            'off_course_escape_count': self.off_course_escape_count,
            'anchor_return_count': self.anchor_return_count,
            'shallow_entry_probe_count': self.shallow_entry_probe_count,
            'exploration_stop_reason': self.exploration_stop_reason,
            'risk_skipped_count': len(self.skipped_risks),
            'skipped_risks': [
                {key: value for key, value in item.items() if key != '_key'}
                for item in self.skipped_risks[:80]
            ],
            'page_map': list(self.page_map.values())[:80],
            'entry_navigation': self.entry_navigation_trace,
            'entry_failed_keywords': [
                item.get('keyword')
                for item in self.entry_navigation_trace
                if item.get('status') != 'matched' and item.get('keyword')
            ],
            'path_draft': [
                {
                    'step': item['step_index'],
                    'action': item['action_label'],
                    'changed': item['changed'],
                }
                for item in steps
                if item['action_type'] in ('tap', 'swipe', 'back')
            ],
            'next_stage': '当前 AI 主要用于报告分析、复核建议和下一轮探索草稿生成；执行仍由受控规则完成。',
        }


class TargetInspectionRunner(RuleExplorationRunner):
    """Controlled target-list inspection runner.

    It only operates configured targets. Misses are recorded as not_found so the
    report reflects real coverage instead of wandering into unrelated pages.
    """

    def _prepare_device(self) -> None:
        self._run_adb(['shell', 'logcat', '-c'], timeout=8, check=False)
        source_summary = self.task.source_summary if isinstance(self.task.source_summary, dict) else {}
        force_launch = bool(source_summary.get('force_launch_app'))
        focus = self._get_focus()
        app_in_foreground = bool(self.package_name and focus.get('package_name') == self.package_name)
        if self.package_name and (force_launch or not app_in_foreground):
            self._run_adb(
                ['shell', 'monkey', '-p', self.package_name, '-c', 'android.intent.category.LAUNCHER', '1'],
                timeout=15,
                check=False,
            )
            time.sleep(1.5)

    def _inspection_target_specs(self) -> list[dict[str, Any]]:
        """Normalize legacy keyword targets and page-map structured targets."""
        source_summary = self.task.source_summary if isinstance(self.task.source_summary, dict) else {}
        raw_targets: list[Any] = []
        for key in ('targets', 'page_map_targets'):
            if isinstance(source_summary.get(key), list):
                raw_targets.extend(source_summary.get(key) or [])
        if isinstance(source_summary.get('target_list'), list):
            raw_targets.extend(source_summary.get('target_list') or [])
        raw_targets.extend(self.task.entry_keywords or [])
        if not raw_targets and self.task.objective:
            raw_targets.extend(re.split(r'[\n,，、;；]+', self.task.objective))

        targets: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        seen_names: set[str] = set()
        for item in raw_targets:
            spec = self._normalize_inspection_target(item)
            if not spec:
                continue
            name_key = str(spec.get('name') or '').strip().lower()
            if name_key and name_key in seen_names:
                continue
            dedupe_key = '|'.join(str(spec.get(key) or '') for key in ('name', 'resource_id', 'text', 'content_desc', 'bounds'))
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            if name_key:
                seen_names.add(name_key)
            targets.append(spec)
            if len(targets) >= 80:
                break
        return targets

    def _inspection_targets(self) -> list[str]:
        return [item['name'] for item in self._inspection_target_specs()]

    def _normalize_inspection_target(self, raw_target: Any) -> dict[str, Any] | None:
        if isinstance(raw_target, dict):
            resource_id = str(raw_target.get('resource_id') or '').strip()
            text = clean_display_label(raw_target.get('text') or '')
            content_desc = clean_display_label(raw_target.get('content_desc') or raw_target.get('content-desc') or '')
            bounds = str(raw_target.get('bounds') or '').strip()
            role = str(raw_target.get('role') or raw_target.get('semantic_role') or raw_target.get('interaction_role') or '').strip()
            name = clean_display_label(
                raw_target.get('target_name')
                or raw_target.get('name')
                or raw_target.get('label')
                or text
                or content_desc
                or (resource_id.split('/')[-1] if resource_id else '')
            )
            element_id = raw_target.get('element_id')
        else:
            resource_id = ''
            text = ''
            content_desc = ''
            bounds = ''
            role = ''
            name = clean_display_label(str(raw_target or ''))
            element_id = None

        values = [name, text, content_desc, resource_id]
        if not any(values) or self._is_blacklisted(values):
            return None
        if not name:
            name = resource_id.split('/')[-1] if resource_id else bounds
        return {
            'name': name,
            'resource_id': resource_id,
            'text': text,
            'content_desc': content_desc,
            'bounds': bounds,
            'role': role,
            'element_id': element_id,
        }

    def run(self) -> dict:
        if not self.device_id:
            raise RuntimeError('探索任务未绑定设备')

        target_specs = self._inspection_target_specs()
        if not target_specs:
            raise RuntimeError('目标巡检模式需要配置目标清单，可在入口关键词中批量填写')
        target_names = [item['name'] for item in target_specs]
        self.current_inspection_targets = target_names
        self.current_inspection_target_specs = target_specs

        self._set_stage('设备检查与 APP 启动中', progress=3)
        self._prepare_device()
        self._set_stage('准备采集 logcat 日志', progress=5)
        self._start_logcat_capture()
        try:
            self._set_stage('执行起始导航动作', progress=10)
            self._run_start_actions()
            anchor_state = self._capture_state(0, 'anchor')
        except Exception:
            self._save_logcat_artifacts()
            raise

        results: list[dict] = []
        issues: list[dict] = []
        max_scrolls = self._inspection_max_scrolls()

        for index, target_spec in enumerate(target_specs, 1):
            target_name = target_spec['name']
            self.task.refresh_from_db(fields=['status'])
            if self.task.status == 'stopped':
                break
            if time.time() - self.started_at > self.task.max_duration:
                self._create_stop_step(index, '达到最大巡检时长，任务停止')
                break

            progress = min(95, 10 + int(index / max(len(target_specs), 1) * 82))
            self._set_stage(f'巡检目标 {index}/{len(target_specs)}：{target_name}', progress=progress)
            result = self._inspect_one_target(index, target_spec, anchor_state, max_scrolls)
            results.append(result)
            if result.get('issue_type'):
                issues.append({
                    'step_index': index,
                    'issue_type': result['issue_type'],
                    'issue_message': result.get('issue_message', ''),
                    'action': f'巡检目标：{target_name}',
                })

            self.task.total_steps = index
            self.task.explored_pages = len(self.visited_pages)
            self.task.issue_count = len(issues)
            self.task.progress = progress
            self.task.summary = self._build_inspection_summary(results, issues, target_specs)
            self.task.save(update_fields=['total_steps', 'explored_pages', 'issue_count', 'progress', 'summary', 'updated_at'])
            if self.execution_run:
                self.execution_run.total_steps = self.task.total_steps
                self.execution_run.explored_pages = self.task.explored_pages
                self.execution_run.issue_count = self.task.issue_count
                self.execution_run.summary = self.task.summary
                self.execution_run.save(update_fields=['total_steps', 'explored_pages', 'issue_count', 'summary', 'updated_at'])

        self._set_stage('生成日志与目标巡检报告', progress=98)
        self._save_logcat_artifacts()
        self.current_stage = '目标巡检完成'
        return self._build_inspection_summary(results, issues, target_specs)

    def _inspection_max_scrolls(self) -> int:
        source_summary = self.task.source_summary or {}
        try:
            return max(0, min(int(source_summary.get('max_scrolls') or 2), 8))
        except (TypeError, ValueError):
            return 2

    def _inspect_one_target(self, step_index: int, target_spec: dict[str, Any], anchor_state: dict, max_scrolls: int) -> dict:
        target = target_spec.get('name') or ''
        risk = self._assess_risk([
            target,
            target_spec.get('text') or '',
            target_spec.get('content_desc') or '',
            target_spec.get('resource_id') or '',
        ])
        if risk and risk.get('level') == 'forbidden':
            self._record_target_result(step_index, target, 'risk_skipped', risk=risk)
            return {'target': target, 'status': 'risk_skipped', 'issue_type': '', 'issue_message': ''}

        candidate = None
        before = None
        scroll_attempts = []
        for attempt in range(max_scrolls + 1):
            before = self._capture_state(step_index, f'before_{attempt + 1}')
            self.visited_pages.add(before['signature'])
            self._register_page(before, step_index)
            candidate = self._find_inspection_candidate(before.get('xml') or '', target_spec)
            if candidate:
                break
            scroll_attempts.append({'attempt': attempt + 1, 'status': 'not_found'})
            if attempt < max_scrolls:
                width, height = before.get('screen_size') or self._get_screen_size()
                self._swipe(width // 2, int(height * 0.78), width // 2, int(height * 0.28))
                time.sleep(0.6)

        if not before:
            before = self._capture_state(step_index, 'before')

        if not candidate:
            step = AppExplorationStep.objects.create(
                task=self.task,
                run=self.execution_run,
                step_index=step_index,
                action_type='wait',
                action_label=f'目标未找到：{target}',
                target_text=target,
                before_activity=before.get('activity', ''),
                after_activity=before.get('activity', ''),
                before_signature=before.get('signature', ''),
                after_signature=before.get('signature', ''),
                changed=False,
                before_screenshot=before.get('screenshot', ''),
                after_screenshot=before.get('screenshot', ''),
                page_source_path=before.get('xml_path', ''),
                issue_type='target_not_found',
                issue_message=f'未在当前页面和有限滑动范围内找到目标：{target}',
                raw={'scroll_attempts': scroll_attempts, 'mode': 'target_inspection'},
            )
            self._record_target_result(
                step_index,
                target,
                'not_found',
                step=step,
                before=before,
                after=before,
                evidence={'scroll_attempts': scroll_attempts},
                error_message=step.issue_message,
            )
            return {
                'target': target,
                'status': 'not_found',
                'issue_type': 'target_not_found',
                'issue_message': step.issue_message,
            }

        self._tap(candidate.x, candidate.y)
        time.sleep(0.9)
        after = self._capture_state(step_index, 'after')
        self.visited_pages.add(after['signature'])
        self._register_page(after, step_index)
        state_change = self._target_state_change(before.get('xml') or '', after.get('xml') or '', candidate)
        state_diagnostics = self._interaction_state_diagnostics(before, after, candidate, state_change)
        changed = bool(state_diagnostics.get('changed'))
        status = 'found_effective' if changed else 'found_unconfirmed'
        issue_type = '' if changed else 'target_state_unconfirmed'
        issue_message = '' if changed else f'已点击目标「{target}」，但页面状态未检测到明显变化'
        target_data = {
            'target_text': candidate.text or target,
            'target_resource_id': candidate.resource_id,
            'target_class': candidate.class_name,
            'bounds': candidate.bounds,
            'x': candidate.x,
            'y': candidate.y,
                'raw': {
                    'mode': 'target_inspection',
                    'target': target,
                    'target_spec': target_spec,
                    'content_desc': candidate.content_desc,
                    'match_reasons': candidate.score_reasons,
                    'scroll_attempts': scroll_attempts,
                    'state_change': state_change,
                    'state_diagnostics': state_diagnostics,
            },
        }
        step = AppExplorationStep.objects.create(
            task=self.task,
            run=self.execution_run,
            step_index=step_index,
            action_type='tap',
            action_label=f'巡检点击：{candidate.label}',
            before_activity=before.get('activity', ''),
            after_activity=after.get('activity', ''),
            before_signature=before.get('signature', ''),
            after_signature=after.get('signature', ''),
            changed=changed,
            before_screenshot=before.get('screenshot', ''),
            after_screenshot=after.get('screenshot', ''),
            page_source_path=before.get('xml_path', ''),
            issue_type=issue_type,
            issue_message=issue_message,
            logcat_excerpt=self._read_logcat_excerpt() if issue_type else '',
            **target_data,
        )
        recovery = self._recover_anchor_if_needed(anchor_state, before, after)
        if recovery.get('status') == 'failed':
            status = 'anchor_recovery_failed'
            issue_type = 'anchor_recovery_failed'
            issue_message = '目标点击后未能恢复到巡检锚点页'

        self._record_target_result(
            step_index,
            target,
            status,
            step=step,
            before=before,
            after=after,
            candidate=candidate,
            evidence={
                'scroll_attempts': scroll_attempts,
                'recovery': recovery,
                'state_change': state_change,
                'state_diagnostics': state_diagnostics,
            },
            error_message=issue_message,
        )
        return {
            'target': target,
            'status': status,
            'changed': changed,
            'issue_type': issue_type,
            'issue_message': issue_message,
        }

    def _find_inspection_candidate(self, xml: str, target_spec: dict[str, Any] | str) -> UiCandidate | None:
        if not xml:
            return None
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            return None

        spec = self._normalize_inspection_target(target_spec) if not isinstance(target_spec, dict) else target_spec
        if not spec:
            return None
        target = str(spec.get('name') or '').strip()
        fallback = None
        target_bounds = self._parse_bounds(str(spec.get('bounds') or ''))
        for node in root.iter('node'):
            attrs = node.attrib
            if attrs.get('enabled') == 'false':
                continue
            bounds = attrs.get('bounds', '')
            parsed = self._parse_bounds(bounds)
            if not parsed:
                continue
            text = clean_display_label(attrs.get('text', ''))
            content_desc = clean_display_label(attrs.get('content-desc', ''))
            resource_id = attrs.get('resource-id', '').strip()
            class_name = attrs.get('class', '').strip()
            descendant = ''
            score, reason = self._score_inspection_match(spec, {
                'text': text,
                'content_desc': content_desc,
                'resource_id': resource_id,
                'class_name': class_name,
                'bounds': bounds,
            })
            if score <= 0:
                descendant = self._descendant_label(node)
                score, reason = self._score_inspection_match(spec, {
                    'text': text,
                    'content_desc': content_desc,
                    'resource_id': resource_id,
                    'class_name': class_name,
                    'bounds': bounds,
                    'descendant': descendant,
                })
                if score > 0 and descendant and not text:
                    text = descendant
            if score <= 0 and target_bounds:
                score, reason = self._score_bounds_match(target_bounds, parsed, str(spec.get('role') or ''), class_name)
            if score <= 0:
                continue

            x1, y1, x2, y2 = parsed
            risk = self._assess_risk([text, content_desc, resource_id, class_name])
            if risk and risk.get('level') == 'forbidden':
                continue
            candidate = UiCandidate(
                text=text,
                resource_id=resource_id,
                content_desc=content_desc,
                class_name=class_name,
                bounds=bounds,
                x=(x1 + x2) // 2,
                y=(y1 + y2) // 2,
                width=max(0, x2 - x1),
                height=max(0, y2 - y1),
                score=score,
                objective_hits=[target],
                score_reasons=[reason],
                risk=risk,
            )
            if score >= 110:
                return candidate
            if fallback is None or candidate.score > fallback.score:
                fallback = candidate
        return fallback

    def _interaction_state_diagnostics(
        self,
        before: dict,
        after: dict,
        candidate: UiCandidate,
        target_state_change: dict,
    ) -> dict:
        before_xml = before.get('xml') or ''
        after_xml = after.get('xml') or ''
        before_summary = self._xml_interaction_summary(before_xml)
        after_summary = self._xml_interaction_summary(after_xml)
        reasons = []

        activity_changed = before.get('activity') != after.get('activity')
        semantic_changed = before.get('semantic_signature') != after.get('semantic_signature')
        if activity_changed:
            reasons.append('activity_changed')
        if semantic_changed:
            reasons.append('semantic_page_changed')
        if target_state_change.get('changed'):
            reasons.append('target_state_changed')

        dialog_change = self._dialog_change(before_summary, after_summary)
        if dialog_change.get('changed'):
            reasons.append(dialog_change.get('reason') or 'dialog_changed')

        list_change = self._list_change(before_summary, after_summary)
        if list_change.get('changed'):
            reasons.append(list_change.get('reason') or 'list_changed')

        unique_reasons = []
        for reason in reasons:
            if reason and reason not in unique_reasons:
                unique_reasons.append(reason)

        return {
            'changed': bool(unique_reasons),
            'reasons': unique_reasons,
            'activity_changed': activity_changed,
            'semantic_changed': semantic_changed,
            'target_state_changed': bool(target_state_change.get('changed')),
            'dialog_change': dialog_change,
            'list_change': list_change,
            'candidate_label': candidate.label,
        }

    def _xml_interaction_summary(self, xml: str) -> dict:
        summary = {
            'node_count': 0,
            'visible_text_count': 0,
            'list_container_count': 0,
            'list_item_count': 0,
            'dialog_signature': '',
            'modal_actions': [],
        }
        if not xml:
            return summary
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            return summary

        modal_actions = []
        for node in root.iter('node'):
            attrs = node.attrib
            summary['node_count'] += 1
            text = clean_display_label(attrs.get('text', '')) or clean_display_label(attrs.get('content-desc', ''))
            resource_id = attrs.get('resource-id', '').lower()
            class_name = attrs.get('class', '').lower()
            if text:
                summary['visible_text_count'] += 1
            if any(marker in resource_id or marker in class_name for marker in ('recycler', 'listview', 'list', 'adapter')):
                summary['list_container_count'] += 1
            if attrs.get('clickable') == 'true' and any(marker in resource_id or marker in class_name for marker in ('item', 'cell', 'card')):
                summary['list_item_count'] += 1
            if text in {'取消', '确定', '确认', '继续', '关闭'} and text not in modal_actions:
                modal_actions.append(text)

        summary['modal_actions'] = modal_actions
        if '取消' in modal_actions and any(item in modal_actions for item in ('确定', '确认', '继续')):
            summary['dialog_signature'] = '|'.join(sorted(modal_actions))
        return summary

    def _dialog_change(self, before_summary: dict, after_summary: dict) -> dict:
        before_signature = before_summary.get('dialog_signature') or ''
        after_signature = after_summary.get('dialog_signature') or ''
        if before_signature != after_signature:
            return {
                'changed': True,
                'reason': 'dialog_opened' if after_signature else 'dialog_closed',
                'before': before_signature,
                'after': after_signature,
            }
        return {'changed': False, 'reason': 'dialog_unchanged', 'before': before_signature, 'after': after_signature}

    def _list_change(self, before_summary: dict, after_summary: dict) -> dict:
        before_count = int(before_summary.get('list_item_count') or before_summary.get('visible_text_count') or 0)
        after_count = int(after_summary.get('list_item_count') or after_summary.get('visible_text_count') or 0)
        if before_count != after_count and (
            before_summary.get('list_container_count') or after_summary.get('list_container_count')
        ):
            return {
                'changed': True,
                'reason': 'list_content_changed',
                'before_count': before_count,
                'after_count': after_count,
            }
        return {'changed': False, 'reason': 'list_unchanged', 'before_count': before_count, 'after_count': after_count}

    def _target_state_change(self, before_xml: str, after_xml: str, candidate: UiCandidate) -> dict:
        before_state = self._candidate_state_snapshot(before_xml, candidate)
        after_state = self._candidate_state_snapshot(after_xml, candidate)
        if not before_state or not after_state:
            return {'changed': False, 'reason': 'target_state_node_not_found'}

        changes = []
        for key in ('checked', 'selected', 'enabled', 'text', 'content_desc'):
            before_value = before_state.get(key, '')
            after_value = after_state.get(key, '')
            if before_value != after_value:
                changes.append({
                    'field': key,
                    'before': before_value,
                    'after': after_value,
                })

        return {
            'changed': bool(changes),
            'reason': 'target_state_changed' if changes else 'target_state_unchanged',
            'changes': changes,
            'before': before_state,
            'after': after_state,
        }

    def _candidate_state_snapshot(self, xml: str, candidate: UiCandidate) -> dict:
        node = self._find_candidate_state_node(xml, candidate)
        if node is None:
            return {}
        attrs = node.attrib
        return {
            'text': clean_display_label(attrs.get('text', '')),
            'content_desc': clean_display_label(attrs.get('content-desc', '')),
            'resource_id': attrs.get('resource-id', '').strip(),
            'class_name': attrs.get('class', '').strip(),
            'bounds': attrs.get('bounds', '').strip(),
            'checked': attrs.get('checked', ''),
            'selected': attrs.get('selected', ''),
            'enabled': attrs.get('enabled', ''),
        }

    def _find_candidate_state_node(self, xml: str, candidate: UiCandidate) -> ET.Element | None:
        if not xml:
            return None
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            return None

        candidate_bounds = self._parse_bounds(candidate.bounds)
        candidate_center = (candidate.x, candidate.y)
        matches: list[tuple[int, int, ET.Element]] = []
        for node in root.iter('node'):
            attrs = node.attrib
            bounds = attrs.get('bounds', '')
            parsed = self._parse_bounds(bounds)
            if not parsed:
                continue
            x1, y1, x2, y2 = parsed
            area = max(1, (x2 - x1) * (y2 - y1))
            score = 0
            if candidate.resource_id and attrs.get('resource-id', '').strip() == candidate.resource_id:
                score += 100
            if candidate.bounds and bounds == candidate.bounds:
                score += 80
            if candidate.text and clean_display_label(attrs.get('text', '')) == clean_display_label(candidate.text):
                score += 45
            if candidate.content_desc and clean_display_label(attrs.get('content-desc', '')) == clean_display_label(candidate.content_desc):
                score += 45
            if candidate_bounds:
                bounds_score, _ = self._score_bounds_match(candidate_bounds, parsed, '', attrs.get('class', ''))
                if bounds_score:
                    score += int(bounds_score)
            if x1 <= candidate_center[0] <= x2 and y1 <= candidate_center[1] <= y2:
                score += 20
            if score > 0:
                matches.append((score, area, node))
        if not matches:
            return None
        matches.sort(key=lambda item: (-item[0], item[1]))
        return matches[0][2]

    def _score_inspection_match(self, target_spec: dict[str, Any], candidate: dict[str, str]) -> tuple[float, str]:
        target_name = clean_display_label(target_spec.get('name') or '')
        target_text = clean_display_label(target_spec.get('text') or '')
        target_desc = clean_display_label(target_spec.get('content_desc') or '')
        target_resource_id = str(target_spec.get('resource_id') or '').strip()
        target_resource_tail = target_resource_id.split('/')[-1] if target_resource_id else ''

        text = clean_display_label(candidate.get('text') or '')
        content_desc = clean_display_label(candidate.get('content_desc') or '')
        descendant = clean_display_label(candidate.get('descendant') or '')
        resource_id = str(candidate.get('resource_id') or '').strip()
        resource_tail = resource_id.split('/')[-1] if resource_id else ''

        if target_resource_id and resource_id:
            if resource_id == target_resource_id:
                return 125, 'resource-id 完全匹配'
            if resource_tail and resource_tail == target_resource_tail:
                return 116, 'resource-id 尾部匹配'
            if target_resource_tail and target_resource_tail.lower() in resource_id.lower():
                return 96, 'resource-id 包含目标尾部'

        exact_pairs = [
            (target_text, text, 'text 精确匹配'),
            (target_text, descendant, '子节点文本精确匹配'),
            (target_desc, content_desc, 'content-desc 精确匹配'),
            (target_name, text, '目标名与文本精确匹配'),
            (target_name, content_desc, '目标名与描述精确匹配'),
            (target_name, descendant, '目标名与子节点文本精确匹配'),
        ]
        for expected, actual, reason in exact_pairs:
            if expected and actual and expected == actual:
                return 108, reason

        fuzzy_pairs = [
            (target_text, text, 'text 包含匹配'),
            (target_text, descendant, '子节点文本包含匹配'),
            (target_desc, content_desc, 'content-desc 包含匹配'),
            (target_name, text, '目标名与文本包含匹配'),
            (target_name, content_desc, '目标名与描述包含匹配'),
            (target_name, descendant, '目标名与子节点文本包含匹配'),
        ]
        for expected, actual, reason in fuzzy_pairs:
            if expected and actual and (expected.lower() in actual.lower() or actual.lower() in expected.lower()):
                return 82, reason

        return 0, ''

    def _score_bounds_match(
        self,
        target_bounds: tuple[int, int, int, int],
        candidate_bounds: tuple[int, int, int, int],
        target_role: str,
        class_name: str,
    ) -> tuple[float, str]:
        tx1, ty1, tx2, ty2 = target_bounds
        cx1, cy1, cx2, cy2 = candidate_bounds
        target_area = max(1, (tx2 - tx1) * (ty2 - ty1))
        candidate_area = max(1, (cx2 - cx1) * (cy2 - cy1))
        area_ratio = candidate_area / target_area
        role_text = (target_role or '').lower()
        max_area_ratio = 14 if any(marker in role_text for marker in ('list', 'container', 'card', 'item')) else 7
        if area_ratio > max_area_ratio:
            return 0, ''
        ix1, iy1 = max(tx1, cx1), max(ty1, cy1)
        ix2, iy2 = min(tx2, cx2), min(ty2, cy2)
        overlap = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        overlap_ratio = overlap / max(1, min(target_area, candidate_area))
        target_center = ((tx1 + tx2) // 2, (ty1 + ty2) // 2)
        candidate_center = ((cx1 + cx2) // 2, (cy1 + cy2) // 2)
        distance = ((target_center[0] - candidate_center[0]) ** 2 + (target_center[1] - candidate_center[1]) ** 2) ** 0.5
        target_diagonal = max(24, ((tx2 - tx1) ** 2 + (ty2 - ty1) ** 2) ** 0.5)
        role_boost = 8 if target_role and target_role.lower() in class_name.lower() else 0
        if overlap_ratio >= 0.65:
            return 72 + role_boost, 'bounds 高重叠兜底匹配'
        if overlap_ratio >= 0.35:
            return 60 + role_boost, 'bounds 部分重叠兜底匹配'
        if distance <= max(36, target_diagonal * 0.35):
            return 52 + role_boost, 'bounds 中心点接近兜底匹配'
        return 0, ''

    def _recover_anchor_if_needed(self, anchor_state: dict, before: dict, after: dict) -> dict:
        if before.get('semantic_signature') == after.get('semantic_signature') and before.get('activity') == after.get('activity'):
            return {'status': 'not_needed'}
        if before.get('package') == after.get('package') and before.get('activity') == after.get('activity'):
            visible_target_count = self._visible_inspection_target_count(after.get('xml') or '')
            if visible_target_count >= 2:
                return {'status': 'not_needed_same_activity', 'visible_target_count': visible_target_count}
        anchor_signature = anchor_state.get('semantic_signature') or anchor_state.get('signature')
        for attempt in range(1, 4):
            self._press_back()
            current = self._capture_state(0, f'recover_{attempt}')
            current_signature = current.get('semantic_signature') or current.get('signature')
            if current_signature == anchor_signature:
                return {'status': 'recovered', 'attempts': attempt}
            if self._visible_inspection_target_count(current.get('xml') or '') >= 2:
                return {'status': 'recovered_by_targets', 'attempts': attempt}
        relaunch_result = self._recover_anchor_by_relaunch(anchor_state)
        if relaunch_result.get('status') != 'failed':
            relaunch_result['back_attempts'] = 3
            return relaunch_result
        return {'status': 'failed', 'attempts': 3, 'relaunch': relaunch_result}

    def _recover_anchor_by_relaunch(self, anchor_state: dict) -> dict:
        if not self.package_name:
            return {'status': 'failed', 'reason': 'missing_package_name'}
        anchor_signature = anchor_state.get('semantic_signature') or anchor_state.get('signature')
        try:
            self._set_stage('返回锚点失败，重启 APP 并重放起始导航', progress=92)
            self._run_adb(['shell', 'am', 'force-stop', self.package_name], timeout=8, check=False)
            time.sleep(0.6)
            self._run_adb(
                ['shell', 'monkey', '-p', self.package_name, '-c', 'android.intent.category.LAUNCHER', '1'],
                timeout=15,
                check=False,
            )
            time.sleep(1.5)
            self._run_start_actions()
            current = self._capture_state(0, 'recover_relaunch')
            current_signature = current.get('semantic_signature') or current.get('signature')
            visible_target_count = self._visible_inspection_target_count(current.get('xml') or '')
            if current_signature == anchor_signature:
                return {'status': 'recovered_by_relaunch', 'visible_target_count': visible_target_count}
            if visible_target_count >= 2:
                return {'status': 'recovered_by_relaunch_targets', 'visible_target_count': visible_target_count}
            return {
                'status': 'failed',
                'reason': 'anchor_not_verified_after_relaunch',
                'visible_target_count': visible_target_count,
            }
        except Exception as exc:
            return {'status': 'failed', 'reason': str(exc)}

    def _visible_inspection_target_count(self, xml: str) -> int:
        target_specs = getattr(self, 'current_inspection_target_specs', None) or []
        if not target_specs:
            target_specs = [{'name': target} for target in (getattr(self, 'current_inspection_targets', []) or [])]
        if not xml or not target_specs:
            return 0
        text = xml.lower()
        count = 0
        for spec in target_specs:
            needles = self._inspection_target_needles(spec)
            if any(needle and needle.lower() in text for needle in needles):
                count += 1
        return count

    def _inspection_target_needles(self, target_spec: dict[str, Any] | str) -> list[str]:
        spec = self._normalize_inspection_target(target_spec) if not isinstance(target_spec, dict) else target_spec
        if not spec:
            return []
        resource_id = str(spec.get('resource_id') or '').strip()
        values = [
            spec.get('name') or '',
            spec.get('text') or '',
            spec.get('content_desc') or '',
            resource_id,
            resource_id.split('/')[-1] if resource_id else '',
        ]
        needles: list[str] = []
        for value in values:
            needle = clean_display_label(str(value or '')).strip()
            if needle and needle not in needles:
                needles.append(needle)
        return needles

    def _record_target_result(
        self,
        step_index: int,
        target: str,
        status: str,
        step: AppExplorationStep | None = None,
        before: dict | None = None,
        after: dict | None = None,
        candidate: UiCandidate | None = None,
        evidence: dict | None = None,
        risk: dict | None = None,
        error_message: str = '',
    ) -> None:
        if not self.execution_run:
            return
        evidence_payload = dict(evidence or {})
        if candidate:
            evidence_payload.update({
                'match_reasons': candidate.score_reasons,
                'match_score': candidate.score,
                'candidate_label': candidate.label,
                'candidate_resource_id': candidate.resource_id,
                'candidate_text': candidate.text,
                'candidate_content_desc': candidate.content_desc,
                'candidate_class': candidate.class_name,
            })
        AppInspectionTargetResult.objects.create(
            task=self.task,
            run=self.execution_run,
            step=step,
            target_name=target,
            status=status,
            action_type='tap' if candidate else 'wait',
            bounds=candidate.bounds if candidate else '',
            x=candidate.x if candidate else None,
            y=candidate.y if candidate else None,
            before_activity=(before or {}).get('activity', ''),
            after_activity=(after or {}).get('activity', ''),
            before_signature=(before or {}).get('signature', ''),
            after_signature=(after or {}).get('signature', ''),
            changed=bool(step.changed) if step else False,
            before_screenshot=(before or {}).get('screenshot', ''),
            after_screenshot=(after or {}).get('screenshot', ''),
            evidence=evidence_payload,
            risk=risk or {},
            error_message=error_message,
        )

    def _build_inspection_summary(self, results: list[dict], issues: list[dict], targets: list[dict[str, Any]] | list[str]) -> dict:
        target_names = [
            item.get('name') if isinstance(item, dict) else str(item or '')
            for item in targets
        ]
        target_specs = [
            item for item in targets
            if isinstance(item, dict)
        ]
        status_counts: dict[str, int] = {}
        for item in results:
            status = item.get('status') or 'unknown'
            status_counts[status] = status_counts.get(status, 0) + 1
        covered = status_counts.get('found_effective', 0) + status_counts.get('found_unconfirmed', 0)
        target_total = len(target_names)
        coverage_rate = round(covered / target_total * 100, 2) if target_total else 0
        return {
            'strategy': 'target_inspection',
            'current_stage': self.current_stage,
            'target_total': target_total,
            'target_covered': covered,
            'target_coverage_rate': coverage_rate,
            'target_status_counts': status_counts,
            'target_results': results,
            'objective_keywords': target_names,
            'structured_target_count': len([
                item for item in target_specs
                if item.get('resource_id') or item.get('text') or item.get('content_desc') or item.get('bounds')
            ]),
            'target_specs': target_specs[:80],
            'objective_hits': {
                item.get('target'): 1
                for item in results
                if item.get('status') in {'found_effective', 'found_unconfirmed'}
            },
            'objective_uncovered': [
                item.get('target')
                for item in results
                if item.get('status') in {'not_found', 'risk_skipped', 'error'}
            ],
            'explored_pages': len(self.visited_pages),
            'issue_count': len(issues),
            'issues': issues,
            'quality_warnings': [] if not issues else ['目标巡检存在未找到、未确认或锚点恢复失败项'],
            'exploration_success': not issues,
            'page_map': list(self.page_map.values())[:80],
            'next_stage': '目标巡检已按清单执行，未命中目标不会自动点击其它控件。',
        }


def run_rule_exploration(task_id: int, run_id: int | None = None) -> dict:
    task = AppExplorationTask.objects.select_related('device', 'app_package', 'project').get(id=task_id)
    run = AppExplorationRun.objects.filter(id=run_id, task=task).first() if run_id else None
    runner = RuleExplorationRunner(task, run)
    return runner.run()


def run_target_inspection(task_id: int, run_id: int | None = None) -> dict:
    task = AppExplorationTask.objects.select_related('device', 'app_package', 'project').get(id=task_id)
    run = AppExplorationRun.objects.filter(id=run_id, task=task).first() if run_id else None
    runner = TargetInspectionRunner(task, run)
    return runner.run()


def run_app_exploration(task_id: int, run_id: int | None = None) -> dict:
    task = AppExplorationTask.objects.only('id', 'strategy').get(id=task_id)
    if task.strategy == 'target_inspection':
        return run_target_inspection(task_id, run_id)
    return run_rule_exploration(task_id, run_id)
