from types import SimpleNamespace

from apps.app_automation.managers.recording_manager import RecordingManager
from apps.app_automation.utils.android_source_inspector import _guess_interaction_role
from apps.app_automation.views.device_views import find_candidate_by_point
from apps.app_automation.views.recording_views import (
    apply_pending_accessibility_events,
    apply_pending_touch_events,
    clear_stale_active_input_if_needed,
    find_changed_input,
    is_likely_keyboard_touch,
    is_weak_container_touch,
    parse_ime_focus_candidate,
    serialize_pending_input,
)
from apps.app_automation.utils.ui_state import extract_valid_xml


def _make_user():
    return SimpleNamespace(username="tester")


def test_extract_valid_xml_accepts_hierarchy_without_xml_declaration():
    output = "UI hierchary dumped to: /sdcard/window.xml\n<hierarchy rotation=\"0\"></hierarchy>\n"

    assert extract_valid_xml(output) == '<hierarchy rotation="0"></hierarchy>'


def test_tap_on_generic_container_uses_pos_selector():
    manager = RecordingManager()
    session = manager.create_session("session-1", "device-1", _make_user(), 1)

    manager.record_tap(
        session.session_id,
        420,
        960,
        {
            "resource_id": "com.demo:id/rv_feed",
            "class_name": "androidx.recyclerview.widget.RecyclerView",
            "scrollable": True,
            "raw_bounds": "[0,400][1080,2200]",
        },
    )

    steps = manager.convert_to_ui_flow(session.session_id, auto_insert_wait=False)
    assert steps[0]["type"] == "click"
    assert steps[0]["config"]["selector_type"] == "pos"
    assert steps[0]["config"]["selector"] == [420, 960]


def test_input_step_contains_value_selector_bounds_and_pos_fallback():
    manager = RecordingManager()
    session = manager.create_session("session-2", "device-1", _make_user(), 1)

    manager.record_input(
        session.session_id,
        "hello world",
        {
            "resource_id": "com.demo:id/et_title",
            "class_name": "android.widget.EditText",
            "hint": "Title",
            "raw_bounds": "[96,320][984,420]",
            "interaction_role": "input",
        },
        x=180,
        y=360,
    )

    steps = manager.convert_to_ui_flow(session.session_id, auto_insert_wait=False)
    config = steps[0]["config"]

    assert steps[0]["type"] == "input"
    assert config["value"] == "hello world"
    assert config["text"] == "hello world"
    assert config["selector_type"] == "selector"
    assert config["selector"]["resource_id"] == "com.demo:id/et_title"
    assert config["selector"]["bounds"] == "[96,320][984,420]"
    assert config["fallback_selector_type"] == "pos"
    assert config["fallback_selector"] == [180, 360]


def test_accessibility_text_changed_records_input_atom():
    manager = RecordingManager()
    session = manager.create_session("session-a11y-input", "device-1", _make_user(), 1)
    page_payload = {
        "package_name": "com.demo",
        "activity": "CreateActivity",
        "candidates": [
            {
                "resource_id": "com.demo:id/et_name",
                "class_name": "android.widget.EditText",
                "text": "Codex 社区",
                "hint": "社区名称",
                "focused": True,
                "bounds": {"x1": 96, "y1": 320, "x2": 984, "y2": 420},
                "raw_bounds": "[96,320][984,420]",
                "interaction_role": "input",
            }
        ],
    }
    manager.add_accessibility_event(
        session.session_id,
        {
            "type": "input",
            "text": "Codex 社区",
            "source": "accessibility_stream",
            "event": {
                "event_type": "TYPE_VIEW_TEXT_CHANGED",
                "class_name": "android.widget.EditText",
                "text": "Codex 社区",
                "before_text": "",
            },
        },
    )

    recorded = apply_pending_accessibility_events(manager, session, page_payload)

    assert len(recorded) == 1
    assert recorded[0]["type"] == "input"
    assert recorded[0]["text"] == "Codex 社区"
    assert recorded[0]["target"]["resource_id"] == "com.demo:id/et_name"


def test_accessibility_focus_sets_pending_input_without_tap_noise():
    manager = RecordingManager()
    session = manager.create_session("session-a11y-focus", "device-1", _make_user(), 1)
    page_payload = {
        "package_name": "com.demo",
        "activity": "CreateActivity",
        "candidates": [
            {
                "resource_id": "com.demo:id/et_desc",
                "class_name": "android.widget.EditText",
                "text": "",
                "hint": "社区介绍",
                "focused": True,
                "bounds": {"x1": 96, "y1": 520, "x2": 984, "y2": 680},
                "raw_bounds": "[96,520][984,680]",
                "interaction_role": "input",
            }
        ],
    }
    manager.add_accessibility_event(
        session.session_id,
        {
            "type": "tap",
            "source": "accessibility_stream",
            "event": {
                "event_type": "TYPE_VIEW_FOCUSED",
                "class_name": "android.widget.EditText",
                "text": "社区介绍",
            },
        },
    )

    recorded = apply_pending_accessibility_events(manager, session, page_payload)
    pending = serialize_pending_input(session)

    assert recorded == []
    assert pending["resource_id"] == "com.demo:id/et_desc"


