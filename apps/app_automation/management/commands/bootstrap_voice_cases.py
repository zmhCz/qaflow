# -*- coding: utf-8 -*-
"""Bootstrap first-batch deterministic voice-room APP test cases."""

from django.core.management.base import BaseCommand, CommandError

from apps.app_automation.models import AppElement, AppPackage, AppProject, AppTestCase


CASE_DEFINITIONS = [
    {
        "name": "语音房-列表基础展示",
        "description": "前置条件：手机已登录并停留在社区首页语音房列表区域。校验列表、筛选、招募和房间名称可见。",
        "steps": [
            ("assert", "断言语音房列表存在", "semantic_v2.voice.voice_room_list"),
            ("assert", "断言房间筛选入口存在", "semantic_v2.voice.voice_room_filter"),
            ("assert", "断言招募队友入口存在", "semantic_v2.voice.recruit_teammate"),
            ("assert", "断言房间名称存在", "semantic_v2.voice.first_room_name"),
        ],
    },
    {
        "name": "语音房-进入房间基础校验",
        "description": "前置条件：手机已登录并停留在社区首页语音房列表区域。点击房间名称进入房内，校验房内标题、麦位和底部操作栏。",
        "steps": [
            ("click", "点击房间名称进入房间", "semantic_v2.voice.first_room_name"),
            ("wait", "等待进入语音房", None, 2),
            ("assert", "断言进入语音房详情页", "semantic_v2.voice.room_container"),
            ("assert", "断言房内房间名称存在", "semantic_v2.voice.room_name"),
            ("assert", "断言房内麦位列表存在", "semantic_v2.voice.room_mic_list"),
            ("assert", "断言房内底部操作栏存在", "semantic_v2.voice.room_bottom_panel"),
            ("click", "返回语音房列表", "semantic_v2.voice.room_quit"),
        ],
    },
    {
        "name": "语音房-发布组队页基础展示",
        "description": "前置条件：手机已登录并停留在社区首页语音房列表区域。点击招募队友进入发布组队页，校验发布页关键字段。",
        "steps": [
            ("click", "点击招募队友", "semantic_v2.voice.recruit_teammate"),
            ("wait", "等待发布组队页", None, 2),
            ("assert", "断言发布组队标题存在", "semantic_v2.voice.publish_title"),
            ("assert", "断言组队文案输入框存在", "semantic_v2.voice.publish_team_text"),
            ("assert", "断言房间人数选择存在", "semantic_v2.voice.publish_member_count"),
            ("assert", "断言发布按钮存在", "semantic_v2.voice.publish_submit"),
            ("click", "返回语音房列表", "semantic_v2.voice.publish_back"),
        ],
    },
]


def build_step(index, kind, name, element_name=None, duration=None):
    step = {
        "id": f"voice_{index:02d}_{kind}",
        "kind": "atomic",
        "name": name,
        "type": kind,
        "config": {
            "timeout": 10,
            "image_scope": "common",
            "selector_type": "selector",
            "image_threshold": 0.7,
        },
    }
    if kind == "wait":
        step["config"].update({
            "duration": duration or 1,
            "selector": "",
            "selector_type": "image",
        })
        return step

    element = AppElement.objects.filter(name=element_name, is_active=True).first()
    if not element:
        raise CommandError(f"Element not found: {element_name}")
    step["config"].update({
        "selector": element.config.get("resource_id") or element.name,
        "element_id": element.id,
    })
    if kind == "assert":
        step["config"].update({
            "assert_type": "exists",
            "expected_exists": True,
            "match_mode": "contains",
            "expected": "",
            "retry_interval": 1,
            "expected_image_scope": "common",
        })
    return step


class Command(BaseCommand):
    help = "Bootstrap first-batch voice-room APP test cases."

    def add_arguments(self, parser):
        parser.add_argument("--project-id", type=int, default=2)
        parser.add_argument("--package-id", type=int, default=1)

    def handle(self, *args, **options):
        project = AppProject.objects.filter(id=options["project_id"]).first()
        if not project:
            raise CommandError(f"Project not found: {options['project_id']}")
        app_package = AppPackage.objects.filter(id=options["package_id"]).first()
        if not app_package:
            raise CommandError(f"AppPackage not found: {options['package_id']}")

        created_count = 0
        updated_count = 0
        for definition in CASE_DEFINITIONS:
            ui_flow = []
            for index, raw_step in enumerate(definition["steps"], start=1):
                ui_flow.append(build_step(index, *raw_step))
            _, created = AppTestCase.objects.update_or_create(
                project=project,
                name=definition["name"],
                defaults={
                    "description": definition["description"],
                    "app_package": app_package,
                    "ui_flow": ui_flow,
                    "variables": {},
                    "timeout": 180,
                    "retry_count": 0,
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"voice cases bootstrapped: created={created_count}, updated={updated_count}"
            )
        )
