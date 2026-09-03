# -*- coding: utf-8 -*-
"""Regression tests for controlled APP target inspection."""

from types import SimpleNamespace

from apps.app_automation.utils.exploration_runner import TargetInspectionRunner, UiCandidate


def _runner(
    source_summary=None,
    entry_keywords=None,
    objective='',
    blacklist_keywords=None,
):
    runner = object.__new__(TargetInspectionRunner)
    runner.task = SimpleNamespace(
        source_summary=source_summary or {},
        entry_keywords=entry_keywords or [],
        objective=objective,
        blacklist_keywords=blacklist_keywords or [],
    )
    return runner


def test_inspection_target_specs_normalize_and_dedupe_structured_targets():
    runner = _runner(
        source_summary={
            'targets': [
                {
                    'target_name': '消息 Tab',
                    'text': '消息',
                    'resource_id': 'com.demo:id/tab_message',
                    'bounds': '[360,2100][720,2280]',
                    'role': 'tab',
                },
                {
                    'name': '消息 Tab',
                    'text': '消息',
                    'resource_id': 'com.demo:id/tab_message',
                    'bounds': '[360,2100][720,2280]',
                },
            ],
            'target_list': ['社区', '退出登录'],
        },
        entry_keywords=['我的'],
    )

    specs = runner._inspection_target_specs()

    assert [item['name'] for item in specs] == ['消息 Tab', '社区', '我的']
    assert specs[0]['resource_id'] == 'com.demo:id/tab_message'
    assert specs[0]['role'] == 'tab'


def test_inspection_target_specs_dedupe_structured_targets_against_keyword_names():
    runner = _runner(
        source_summary={
            'targets': [
                {
                    'target_name': '搜索view',
                    'resource_id': 'com.demo:id/searchView',
                    'bounds': '[60,126][864,234]',
                },
                {
                    'target_name': 'more图标',
                    'resource_id': 'com.demo:id/ivMore',
                    'bounds': '[912,126][1020,234]',
                },
            ],
            'target_list': ['搜索view', 'more图标'],
        },
        entry_keywords=['搜索view', 'more图标'],
    )

    specs = runner._inspection_target_specs()

    assert [item['name'] for item in specs] == ['搜索view', 'more图标']
    assert specs[0]['resource_id'] == 'com.demo:id/searchView'
    assert specs[1]['resource_id'] == 'com.demo:id/ivMore'


def test_find_inspection_candidate_prefers_exact_resource_id():
    runner = _runner()
    xml = """
    <hierarchy>
      <node enabled="true" text="消息" resource-id="com.demo:id/random_text" class="android.widget.TextView" bounds="[0,0][100,80]" />
      <node enabled="true" text="" resource-id="com.demo:id/tab_message" class="android.widget.FrameLayout" bounds="[360,2100][720,2280]" />
    </hierarchy>
    """

    candidate = runner._find_inspection_candidate(xml, {
        'name': '消息',
        'resource_id': 'com.demo:id/tab_message',
        'text': '',
        'content_desc': '',
        'bounds': '',
        'role': 'tab',
    })

    assert candidate is not None
    assert candidate.resource_id == 'com.demo:id/tab_message'
    assert candidate.score_reasons == ['resource-id 完全匹配']


def test_find_inspection_candidate_matches_clickable_parent_by_descendant_text():
    runner = _runner()
    xml = """
    <hierarchy>
      <node enabled="true" text="" resource-id="com.demo:id/community_entry" class="android.widget.FrameLayout" bounds="[20,300][1060,460]">
        <node enabled="true" text="社区" resource-id="com.demo:id/title" class="android.widget.TextView" bounds="[60,330][180,390]" />
      </node>
    </hierarchy>
    """

    candidate = runner._find_inspection_candidate(xml, {
        'name': '社区',
        'resource_id': '',
        'text': '',
        'content_desc': '',
        'bounds': '',
        'role': 'entry',
    })

    assert candidate is not None
    assert candidate.resource_id == 'com.demo:id/community_entry'
    assert candidate.score_reasons == ['目标名与子节点文本精确匹配']