def test_accessibility_scroll_records_swipe_atom():
    manager = RecordingManager()
    session = manager.create_session("session-a11y-scroll", "device-1", _make_user(), 1)
    page_payload = {
        "package_name": "com.demo",
        "activity": "FeedActivity",
        "candidates": [
            {
                "resource_id": "com.demo:id/rv_feed",
                "class_name": "androidx.recyclerview.widget.RecyclerView",
                "scrollable": True,
                "bounds": {"x1": 0, "y1": 260, "x2": 1080, "y2": 2200},
                "raw_bounds": "[0,260][1080,2200]",
            }
        ],
    }
    manager.add_accessibility_event(
        session.session_id,
        {
            "type": "swipe",
            "source": "accessibility_stream",
            "event": {
                "event_type": "TYPE_VIEW_SCROLLED",
                "class_name": "androidx.recyclerview.widget.RecyclerView",
                "scroll_delta_y": "640",
            },
        },
    )

    recorded = apply_pending_accessibility_events(manager, session, page_payload)

    assert len(recorded) == 1
    assert recorded[0]["type"] == "swipe"
    assert recorded[0]["source"] == "touch_stream"
    assert recorded[0]["y1"] > recorded[0]["y2"]


def test_recorded_tap_is_action_atom_with_semantic_target():
    manager = RecordingManager()
    session = manager.create_session("session-atom", "device-1", _make_user(), 1)

    atom = manager.record_tap(
        session.session_id,
        180,
        360,
        {
            "resource_id": "com.demo:id/create",
            "class_name": "android.widget.TextView",
            "text": "Create",
            "raw_bounds": "[120,320][260,400]",
            "interaction_role": "button",
        },
        page_data={"package_name": "com.demo", "activity": "HomeActivity"},
        source="observer",
    )

    assert atom["id"].startswith("atom_")
    assert atom["type"] == "tap"
    assert atom["source"] == "observer"
    assert atom["target"]["strategy"] == "semantic"
    assert atom["target"]["resource_id"] == "com.demo:id/create"
    assert atom["target"]["fallback"]["value"] == [180, 360]
    assert atom["page"]["activity"] == "HomeActivity"


def test_manual_input_reuses_previous_target_when_no_target_is_supplied():
    manager = RecordingManager()
    session = manager.create_session("session-input-reuse", "device-1", _make_user(), 1)

    manager.record_tap(
        session.session_id,
        180,
        360,
        {
            "resource_id": "com.demo:id/name",
            "class_name": "android.widget.EditText",
            "hint": "Name",
            "raw_bounds": "[96,320][984,420]",
            "interaction_role": "input",
        },
    )
    atom = manager.record_input(session.session_id, "team hub")
    steps = manager.convert_to_ui_flow(session.session_id, auto_insert_wait=False)

    assert atom["target"]["resource_id"] == "com.demo:id/name"
    assert atom["target"]["fallback"]["value"] == [180, 360]
    assert len(steps) == 1
    assert steps[0]["type"] == "input"
    assert steps[0]["config"]["selector_type"] == "selector"
    assert steps[0]["config"]["selector"]["resource_id"] == "com.demo:id/name"


def test_manual_input_uses_active_input_candidate_when_confirmed():
    manager = RecordingManager()
    session = manager.create_session("session-active-input-confirm", "device-1", _make_user(), 1)
    session.active_input_candidate = {
        "resource_id": "com.demo:id/inputCommunityName",
        "class_name": "android.view.View",
        "hint": "社区名称",
        "raw_bounds": "[96,520][984,620]",
        "bounds": {"x1": 96, "y1": 520, "x2": 984, "y2": 620},
        "interaction_role": "input",
        "_input_key": "com.demo:id/inputCommunityName|android.view.View|[96,520][984,620]",
        "_touch_point": {"x": 200, "y": 560, "type": "tap"},
    }

    atom = manager.record_input(session.session_id, "Codex 社区")
    steps = manager.convert_to_ui_flow(session.session_id, auto_insert_wait=False)

    assert atom["type"] == "input"
    assert atom["target"]["resource_id"] == "com.demo:id/inputCommunityName"
    assert atom["target"]["fallback"]["value"] == [200, 560]
    assert session.active_input_candidate is None
    assert steps[0]["config"]["selector"]["resource_id"] == "com.demo:id/inputCommunityName"
    assert steps[0]["config"]["fallback_selector"] == [200, 560]


