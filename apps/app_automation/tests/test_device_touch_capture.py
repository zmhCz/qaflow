import subprocess

from apps.app_automation.views.device_views import (
    build_interaction_from_accessibility_event,
    choose_primary_touch_device,
    infer_interaction_from_page_diff,
    parse_accessibility_event_line,
    parse_touch_input_devices,
    parse_touch_interaction_from_getevent,
    page_state_changed,
    wait_for_next_touch,
)


def test_parse_touch_input_devices_prefers_direct_multitouch_panel():
    output = """
add device 3: /dev/input/event6
  name:     "vivo_ts"
  events:
    KEY (0001): BTN_TOOL_FINGER BTN_TOUCH
    ABS (0003): ABS_MT_SLOT
                ABS_MT_POSITION_X
                ABS_MT_POSITION_Y
                ABS_MT_TRACKING_ID
  input props:
    INPUT_PROP_DIRECT
add device 5: /dev/input/event5
  name:     "vivo_ts_pen"
  events:
    KEY (0001): BTN_TOUCH
    ABS (0003): ABS_X
                ABS_Y
  input props:
    INPUT_PROP_DIRECT
"""
    devices = parse_touch_input_devices(output)

    assert choose_primary_touch_device(devices) == "/dev/input/event6"


def test_parse_touch_interaction_from_getevent_handles_btn_tool_finger():
    output = """
[ 1111.111111] /dev/input/event6: EV_KEY       BTN_TOOL_FINGER      DOWN
[ 1111.111112] /dev/input/event6: EV_ABS       ABS_MT_TRACKING_ID   00001234
[ 1111.111113] /dev/input/event6: EV_ABS       ABS_MT_POSITION_X    0000021c
[ 1111.111114] /dev/input/event6: EV_ABS       ABS_MT_POSITION_Y    000004b0
[ 1111.111115] /dev/input/event6: EV_SYN       SYN_REPORT           00000000
[ 1111.211111] /dev/input/event6: EV_KEY       BTN_TOOL_FINGER      UP
[ 1111.211112] /dev/input/event6: EV_ABS       ABS_MT_TRACKING_ID   ffffffff
[ 1111.211113] /dev/input/event6: EV_SYN       SYN_REPORT           00000000
"""
    interaction = parse_touch_interaction_from_getevent(
        output,
        (1080, 2408),
        {"max_x": 1079, "max_y": 2407},
    )

    assert interaction is not None
    assert interaction["type"] == "tap"
    assert interaction["x"] == 540
    assert interaction["y"] == 1200


def test_wait_for_next_touch_uses_quiet_touch_device_command(monkeypatch):
    captured_commands = []
    partial_output = b"""
[ 2222.111111] /dev/input/event6: EV_KEY       BTN_TOUCH            DOWN
[ 2222.111112] /dev/input/event6: EV_ABS       ABS_MT_POSITION_X    0000012c
[ 2222.111113] /dev/input/event6: EV_ABS       ABS_MT_POSITION_Y    00000258
[ 2222.111114] /dev/input/event6: EV_KEY       BTN_TOUCH            UP
"""

    def fake_run_adb_command(adb_path, device_id, args, timeout=15):
        captured_commands.append(args)
        if args == ["shell", "wm", "size"]:
            return subprocess.CompletedProcess(args, 0, stdout=b"Physical size: 1080x2408\n", stderr=b"")
        if args == ["shell", "getevent", "-lp"]:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=b"ABS_MT_POSITION_X : value 0, min 0, max 1079\nABS_MT_POSITION_Y : value 0, min 0, max 2407\n",
                stderr=b"",
            )
        if args == ["shell", "getevent", "-pl"]:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=(
                    b"add device 3: /dev/input/event6\n"
                    b"  name:     \"vivo_ts\"\n"
                    b"  events:\n"
                    b"    KEY (0001): BTN_TOOL_FINGER BTN_TOUCH\n"
                    b"    ABS (0003): ABS_MT_POSITION_X\n"
                    b"                ABS_MT_POSITION_Y\n"
                    b"                ABS_MT_TRACKING_ID\n"
                    b"  input props:\n"
                    b"    INPUT_PROP_DIRECT\n"
                ),
                stderr=b"",
            )
        if args == ["shell", "getevent", "-qlt", "/dev/input/event6"]:
            raise subprocess.TimeoutExpired(cmd=args, timeout=timeout, output=partial_output)
        raise AssertionError(f"unexpected adb command: {args}")

    monkeypatch.setattr("apps.app_automation.views.device_views.run_adb_command", fake_run_adb_command)

    interaction = wait_for_next_touch("adb", "device-1", timeout=3)
    assert interaction["type"] == "tap"
    assert ["shell", "getevent", "-qlt", "/dev/input/event6"] in captured_commands


def test_parse_accessibility_event_line_builds_input_interaction():
    line = (
        "06-27 14:41:45.929 EventType: TYPE_VIEW_TEXT_CHANGED; EventTime: 745766146; "
        "PackageName: com.example.demo; MovementGranularity: 0; Action: 0; "
        "ContentChangeTypes: []; WindowChangeTypes: [] [ ClassName: android.widget.EditText; "
        "Text: [aaa社区]; ContentDescription: null; BeforeText: aa ]"
    )

    event = parse_accessibility_event_line(line)
    interaction = build_interaction_from_accessibility_event(event)

    assert event["event_type"] == "TYPE_VIEW_TEXT_CHANGED"
    assert event["text"] == "aaa社区"
    assert interaction is not None
    assert interaction["type"] == "input"
    assert interaction["text"] == "aaa社区"


