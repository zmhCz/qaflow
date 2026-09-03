# -*- coding: utf-8 -*-
"""Bootstrap P0 voice-room semantic dictionary and elements."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.app_automation.models import (
    AppElement,
    AppPackage,
    AppProject,
    AppSemanticDictionary,
)


SCREEN_WIDTH = 1080
SCREEN_HEIGHT = 2400
APP_IDENTIFIER = getattr(settings, "APP_AUTOMATION_TARGET_PACKAGE", "") or "com.example.demo"
MAIN_ACTIVITY = getattr(settings, "APP_AUTOMATION_MAIN_ACTIVITY", "") or "com.example.demo.activity.MainActivity"
SEARCH_ROOM_ACTIVITY = getattr(settings, "APP_AUTOMATION_SEARCH_ROOM_ACTIVITY", "") or "com.example.demo.activity.SearchRoomActivity"
PUBLISH_TEAM_ACTIVITY = getattr(settings, "APP_AUTOMATION_PUBLISH_TEAM_ACTIVITY", "") or "com.example.demo.activity.PublishTeamActivity"
ROOM_ACTIVITY = getattr(settings, "APP_AUTOMATION_ROOM_ACTIVITY", "") or "com.example.demo.activity.RoomActivity"


def rid(name: str) -> str:
    return f"{APP_IDENTIFIER}:id/{name}"


DICTIONARY_ITEMS = {
    "page": [
        "语音房列表页",
        "语音房详情页",
        "语音房筛选页",
        "发布组队页",
        "招募队友弹窗",
        "房内聊天区",
        "房内麦位区",
        "房内成员列表",
        "语音房底部操作栏",
    ],
    "object": [
        "全员大厅",
        "专属房间分类",
        "房间搜索筛选",
        "招募队友",
        "发布组队",
        "组队文案",
        "组队标签",
        "更多标签",
        "区服选择",
        "房间人数选择",
        "房间有效期",
        "发布组队按钮",
        "刷新房间列表",
        "语音房列表",
        "语音房卡片",
        "房间序号",
        "房间名称",
        "房间人数",
        "当前人数",
        "最大人数",
        "加入房间",
        "收起房间",
        "收起房间返回列表",
        "房内底部操作栏",
        "房内招募队友",
        "房内聊天",
        "麦克风开关",
        "扬声器开关",
        "取消通话",
        "聊天输入框",
        "发送消息",
        "麦位列表",
        "上麦",
        "下麦",
        "闭麦",
        "开麦",
    ],
    "role": [
        "页面入口",
        "房间卡片",
        "麦位",
        "人数",
    ],
    "purpose": [
        "进房",
        "筛选房间",
        "刷新列表",
        "发送IM消息",
        "麦位操作",
    ],
}


ELEMENT_SPECS = [
    {
        "key": "voice_room_list",
        "page": "语音房列表页",
        "object": "语音房列表",
        "role": "容器",
        "resource_id": rid("rvRooms"),
        "class_name": "androidx.recyclerview.widget.RecyclerView",
        "bounds": "[0,414][1080,2157]",
        "note": "语音房列表容器，用于列表存在断言和滑动范围。",
    },
    {
        "key": "member_hall_entry",
        "page": "语音房列表页",
        "object": "全员大厅",
        "role": "页面入口",
        "resource_id": rid("tvTitle"),
        "text": "全员大厅",
        "class_name": "android.widget.TextView",
        "bounds": "[114,769][996,838]",
        "note": "社区首页进入全员大厅的入口锚点。",
    },
    {
        "key": "voice_room_filter",
        "page": "语音房列表页",
        "object": "房间搜索筛选",
        "role": "页面入口",
        "resource_id": rid("searchRoomIdFilter"),
        "class_name": "android.widget.FrameLayout",
        "bounds": "[48,576][420,684]",
        "note": "语音房列表的房间 ID / 筛选入口外层点击热区。",
        "clickable": True,
    },
    {
        "key": "filter_search_input",
        "page": "语音房筛选页",
        "object": "房间筛选搜索框",
        "role": "输入框",
        "activity": SEARCH_ROOM_ACTIVITY,
        "resource_id": rid("etContent"),
        "text": "全局搜索关键词、房间号",
        "class_name": "android.widget.EditText",
        "bounds": "[486,126][1008,234]",
        "note": "语音房筛选/搜索页输入框，用于验证筛选页已打开。",
        "clickable": True,
    },
    {
        "key": "filter_team_tab",
        "page": "语音房筛选页",
        "object": "组队分类",
        "role": "Tab",
        "activity": SEARCH_ROOM_ACTIVITY,
        "resource_id": rid("nn_tab_layout_text_view"),
        "text": "组队",
        "class_name": "android.widget.TextView",
        "bounds": "[48,287][144,352]",
        "note": "语音房筛选/搜索页的组队分类 Tab。",
    },
    {
        "key": "recruit_teammate",
        "page": "语音房列表页",
        "object": "招募队友",
        "role": "按钮",
        "resource_id": rid("tvRecruitTeammate"),
        "text": "招募队友",
        "class_name": "android.widget.TextView",
        "bounds": "[618,1485][786,1545]",
        "note": "语音房列表页招募队友按钮。",
    },
    {
        "key": "first_room_sequence",
        "page": "语音房列表页",
        "object": "房间序号",
        "role": "文本",
        "resource_id": rid("tvRoomSequenceNum"),
        "class_name": "android.widget.TextView",
        "bounds": "[48,764][113,812]",
        "note": "首个可见语音房卡片的序号，用于列表排序和房间存在断言。",
    },
    {
        "key": "first_room_name",
        "page": "语音房列表页",
        "object": "房间名称",
        "role": "文本",
        "resource_id": rid("tvRoomName"),
        "class_name": "android.widget.TextView",
        "bounds": "[131,755][888,820]",
        "note": "首个可见语音房卡片的房间名称，仅用于展示断言；进入房间请使用加入房间控件。",
    },
    {
        "key": "first_room_members",
        "page": "语音房列表页",
        "object": "房间人数",
        "role": "人数",
        "resource_id": rid("members_layout"),
        "class_name": "android.widget.LinearLayout",
        "bounds": "[954,752][1026,824]",
        "note": "首个可见语音房卡片的人数/房态展示区域。",
    },
    {
        "key": "first_room_join",
        "page": "语音房列表页",
        "object": "加入房间",
        "role": "按钮",
        "resource_id": rid("llJoin"),
        "class_name": "android.widget.LinearLayout",
        "bounds": "[48,860][144,956]",
        "note": "首个可见且可进入语音房卡片的加入位。用于轻量进房链路，不直接代表整张房间卡片。",
        "clickable": True,
    },
    {
        "key": "publish_back",
        "page": "发布组队页",
        "object": "返回",
        "role": "按钮",
        "activity": PUBLISH_TEAM_ACTIVITY,
        "resource_id": rid("ifvBack"),
        "class_name": "android.widget.TextView",
        "bounds": "[36,144][132,240]",
        "note": "发布组队页返回按钮。",
        "clickable": True,
    },
    {
        "key": "publish_title",
        "page": "发布组队页",
        "object": "发布组队",
        "role": "文本",
        "activity": PUBLISH_TEAM_ACTIVITY,
        "resource_id": rid("tvTitle"),
        "text": "发布组队",
        "class_name": "android.widget.TextView",
        "bounds": "[444,158][636,227]",
        "note": "发布组队页标题，用于进入发布页断言。",
    },
    {
        "key": "publish_team_text",
        "page": "发布组队页",
        "object": "组队文案",
        "role": "输入框",
        "activity": PUBLISH_TEAM_ACTIVITY,
        "resource_id": rid("editInput"),
        "class_name": "android.widget.EditText",
        "bounds": "[48,344][852,413]",
        "note": "发布组队文案输入框。",
        "clickable": True,
    },
    {
        "key": "publish_more_tags",
        "page": "发布组队页",
        "object": "更多标签",
        "role": "按钮",
        "activity": PUBLISH_TEAM_ACTIVITY,
        "resource_id": rid("tvRecommendMore"),
        "text": "更多",
        "class_name": "android.widget.TextView",
        "bounds": "[864,527][948,587]",
        "note": "发布组队页更多标签入口。",
        "clickable": True,
    },
    {
        "key": "publish_region",
        "page": "发布组队页",
        "object": "区服选择",
        "role": "页面入口",
        "activity": PUBLISH_TEAM_ACTIVITY,
        "resource_id": rid("tvTailText"),
        "text": "全部区服",
        "class_name": "android.widget.TextView",
        "bounds": "[792,885][960,945]",
        "note": "发布组队页区服选择当前值，用于区服行断言和辅助点击。",
    },
    {
        "key": "publish_member_count",
        "page": "发布组队页",
        "object": "房间人数选择",
        "role": "页面入口",
        "activity": PUBLISH_TEAM_ACTIVITY,
        "resource_id": rid("numberOfPeopleRoom"),
        "class_name": "android.view.ViewGroup",
        "bounds": "[0,993][1080,1149]",
        "note": "发布组队页房间人数选择行。",
        "clickable": True,
    },
    {
        "key": "publish_valid_period",
        "page": "发布组队页",
        "object": "房间有效期",
        "role": "文本",
        "activity": PUBLISH_TEAM_ACTIVITY,
        "resource_id": rid("tvTailText"),
        "text": "60分钟",
        "class_name": "android.widget.TextView",
        "bounds": "[824,1197][960,1257]",
        "note": "发布组队页房间有效期展示值。",
    },
    {
        "key": "publish_submit",
        "page": "发布组队页",
        "object": "发布组队按钮",
        "role": "按钮",
        "activity": PUBLISH_TEAM_ACTIVITY,
        "resource_id": rid("tvPublishTeam"),
        "class_name": "androidx.appcompat.widget.LinearLayoutCompat",
        "bounds": "[48,1389][1032,1533]",
        "note": "发布组队页底部发布按钮。",
        "clickable": True,
    },
    {
        "key": "room_container",
        "page": "语音房详情页",
        "object": "语音房详情页",
        "role": "容器",
        "activity": ROOM_ACTIVITY,
        "resource_id": rid("roomContainer"),
        "class_name": "android.widget.FrameLayout",
        "bounds": "[0,0][1080,2205]",
        "note": "房内页面容器，用于进房成功断言。",
    },
    {
        "key": "room_quit",
        "page": "语音房详情页",
        "object": "收起房间返回列表",
        "role": "按钮",
        "activity": ROOM_ACTIVITY,
        "resource_id": rid("iv_quit"),
        "class_name": "android.widget.TextView",
        "bounds": "[0,156][132,228]",
        "note": "房内左上角收起入口，点击后回到语音房列表；不是彻底退出房间。",
        "clickable": True,
    },
    {
        "key": "room_sequence",
        "page": "语音房详情页",
        "object": "房间序号",
        "role": "文本",
        "activity": ROOM_ACTIVITY,
        "resource_id": rid("tvRoomSequenceNum"),
        "class_name": "android.widget.TextView",
        "bounds": "[132,156][210,228]",
        "note": "房内顶部房间序号，用于确认进入目标房间。",
    },
    {
        "key": "room_name",
        "page": "语音房详情页",
        "object": "房间名称",
        "role": "文本",
        "activity": ROOM_ACTIVITY,
        "resource_id": rid("tv_room_name"),
        "class_name": "android.widget.TextView",
        "bounds": "[222,162][432,222]",
        "note": "房内顶部房间名称，用于进房断言。",
    },
    {
        "key": "room_mic_list",
        "page": "房内麦位区",
        "object": "麦位列表",
        "role": "容器",
        "activity": ROOM_ACTIVITY,
        "resource_id": rid("rv_mic"),
        "class_name": "android.widget.GridView",
        "bounds": "[0,336][1080,919]",
        "note": "房内麦位列表容器。普通语音房进房后通常已在麦上，互动语音房进房后通常展示空麦/点击上麦位。",
    },
    {
        "key": "room_first_mic",
        "page": "房内麦位区",
        "object": "麦位列表",
        "role": "麦位",
        "activity": ROOM_ACTIVITY,
        "resource_id": rid("mic_container"),
        "class_name": "android.view.ViewGroup",
        "bounds": "[293,883][786,1466]",
        "note": "普通语音房房内可见麦位/成员位区域。普通语音房进房后通常已在麦上，不应复用互动房 empty_mic 上麦位判断。",
    },
    {
        "key": "room_bottom_panel",
        "page": "语音房底部操作栏",
        "object": "房内底部操作栏",
        "role": "容器",
        "activity": ROOM_ACTIVITY,
        "resource_id": rid("bottom_panel"),
        "class_name": "android.widget.LinearLayout",
        "bounds": "[0,2012][1080,2408]",
        "note": "房内底部操作栏容器。不同房型按钮不同，通用断言只校验底部栏存在。",
    },
    {
        "key": "room_recruit",
        "page": "语音房底部操作栏",
        "object": "房内招募队友",
        "role": "按钮",
        "activity": ROOM_ACTIVITY,
        "resource_id": rid("llOperation"),
        "class_name": "android.view.ViewGroup",
        "bounds": "[0,1989][216,2205]",
        "note": "房内底部第一个操作按钮：招募队友。该组件 resource-id 与其它底部按钮复用，必须结合 bounds 使用。",
        "clickable": True,
    },
    {
        "key": "room_chat",
        "page": "语音房底部操作栏",
        "object": "房内聊天",
        "role": "按钮",
        "activity": ROOM_ACTIVITY,
        "resource_id": rid("tvContent"),
        "class_name": "android.widget.TextView",
        "text": "聊天",
        "bounds": "[288,2312][360,2360]",
        "note": "普通语音房底部聊天入口文案。该区域存在多个 tvContent，必须结合 text=聊天 使用。",
        "clickable": False,
    },
    {
        "key": "room_mic_toggle",
        "page": "语音房底部操作栏",
        "object": "麦克风开关",
        "role": "按钮",
        "activity": ROOM_ACTIVITY,
        "resource_id": rid("llOperation"),
        "class_name": "android.view.ViewGroup",
        "bounds": "[432,1989][648,2205]",
        "note": "房内底部第三个操作按钮：麦克风开关。该组件 resource-id 与其它底部按钮复用，必须结合 bounds 使用。",
        "clickable": True,
    },
    {
        "key": "room_speaker_toggle",
        "page": "语音房底部操作栏",
        "object": "扬声器开关",
        "role": "按钮",
        "activity": ROOM_ACTIVITY,
        "resource_id": rid("llOperation"),
        "class_name": "android.view.ViewGroup",
        "bounds": "[648,1989][864,2205]",
        "note": "房内底部第四个操作按钮：扬声器开关。该组件 resource-id 与其它底部按钮复用，必须结合 bounds 使用。",
        "clickable": True,
    },
    {
        "key": "room_cancel_call",
        "page": "语音房底部操作栏",
        "object": "取消通话",
        "role": "按钮",
        "activity": ROOM_ACTIVITY,
        "resource_id": rid("llOperation"),
        "class_name": "android.view.ViewGroup",
        "bounds": "[864,1989][1080,2205]",
        "note": "房内底部第五个操作按钮：取消/挂断。该组件 resource-id 与其它底部按钮复用，必须结合 bounds 使用。",
        "clickable": True,
    },
]


def parse_bounds(bounds_text):
    match = re.match(r"\[(\d+),(\d+)]\[(\d+),(\d+)]", bounds_text or "")
    if not match:
        return None
    return tuple(int(item) for item in match.groups())


def normalize_bounds(bounds_text):
    parsed = parse_bounds(bounds_text)
    if not parsed:
        return {}
    x1, y1, x2, y2 = parsed
    return {
        "x1": round(x1 / SCREEN_WIDTH, 6),
        "y1": round(y1 / SCREEN_HEIGHT, 6),
        "x2": round(x2 / SCREEN_WIDTH, 6),
        "y2": round(y2 / SCREEN_HEIGHT, 6),
    }


def bounds_rank(actual_bounds, expected_bounds):
    actual = parse_bounds(actual_bounds)
    expected = parse_bounds(expected_bounds)
    if not actual or not expected:
        return (0, 0, 0)
    ax1, ay1, ax2, ay2 = actual
    ex1, ey1, ex2, ey2 = expected
    overlap_width = max(0, min(ax2, ex2) - max(ax1, ex1))
    overlap_height = max(0, min(ay2, ey2) - max(ay1, ey1))
    overlap_area = overlap_width * overlap_height
    actual_center = ((ax1 + ax2) // 2, (ay1 + ay2) // 2)
    expected_center = ((ex1 + ex2) // 2, (ey1 + ey2) // 2)
    center_distance = abs(actual_center[0] - expected_center[0]) + abs(actual_center[1] - expected_center[1])
    actual_area = max(1, (ax2 - ax1) * (ay2 - ay1))
    expected_area = max(1, (ex2 - ex1) * (ey2 - ey1))
    area_delta = abs(actual_area - expected_area)
    return (overlap_area, -center_distance, -area_delta)


def read_xml_node(xml_root, resource_id, text="", expected_bounds=""):
    if xml_root is None:
        return None
    matches = []
    for node in xml_root.iter("node"):
        if resource_id and node.attrib.get("resource-id") != resource_id:
            continue
        if text and node.attrib.get("text") != text:
            continue
        matches.append(node)
    if not matches:
        return None
    if expected_bounds:
        return max(matches, key=lambda item: bounds_rank(item.attrib.get("bounds"), expected_bounds))
    return matches[0]


class Command(BaseCommand):
    help = "Bootstrap P0 voice-room semantic dictionary and selector elements."

    def add_arguments(self, parser):
        parser.add_argument("--project-id", type=int, default=2)
        parser.add_argument("--package-id", type=int, default=1)
        parser.add_argument("--xml", type=str, default="")
        parser.add_argument("--activity", type=str, default="")
        parser.add_argument("--status", type=str, default="待验证")

    def handle(self, *args, **options):
        project = AppProject.objects.filter(id=options["project_id"]).first()
        if not project:
            raise CommandError(f"Project not found: {options['project_id']}")

        app_package = AppPackage.objects.filter(id=options["package_id"]).first()
        if not app_package:
            raise CommandError(f"AppPackage not found: {options['package_id']}")

        xml_root = None
        xml_path = options.get("xml") or ""
        if xml_path:
            path = Path(xml_path)
            if not path.exists():
                raise CommandError(f"XML file not found: {path}")
            xml_root = ET.parse(path).getroot()

        dict_created = 0
        dict_updated = 0
        sort_base = 1000
        for category, values in DICTIONARY_ITEMS.items():
            for offset, value in enumerate(values):
                _, created = AppSemanticDictionary.objects.update_or_create(
                    project=project,
                    category=category,
                    value=value,
                    defaults={
                        "label": value,
                        "description": "语音房自动化 P0 语义词，由 bootstrap_voice_semantics 初始化。",
                        "governance_status": "approved",
                        "source": "voice_bootstrap",
                        "sort_order": sort_base + offset,
                        "is_active": True,
                    },
                )
                if created:
                    dict_created += 1
                else:
                    dict_updated += 1

        elem_created = 0
        elem_updated = 0
        capture_activity = str(options.get("activity") or "").strip()
        for spec in ELEMENT_SPECS:
            spec_activity = spec.get("activity") or MAIN_ACTIVITY
            can_use_xml = not capture_activity or capture_activity == spec_activity
            node = (
                read_xml_node(xml_root, spec["resource_id"], spec.get("text", ""), spec.get("bounds", ""))
                if xml_root is not None and can_use_xml
                else None
            )
            bounds = node.attrib.get("bounds") if node is not None else spec["bounds"]
            class_name = node.attrib.get("class") if node is not None else spec["class_name"]
            text = node.attrib.get("text") if node is not None else spec.get("text", "")
            clickable = (
                str(node.attrib.get("clickable")).lower() == "true"
                if node is not None
                else bool(spec.get("clickable", False))
            )
            name = f"semantic_v2.voice.{spec['key']}"
            semantic_status = options["status"]
            config = {
                "strategy": "selector",
                "semantic_version": "v2",
                "semantic_status": semantic_status,
                "semantic_status_source": "voice_bootstrap",
                "needs_human_confirm": True,
                "description": spec["object"],
                "manual_note": spec["note"],
                "package": app_package.package_name or APP_IDENTIFIER,
                "activity": spec_activity,
                "resource_id": spec["resource_id"],
                "class": class_name,
                "text": text,
                "content_desc": "",
                "bounds": bounds,
                "normalized_bounds": normalize_bounds(bounds),
                "locator_key": f"voice_{spec['key']}",
                "semantic_page": spec.get("page") or "语音房列表页",
                "semantic_object": spec["object"],
                "semantic_role": spec["role"],
                "interaction_role": spec["role"],
                "source_confidence": "medium",
                "source": "voice_bootstrap",
                "clickable": clickable,
                "enabled": True,
                "screen_size": [SCREEN_WIDTH, SCREEN_HEIGHT],
            }
            tags = ["semantic_v2", "语音房", "voice_p0", semantic_status, spec["role"]]
            element, created = AppElement.objects.update_or_create(
                name=name,
                defaults={
                    "project": project,
                    "element_type": "selector",
                    "tags": tags,
                    "config": config,
                    "is_active": True,
                },
            )
            if created:
                elem_created += 1
            else:
                elem_updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                "voice semantics bootstrapped: "
                f"dictionary created={dict_created}, updated={dict_updated}; "
                f"elements created={elem_created}, updated={elem_updated}"
            )
        )