def test_pending_input_serializes_target_for_frontend_confirmation():
    manager = RecordingManager()
    session = manager.create_session("session-pending-input", "device-1", _make_user(), 1)
    session.active_input_candidate = {
        "resource_id": "com.demo:id/editManifesto",
        "class_name": "android.view.View",
        "name": "社区介绍",
        "raw_bounds": "[96,700][984,920]",
        "bounds": {"x1": 96, "y1": 700, "x2": 984, "y2": 920},
        "interaction_role": "input",
        "_input_key": "com.demo:id/editManifesto|android.view.View|[96,700][984,920]",
    }

    pending = serialize_pending_input(session)

    assert pending["key"] == "com.demo:id/editManifesto|android.view.View|[96,700][984,920]"
    assert pending["label"] == "社区介绍"
    assert pending["x"] == 540
    assert pending["y"] == 810
    assert pending["element_data"]["resource_id"] == "com.demo:id/editManifesto"
    assert "_input_key" not in pending["element_data"]


def test_parse_ime_focus_candidate_from_dumpsys_served_view():
    dumpsys_text = """
      mServedView=androidx.appcompat.widget.AppCompatEditText{158dab7 VFED..CL. 0,40-804,105 #7f0a0297 app:id/editInput aid=1073741824}
      mCurrentEditorInfo:
        packageName=com.example.demo autofillId=1073741824 fieldId=2131362455 fieldName=null
    """

    candidate = parse_ime_focus_candidate(dumpsys_text)

    assert candidate["interaction_role"] == "input"
    assert candidate["resource_id"] == "com.example.demo:id/editInput"
    assert candidate["class_name"] == "androidx.appcompat.widget.AppCompatEditText"
    assert candidate["source_declared_tag"] == "input_method_focus"


def test_continuous_input_updates_last_input_atom_for_same_target():
    manager = RecordingManager()
    session = manager.create_session("session-input-merge", "device-1", _make_user(), 1)
    element = {
        "resource_id": "com.demo:id/name",
        "class_name": "android.widget.EditText",
        "hint": "Name",
        "raw_bounds": "[96,320][984,420]",
        "interaction_role": "input",
    }

    first = manager.record_input(session.session_id, "a", element, x=180, y=360)
    second = manager.record_input(session.session_id, "abc", element, x=180, y=360)

    assert first["id"] == second["id"]
    assert len(session.interactions) == 1
    assert session.interactions[0]["text"] == "abc"
    assert session.interactions[0]["input"]["value"] == "abc"


def test_input_snapshot_detects_text_change():
    manager = RecordingManager()
    session = manager.create_session("session-input-snapshot", "device-1", _make_user(), 1)
    session.last_input_values = {
        "com.demo:id/name|android.widget.EditText|[96,320][984,420]": "",
    }
    page_payload = {
        "candidates": [
            {
                "resource_id": "com.demo:id/name",
                "class_name": "android.widget.EditText",
                "text": "aaaaoo",
                "focused": True,
                "raw_bounds": "[96,320][984,420]",
                "bounds": {"x1": 96, "y1": 320, "x2": 984, "y2": 420},
            }
        ]
    }

    detected = find_changed_input(manager, session, page_payload)

    assert detected is not None
    assert detected["interaction_type"] == "input"
    assert detected["inferred_input"]["text"] == "aaaaoo"


def test_keyboard_touch_is_filtered_when_input_is_focused():
    page_payload = {
        "candidates": [
            {
                "resource_id": "com.demo:id/name",
                "class_name": "android.widget.EditText",
                "focused": True,
                "bounds": {"x1": 96, "y1": 320, "x2": 984, "y2": 420},
            },
            {
                "resource_id": "android:id/content",
                "class_name": "android.widget.FrameLayout",
                "bounds": {"x1": 0, "y1": 0, "x2": 1080, "y2": 2408},
            },
        ]
    }

    assert is_likely_keyboard_touch({"x": 420, "y": 2050}, page_payload)
    assert is_likely_keyboard_touch({"x": 493, "y": 1344}, page_payload)
    assert not is_likely_keyboard_touch({"x": 420, "y": 400}, page_payload)
    assert not is_likely_keyboard_touch({"x": 500, "y": 946}, page_payload)


def test_touch_below_app_hierarchy_is_filtered_as_keyboard_area():
    page_payload = {
        "candidates": [
            {
                "resource_id": "android:id/content",
                "class_name": "android.widget.FrameLayout",
                "bounds": {"x1": 0, "y1": 0, "x2": 1080, "y2": 1600},
            },
        ]
    }

    assert is_likely_keyboard_touch({"x": 420, "y": 1900}, page_payload)
    assert not is_likely_keyboard_touch({"x": 420, "y": 1200}, page_payload)


def test_lower_half_touch_on_main_content_container_is_filtered():
    page_payload = {
        "candidates": [
            {
                "resource_id": "com.example.demo:id/main_content_container",
                "class_name": "android.widget.FrameLayout",
                "bounds": {"x1": 0, "y1": 0, "x2": 1080, "y2": 2408},
            },
        ]
    }
    matched = page_payload["candidates"][0]

    assert is_weak_container_touch({"type": "tap", "x": 430, "y": 1900}, matched, page_payload)
    assert not is_weak_container_touch({"type": "tap", "x": 430, "y": 320}, matched, page_payload)


