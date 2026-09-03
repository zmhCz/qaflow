#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""初始化社区 APP 自动化的基础数据。"""

from __future__ import annotations

import os
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

import django  # noqa: E402


django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.db import transaction  # noqa: E402

from apps.app_automation.models import AppPackage, AppProject, AppTestConfig  # noqa: E402
from django.conf import settings  # noqa: E402


User = get_user_model()


def get_owner() -> object:
    user = User.objects.filter(username="admin").first()
    if user:
        return user

    user = User.objects.filter(is_superuser=True).order_by("id").first()
    if user:
        return user

    raise RuntimeError("未找到可用管理员用户，请先创建 admin 或至少一个 superuser。")


@transaction.atomic
def bootstrap() -> None:
    owner = get_owner()

    project, project_created = AppProject.objects.update_or_create(
        name="社区APP自动化",
        defaults={
            "description": "社区 APP 登录、创建社区、解散社区、取消关注、退出登录等核心回归场景。",
            "status": "IN_PROGRESS",
            "owner": owner,
        },
    )
    project.members.add(owner)

    package, package_created = AppPackage.objects.update_or_create(
        package_name=getattr(settings, "APP_AUTOMATION_TARGET_PACKAGE", "") or "com.example.demo",
        defaults={
            "name": "演示业务 APP",
            "created_by": owner,
        },
    )

    config, config_created = AppTestConfig.objects.get_or_create(
        id=1,
        defaults={"adb_path": "adb"},
    )
    if not config.adb_path:
        config.adb_path = "adb"
        config.save(update_fields=["adb_path", "updated_at"])

    print("APP 自动化基础数据初始化完成")
    print(f"- 项目: {project.name} ({'新建' if project_created else '已存在/已更新'})")
    print(f"- 包名: {package.name} / {package.package_name} ({'新建' if package_created else '已存在/已更新'})")
    print(f"- ADB配置: {config.adb_path} ({'新建' if config_created else '已存在'})")
    print(f"- 负责人: {owner.username}")


if __name__ == "__main__":
    bootstrap()
