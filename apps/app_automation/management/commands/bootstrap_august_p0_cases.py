# -*- coding: utf-8 -*-
"""Bootstrap August P0 APP automation cases and foundation semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.app_automation.models import AppElement, AppPackage, AppProject, AppTestCase


APP_PACKAGE = getattr(settings, "APP_AUTOMATION_TARGET_PACKAGE", "") or "com.example.demo"
MAIN_ACTIVITY = getattr(settings, "APP_AUTOMATION_MAIN_ACTIVITY", "") or "com.example.demo.activity.MainActivity"
SCREEN_WIDTH = 1080
SCREEN_HEIGHT = 2408
TEST_LOGIN_PASSWORD = getattr(settings, "APP_AUTOMATION_TEST_LOGIN_PASSWORD", "") or ""
TEST_LOGIN_PHONE = getattr(settings, "APP_AUTOMATION_TEST_LOGIN_PHONE", "") or ""
TEST_COMMUNITY_KEYWORD = getattr(settings, "APP_AUTOMATION_TEST_COMMUNITY_KEYWORD", "") or ""
TEST_COMMUNITY_NAME = getattr(settings, "APP_AUTOMATION_TEST_COMMUNITY_NAME", "") or ""


def rid(name: str) -> str:
    return f"{APP_PACKAGE}:id/{name}"


def normalize_bounds(bounds: str) -> dict[str, float]:
    left, right = bounds.strip().split("][", 1)
    x1, y1 = [int(item) for item in left.lstrip("[").split(",", 1)]
    x2, y2 = [int(item) for item in right.rstrip("]").split(",", 1)]
    return {
        "x1": round(x1 / SCREEN_WIDTH, 6),
        "y1": round(y1 / SCREEN_HEIGHT, 6),
        "x2": round(x2 / SCREEN_WIDTH, 6),
        "y2": round(y2 / SCREEN_HEIGHT, 6),
    }


BOTTOM_TABS = [
    {
        "legacy_id": 137,
        "name": "semantic_v2.main.current_community_tab",
        "object": "当前社区TAB",
        "note": "底部左侧固定位置，文案是当前社区名称，会随切换社区变化，不能绑定具体 text。",
        "bounds": "[0,2240][360,2408]",
        "normalized": {"x1": 0.0, "x2": 0.333333, "y1": 0.930233, "y2": 1.0},
        "text": "",
        "locator_key": "main_current_community_tab",
    },
    {
        "legacy_id": 138,
        "name": "semantic_v2.main.shop_tab",
        "object": "商城TAB",
        "note": "底部中间固定位置，当前文案为“商城”。",
        "bounds": "[360,2240][720,2408]",
        "normalized": {"x1": 0.333333, "x2": 0.666667, "y1": 0.930233, "y2": 1.0},
        "text": "",
        "locator_key": "main_shop_tab",
    },
    {
        "legacy_id": 139,
        "name": "semantic_v2.main.message_tab",
        "object": "消息TAB",
        "note": "底部右侧固定位置，当前文案为“消息”。",
        "bounds": "[720,2240][1080,2408]",
        "normalized": {"x1": 0.666667, "x2": 1.0, "y1": 0.930233, "y2": 1.0},
        "text": "",
        "locator_key": "main_message_tab",
    },
]


MAIN_ELEMENT_SPECS = [
    {
        "name": "semantic_v2.login.password_login_switch",
        "page": "登录页",
        "object": "密码登录切换",
        "role": "按钮",
        "resource_id": rid("tvPasswordLogin"),
        "class_name": "",
        "bounds": "[744,1512][1000,1588]",
        "note": "手机号登录页切换到账号密码登录的入口，来自历史登录用例 resource-id。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.login.phone_input",
        "page": "登录页",
        "object": "手机号输入框",
        "role": "输入框",
        "resource_id": rid("et_number"),
        "class_name": "android.widget.EditText",
        "bounds": "[96,756][984,876]",
        "note": "账号密码登录手机号输入框，来自历史登录用例 resource-id。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.login.password_input",
        "page": "登录页",
        "object": "密码输入框",
        "role": "输入框",
        "resource_id": rid("etPassword"),
        "class_name": "android.widget.EditText",
        "bounds": "[96,900][984,1020]",
        "note": "账号密码登录密码输入框，来自历史登录用例 resource-id。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.login.agreement_checkbox",
        "page": "登录页",
        "object": "用户协议勾选框",
        "role": "复选框",
        "resource_id": rid("cbkAgree"),
        "class_name": "android.widget.CheckBox",
        "bounds": "[80,1320][144,1384]",
        "note": "登录前用户协议勾选框，来自历史登录用例 resource-id。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.login.submit_button",
        "page": "登录页",
        "object": "登录按钮",
        "role": "按钮",
        "resource_id": rid("btnLogin"),
        "class_name": "",
        "bounds": "[96,1180][984,1300]",
        "note": "登录页提交按钮，同时可作为退出登录后回到登录页的稳定断言。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.main.home_container",
        "page": "社区首页",
        "object": "首页主容器",
        "role": "容器",
        "resource_id": rid("fragment_container"),
        "class_name": "android.widget.FrameLayout",
        "bounds": "[0,0][1080,2240]",
        "note": "登录成功后主页面内容容器。用于登录成功断言，避免底部坐标类元素造成假阳性。",
    },
    {
        "name": "semantic_v2.community.preview_follow_bar",
        "page": "未关注社区首页",
        "object": "预览关注提示条",
        "role": "状态提示",
        "resource_id": rid("previewLayout"),
        "class_name": "android.view.ViewGroup",
        "bounds": "[0,2072][1080,2240]",
        "note": "未关注社区首页底部预览提示条。关注成功后该提示条应消失，用于替代易变的成功文案断言。",
    },
    {
        "name": "semantic_v2.community.follow_button",
        "page": "未关注社区首页",
        "object": "关注社区",
        "role": "按钮",
        "resource_id": rid("btnJoinServer"),
        "class_name": "androidx.appcompat.widget.LinearLayoutCompat",
        "bounds": "[768,2108][1032,2204]",
        "note": "未关注社区首页底部预览条右侧关注按钮，按钮文案为“关注社区”。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.community.more_bottom_sheet",
        "page": "社区首页更多菜单",
        "object": "更多菜单面板",
        "role": "容器",
        "resource_id": rid("bottomPopupContainer"),
        "class_name": "android.widget.LinearLayout",
        "bounds": "[0,0][1080,2408]",
        "note": "社区首页右上角更多按钮拉起的底部菜单容器，用于确认菜单已展开。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.community.exit_entry",
        "page": "社区首页更多菜单",
        "object": "退出社区",
        "role": "按钮",
        "resource_id": rid("cv_exit"),
        "class_name": "android.widget.TextView",
        "bounds": "[48,2150][1032,2294]",
        "note": "已关注社区更多菜单底部的退出社区入口。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.community.exit_confirm_title",
        "page": "退出社区确认弹窗",
        "object": "退出社区标题",
        "role": "弹窗标题",
        "resource_id": rid("dialog_hint_title"),
        "class_name": "android.widget.TextView",
        "bounds": "[444,1050][636,1115]",
        "note": "退出社区二次确认弹窗标题。",
    },
    {
        "name": "semantic_v2.community.exit_confirm_message",
        "page": "退出社区确认弹窗",
        "object": "退出社区确认文案",
        "role": "弹窗文案",
        "resource_id": rid("dialog_hint_message"),
        "class_name": "android.widget.TextView",
        "bounds": "[85,1151][994,1274]",
        "note": "退出社区二次确认弹窗内容文案，文案中的天数可能变化，不绑定完整 text。",
    },
    {
        "name": "semantic_v2.hall.message_list",
        "page": "全员大厅",
        "object": "消息列表",
        "role": "列表",
        "resource_id": rid("rv_chat"),
        "class_name": "androidx.recyclerview.widget.RecyclerView",
        "bounds": "[0,414][1080,2202]",
        "note": "全员大厅聊天消息列表，用于判断已进入大厅和发送后消息展示。",
    },
    {
        "name": "semantic_v2.hall.message_text",
        "page": "全员大厅",
        "object": "消息文本",
        "role": "文本",
        "resource_id": rid("tv_text"),
        "class_name": "android.widget.TextView",
        "bounds": "[204,2040][348,2172]",
        "note": "全员大厅单条消息文本节点，断言时按本次输入内容动态匹配。",
    },
    {
        "name": "semantic_v2.hall.input",
        "page": "全员大厅",
        "object": "聊天输入框",
        "role": "输入框",
        "resource_id": rid("chat_message_input"),
        "class_name": "android.widget.EditText",
        "bounds": "[72,2272][804,2337]",
        "note": "全员大厅底部聊天输入框。龟速模式打开时可能显示发言间隔提示，但本用例只验证基础发消息。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.hall.unfollow_input_entry",
        "page": "未关注社区全员大厅",
        "object": "聊天区入口",
        "role": "入口",
        "resource_id": rid("ll_input"),
        "class_name": "androidx.appcompat.widget.LinearLayoutCompat",
        "bounds": "[36,2240][1044,2372]",
        "note": "未关注态大厅底部聊天区外层入口。内部输入框 disabled，点击外层入口会触发关注社区弹窗。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.hall.follow_required_title",
        "page": "关注社区引导弹窗",
        "object": "关注社区标题",
        "role": "弹窗标题",
        "resource_id": rid("dialog_hint_title"),
        "class_name": "android.widget.TextView",
        "text": "关注社区",
        "bounds": "[444,1050][636,1115]",
        "note": "未关注社区全员大厅点击聊天区后展示的关注引导弹窗标题。",
    },
    {
        "name": "semantic_v2.hall.follow_required_message",
        "page": "关注社区引导弹窗",
        "object": "关注社区提示文案",
        "role": "弹窗文案",
        "resource_id": rid("dialog_hint_message"),
        "class_name": "android.widget.TextView",
        "text": "你目前正处于逛一逛状态，你确定要关注该社区吗？",
        "bounds": "[85,1151][994,1274]",
        "note": "未关注态操作受限时的关注引导文案，用于校验业务限制被正确触发。",
    },
    {
        "name": "semantic_v2.hall.send_button",
        "page": "全员大厅",
        "object": "发送消息",
        "role": "按钮",
        "resource_id": rid("send_btn"),
        "class_name": "android.widget.TextView",
        "bounds": "[960,2250][1044,2370]",
        "note": "全员大厅输入文字后右侧出现的发送按钮；未输入时同位置可能是加号按钮。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.main.bottom_navigation",
        "page": "主页面",
        "object": "底部导航栏",
        "role": "容器",
        "resource_id": rid("bottomNavigationBar"),
        "class_name": "android.widget.FrameLayout",
        "bounds": "[0,2240][1080,2408]",
        "note": "APP 主页面底部导航容器，用于登录成功和主页面状态断言。",
    },
    {
        "name": "semantic_v2.main.message_page_container",
        "page": "消息页",
        "object": "消息列表",
        "role": "容器",
        "resource_id": rid("rv_conversation"),
        "class_name": "androidx.recyclerview.widget.RecyclerView",
        "bounds": "[0,600][1080,2240]",
        "note": "消息页会话列表容器，用于验证点击消息 Tab 后已经进入消息页。",
    },
    {
        "name": "semantic_v2.main.message_search_entry",
        "page": "消息页",
        "object": "会话搜索入口",
        "role": "页面入口",
        "resource_id": rid("searchInput"),
        "class_name": "android.view.ViewGroup",
        "bounds": "[0,324][1080,468]",
        "note": "消息页顶部搜索入口，后续补充会话搜索用例时复用。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.message.search_input",
        "page": "消息搜索页",
        "object": "搜索输入框",
        "role": "输入框",
        "resource_id": rid("etContent"),
        "class_name": "android.widget.EditText",
        "bounds": "[240,126][900,234]",
        "note": "消息搜索页顶部输入框，支持按 NN 号或用户昵称搜索。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.message.search_submit",
        "page": "消息搜索页",
        "object": "搜索",
        "role": "按钮",
        "resource_id": rid("tvSearch"),
        "class_name": "android.widget.TextView",
        "text": "搜索",
        "bounds": "[930,126][1050,234]",
        "note": "消息搜索页右上角搜索按钮。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.message.search_result_list",
        "page": "消息搜索页",
        "object": "搜索结果列表",
        "role": "列表",
        "resource_id": rid("rv_content"),
        "class_name": "androidx.recyclerview.widget.RecyclerView",
        "bounds": "[0,375][1080,2408]",
        "note": "消息搜索结果列表容器，具体是否有结果由业务断言校验。",
    },
    {
        "name": "semantic_v2.dynamic.list_container",
        "page": "动态列表页",
        "object": "动态列表",
        "role": "列表",
        "resource_id": rid("rv_my_moments"),
        "class_name": "androidx.recyclerview.widget.RecyclerView",
        "bounds": "[0,252][1080,2408]",
        "note": "个人主页动态列表容器，用于验证动态流已展示并可滚动。",
    },
    {
        "name": "semantic_v2.dynamic.first_feed_item",
        "page": "动态列表页",
        "object": "首条动态",
        "role": "列表项",
        "resource_id": rid("feedItemRoot"),
        "class_name": "android.view.ViewGroup",
        "bounds": "[0,854][1080,1889]",
        "note": "动态列表中的首条动态根节点。列表数据会变化，不绑定发布文案或标题。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.dynamic.first_feed_content",
        "page": "动态列表页",
        "object": "首条动态内容",
        "role": "内容区",
        "resource_id": rid("flDynamicContent"),
        "class_name": "android.widget.FrameLayout",
        "bounds": "[0,1046][1080,1757]",
        "note": "首条动态的内容区域，点击后进入动态内容预览页。比点击整条根节点更不容易点到更多/点赞/评论。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.dynamic.preview_container",
        "page": "动态内容预览页",
        "object": "动态内容预览容器",
        "role": "容器",
        "resource_id": rid("viewPager"),
        "class_name": "androidx.viewpager.widget.ViewPager",
        "bounds": "[0,0][1080,2408]",
        "note": "动态图片/视频预览页的公共容器，用于兼容图片动态和视频动态。",
    },
    {
        "name": "semantic_v2.dynamic.preview_player",
        "page": "动态内容预览页",
        "object": "视频预览播放器",
        "role": "容器",
        "resource_id": rid("playerRoot"),
        "class_name": "android.widget.FrameLayout",
        "bounds": "[0,0][1080,2408]",
        "note": "动态视频预览页播放器根容器，用于确认已进入动态内容预览。",
    },
    {
        "name": "semantic_v2.dynamic.preview_back",
        "page": "动态内容预览页",
        "object": "返回",
        "role": "按钮",
        "resource_id": rid("iv_back"),
        "class_name": "android.widget.TextView",
        "bounds": "[36,144][108,216]",
        "note": "动态视频预览页顶部返回按钮，点击后回到动态列表。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.main.shop_page_container",
        "page": "商城页",
        "object": "商城 Web 容器",
        "role": "容器",
        "resource_id": rid("webContentContainer"),
        "class_name": "android.widget.FrameLayout",
        "bounds": "[0,0][1080,2240]",
        "note": "商城页 Web 容器，用于验证点击商城 Tab 后已经进入商城页。",
    },
    {
        "name": "semantic_v2.main.community_drawer_panel",
        "page": "社区抽屉",
        "object": "社区抽屉面板",
        "role": "容器",
        "resource_id": rid("leftDrawerContainer"),
        "class_name": "android.widget.FrameLayout",
        "bounds": "[0,0][780,2408]",
        "note": "左侧社区抽屉整体面板，用于验证抽屉已展开。",
    },
    {
        "name": "semantic_v2.main.community_drawer_list",
        "page": "社区抽屉",
        "object": "社区列表",
        "role": "列表",
        "resource_id": rid("rvServer"),
        "class_name": "androidx.recyclerview.widget.RecyclerView",
        "bounds": "[0,1231][780,1897]",
        "note": "左侧抽屉中的社区列表，用于验证已加载用户加入的社区。",
    },
    {
        "name": "semantic_v2.settings.menu_entry",
        "page": "消息页",
        "object": "设置侧边栏入口",
        "role": "按钮",
        "resource_id": rid("menu"),
        "class_name": "android.widget.ImageView",
        "bounds": "[948,156][1044,252]",
        "note": "消息页右上角菜单，点击后打开右侧个人/设置侧边栏。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.settings.drawer_container",
        "page": "设置侧边栏",
        "object": "设置侧边栏容器",
        "role": "容器",
        "resource_id": rid("rightDrawerContainer"),
        "class_name": "android.widget.FrameLayout",
        "bounds": "[300,0][1080,2408]",
        "note": "右侧个人/设置侧边栏整体容器，用于断言设置侧边栏已打开。",
    },
    {
        "name": "semantic_v2.settings.notification_entry",
        "page": "设置侧边栏",
        "object": "通知设置",
        "role": "页面入口",
        "resource_id": "",
        "class_name": "",
        "text": "通知设置",
        "bounds": "[468,354][636,403]",
        "note": "设置侧边栏中的通知设置入口。无稳定 resource-id，优先按文案断言/点击。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.settings.privacy_entry",
        "page": "设置侧边栏",
        "object": "隐私设置",
        "role": "页面入口",
        "resource_id": "",
        "class_name": "",
        "text": "隐私设置",
        "bounds": "[468,510][636,559]",
        "note": "设置侧边栏中的隐私设置入口。无稳定 resource-id，优先按文案断言/点击。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.settings.about_entry",
        "page": "设置侧边栏",
        "object": "关于NN",
        "role": "页面入口",
        "resource_id": "",
        "class_name": "",
        "text": "关于NN",
        "bounds": "[468,2130][616,2179]",
        "note": "设置侧边栏中的关于 NN 入口，可作为设置侧边栏底部稳定菜单项。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.settings.notification_title",
        "page": "通知设置页",
        "object": "通知设置标题",
        "role": "文本",
        "resource_id": rid("tvTitle"),
        "class_name": "android.widget.TextView",
        "text": "通知设置",
        "bounds": "[444,148][636,213]",
        "note": "通知设置详情页顶部标题，用于确认从设置侧边栏进入了正确页面。",
    },
    {
        "name": "semantic_v2.settings.notification_msg_switch",
        "page": "通知设置页",
        "object": "消息通知总开关",
        "role": "开关",
        "resource_id": rid("msg_switch_compose_view"),
        "class_name": "androidx.compose.ui.platform.ComposeView",
        "bounds": "[903,428][1032,497]",
        "note": "通知设置页消息通知总开关容器。P0 用例只断言存在，不点击改变用户配置。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.settings.notification_category_list",
        "page": "通知设置页",
        "object": "通知分类开关列表",
        "role": "列表",
        "resource_id": rid("rv_msg_notify_category_list"),
        "class_name": "androidx.recyclerview.widget.RecyclerView",
        "bounds": "[0,761][1080,1229]",
        "note": "通知设置页活动推送、私聊、好友申请等分类开关列表。",
    },
    {
        "name": "semantic_v2.settings.notification_activity_push",
        "page": "通知设置页",
        "object": "活动推送",
        "role": "文本",
        "resource_id": rid("tvTitle"),
        "class_name": "android.widget.TextView",
        "text": "活动推送",
        "bounds": "[48,807][240,872]",
        "note": "通知设置页分类开关项，用于验证通知分类列表内容已加载。",
    },
    {
        "name": "semantic_v2.search.input",
        "page": "全局搜索页",
        "object": "搜索输入框",
        "role": "输入框",
        "resource_id": rid("etContent"),
        "class_name": "android.widget.EditText",
        "text": "",
        "bounds": "[240,126][900,234]",
        "note": "全局搜索页输入框，可输入社区号、社区名、用户名称或 ID。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.search.submit",
        "page": "全局搜索页",
        "object": "搜索按钮",
        "role": "按钮",
        "resource_id": rid("tvSearch"),
        "class_name": "android.widget.TextView",
        "text": "搜索",
        "bounds": "[930,126][1050,234]",
        "note": "全局搜索页右上角搜索提交按钮。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.search.result_list",
        "page": "全局搜索页",
        "object": "搜索结果列表",
        "role": "列表",
        "resource_id": rid("recyclerView"),
        "class_name": "androidx.recyclerview.widget.RecyclerView",
        "bounds": "[0,254][1080,2408]",
        "note": f"全局搜索结果列表。输入目标社区关键词 {TEST_COMMUNITY_KEYWORD or '未配置'} 后应展示社区结果。",
    },
    {
        "name": "semantic_v2.search.result_section_community",
        "page": "全局搜索页",
        "object": "社区结果分组",
        "role": "文本",
        "resource_id": rid("tvTitle"),
        "class_name": "android.widget.TextView",
        "text": "社区",
        "bounds": "[48,302][1032,359]",
        "note": "全局搜索结果中的社区分组标题。",
    },
    {
        "name": "semantic_v2.search.community_result_item",
        "page": "全局搜索页",
        "object": "社区搜索结果行",
        "role": "卡片",
        "resource_id": rid("rootView"),
        "class_name": "android.view.ViewGroup",
        "bounds": "[0,377][1080,677]",
        "note": f"目标社区 {TEST_COMMUNITY_KEYWORD or '未配置'} 搜索结果整行热区，点击可进入社区。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.search.community_result_name",
        "page": "全局搜索页",
        "object": TEST_COMMUNITY_NAME,
        "role": "文本",
        "resource_id": rid("tvName"),
        "class_name": "android.widget.TextView",
        "text": TEST_COMMUNITY_NAME,
        "bounds": "[477,418][618,475]",
        "note": f"目标社区 {TEST_COMMUNITY_KEYWORD or '未配置'} 对应的社区昵称，用于验证搜索结果正确。",
    },
    {
        "name": "semantic_v2.drawer.community_chengliuxiang",
        "page": "社区抽屉",
        "object": "橙留香",
        "role": "列表项",
        "resource_id": rid("tvServerName"),
        "class_name": "android.widget.TextView",
        "text": "橙留香",
        "bounds": "[216,1173][342,1230]",
        "note": "社区抽屉中的橙留香社区项。点击文本中心可触发父级社区行切换。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.main.current_community_name_chengliuxiang",
        "page": "底部TAB",
        "object": "橙留香当前社区名",
        "role": "文本",
        "resource_id": rid("main_tab_item_text"),
        "class_name": "android.widget.TextView",
        "text": "橙留香",
        "bounds": "[135,2355][225,2396]",
        "note": "底部左侧当前社区 Tab 文案。用于验证社区抽屉切换到橙留香后生效。",
    },
    {
        "name": "semantic_v2.article.list_container",
        "page": "社区首页",
        "object": "文章插件列表",
        "role": "列表",
        "resource_id": rid("rvRooms"),
        "class_name": "androidx.recyclerview.widget.RecyclerView",
        "bounds": "[0,713][1080,2240]",
        "note": "社区首页内容流容器，房间列表上方展示文章插件卡片。",
    },
    {
        "name": "semantic_v2.article.first_card",
        "page": "社区首页",
        "object": "文章插件卡片",
        "role": "卡片",
        "resource_id": rid("ll_content"),
        "class_name": "android.widget.LinearLayout",
        "bounds": "[42,1211][1032,1355]",
        "note": "当前可见第一条文章插件卡片整行热区，点击可进入文章详情。",
    },
    {
        "name": "semantic_v2.article.first_tag",
        "page": "社区首页",
        "object": "文章标签",
        "role": "标签",
        "resource_id": rid("ctvTitleTag"),
        "class_name": "android.widget.LinearLayout",
        "bounds": "[42,1253][150,1313]",
        "note": "文章插件卡片左侧标签，如公告、攻略、活动、#。",
    },
    {
        "name": "semantic_v2.article.first_title",
        "page": "社区首页",
        "object": "文章标题",
        "role": "文本",
        "resource_id": rid("tvTitle"),
        "class_name": "android.widget.TextView",
        "text": "23.4.2版更新公告",
        "bounds": "[162,1250][1032,1315]",
        "note": "当前可见第一条文章标题，用于文章插件展示断言。标题是测试社区现有数据，若数据变化需更新。",
    },
    {
        "name": "semantic_v2.article.detail_back",
        "page": "文章详情页",
        "object": "返回",
        "role": "按钮",
        "resource_id": rid("ifvBack"),
        "class_name": "android.widget.TextView",
        "bounds": "[36,132][132,228]",
        "note": "文章详情页顶部返回按钮。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.article.detail_page_title",
        "page": "文章详情页",
        "object": "动态详情",
        "role": "文本",
        "resource_id": rid("tvTitle"),
        "class_name": "android.widget.TextView",
        "text": "动态详情",
        "bounds": "[444,148][636,213]",
        "note": "文章详情页顶部页面标题，用于断言已进入详情页。",
    },
    {
        "name": "semantic_v2.article.detail_content_title",
        "page": "文章详情页",
        "object": "文章详情标题",
        "role": "文本",
        "resource_id": rid("tvTitle"),
        "class_name": "android.widget.TextView",
        "text": "23.4.2版更新公告",
        "bounds": "[48,312][1032,384]",
        "note": "文章详情正文标题，用于验证进入的文章详情内容。",
    },
    {
        "name": "semantic_v2.article.detail_content_container",
        "page": "文章详情页",
        "object": "文章正文容器",
        "role": "容器",
        "resource_id": rid("htmlView"),
        "class_name": "android.widget.ScrollView",
        "bounds": "[48,516][1032,608]",
        "note": "文章详情正文区域容器。",
    },
    {
        "name": "semantic_v2.settings.logout_entry",
        "page": "设置侧边栏",
        "object": "退出登录",
        "role": "按钮",
        "resource_id": "",
        "class_name": "",
        "text": "退出登录",
        "bounds": "[468,2234][636,2283]",
        "note": "设置侧边栏底部退出登录入口。需要先在设置侧边栏内向上滑动到底部。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.common.logout_confirm_message",
        "page": "二级确认弹窗",
        "object": "退出登录确认文案",
        "role": "文本",
        "resource_id": rid("dialog_hint_message"),
        "class_name": "android.widget.TextView",
        "text": "确认退出？",
        "bounds": "[85,1126][994,1198]",
        "note": "退出登录二级确认弹窗文案，用于断言弹窗已打开。",
    },
    {
        "name": "semantic_v2.common.dialog_cancel",
        "page": "二级确认弹窗",
        "object": "取消",
        "role": "按钮",
        "resource_id": rid("dialog_hint_cancel"),
        "class_name": "androidx.appcompat.widget.LinearLayoutCompat",
        "bounds": "[157,1270][517,1390]",
        "note": "二级确认弹窗取消按钮，公共组件。",
        "clickable": True,
    },
    {
        "name": "semantic_v2.common.dialog_confirm",
        "page": "二级确认弹窗",
        "object": "确认",
        "role": "按钮",
        "resource_id": rid("dialog_hint_confirm"),
        "class_name": "androidx.appcompat.widget.LinearLayoutCompat",
        "bounds": "[562,1270][922,1390]",
        "note": "二级确认弹窗确认按钮，公共组件。退出登录用例完整确认前需保证可自动重新登录。",
        "clickable": True,
    },
]


@dataclass
class StepSpec:
    kind: str
    name: str
    element: str = ""
    value: Any = None
    duration: float = 1
    clear_first: bool = True
    expected_exists: bool = True


@dataclass
class CaseSpec:
    code: str
    module: str
    title: str
    precondition: str
    assertions: str
    steps: list[StepSpec] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def case_name(self) -> str:
        prefix = "【待补元素】" if self.missing else "【可执行】"
        return f"{prefix}{self.code} {self.module}-{self.title}"


def build_step(index: int, spec: StepSpec, elements: dict[str, AppElement]) -> dict[str, Any]:
    step = {
        "id": f"aug_p0_{index:02d}_{spec.kind}",
        "kind": "atomic",
        "name": spec.name,
        "type": spec.kind,
        "config": {
            "timeout": 10,
            "selector_type": "selector",
            "selector": "",
            "image_scope": "common",
            "image_threshold": 0.7,
        },
    }
    if spec.kind in {"wait", "sleep"}:
        step["config"].update({"duration": spec.duration, "selector_type": "image"})
        return step
    if spec.kind == "swipe":
        step["config"].update({
            "start": "540,1850",
            "end": "540,820",
            "duration": spec.duration,
            "selector_type": "pos",
        })
        return step
    if spec.kind in {"keyevent", "back"}:
        step["config"].update({
            "keyevent": spec.value or "BACK",
            "duration": spec.duration,
            "selector_type": "image",
        })
        return step
    if spec.kind == "back_until":
        element = elements.get(spec.element)
        if not element:
            raise CommandError(f"Element not found for step '{spec.name}': {spec.element}")
        step["config"].update({
            "target_element_id": element.id,
            "target_selector": element.config.get("resource_id") or element.name,
            "target_selector_type": "selector",
            "max_backs": 3,
            "duration": spec.duration,
            "selector_type": "business",
        })
        return step
    if spec.kind == "launch_activity":
        config = spec.value if isinstance(spec.value, dict) else {}
        step["config"].update({
            "package": config.get("package", APP_PACKAGE),
            "activity": config.get("activity", MAIN_ACTIVITY),
            "force_stop": bool(config.get("force_stop", False)),
            "duration": spec.duration,
            "selector_type": "system",
        })
        return step
    if spec.kind == "click_available_voice_room":
        step["config"].update({
            "room_type": spec.value or "any",
            "duration": spec.duration,
            "selector_type": "business",
        })
        return step
    if spec.kind == "assert_voice_room_type":
        step["config"].update({
            "expected": spec.value or "normal",
            "room_type": spec.value or "normal",
            "duration": spec.duration,
            "selector_type": "business",
        })
        return step
    if spec.kind == "click_member_hall_entry":
        step["config"].update({
            "duration": spec.duration,
            "selector_type": "business",
            "timeout": 10,
        })
        return step
    if spec.kind == "assert_member_hall_opened":
        step["config"].update({
            "duration": spec.duration,
            "selector_type": "business",
            "timeout": spec.duration or 8,
        })
        return step
    if spec.kind == "ensure_personal_dynamic_list":
        step["config"].update({
            "duration": spec.duration,
            "selector_type": "business",
            "timeout": spec.duration or 12,
            "package": APP_PACKAGE,
            "phone": "{{phone}}",
            "password": "{{password}}",
        })
        return step
    if spec.kind == "assert_hall_message_sent":
        step["config"].update({
            "duration": spec.duration,
            "selector_type": "business",
            "timeout": spec.duration or 8,
            "expected": spec.value or "",
        })
        return step
    if spec.kind == "remember_first_message_conversation":
        step["config"].update({
            "duration": spec.duration,
            "selector_type": "business",
            "timeout": spec.duration or 8,
        })
        return step
    if spec.kind == "assert_message_search_results":
        step["config"].update({
            "duration": spec.duration,
            "selector_type": "business",
            "timeout": spec.duration or 8,
            "expected": spec.value or "",
        })
        return step
    if spec.kind == "ensure_account_logged_in":
        step["config"].update({
            "phone": "{{phone}}",
            "password": "{{password}}",
            "duration": spec.duration,
            "selector_type": "business",
            "timeout": 20,
        })
        return step
    if spec.kind == "ensure_logged_out":
        step["config"].update({
            "duration": spec.duration,
            "selector_type": "business",
            "timeout": spec.duration or 20,
            "package": APP_PACKAGE,
        })
        return step
    if spec.kind in {"clear_runtime_blockers", "handle_startup_blockers"}:
        step["config"].update({
            "duration": spec.duration,
            "selector_type": "business",
            "timeout": spec.duration or 4,
        })
        return step
    if spec.kind in {
        "ensure_unfollowed_community_home",
        "ensure_followed_community_home",
        "ensure_unfollowed_member_hall",
    }:
        step["config"].update({
            "duration": spec.duration,
            "selector_type": "business",
            "timeout": spec.duration or 12,
            "community_keywords": spec.value or TEST_COMMUNITY_KEYWORD,
        })
        return step
    if spec.kind == "assert_logout_confirm_dialog":
        step["config"].update({
            "duration": spec.duration,
            "selector_type": "business",
            "timeout": spec.duration or 4,
            "expected": spec.value or "确认退出？",
        })
        return step
    if spec.kind in {"remember_current_community", "click_other_followed_community", "assert_current_community_switched"}:
        step["config"].update({
            "duration": spec.duration,
            "selector_type": "business",
            "timeout": spec.duration or 8,
        })
        return step
    if spec.kind in {"assert_article_plugin_card", "click_article_plugin_card"}:
        step["config"].update({
            "duration": spec.duration,
            "selector_type": "business",
        })
        return step
    if spec.kind == "handle_slider":
        step["config"].update({
            "duration": spec.duration,
            "selector_type": "business",
            "success_element_id": elements["semantic_v2.main.home_container"].id,
            "success_selector_type": "selector",
            "timeout": 6,
            "post_login_timeout": 10,
        })
        return step

    element = elements.get(spec.element)
    if not element:
        raise CommandError(f"Element not found for step '{spec.name}': {spec.element}")

    step["config"].update({
        "element_id": element.id,
        "selector": element.config.get("resource_id") or element.name,
    })
    if spec.kind == "assert":
        step["config"].update({
            "assert_type": "exists",
            "expected_exists": spec.expected_exists,
            "match_mode": "contains",
            "expected": "",
            "retry_interval": 1,
        })
    if spec.kind == "input":
        step["config"].update({
            "value": spec.value or "",
            "clear_first": spec.clear_first,
            "send_enter": False,
        })
    return step


def wait_note(text: str) -> StepSpec:
    return StepSpec("wait", f"待补语义元素：{text}", duration=0.5)


def ensure_community_home_steps() -> list[StepSpec]:
    return [
        StepSpec(
            "launch_activity",
            "冷启动 APP",
            value={"package": APP_PACKAGE, "activity": "", "force_stop": True},
            duration=2,
        ),
        StepSpec("ensure_account_logged_in", "确认账号处于登录态", duration=1),
        StepSpec("click", "切到当前社区首页 Tab", "semantic_v2.main.current_community_tab"),
        StepSpec("wait", "等待社区首页稳定", duration=1),
    ]


def ensure_voice_room_area_steps() -> list[StepSpec]:
    return ensure_community_home_steps() + [
        StepSpec("swipe", "滑动到语音房操作区", duration=0.45),
        StepSpec("wait", "等待语音房操作区稳定", duration=0.8),
    ]


def enter_room_steps() -> list[StepSpec]:
    return [
        StepSpec("click_available_voice_room", "点击首个可进入普通语音房整行", value="normal", duration=0.8),
        StepSpec("assert_voice_room_type", "断言进入的是普通语音房", value="normal"),
        StepSpec("wait", "等待进入房间", duration=2),
        StepSpec("assert", "断言房间详情页存在", "semantic_v2.voice.room_container"),
    ]


def exit_room_steps() -> list[StepSpec]:
    return [
        StepSpec("click", "收起房间返回列表", "semantic_v2.voice.room_quit"),
        StepSpec("wait", "等待回到语音房列表", duration=1),
    ]


def enter_publish_steps() -> list[StepSpec]:
    return [
        StepSpec("click", "点击招募队友", "semantic_v2.voice.recruit_teammate"),
        StepSpec("wait", "等待发布组队页", duration=2),
        StepSpec("assert", "断言发布组队标题存在", "semantic_v2.voice.publish_title"),
    ]


def password_login_steps(prefix: str = "") -> list[StepSpec]:
    name_prefix = f"{prefix}-" if prefix else ""
    return [
        StepSpec("click", f"{name_prefix}切换到密码登录", "semantic_v2.login.password_login_switch"),
        StepSpec("wait", f"{name_prefix}等待密码登录页", duration=0.8),
        StepSpec("assert", f"{name_prefix}断言手机号输入框存在", "semantic_v2.login.phone_input"),
        StepSpec("input", f"{name_prefix}输入手机号", "semantic_v2.login.phone_input", value="{{phone}}"),
        StepSpec("input", f"{name_prefix}输入密码", "semantic_v2.login.password_input", value="{{password}}"),
        StepSpec("click", f"{name_prefix}勾选用户协议", "semantic_v2.login.agreement_checkbox"),
        StepSpec("click", f"{name_prefix}点击登录", "semantic_v2.login.submit_button"),
        StepSpec("handle_slider", f"{name_prefix}处理滑块验证", duration=1),
        StepSpec("wait", f"{name_prefix}等待进入首页", duration=3),
        StepSpec("assert", f"{name_prefix}断言进入首页主容器", "semantic_v2.main.home_container"),
        StepSpec("assert", f"{name_prefix}断言底部导航栏存在", "semantic_v2.main.bottom_navigation"),
    ]


def back_step(name: str = "返回上一页") -> StepSpec:
    return StepSpec("keyevent", name, value="BACK", duration=0.8)


CASE_SPECS = [
    CaseSpec("APP-P0-001", "登录", "账号密码正常登录", "测试账号可用，账号未被封禁。", "先确认处于登出态，再输入账号密码，登录成功进入社区首页。", steps=[
        StepSpec("ensure_logged_out", "确认处于登出态", duration=20),
    ] + password_login_steps()),
    CaseSpec("APP-P0-002", "登录", "退出登录", "账号已登录。", "点击退出登录后展示确认弹窗；确认退出后回到登录页，并可自动重新登录恢复状态。", steps=ensure_community_home_steps() + [
        StepSpec("click", "点击消息 Tab", "semantic_v2.main.message_tab"),
        StepSpec("wait", "等待消息页", duration=1),
        StepSpec("click", "点击右上角设置侧边栏入口", "semantic_v2.settings.menu_entry"),
        StepSpec("wait", "等待设置侧边栏展开", duration=1),
        StepSpec("assert", "断言设置侧边栏容器存在", "semantic_v2.settings.drawer_container"),
        StepSpec("swipe", "滑动到退出登录入口", duration=0.65),
        StepSpec("wait", "等待底部菜单稳定", duration=0.5),
        StepSpec("click", "点击退出登录", "semantic_v2.settings.logout_entry"),
        StepSpec("wait", "等待退出登录确认弹窗", duration=0.8),
        StepSpec("assert_logout_confirm_dialog", "断言退出登录确认弹窗完整展示", value="确认退出？", duration=2),
        StepSpec("click", "点击确认退出登录", "semantic_v2.common.dialog_confirm"),
        StepSpec("wait", "等待回到登录页", duration=2),
        StepSpec("assert", "断言密码登录切换入口存在", "semantic_v2.login.password_login_switch"),
    ] + password_login_steps("退出后恢复登录")),
    CaseSpec("APP-P0-003", "底部TAB", "基础切换", "账号已登录，停留在主页面。", "当前社区、商城、消息三个入口均可点击并返回。", steps=ensure_community_home_steps() + [
        StepSpec("assert", "断言当前社区 Tab 存在", "semantic_v2.main.current_community_tab"),
        StepSpec("click", "点击商城 Tab", "semantic_v2.main.shop_tab"),
        StepSpec("wait", "等待商城页切换", duration=1),
        StepSpec("click", "点击消息 Tab", "semantic_v2.main.message_tab"),
        StepSpec("wait", "等待消息页切换", duration=1),
        StepSpec("click", "回到当前社区 Tab", "semantic_v2.main.current_community_tab"),
    ]),
    CaseSpec("APP-P0-004", "社区抽屉", "点击入口打开社区抽屉", "账号已登录。", "左侧社区抽屉展开，社区列表展示。", steps=ensure_community_home_steps() + [
        StepSpec("click", "点击左侧社区列表入口", "semantic_v2.leftserverguideanim"),
        StepSpec("wait", "等待社区抽屉展开", duration=1),
        StepSpec("assert", "断言社区抽屉面板存在", "semantic_v2.main.community_drawer_panel"),
        StepSpec("assert", "断言社区列表存在", "semantic_v2.main.community_drawer_list"),
        back_step("关闭社区抽屉"),
    ]),
    CaseSpec("APP-P0-005", "社区抽屉", "切换社区", "账号至少关注两个社区。", "在社区抽屉选择任意其他已关注社区后，底部当前社区 Tab 切换为所选社区。", steps=ensure_community_home_steps() + [
        StepSpec("remember_current_community", "记录切换前社区", duration=5),
        StepSpec("click", "点击左侧社区列表入口", "semantic_v2.leftserverguideanim"),
        StepSpec("wait", "等待社区抽屉展开", duration=1),
        StepSpec("assert", "断言社区抽屉面板存在", "semantic_v2.main.community_drawer_panel"),
        StepSpec("assert", "断言社区列表存在", "semantic_v2.main.community_drawer_list"),
        StepSpec("click_other_followed_community", "选择其他已关注社区", duration=8),
        StepSpec("wait", "等待社区切换完成", duration=2),
        StepSpec("assert_current_community_switched", "断言底部当前社区切换为所选社区", duration=8),
    ]),
    CaseSpec("APP-P0-006", "发现/搜索", "搜索社区并进入", "存在可搜索的目标社区。", f"搜索结果展示 {TEST_COMMUNITY_NAME}，点击后进入社区首页。", steps=ensure_community_home_steps() + [
        StepSpec("click", "点击全局搜索入口", "semantic_v2.tvhinttext"),
        StepSpec("wait", "等待全局搜索页", duration=1),
        StepSpec("assert", "断言搜索输入框存在", "semantic_v2.search.input"),
        StepSpec("input", "输入社区关键词", "semantic_v2.search.input", value=TEST_COMMUNITY_KEYWORD, clear_first=False),
        StepSpec("click", "点击搜索按钮", "semantic_v2.search.submit"),
        StepSpec("wait", "等待搜索结果", duration=2),
        StepSpec("assert", "断言搜索结果列表存在", "semantic_v2.search.result_list"),
        StepSpec("assert", "断言社区结果分组存在", "semantic_v2.search.result_section_community"),
        StepSpec("assert", f"断言 {TEST_COMMUNITY_NAME} 结果存在", "semantic_v2.search.community_result_name"),
        StepSpec("click", f"点击 {TEST_COMMUNITY_NAME} 社区结果", "semantic_v2.search.community_result_item"),
        StepSpec("wait", "等待进入社区首页", duration=2),
        StepSpec("assert", "断言进入社区首页主容器", "semantic_v2.main.home_container"),
        StepSpec("assert", "断言底部导航栏存在", "semantic_v2.main.bottom_navigation"),
    ]),
    CaseSpec("APP-P0-007", "社区首页", "基础展示", "账号已登录并停留在社区首页。", "搜索、更多、顶部社区内容入口和底部 Tab 可见。", steps=ensure_community_home_steps() + [
        StepSpec("assert", "断言全局搜索入口存在", "semantic_v2.tvhinttext"),
        StepSpec("assert", "断言更多按钮存在", "semantic_v2.ivmore"),
        StepSpec("assert", "断言当前社区 Tab 存在", "semantic_v2.main.current_community_tab"),
    ]),
    CaseSpec("APP-P0-008", "社区首页", "关注社区", "进入未关注社区。", "关注成功，关注状态变化。", steps=[
        StepSpec("ensure_unfollowed_community_home", "进入未关注测试社区", value=TEST_COMMUNITY_KEYWORD, duration=18),
        StepSpec("assert", "断言未关注预览提示条存在", "semantic_v2.community.preview_follow_bar"),
        StepSpec("assert", "断言关注社区按钮存在", "semantic_v2.community.follow_button"),
        StepSpec("click", "点击关注社区", "semantic_v2.community.follow_button"),
        StepSpec("wait", "等待关注状态刷新", duration=2),
        StepSpec("assert", "断言未关注预览提示条消失", "semantic_v2.community.preview_follow_bar", expected_exists=False),
    ]),
    CaseSpec("APP-P0-009", "社区首页", "退出或取消关注社区", "当前社区已关注。", "退出成功后自动切换到其他已关注社区。", steps=[
        StepSpec("ensure_followed_community_home", "进入可退出的已关注测试社区", value=TEST_COMMUNITY_KEYWORD, duration=18),
        StepSpec("remember_current_community", "记录退出前当前社区", duration=5),
        StepSpec("click", "点击更多按钮", "semantic_v2.ivmore"),
        StepSpec("wait", "等待更多菜单展开", duration=0.8),
        StepSpec("assert", "断言更多菜单面板存在", "semantic_v2.community.more_bottom_sheet"),
        StepSpec("assert", "断言退出社区入口存在", "semantic_v2.community.exit_entry"),
        StepSpec("click", "点击退出社区", "semantic_v2.community.exit_entry"),
        StepSpec("wait", "等待退出社区确认弹窗", duration=0.8),
        StepSpec("assert", "断言退出社区弹窗标题存在", "semantic_v2.community.exit_confirm_title"),
        StepSpec("assert", "断言退出社区确认文案存在", "semantic_v2.community.exit_confirm_message"),
        StepSpec("assert", "断言取消按钮存在", "semantic_v2.common.dialog_cancel"),
        StepSpec("assert", "断言确认按钮存在", "semantic_v2.common.dialog_confirm"),
        StepSpec("click", "确认退出社区", "semantic_v2.common.dialog_confirm"),
        StepSpec("wait", "等待自动切换到下一个社区", duration=2),
        StepSpec("assert_current_community_switched", "断言当前社区已不是退出前社区", duration=8),
        StepSpec("assert", "断言仍在社区首页主容器", "semantic_v2.main.home_container"),
        StepSpec("assert", "断言底部导航栏存在", "semantic_v2.main.bottom_navigation"),
    ]),
    CaseSpec("APP-P0-010", "社区大厅", "进入全员大厅", "账号已登录并停留在社区首页。", "按入口图标进入全员大厅，成功进入聊天大厅页面，并可返回社区首页。", steps=ensure_community_home_steps() + [
        StepSpec("click_member_hall_entry", "按图标点击全员大厅入口", duration=0.8),
        StepSpec("assert_member_hall_opened", "断言进入全员大厅聊天页", duration=8),
        back_step("从全员大厅返回社区首页"),
        StepSpec("wait", "等待社区首页恢复", duration=1),
        StepSpec("assert", "断言语音房列表恢复", "semantic_v2.voice.voice_room_list"),
    ]),
    CaseSpec("APP-P0-011", "社区大厅", "发送文本消息", "当前社区已关注并可发言。", "消息发送后出现在消息列表中。", steps=ensure_community_home_steps() + [
        StepSpec("click_member_hall_entry", "按图标进入全员大厅", duration=0.8),
        StepSpec("assert_member_hall_opened", "断言进入全员大厅聊天页", duration=8),
        StepSpec("assert", "断言大厅消息列表存在", "semantic_v2.hall.message_list"),
        StepSpec("assert", "断言大厅输入框存在", "semantic_v2.hall.input"),
        StepSpec("input", "输入大厅文本消息", "semantic_v2.hall.input", value="831011"),
        StepSpec("assert", "断言发送按钮出现", "semantic_v2.hall.send_button"),
        StepSpec("click", "点击发送消息", "semantic_v2.hall.send_button"),
        StepSpec("wait", "等待消息上屏", duration=1.5),
        StepSpec("assert_hall_message_sent", "断言本次消息出现在大厅消息列表", duration=8),
        StepSpec("back_until", "返回直到社区首页语音房列表可见", "semantic_v2.voice.voice_room_list", duration=1),
    ]),
    CaseSpec("APP-P0-012", "社区大厅", "未关注触发关注弹窗", "当前社区未关注并停留在全员大厅。", "点击聊天区后弹出关注引导，取消后仍停留在大厅且不改变关注状态。", steps=[
        StepSpec("ensure_unfollowed_member_hall", "进入未关注测试社区全员大厅", value=TEST_COMMUNITY_KEYWORD, duration=24),
        StepSpec("assert", "断言大厅消息列表存在", "semantic_v2.hall.message_list"),
        StepSpec("assert", "断言未关注聊天区入口存在", "semantic_v2.hall.unfollow_input_entry"),
        StepSpec("click", "点击未关注聊天区入口", "semantic_v2.hall.unfollow_input_entry"),
        StepSpec("wait", "等待关注社区弹窗", duration=0.8),
        StepSpec("assert", "断言关注社区弹窗标题存在", "semantic_v2.hall.follow_required_title"),
        StepSpec("assert", "断言关注社区弹窗文案存在", "semantic_v2.hall.follow_required_message"),
        StepSpec("assert", "断言弹窗取消按钮存在", "semantic_v2.common.dialog_cancel"),
        StepSpec("assert", "断言弹窗确认按钮存在", "semantic_v2.common.dialog_confirm"),
        StepSpec("click", "点击取消关闭关注弹窗", "semantic_v2.common.dialog_cancel"),
        StepSpec("wait", "等待弹窗关闭", duration=0.8),
        StepSpec("assert", "断言关注社区弹窗已关闭", "semantic_v2.hall.follow_required_title", expected_exists=False),
        StepSpec("assert", "断言仍停留在全员大厅", "semantic_v2.hall.message_list"),
    ]),
    CaseSpec("APP-P0-013", "动态", "动态列表展示", "账号已登录。", "进入个人动态列表后，动态列表和首条动态可见，列表可滚动且滚动后仍保持动态流结构。", steps=[
        StepSpec("ensure_personal_dynamic_list", "进入个人动态列表", duration=12),
        StepSpec("assert", "断言动态列表存在", "semantic_v2.dynamic.list_container"),
        StepSpec("assert", "断言首条动态存在", "semantic_v2.dynamic.first_feed_item"),
        StepSpec("assert", "断言首条动态内容区存在", "semantic_v2.dynamic.first_feed_content"),
        StepSpec("swipe", "上滑浏览动态列表", duration=0.45),
        StepSpec("wait", "等待动态列表滚动稳定", duration=0.8),
        StepSpec("assert", "断言滚动后仍在动态列表", "semantic_v2.dynamic.list_container"),
        StepSpec("assert", "断言滚动后仍有动态内容", "semantic_v2.dynamic.first_feed_item"),
    ]),
    CaseSpec("APP-P0-014", "动态", "动态内容预览进入返回", "账号已登录，个人动态列表存在可进入的图片或视频动态。", "进入个人动态列表，点击首条动态内容后进入预览页，点击返回后回到动态列表。", steps=[
        StepSpec("ensure_personal_dynamic_list", "进入个人动态列表", duration=12),
        StepSpec("assert", "断言动态列表存在", "semantic_v2.dynamic.list_container"),
        StepSpec("assert", "断言首条动态内容区存在", "semantic_v2.dynamic.first_feed_content"),
        StepSpec("click", "点击首条动态内容区", "semantic_v2.dynamic.first_feed_content"),
        StepSpec("wait", "等待动态内容预览页", duration=1.2),
        StepSpec("assert", "断言动态内容预览容器存在", "semantic_v2.dynamic.preview_container"),
        StepSpec("click", "点击预览页返回", "semantic_v2.dynamic.preview_back"),
        StepSpec("wait", "等待回到动态列表", duration=1),
        StepSpec("assert", "断言回到动态列表", "semantic_v2.dynamic.list_container"),
    ]),
    CaseSpec("APP-P0-015", "插件文章", "文章展示", "社区存在插件文章。", "插件文章卡片可见。", steps=ensure_community_home_steps() + [
        StepSpec("assert", "断言文章插件列表存在", "semantic_v2.article.list_container"),
        StepSpec("assert_article_plugin_card", "按文章标签断言文章插件卡片存在"),
        StepSpec("assert", "断言文章标签存在", "semantic_v2.article.first_tag"),
    ]),
    CaseSpec("APP-P0-016", "插件文章", "文章详情进入返回", "社区存在插件文章。", "进入文章详情后内容展示，返回正常。", steps=ensure_community_home_steps() + [
        StepSpec("assert_article_plugin_card", "按文章标签断言文章插件卡片存在"),
        StepSpec("click_article_plugin_card", "按文章标签点击文章插件卡片"),
        StepSpec("wait", "等待文章详情页", duration=1.5),
        StepSpec("assert", "断言文章详情页标题存在", "semantic_v2.article.detail_page_title"),
        StepSpec("assert", "断言文章正文容器存在", "semantic_v2.article.detail_content_container"),
        StepSpec("click", "返回社区首页", "semantic_v2.article.detail_back"),
        StepSpec("wait", "等待社区首页恢复", duration=1),
        StepSpec("assert_article_plugin_card", "断言文章插件卡片恢复可见"),
    ]),
    CaseSpec("APP-P0-017", "语音房", "列表基础展示", "停留在社区首页语音房列表区域。", "语音房列表、筛选、招募和房间名称可见。", steps=ensure_voice_room_area_steps() + [
        StepSpec("assert", "断言语音房列表存在", "semantic_v2.voice.voice_room_list"),
        StepSpec("assert", "断言房间筛选入口存在", "semantic_v2.voice.voice_room_filter"),
        StepSpec("assert", "断言招募队友入口存在", "semantic_v2.voice.recruit_teammate"),
        StepSpec("assert", "断言房间名称存在", "semantic_v2.voice.first_room_name"),
    ]),
    CaseSpec("APP-P0-018", "语音房", "筛选分类入口", "停留在社区首页语音房列表区域。", "点击房间ID/筛选入口后进入筛选/搜索页，分类 Tab 和搜索输入框可见。", steps=ensure_voice_room_area_steps() + [
        StepSpec("click", "点击房间筛选入口", "semantic_v2.voice.voice_room_filter"),
        StepSpec("wait", "等待房间筛选页", duration=1),
        StepSpec("assert", "断言房间筛选输入框存在", "semantic_v2.voice.filter_search_input"),
        StepSpec("assert", "断言组队分类存在", "semantic_v2.voice.filter_team_tab"),
        StepSpec("back_until", "返回语音房列表", "semantic_v2.voice.voice_room_filter", duration=0.8),
        StepSpec("assert", "断言语音房列表已恢复", "semantic_v2.voice.voice_room_list"),
        StepSpec("assert", "断言房间筛选入口已恢复", "semantic_v2.voice.voice_room_filter"),
    ]),
    CaseSpec("APP-P0-019", "语音房", "按房间信息进入", "停留在语音房列表，列表存在可进入普通语音房。", "自动跳过互动房、已满/已锁房间，点击首个可进入普通语音房后进入房内。", steps=ensure_voice_room_area_steps() + [StepSpec("click_available_voice_room", "点击首个可进入普通语音房整行", value="normal", duration=0.8), StepSpec("assert_voice_room_type", "断言进入的是普通语音房", value="normal"), StepSpec("wait", "等待进入房间", duration=2), StepSpec("assert", "断言房间详情页存在", "semantic_v2.voice.room_container"), StepSpec("click", "收起房间返回列表", "semantic_v2.voice.room_quit")]),
    CaseSpec("APP-P0-020", "语音房", "详情页基础信息", "停留在社区首页语音房列表区域。", "进入房间后房间名称、房间序号可见，并可退出回列表。", steps=ensure_voice_room_area_steps() + enter_room_steps() + [StepSpec("assert", "断言房内房间名称存在", "semantic_v2.voice.room_name"), StepSpec("assert", "断言房间序号存在", "semantic_v2.voice.room_sequence")] + exit_room_steps()),
    CaseSpec("APP-P0-021", "语音房", "麦位区展示", "停留在社区首页语音房列表区域。", "进入房间后麦位列表和可见麦位/上麦位区域存在，并可退出回列表。", steps=ensure_voice_room_area_steps() + enter_room_steps() + [StepSpec("assert", "断言麦位列表存在", "semantic_v2.voice.room_mic_list"), StepSpec("assert", "断言可见麦位/上麦位区域存在", "semantic_v2.voice.room_first_mic")] + exit_room_steps()),
    CaseSpec("APP-P0-022", "语音房", "底部操作栏展示", "停留在社区首页语音房列表区域。", "进入房间后底部操作栏和聊天入口可见，并可退出回列表。", steps=ensure_voice_room_area_steps() + enter_room_steps() + [StepSpec("assert", "断言底部操作栏存在", "semantic_v2.voice.room_bottom_panel"), StepSpec("assert", "断言房内聊天入口存在", "semantic_v2.voice.room_chat")] + exit_room_steps()),
    CaseSpec("APP-P0-023", "语音房", "收起房间返回列表", "停留在社区首页语音房列表区域。", "进入房间后点击左上角收起入口，回到语音房列表。", steps=ensure_voice_room_area_steps() + enter_room_steps() + [StepSpec("click", "点击房内收起入口", "semantic_v2.voice.room_quit"), StepSpec("wait", "等待回到列表", duration=1), StepSpec("assert", "断言语音房列表存在", "semantic_v2.voice.voice_room_list")]),
    CaseSpec("APP-P0-024", "发布组队", "页面进入", "停留在语音房列表区域。", "点击招募队友进入发布组队页，并可返回列表。", steps=ensure_voice_room_area_steps() + [StepSpec("click", "点击招募队友", "semantic_v2.voice.recruit_teammate"), StepSpec("wait", "等待发布组队页", duration=2), StepSpec("assert", "断言发布组队标题存在", "semantic_v2.voice.publish_title"), StepSpec("click", "返回语音房列表", "semantic_v2.voice.publish_back"), StepSpec("wait", "等待语音房列表恢复", duration=1)]),
    CaseSpec("APP-P0-025", "发布组队", "基础字段展示", "停留在社区首页语音房列表区域。", "进入发布组队页后，文案输入、人数、有效期、发布按钮可见，并可返回列表。", steps=ensure_voice_room_area_steps() + enter_publish_steps() + [StepSpec("assert", "断言组队文案输入框存在", "semantic_v2.voice.publish_team_text"), StepSpec("assert", "断言房间人数选择存在", "semantic_v2.voice.publish_member_count"), StepSpec("assert", "断言房间有效期存在", "semantic_v2.voice.publish_valid_period"), StepSpec("assert", "断言发布按钮存在", "semantic_v2.voice.publish_submit"), StepSpec("click", "返回语音房列表", "semantic_v2.voice.publish_back"), StepSpec("wait", "等待语音房列表恢复", duration=1)]),
    CaseSpec("APP-P0-026", "消息", "消息页进入", "账号已登录。", "点击消息 Tab 后进入消息页。", steps=ensure_community_home_steps() + [
        StepSpec("click", "点击消息 Tab", "semantic_v2.main.message_tab"),
        StepSpec("wait", "等待消息页", duration=1),
        StepSpec("assert", "断言消息列表容器存在", "semantic_v2.main.message_page_container"),
        StepSpec("assert", "断言会话搜索入口存在", "semantic_v2.main.message_search_entry"),
        StepSpec("click", "回到当前社区 Tab", "semantic_v2.main.current_community_tab"),
    ]),
    CaseSpec("APP-P0-027", "消息", "会话搜索", "消息列表存在至少一个非系统会话。", "读取首条会话昵称作为关键词，搜索后展示非空结果且包含目标会话。", steps=ensure_community_home_steps() + [
        StepSpec("click", "点击消息 Tab", "semantic_v2.main.message_tab"),
        StepSpec("wait", "等待消息页", duration=1),
        StepSpec("assert", "断言消息列表容器存在", "semantic_v2.main.message_page_container"),
        StepSpec("remember_first_message_conversation", "记录首条消息会话昵称", duration=8),
        StepSpec("click", "点击会话搜索入口", "semantic_v2.main.message_search_entry"),
        StepSpec("wait", "等待消息搜索页", duration=0.8),
        StepSpec("assert", "断言消息搜索输入框存在", "semantic_v2.message.search_input"),
        StepSpec("input", "输入会话搜索关键词", "semantic_v2.message.search_input", value="{{outputs.message_search_keyword}}"),
        StepSpec("click", "点击消息搜索按钮", "semantic_v2.message.search_submit"),
        StepSpec("wait", "等待搜索结果", duration=1.5),
        StepSpec("assert", "断言搜索结果列表存在", "semantic_v2.message.search_result_list"),
        StepSpec("assert_message_search_results", "断言搜索结果包含目标会话", value="{{outputs.message_search_keyword}}", duration=8),
        back_step("返回消息页"),
        StepSpec("assert", "断言回到消息列表", "semantic_v2.main.message_page_container"),
    ]),
    CaseSpec("APP-P0-028", "商城", "商城页进入", "账号已登录。", "点击商城 Tab 后进入商城页。", steps=ensure_community_home_steps() + [
        StepSpec("click", "点击商城 Tab", "semantic_v2.main.shop_tab"),
        StepSpec("wait", "等待商城页", duration=1.5),
        StepSpec("assert", "断言商城 Web 容器存在", "semantic_v2.main.shop_page_container"),
        StepSpec("click", "回到当前社区 Tab", "semantic_v2.main.current_community_tab"),
    ]),
    CaseSpec("APP-P0-029", "设置", "设置页进入", "账号已登录。", "可进入设置侧边栏，关键配置项可见。", steps=ensure_community_home_steps() + [
        StepSpec("click", "点击消息 Tab", "semantic_v2.main.message_tab"),
        StepSpec("wait", "等待消息页", duration=1),
        StepSpec("click", "点击右上角设置侧边栏入口", "semantic_v2.settings.menu_entry"),
        StepSpec("wait", "等待设置侧边栏展开", duration=1),
        StepSpec("assert", "断言设置侧边栏容器存在", "semantic_v2.settings.drawer_container"),
        StepSpec("assert", "断言通知设置入口存在", "semantic_v2.settings.notification_entry"),
        StepSpec("assert", "断言隐私设置入口存在", "semantic_v2.settings.privacy_entry"),
        back_step("关闭设置侧边栏"),
    ]),
    CaseSpec("APP-P0-030", "设置", "通知设置校验", "账号已登录并进入设置页。", "通知设置页面可打开，消息通知总开关和分类开关列表展示正常。", steps=ensure_community_home_steps() + [
        StepSpec("click", "点击消息 Tab", "semantic_v2.main.message_tab"),
        StepSpec("wait", "等待消息页", duration=1),
        StepSpec("click", "点击右上角设置侧边栏入口", "semantic_v2.settings.menu_entry"),
        StepSpec("wait", "等待设置侧边栏展开", duration=1),
        StepSpec("assert", "断言设置侧边栏容器存在", "semantic_v2.settings.drawer_container"),
        StepSpec("click", "点击通知设置", "semantic_v2.settings.notification_entry"),
        StepSpec("wait", "等待通知设置页", duration=1.5),
        StepSpec("assert", "断言通知设置标题存在", "semantic_v2.settings.notification_title"),
        StepSpec("assert", "断言消息通知总开关存在", "semantic_v2.settings.notification_msg_switch"),
        StepSpec("assert", "断言通知分类开关列表存在", "semantic_v2.settings.notification_category_list"),
        StepSpec("assert", "断言活动推送开关项存在", "semantic_v2.settings.notification_activity_push"),
        back_step("返回消息页"),
    ]),
]


class Command(BaseCommand):
    help = "Bootstrap August 30 P0 APP automation cases and bottom tab semantics."

    def add_arguments(self, parser):
        parser.add_argument("--project-id", type=int, default=2)
        parser.add_argument("--package-id", type=int, default=1)

    def handle(self, *args, **options):
        required_settings = {
            "APP_AUTOMATION_TEST_LOGIN_PHONE": TEST_LOGIN_PHONE,
            "APP_AUTOMATION_TEST_LOGIN_PASSWORD": TEST_LOGIN_PASSWORD,
            "APP_AUTOMATION_TEST_COMMUNITY_KEYWORD": TEST_COMMUNITY_KEYWORD,
            "APP_AUTOMATION_TEST_COMMUNITY_NAME": TEST_COMMUNITY_NAME,
        }
        missing_settings = [key for key, value in required_settings.items() if not str(value or "").strip()]
        if missing_settings:
            raise CommandError(
                "缺少 APP 自动化种子用例测试数据配置："
                + "、".join(missing_settings)
                + "。请在 .env 中按目标环境配置后再执行。"
            )

        project = AppProject.objects.filter(id=options["project_id"]).first()
        if not project:
            raise CommandError(f"Project not found: {options['project_id']}")
        app_package = AppPackage.objects.filter(id=options["package_id"]).first()
        if not app_package:
            raise CommandError(f"AppPackage not found: {options['package_id']}")

        tab_created = 0
        tab_updated = 0
        for tab in BOTTOM_TABS:
            config = {
                "strategy": "manual_bounds",
                "semantic_version": "v2",
                "semantic_status": "已验证",
                "semantic_status_source": "august_p0_bootstrap",
                "needs_human_confirm": False,
                "description": tab["object"],
                "manual_note": tab["note"],
                "package": app_package.package_name or APP_PACKAGE,
                "activity": MAIN_ACTIVITY,
                "resource_id": "",
                "class": "android.view.ViewGroup",
                "text": tab["text"],
                "content_desc": "",
                "bounds": tab["bounds"],
                "normalized_bounds": tab["normalized"],
                "locator_key": tab["locator_key"],
                "semantic_page": "底部TAB",
                "semantic_object": tab["object"],
                "semantic_role": "Tab",
                "interaction_role": "Tab",
                "source_confidence": "high",
                "source": "august_p0_bootstrap",
                "clickable": True,
                "focusable": True,
                "enabled": True,
                "screen_size": [SCREEN_WIDTH, SCREEN_HEIGHT],
            }
            legacy = AppElement.objects.filter(id=tab["legacy_id"]).first()
            existing = AppElement.objects.filter(name=tab["name"]).first()
            element = existing or legacy
            if element:
                element.name = tab["name"]
                element.project = project
                element.element_type = "selector"
                element.tags = ["semantic_v2", "底部TAB", "Tab", "已验证", "august_p0"]
                element.config = config
                element.is_active = True
                element.save()
                tab_updated += 1
            else:
                AppElement.objects.create(
                    project=project,
                    name=tab["name"],
                    element_type="selector",
                    tags=["semantic_v2", "底部TAB", "Tab", "已验证", "august_p0"],
                    config=config,
                    is_active=True,
                )
                tab_created += 1

        main_created = 0
        main_updated = 0
        for spec in MAIN_ELEMENT_SPECS:
            config = {
                "strategy": "selector",
                "semantic_version": "v2",
                "semantic_status": "待验证",
                "semantic_status_source": "august_p0_bootstrap",
                "needs_human_confirm": True,
                "description": spec["object"],
                "manual_note": spec["note"],
                "package": app_package.package_name or APP_PACKAGE,
                "activity": MAIN_ACTIVITY,
                "resource_id": spec["resource_id"],
                "class": spec["class_name"],
                "text": spec.get("text", ""),
                "content_desc": "",
                "bounds": spec["bounds"],
                "normalized_bounds": normalize_bounds(spec["bounds"]),
                "locator_key": spec["name"].split(".")[-1],
                "semantic_page": spec["page"],
                "semantic_object": spec["object"],
                "semantic_role": spec["role"],
                "interaction_role": spec["role"],
                "source_confidence": "medium",
                "source": "august_p0_bootstrap",
                "clickable": bool(spec.get("clickable", False)),
                "enabled": True,
                "screen_size": [SCREEN_WIDTH, SCREEN_HEIGHT],
            }
            _, created = AppElement.objects.update_or_create(
                name=spec["name"],
                defaults={
                    "project": project,
                    "element_type": "selector",
                    "tags": ["semantic_v2", spec["page"], spec["role"], "august_p0", "待验证"],
                    "config": config,
                    "is_active": True,
                },
            )
            if created:
                main_created += 1
            else:
                main_updated += 1

        elements = {item.name: item for item in AppElement.objects.filter(is_active=True)}
        case_created = 0
        case_updated = 0
        for case in CASE_SPECS:
            ui_flow = [build_step(index, step, elements) for index, step in enumerate(case.steps, start=1)]
            readiness = "draft_missing_elements" if case.missing else "executable"
            description = (
                f"8月P0自动化目标。\n"
                f"前置条件：{case.precondition}\n"
                f"核心断言：{case.assertions}\n"
                f"自动化状态：{'待补语义元素' if case.missing else '可直接执行'}"
            )
            if case.missing:
                description += "\n待补元素：" + "、".join(case.missing)

            defaults = {
                "name": case.case_name,
                "description": description,
                "app_package": app_package,
                "ui_flow": ui_flow,
                "variables": {
                    "source": "august_p0_bootstrap",
                    "code": case.code,
                    "module": case.module,
                    "readiness": readiness,
                    "missing_elements": case.missing,
                    "phone": TEST_LOGIN_PHONE,
                    "password": TEST_LOGIN_PASSWORD,
                },
                "timeout": 240,
                "retry_count": 0,
            }
            existing_cases = list(
                AppTestCase.objects.filter(
                    project=project,
                    variables__source="august_p0_bootstrap",
                    variables__code=case.code,
                ).order_by("id")
            )
            if existing_cases:
                test_case = existing_cases[0]
                for field, value in defaults.items():
                    setattr(test_case, field, value)
                test_case.save()
                if len(existing_cases) > 1:
                    AppTestCase.objects.filter(id__in=[item.id for item in existing_cases[1:]]).delete()
                created = False
            else:
                AppTestCase.objects.create(project=project, **defaults)
                created = True

            if created:
                case_created += 1
            else:
                case_updated += 1

        self.stdout.write(self.style.SUCCESS(
            "august p0 bootstrapped: "
            f"tabs created={tab_created}, tabs updated={tab_updated}, "
            f"main created={main_created}, main updated={main_updated}, "
            f"cases created={case_created}, cases updated={case_updated}"
        ))