def test_input_without_target_types_into_current_focus_instead_of_origin():
    manager = RecordingManager()
    session = manager.create_session("session-focused-input", "device-1", _make_user(), 1)

    manager.record_input(session.session_id, "focus text")
    steps = manager.convert_to_ui_flow(session.session_id, auto_insert_wait=False)

    assert steps[0]["type"] == "input"
    assert steps[0]["config"]["value"] == "focus text"
    assert "selector_type" not in steps[0]["config"]
    assert "selector" not in steps[0]["config"]


def test_find_candidate_by_point_prefers_input_over_large_scroll_container():
    candidates = [
        {
            "name": "Feed",
            "resource_id": "com.demo:id/rv_feed",
            "class_name": "androidx.recyclerview.widget.RecyclerView",
            "scrollable": True,
            "is_hotzone": True,
            "bounds": {"x1": 0, "y1": 200, "x2": 1080, "y2": 2200},
            "raw_bounds": "[0,200][1080,2200]",
        },
        {
            "name": "Search",
            "resource_id": "com.demo:id/et_search",
            "class_name": "android.widget.EditText",
            "hint": "搜索",
            "interaction_role": "input",
            "is_hotzone": True,
            "bounds": {"x1": 120, "y1": 260, "x2": 960, "y2": 360},
            "raw_bounds": "[120,260][960,360]",
        },
    ]

    matched = find_candidate_by_point(candidates, 240, 300)
    assert matched is not None
    assert matched["resource_id"] == "com.demo:id/et_search"


def test_find_candidate_by_point_penalizes_drawer_layout_container():
    candidates = [
        {
            "name": "Drawer",
            "resource_id": "com.example.demo:id/drawerLayout",
            "class_name": "androidx.drawerlayout.widget.DrawerLayout",
            "is_hotzone": True,
            "bounds": {"x1": 0, "y1": 0, "x2": 1080, "y2": 2408},
            "raw_bounds": "[0,0][1080,2408]",
        },
        {
            "name": "Create Community",
            "resource_id": "com.example.demo:id/createCommunity",
            "class_name": "android.widget.TextView",
            "text": "Create",
            "interaction_role": "button",
            "is_hotzone": True,
            "bounds": {"x1": 812, "y1": 132, "x2": 1044, "y2": 228},
            "raw_bounds": "[812,132][1044,228]",
        },
    ]

    matched = find_candidate_by_point(candidates, 950, 180)
    assert matched is not None
    assert matched["resource_id"] == "com.example.demo:id/createCommunity"


def test_find_candidate_by_point_penalizes_android_content_root():
    candidates = [
        {
            "name": "Content Root",
            "resource_id": "android:id/content",
            "class_name": "android.widget.FrameLayout",
            "is_hotzone": True,
            "bounds": {"x1": 0, "y1": 0, "x2": 1080, "y2": 2408},
            "raw_bounds": "[0,0][1080,2408]",
        },
        {
            "name": "Community Name",
            "resource_id": "com.example.demo:id/communityName",
            "class_name": "android.widget.EditText",
            "hint": "Community name",
            "interaction_role": "input",
            "is_hotzone": True,
            "bounds": {"x1": 96, "y1": 320, "x2": 984, "y2": 420},
            "raw_bounds": "[96,320][984,420]",
        },
    ]

    matched = find_candidate_by_point(candidates, 180, 360)
    assert matched is not None
    assert matched["resource_id"] == "com.example.demo:id/communityName"


def test_find_candidate_by_point_uses_nearby_button_text_when_click_hits_container_background():
    candidates = [
        {
            "name": "Main content container",
            "resource_id": "com.example.demo:id/main_content_container",
            "class_name": "android.widget.FrameLayout",
            "bounds": {"x1": 0, "y1": 0, "x2": 1080, "y2": 2408, "width": 1080, "height": 2408},
            "raw_bounds": "[0,0][1080,2408]",
        },
        {
            "name": "Cancel",
            "resource_id": "com.example.demo:id/tvCancel",
            "class_name": "android.widget.TextView",
            "text": "取消",
            "interaction_role": "button",
            "bounds": {"x1": 118, "y1": 1840, "x2": 236, "y2": 1900, "width": 118, "height": 60},
            "raw_bounds": "[118,1840][236,1900]",
        },
    ]

    matched = find_candidate_by_point(candidates, 92, 1870)

    assert matched is not None
    assert matched["resource_id"] == "com.example.demo:id/tvCancel"


def test_find_candidate_by_point_prefers_matched_resource_over_unrelated_nearby_text():
    candidates = [
        {
            "name": "Confirm icon",
            "resource_id": "com.demo:id/btnConfirm",
            "class_name": "android.widget.ImageView",
            "interaction_role": "button",
            "bounds": {"x1": 580, "y1": 1450, "x2": 900, "y2": 1540, "width": 320, "height": 90},
            "raw_bounds": "[580,1450][900,1540]",
        },
        {
            "name": "Game room",
            "resource_id": "com.demo:id/tvRoomName",
            "class_name": "android.widget.TextView",
            "text": "Game room",
            "interaction_role": "static",
            "bounds": {"x1": 114, "y1": 1417, "x2": 932, "y2": 1482, "width": 818, "height": 65},
            "raw_bounds": "[114,1417][932,1482]",
        },
    ]

    matched = find_candidate_by_point(candidates, 740, 1500)

    assert matched is not None
    assert matched["resource_id"] == "com.demo:id/btnConfirm"