def test_bounds_fallback_rejects_full_page_container():
    runner = _runner()
    xml = """
    <hierarchy>
      <node enabled="true" text="" resource-id="android:id/content" class="android.widget.FrameLayout" bounds="[0,0][1080,2400]" />
    </hierarchy>
    """

    candidate = runner._find_inspection_candidate(xml, {
        'name': '消息',
        'resource_id': '',
        'text': '',
        'content_desc': '',
        'bounds': '[360,2100][720,2280]',
        'role': 'tab',
    })

    assert candidate is None


def test_bounds_fallback_keeps_reasonable_same_area_candidate():
    runner = _runner()
    xml = """
    <hierarchy>
      <node enabled="true" text="" resource-id="android:id/content" class="android.widget.FrameLayout" bounds="[0,0][1080,2400]" />
      <node enabled="true" text="" resource-id="com.demo:id/tab_message" class="android.widget.FrameLayout" bounds="[360,2100][720,2280]" />
    </hierarchy>
    """

    candidate = runner._find_inspection_candidate(xml, {
        'name': '消息',
        'resource_id': '',
        'text': '',
        'content_desc': '',
        'bounds': '[360,2100][720,2280]',
        'role': 'tab',
    })

    assert candidate is not None
    assert candidate.resource_id == 'com.demo:id/tab_message'
    assert candidate.score_reasons == ['bounds 高重叠兜底匹配']


def test_build_inspection_summary_reports_target_quality_metrics():
    runner = _runner()
    runner.current_stage = '目标巡检完成'
    runner.visited_pages = {'anchor', 'detail'}
    runner.page_map = {}
    results = [
        {'target': '消息', 'status': 'found_effective'},
        {'target': '社区', 'status': 'found_unconfirmed'},
        {'target': '搜索', 'status': 'not_found'},
    ]
    issues = [{'issue_type': 'target_not_found'}]

    summary = runner._build_inspection_summary(
        results,
        issues,
        [{'name': '消息', 'resource_id': 'id/message'}, {'name': '社区'}, {'name': '搜索'}],
    )

    assert summary['strategy'] == 'target_inspection'
    assert summary['target_total'] == 3
    assert summary['target_covered'] == 2
    assert summary['target_coverage_rate'] == 66.67
    assert summary['structured_target_count'] == 1
    assert summary['objective_uncovered'] == ['搜索']
    assert summary['quality_warnings']


def test_target_state_change_detects_switch_checked_delta():
    runner = _runner()
    candidate = UiCandidate(
        text='',
        resource_id='com.demo:id/notify_switch',
        content_desc='消息通知',
        class_name='android.widget.Switch',
        bounds='[800,300][980,390]',
        x=890,
        y=345,
        width=180,
        height=90,
        score=125,
        objective_hits=['消息通知'],
        score_reasons=['resource-id 完全匹配'],
    )
    before_xml = """
    <hierarchy>
      <node enabled="true" checked="false" selected="false" text="" content-desc="消息通知" resource-id="com.demo:id/notify_switch" class="android.widget.Switch" bounds="[800,300][980,390]" />
    </hierarchy>
    """
    after_xml = """
    <hierarchy>
      <node enabled="true" checked="true" selected="false" text="" content-desc="消息通知" resource-id="com.demo:id/notify_switch" class="android.widget.Switch" bounds="[800,300][980,390]" />
    </hierarchy>
    """

    state_change = runner._target_state_change(before_xml, after_xml, candidate)

    assert state_change['changed'] is True
    assert state_change['changes'] == [{'field': 'checked', 'before': 'false', 'after': 'true'}]