def test_parse_accessibility_scroll_event_builds_swipe_interaction():
    line = (
        "06-29 20:18:45.929 EventType: TYPE_VIEW_SCROLLED; EventTime: 745766146; "
        "PackageName: com.example.demo; MovementGranularity: 0; Action: 0; "
        "ContentChangeTypes: []; WindowChangeTypes: [] [ ClassName: androidx.recyclerview.widget.RecyclerView; "
        "Text: []; ContentDescription: null; ScrollX: 0; ScrollY: 980; MaxScrollX: 0; MaxScrollY: 3000; "
        "ScrollDeltaX: 0; ScrollDeltaY: 640; BeforeText: null ]"
    )

    event = parse_accessibility_event_line(line)
    interaction = build_interaction_from_accessibility_event(event)

    assert event["event_type"] == "TYPE_VIEW_SCROLLED"
    assert event["scroll_delta_y"] == "640"
    assert interaction is not None
    assert interaction["type"] == "swipe"


def test_wait_for_next_touch_falls_back_to_accessibility_events(monkeypatch):
    captured_commands = []
    accessibility_output = (
        "06-27 14:41:45.929 EventType: TYPE_VIEW_CLICKED; EventTime: 745766146; "
        "PackageName: com.example.demo; MovementGranularity: 0; Action: 0; "
        "ContentChangeTypes: []; WindowChangeTypes: [] [ ClassName: android.widget.Button; "
        "Text: [创建社区]; ContentDescription: null; BeforeText: null ]"
    ).encode("utf-8")

    def fake_run_adb_command(adb_path, device_id, args, timeout=15):
        captured_commands.append(args)
        if args == ["shell", "wm", "size"]:
            return subprocess.CompletedProcess(args, 0, stdout=b"Physical size: 1080x2408\n", stderr=b"")
        if args == ["shell", "getevent", "-lp"]:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=b"ABS_MT_POSITION_X : value 0, min 0, max 1079\nABS_MT_POSITION_Y : value 0, min 0, max 2407\n",
                stderr=b"",
            )
        if args == ["shell", "getevent", "-pl"]:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=(b"add device 3: /dev/input/event6\n  name:     \"vivo_ts\"\n  events:\n"),
                stderr=b"",
            )
        if args == ["shell", "getevent", "-qlt"]:
            raise subprocess.TimeoutExpired(cmd=args, timeout=timeout, output=b"")
        if args == ["shell", "uiautomator", "events"]:
            raise subprocess.TimeoutExpired(cmd=args, timeout=timeout, output=accessibility_output)
        raise AssertionError(f"unexpected adb command: {args}")

    monkeypatch.setattr("apps.app_automation.views.device_views.run_adb_command", fake_run_adb_command)

    interaction = wait_for_next_touch("adb", "device-1", timeout=2)
    assert interaction["type"] == "tap"
    assert interaction["source"] == "accessibility"
    assert interaction["event"]["text"] == "创建社区"
    assert ["shell", "uiautomator", "events"] in captured_commands


def test_infer_interaction_from_page_diff_detects_focus_then_input():
    before_payload = {
        "package_name": "com.demo",
        "activity": "CreateCommunityActivity",
        "candidates": [
            {
                "resource_id": "com.demo:id/et_name",
                "class_name": "android.widget.EditText",
                "hint": "名称",
                "text": "",
                "focused": False,
                "bounds": {"x1": 100, "y1": 300, "x2": 900, "y2": 420},
                "raw_bounds": "[100,300][900,420]",
            }
        ],
    }
    after_focus_payload = {
        "package_name": "com.demo",
        "activity": "CreateCommunityActivity",
        "candidates": [
            {
                "resource_id": "com.demo:id/et_name",
                "class_name": "android.widget.EditText",
                "hint": "名称",
                "text": "",
                "focused": True,
                "bounds": {"x1": 100, "y1": 300, "x2": 900, "y2": 420},
                "raw_bounds": "[100,300][900,420]",
            }
        ],
    }
    after_input_payload = {
        "package_name": "com.demo",
        "activity": "CreateCommunityActivity",
        "candidates": [
            {
                "resource_id": "com.demo:id/et_name",
                "class_name": "android.widget.EditText",
                "hint": "名称",
                "text": "aaa社区",
                "focused": True,
                "bounds": {"x1": 100, "y1": 300, "x2": 900, "y2": 420},
                "raw_bounds": "[100,300][900,420]",
            }
        ],
    }

    assert page_state_changed(before_payload, after_focus_payload) is True

    focus_interaction = infer_interaction_from_page_diff(before_payload, after_focus_payload)
    assert focus_interaction is not None
    assert focus_interaction["interaction_type"] == "tap"
    assert focus_interaction["matched_candidate"]["resource_id"] == "com.demo:id/et_name"

    input_interaction = infer_interaction_from_page_diff(after_focus_payload, after_input_payload)
    assert input_interaction is not None
    assert input_interaction["interaction_type"] == "input"
    assert input_interaction["inferred_input"]["text"] == "aaa社区"