def test_find_candidate_by_point_penalizes_decorative_background_image():
    candidates = [
        {
            "name": "Background",
            "resource_id": "com.example.demo:id/ivBackgroundImage",
            "class_name": "android.widget.ImageView",
            "is_hotzone": True,
            "bounds": {"x1": 0, "y1": 96, "x2": 1080, "y2": 620},
            "raw_bounds": "[0,96][1080,620]",
        },
        {
            "name": "Create Community",
            "resource_id": "com.example.demo:id/tvCreateCommunity",
            "class_name": "android.widget.TextView",
            "text": "Create community",
            "interaction_role": "button",
            "is_hotzone": True,
            "bounds": {"x1": 760, "y1": 160, "x2": 1040, "y2": 240},
            "raw_bounds": "[760,160][1040,240]",
        },
    ]

    matched = find_candidate_by_point(candidates, 900, 200)
    assert matched is not None
    assert matched["resource_id"] == "com.example.demo:id/tvCreateCommunity"


def test_component_input_tap_is_deferred_until_text_changes():
    manager = RecordingManager()
    session = manager.create_session("session-component-input", "device-1", _make_user(), 1)
    text_candidate = {
        "resource_id": "com.example.demo:id/tvMsgContent",
        "class_name": "android.widget.TextView",
        "text": "",
        "interaction_role": "input",
        "is_hotzone": True,
        "bounds": {"x1": 114, "y1": 854, "x2": 916, "y2": 911},
        "raw_bounds": "[114,854][916,911]",
    }
    page_before = {
        "candidates": [
            {
                "resource_id": "android:id/content",
                "class_name": "android.widget.FrameLayout",
                "bounds": {"x1": 0, "y1": 0, "x2": 1080, "y2": 2408},
                "raw_bounds": "[0,0][1080,2408]",
            },
            text_candidate,
        ]
    }
    session.last_input_values = {
        "com.example.demo:id/tvMsgContent|android.widget.TextView|[114,854][916,911]": "",
    }

    manager.add_touch_event(session.session_id, {"type": "tap", "x": 430, "y": 880})
    recorded = apply_pending_touch_events(manager, session, page_before)

    assert recorded == []
    assert session.interactions == []
    assert session.active_input_candidate is not None

    page_after = {
        "candidates": [
            {
                **text_candidate,
                "text": "hahhhwoca",
            }
        ]
    }
    detected = find_changed_input(manager, session, page_after)
    atom = manager.record_detected_interaction(session.session_id, detected, page_data=page_after)

    assert atom["type"] == "input"
    assert atom["text"] == "hahhhwoca"
    assert len(session.interactions) == 1
    assert session.interactions[0]["type"] == "input"
    assert session.active_input_candidate is None


def test_keyboard_noise_after_component_input_focus_is_ignored():
    manager = RecordingManager()
    session = manager.create_session("session-keyboard-noise", "device-1", _make_user(), 1)
    text_candidate = {
        "resource_id": "com.example.demo:id/tvMsgContent",
        "class_name": "android.widget.TextView",
        "text": "",
        "interaction_role": "input",
        "bounds": {"x1": 114, "y1": 854, "x2": 916, "y2": 911},
        "raw_bounds": "[114,854][916,911]",
    }
    session.active_input_candidate = {
        **text_candidate,
        "_input_key": "com.example.demo:id/tvMsgContent|android.widget.TextView|[114,854][916,911]",
    }
    page_payload = {
        "candidates": [
            text_candidate,
            {
                "resource_id": "android:id/content",
                "class_name": "android.widget.FrameLayout",
                "bounds": {"x1": 0, "y1": 0, "x2": 1080, "y2": 2408},
                "raw_bounds": "[0,0][1080,2408]",
            },
        ]
    }

    manager.add_touch_event(session.session_id, {"type": "tap", "x": 450, "y": 1900})
    manager.add_touch_event(session.session_id, {"type": "swipe", "start_x": 700, "start_y": 2100, "end_x": 700, "end_y": 1600, "x": 700, "y": 1600})
    recorded = apply_pending_touch_events(manager, session, page_payload)

    assert recorded == []
    assert session.interactions == []