def test_target_state_change_keeps_unchanged_tap_unconfirmed():
    runner = _runner()
    candidate = UiCandidate(
        text='帮助',
        resource_id='com.demo:id/help',
        content_desc='',
        class_name='android.widget.TextView',
        bounds='[30,600][180,680]',
        x=105,
        y=640,
        width=150,
        height=80,
        score=108,
        objective_hits=['帮助'],
        score_reasons=['目标名与文本精确匹配'],
    )
    xml = """
    <hierarchy>
      <node enabled="true" checked="false" selected="false" text="帮助" content-desc="" resource-id="com.demo:id/help" class="android.widget.TextView" bounds="[30,600][180,680]" />
    </hierarchy>
    """

    state_change = runner._target_state_change(xml, xml, candidate)

    assert state_change['changed'] is False
    assert state_change['reason'] == 'target_state_unchanged'
    assert state_change['changes'] == []


def test_interaction_state_diagnostics_detects_dialog_opened():
    runner = _runner()
    candidate = UiCandidate(
        text='退出登录',
        resource_id='com.demo:id/logout',
        content_desc='',
        class_name='android.widget.TextView',
        bounds='[40,500][260,580]',
        x=150,
        y=540,
        width=220,
        height=80,
        score=108,
        objective_hits=['退出登录'],
        score_reasons=['目标名与文本精确匹配'],
    )
    before = {
        'xml': '<hierarchy><node enabled="true" text="退出登录" resource-id="com.demo:id/logout" class="android.widget.TextView" bounds="[40,500][260,580]" /></hierarchy>',
        'activity': '.SettingsActivity',
        'semantic_signature': 'settings',
    }
    after = {
        'xml': """
        <hierarchy>
          <node enabled="true" text="退出登录" resource-id="com.demo:id/logout" class="android.widget.TextView" bounds="[40,500][260,580]" />
          <node enabled="true" text="取消" resource-id="com.demo:id/cancel" class="android.widget.Button" bounds="[150,1400][420,1500]" />
          <node enabled="true" text="确定" resource-id="com.demo:id/confirm" class="android.widget.Button" bounds="[660,1400][930,1500]" />
        </hierarchy>
        """,
        'activity': '.SettingsActivity',
        'semantic_signature': 'settings_dialog',
    }

    diagnostics = runner._interaction_state_diagnostics(before, after, candidate, {'changed': False})

    assert diagnostics['changed'] is True
    assert 'dialog_opened' in diagnostics['reasons']
    assert diagnostics['dialog_change']['after'] == '取消|确定'


def test_interaction_state_diagnostics_detects_list_content_changed():
    runner = _runner()
    candidate = UiCandidate(
        text='刷新',
        resource_id='com.demo:id/refresh',
        content_desc='',
        class_name='android.widget.TextView',
        bounds='[40,80][160,150]',
        x=100,
        y=115,
        width=120,
        height=70,
        score=108,
        objective_hits=['刷新'],
        score_reasons=['目标名与文本精确匹配'],
    )
    before = {
        'xml': """
        <hierarchy>
          <node enabled="true" resource-id="com.demo:id/community_list" class="androidx.recyclerview.widget.RecyclerView" bounds="[0,200][1080,1800]" />
          <node enabled="true" text="社区 A" resource-id="com.demo:id/item_name" class="android.widget.TextView" bounds="[40,240][300,320]" />
        </hierarchy>
        """,
        'activity': '.CommunityActivity',
        'semantic_signature': 'list_before',
    }
    after = {
        'xml': """
        <hierarchy>
          <node enabled="true" resource-id="com.demo:id/community_list" class="androidx.recyclerview.widget.RecyclerView" bounds="[0,200][1080,1800]" />
          <node enabled="true" text="社区 A" resource-id="com.demo:id/item_name" class="android.widget.TextView" bounds="[40,240][300,320]" />
          <node enabled="true" text="社区 B" resource-id="com.demo:id/item_name" class="android.widget.TextView" bounds="[40,360][300,440]" />
        </hierarchy>
        """,
        'activity': '.CommunityActivity',
        'semantic_signature': 'list_after',
    }

    diagnostics = runner._interaction_state_diagnostics(before, after, candidate, {'changed': False})

    assert diagnostics['changed'] is True
    assert 'list_content_changed' in diagnostics['reasons']
    assert diagnostics['list_change']['before_count'] == 1
    assert diagnostics['list_change']['after_count'] == 2
