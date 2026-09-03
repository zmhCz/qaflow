#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""批量导入社区 APP 的 locator 元素到平台元素库。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml


BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

import django  # noqa: E402


django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.db import transaction  # noqa: E402

from apps.app_automation.constants import ElementType  # noqa: E402
from apps.app_automation.models import AppElement, AppProject  # noqa: E402


User = get_user_model()
LOCATOR_DIR = Path(os.getenv("QAFLOW_LOCATOR_DIR", "config/locators")).expanduser()
TARGET_PROJECT_NAME = "社区APP自动化"
SKIP_FILE_MARKERS = ("current_page.generated", "current_login_page")


def get_owner() -> object:
    user = User.objects.filter(username="admin").first()
    if user:
        return user

    user = User.objects.filter(is_superuser=True).order_by("id").first()
    if user:
        return user

    raise RuntimeError("未找到可用管理员用户，请先创建 admin 或至少一个 superuser。")


def get_project() -> AppProject:
    project = AppProject.objects.filter(name=TARGET_PROJECT_NAME).first()
    if not project:
        raise RuntimeError(f"未找到项目：{TARGET_PROJECT_NAME}")
    return project


def should_skip_file(file_path: Path) -> bool:
    stem = file_path.stem.lower()
    return any(marker in stem for marker in SKIP_FILE_MARKERS)


def should_keep_locator(locator_key: str, locator_data: dict) -> bool:
    meaningful_fields = (
        locator_data.get("resource_id"),
        locator_data.get("text"),
        locator_data.get("content_desc"),
        locator_data.get("hint"),
        locator_data.get("class"),
    )
    if not any(meaningful_fields):
        return False

    key = (locator_key or "").strip().lower()
    if key in {"root", "content", "container"} and not locator_data.get("resource_id"):
        return False

    return True


def build_tags(file_path: Path, activity: str) -> list[str]:
    stem = file_path.stem.lower()
    tags = ["community"]

    for token in stem.replace(".", "_").split("_"):
        if token in {"community", "yaml", "refreshed", "generated", "current"}:
            continue
        if token and token not in tags:
            tags.append(token)

    activity_name = activity.split(".")[-1].replace("Activity", "").strip()
    if activity_name:
        tags.append(activity_name.lower())

    return tags


def iter_locator_files() -> list[Path]:
    files = sorted(LOCATOR_DIR.glob("community*.yaml"))
    return [file_path for file_path in files if not should_skip_file(file_path)]


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


@transaction.atomic
def run() -> None:
    owner = get_owner()
    project = get_project()
    all_files = sorted(LOCATOR_DIR.glob("community*.yaml"))
    import_files = [file_path for file_path in all_files if not should_skip_file(file_path)]

    created_count = 0
    updated_count = 0
    skipped_files = [file_path.name for file_path in all_files if should_skip_file(file_path)]
    imported_names: list[str] = []

    for file_path in import_files:
        payload = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
        package_name = normalize_text(payload.get("package"))
        activity = normalize_text(payload.get("activity"))
        generated_from = normalize_text(payload.get("generated_from"))
        locators = payload.get("locators") or {}

        tags = build_tags(file_path, activity)

        for locator_key, locator_data in locators.items():
            if not isinstance(locator_data, dict):
                continue
            if not should_keep_locator(locator_key, locator_data):
                continue

            element_name = f"{file_path.stem}.{locator_key}"
            config = {
                "package": package_name,
                "activity": activity,
                "resource_id": normalize_text(locator_data.get("resource_id")),
                "text": normalize_text(locator_data.get("text")),
                "content_desc": normalize_text(locator_data.get("content_desc")),
                "hint": normalize_text(locator_data.get("hint")),
                "class": normalize_text(locator_data.get("class")),
                "locator_key": normalize_text(locator_key),
                "source_file": file_path.name,
                "bounds": normalize_text(locator_data.get("bounds")),
                "clickable": bool(locator_data.get("clickable", False)),
                "focusable": bool(locator_data.get("focusable", False)),
                "enabled": bool(locator_data.get("enabled", True)),
                "description": normalize_text(locator_data.get("description")),
                "generated_from": generated_from,
            }

            element, created = AppElement.objects.update_or_create(
                name=element_name,
                defaults={
                    "project": project,
                    "element_type": ElementType.SELECTOR,
                    "tags": tags,
                    "config": config,
                    "created_by": owner,
                    "is_active": True,
                },
            )

            imported_names.append(element.name)
            if created:
                created_count += 1
            else:
                updated_count += 1

    print("社区 locator 元素导入完成")
    print(f"- 项目: {project.name}")
    print(f"- 导入文件数: {len(iter_locator_files())}")
    print(f"- 新增元素: {created_count}")
    print(f"- 更新元素: {updated_count}")
    print(f"- 元素总数: {len(imported_names)}")
    if skipped_files:
      print(f"- 跳过文件: {', '.join(skipped_files)}")
    print("- 示例元素:")
    for name in imported_names[:10]:
        print(f"  - {name}")


if __name__ == "__main__":
    run()