def test_tap_below_active_input_but_above_keyboard_is_recorded():
    manager = RecordingManager()
    session = manager.create_session("session-input-next-button", "device-1", _make_user(), 1)
    input_candidate = {
        "resource_id": "com.demo:id/et_number",
        "class_name": "android.widget.EditText",
        "hint": "Phone",
        "interaction_role": "input",
        "bounds": {"x1": 80, "y1": 460, "x2": 920, "y2": 560},
        "raw_bounds": "[80,460][920,560]",
    }
    button_candidate = {
        "resource_id": "com.demo:id/btnLogin",
        "class_name": "android.widget.Button",
        "text": "Login",
        "interaction_role": "button",
        "bounds": {"x1": 120, "y1": 760, "x2": 900, "y2": 860},
        "raw_bounds": "[120,760][900,860]",
    }
    session.active_input_candidate = {
        **input_candidate,
        "_input_key": "com.demo:id/et_number|android.widget.EditText|[80,460][920,560]",
    }
    page_payload = {
        "candidates": [
            input_candidate,
            button_candidate,
            {
                "resource_id": "android:id/content",
                "class_name": "android.widget.FrameLayout",
                "bounds": {"x1": 0, "y1": 0, "x2": 1080, "y2": 2408},
                "raw_bounds": "[0,0][1080,2408]",
            },
        ]
    }

    manager.add_touch_event(session.session_id, {"type": "tap", "x": 500, "y": 810})
    recorded = apply_pending_touch_events(manager, session, page_payload)

    assert len(recorded) == 1
    assert recorded[0]["type"] == "tap"
    assert recorded[0]["element"]["resource_id"] == "com.demo:id/btnLogin"


def test_duplicate_touch_events_are_deduped_on_enqueue():
    manager = RecordingManager()
    session = manager.create_session("session-dedupe-touch", "device-1", _make_user(), 1)

    manager.add_touch_event(session.session_id, {"type": "tap", "x": 493, "y": 1344, "captured_at": 1000.0})
    manager.add_touch_event(session.session_id, {"type": "tap", "x": 499, "y": 1350, "captured_at": 1000.2})

    events = manager.pop_touch_events(session.session_id)

    assert len(events) == 1


def test_empty_page_state_records_non_keyboard_tap_and_keeps_swipe():
    manager = RecordingManager()
    session = manager.create_session("session-empty-page-touch", "device-1", _make_user(), 1)
    empty_page = {"candidates": [], "screen_height": 2408, "input_method_shown": True}

    manager.add_touch_event(session.session_id, {"type": "tap", "x": 493, "y": 1344})
    manager.add_touch_event(session.session_id, {"type": "tap", "x": 493, "y": 946})
    manager.add_touch_event(
        session.session_id,
        {"type": "swipe", "start_x": 760, "start_y": 1800, "end_x": 760, "end_y": 900, "x": 760, "y": 900},
    )
    recorded = apply_pending_touch_events(manager, session, empty_page)

    assert [item["type"] for item in recorded] == ["tap", "swipe"]
    assert recorded[0]["x"] == 493
    assert recorded[0]["y"] == 946


def test_stale_active_input_is_cleared_before_post_login_swipe():
    manager = RecordingManager()
    session = manager.create_session("session-stale-input-swipe", "device-1", _make_user(), 1)
    session.active_input_candidate = {
        "resource_id": "com.demo:id/et_number",
        "class_name": "android.widget.EditText",
        "interaction_role": "input",
        "bounds": {"x1": 80, "y1": 460, "x2": 920, "y2": 560},
        "raw_bounds": "[80,460][920,560]",
        "_input_key": "com.demo:id/et_number|android.widget.EditText|[80,460][920,560]",
    }
    page_payload = {
        "activity": "ProfileActivity",
        "package_name": "com.demo",
        "candidates": [
            {
                "resource_id": "com.demo:id/profileList",
                "class_name": "androidx.recyclerview.widget.RecyclerView",
                "scrollable": True,
                "bounds": {"x1": 0, "y1": 300, "x2": 1080, "y2": 2200},
                "raw_bounds": "[0,300][1080,2200]",
            }
        ],
    }

    clear_stale_active_input_if_needed(session, page_payload)
    manager.add_touch_event(
        session.session_id,
        {"type": "swipe", "start_x": 700, "start_y": 1850, "end_x": 700, "end_y": 980, "x": 700, "y": 980},
    )
    recorded = apply_pending_touch_events(manager, session, page_payload)

    assert session.active_input_candidate is None
    assert len(recorded) == 1
    assert recorded[0]["type"] == "swipe"


def test_touch_stream_matches_dialog_button_from_previous_snapshot():
    manager = RecordingManager()
    session = manager.create_session("session-dialog-before-after", "device-1", _make_user(), 1)
    page_before = {
        "activity": "DialogActivity",
        "package_name": "com.demo",
        "candidates": [
            {
                "name": "Game",
                "resource_id": "com.demo:id/gameTitle",
                "class_name": "android.widget.TextView",
                "text": "游戏开黑",
                "interaction_role": "button",
                "bounds": {"x1": 360, "y1": 1260, "x2": 720, "y2": 1360},
                "raw_bounds": "[360,1260][720,1360]",
            },
            {
                "name": "Confirm",
                "resource_id": "com.demo:id/confirm",
                "class_name": "android.widget.Button",
                "text": "确认",
                "interaction_role": "button",
                "is_hotzone": True,
                "bounds": {"x1": 580, "y1": 1230, "x2": 900, "y2": 1330},
                "raw_bounds": "[580,1230][900,1330]",
            },
        ],
    }
    page_after = {
        "activity": "HomeActivity",
        "package_name": "com.demo",
        "candidates": [
            {
                "name": "Game",
                "resource_id": "com.demo:id/gameTitle",
                "class_name": "android.widget.TextView",
                "text": "游戏开黑",
                "interaction_role": "button",
                "is_hotzone": True,
                "bounds": {"x1": 360, "y1": 1260, "x2": 900, "y2": 1360},
                "raw_bounds": "[360,1260][900,1360]",
            },
        ],
    }

    manager.add_touch_event(session.session_id, {"type": "tap", "x": 700, "y": 1280})
    recorded = apply_pending_touch_events(manager, session, page_after, previous_payload=page_before, page_changed=True)

    assert len(recorded) == 1
    assert recorded[0]["name"] == "Tap 确认"
    assert recorded[0]["element"]["text"] == "确认"
    assert recorded[0]["page"]["activity"] == "HomeActivity"
    assert recorded[0]["element"]["text"] != "游戏开黑"


def test_touch_stream_prefers_nearby_dialog_action_over_underlying_text():
    manager = RecordingManager()
    session = manager.create_session("session-dialog-near-action", "device-1", _make_user(), 1)
    page_before = {
        "activity": "DialogActivity",
        "package_name": "com.demo",
        "candidates": [
            {
                "name": "Confirm",
                "resource_id": "com.demo:id/tvConfirm",
                "class_name": "android.widget.TextView",
                "text": "Confirm",
                "interaction_role": "button",
                "bounds": {"x1": 610, "y1": 1500, "x2": 790, "y2": 1570},
                "raw_bounds": "[610,1500][790,1570]",
            },
        ],
    }
    page_after = {
        "activity": "HomeActivity",
        "package_name": "com.demo",
        "candidates": [
            {
                "name": "Game room",
                "resource_id": "com.demo:id/tvRoomName",
                "class_name": "android.widget.TextView",
                "text": "Game room",
                "interaction_role": "button",
                "bounds": {"x1": 114, "y1": 1417, "x2": 932, "y2": 1482},
                "raw_bounds": "[114,1417][932,1482]",
            },
        ],
    }

    manager.add_touch_event(session.session_id, {"type": "tap", "x": 700, "y": 1488})
    recorded = apply_pending_touch_events(manager, session, page_after, previous_payload=page_before, page_changed=True)

    assert len(recorded) == 1
    assert recorded[0]["element"]["text"] == "Confirm"
    assert recorded[0]["element"]["text"] != "Game room"


def test_touch_stream_does_not_reuse_previous_normal_page_for_batch():
    manager = RecordingManager()
    session = manager.create_session("session-stale-normal-page", "device-1", _make_user(), 1)
    page_before = {
        "activity": "HomeActivity",
        "package_name": "com.demo",
        "candidates": [
            {
                "name": "Member Hall",
                "resource_id": "com.demo:id/memberHall",
                "class_name": "android.widget.TextView",
                "text": "成员大厅",
                "interaction_role": "button",
                "is_hotzone": True,
                "bounds": {"x1": 90, "y1": 480, "x2": 520, "y2": 560},
                "raw_bounds": "[90,480][520,560]",
            },
        ],
    }
    page_after = {
        "activity": "LoginActivity",
        "package_name": "com.demo",
        "candidates": [
            {
                "name": "Phone",
                "resource_id": "com.demo:id/et_number",
                "class_name": "android.widget.EditText",
                "hint": "请输入手机号",
                "interaction_role": "input",
                "is_hotzone": True,
                "bounds": {"x1": 80, "y1": 460, "x2": 920, "y2": 560},
                "raw_bounds": "[80,460][920,560]",
            },
        ],
    }

    manager.add_touch_event(session.session_id, {"type": "tap", "x": 300, "y": 510})
    recorded = apply_pending_touch_events(manager, session, page_after, previous_payload=page_before, page_changed=True)

    assert recorded == []
    assert session.active_input_candidate is not None
    assert session.active_input_candidate["resource_id"] == "com.demo:id/et_number"
    assert "成员大厅" not in str(session.active_input_candidate)


def test_accessibility_text_changed_records_with_active_input_when_page_moved():
    manager = RecordingManager()
    session = manager.create_session("session-a11y-input-fallback", "device-1", _make_user(), 1)
    session.active_input_candidate = {
        "resource_id": "com.demo:id/et_number",
        "class_name": "android.widget.EditText",
        "hint": "请输入手机号",
        "interaction_role": "input",
        "bounds": {"x1": 80, "y1": 460, "x2": 920, "y2": 560},
        "raw_bounds": "[80,460][920,560]",
        "_input_key": "com.demo:id/et_number|android.widget.EditText|[80,460][920,560]",
        "_touch_point": {"x": 300, "y": 510, "type": "tap"},
    }
    manager.add_accessibility_event(
        session.session_id,
        {
            "type": "input",
            "text": "13800138000",
            "before_text": "",
            "event": {
                "event_type": "TYPE_VIEW_TEXT_CHANGED",
                "class_name": "android.widget.EditText",
                "text": "13800138000",
                "before_text": "",
            },
        },
    )
    page_after = {
        "activity": "HomeActivity",
        "package_name": "com.demo",
        "candidates": [],
    }

    recorded = apply_pending_accessibility_events(manager, session, page_after)

    assert len(recorded) == 1
    assert recorded[0]["type"] == "input"
    assert recorded[0]["text"] == "13800138000"
    assert recorded[0]["element"]["resource_id"] == "com.demo:id/et_number"


def test_uikit_component_roles_are_classified_from_source_tags():
    cases = [
        ("simpleInput1", "android.view.View", "NNCommonInputBox", "input"),
        ("phoneInput", "android.view.View", "NNPhoneInputBox", "input"),
        ("switchView", "android.view.View", "NNAnimSwitch", "switch"),
        ("ckbCheck", "android.view.View", "NNRoundCheckBox", "checkbox"),
        ("label", "android.view.View", "NNSelectableLabel", "option"),
        ("entry", "android.view.View", "NNArrowEntryView", "entry"),
        ("tabs", "android.view.View", "NNTabLayout", "tab"),
        ("search", "android.view.View", "NNSearchView", "search"),
        ("seekbar", "android.view.View", "NNSeekbar", "slider"),
        ("submit", "android.view.View", "ButtonWithIcon", "button"),
        ("ivBackgroundImage", "android.widget.ImageView", "", "static"),
    ]

    for resource_name, class_name, declared_tag, expected_role in cases:
        role, _label = _guess_interaction_role(
            resource_name=resource_name,
            runtime_class_name=class_name,
            declared_tag=declared_tag,
            has_click_listener=False,
            has_movement_method=False,
            clickable=False,
            focusable=False,
            checkable=False,
        )
        assert role == expected_role


def test_active_input_records_even_if_snapshot_baseline_was_overwritten():
    manager = RecordingManager()
    session = manager.create_session("session-input-converge", "device-1", _make_user(), 1)
    active_candidate = {
        "resource_id": "com.demo:id/editInput",
        "class_name": "android.widget.EditText",
        "text": "",
        "interaction_role": "input",
        "bounds": {"x1": 96, "y1": 520, "x2": 984, "y2": 620},
        "raw_bounds": "[96,520][984,620]",
    }
    session.active_input_candidate = {
        **active_candidate,
        "_input_key": "com.demo:id/editInput|android.widget.EditText|[96,520][984,620]",
        "_initial_text": "",
    }
    session.last_input_values = {
        "com.demo:id/editInput|android.widget.EditText|[96,520][984,620]": "haha",
    }
    page_payload = {
        "candidates": [
            {
                **active_candidate,
                "text": "haha",
            }
        ]
    }

    detected = find_changed_input(manager, session, page_payload)

    assert detected is not None
    assert detected["interaction_type"] == "input"
    assert detected["inferred_input"]["text"] == "haha"


def test_input_records_against_session_baseline_when_previous_snapshot_matches_current():
    manager = RecordingManager()
    session = manager.create_session("session-input-baseline", "device-1", _make_user(), 1)
    key = "com.demo:id/etContent|android.widget.EditText|[96,700][984,960]"
    session.input_baseline_values = {key: ""}
    session.last_input_values = {key: "hello intro"}
    page_payload = {
        "candidates": [
            {
                "resource_id": "com.demo:id/etContent",
                "class_name": "android.widget.EditText",
                "text": "hello intro",
                "interaction_role": "input",
                "bounds": {"x1": 96, "y1": 700, "x2": 984, "y2": 960},
                "raw_bounds": "[96,700][984,960]",
            }
        ]
    }

    detected = find_changed_input(manager, session, page_payload)

    assert detected is not None
    assert detected["interaction_type"] == "input"
    assert detected["inferred_input"]["text"] == "hello intro"


def test_find_candidate_by_point_prefers_switch_over_large_entry_container():
    candidates = [
        {
            "name": "Switch row",
            "resource_id": "com.demo:id/rootView",
            "class_name": "androidx.constraintlayout.widget.ConstraintLayout",
            "interaction_role": "static",
            "is_hotzone": True,
            "bounds": {"x1": 0, "y1": 600, "x2": 1080, "y2": 720},
            "raw_bounds": "[0,600][1080,720]",
        },
        {
            "name": "Enable",
            "resource_id": "com.demo:id/switchView",
            "class_name": "android.view.View",
            "interaction_role": "switch",
            "is_hotzone": True,
            "bounds": {"x1": 900, "y1": 628, "x2": 1010, "y2": 692},
            "raw_bounds": "[900,628][1010,692]",
        },
    ]

    matched = find_candidate_by_point(candidates, 950, 660)

    assert matched is not None
    assert matched["resource_id"] == "com.demo:id/switchView"
