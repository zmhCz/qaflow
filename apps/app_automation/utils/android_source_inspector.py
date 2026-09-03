# -*- coding: utf-8 -*-
"""Read-only Android source inspector used to enrich runtime UI nodes.

The Android project is treated as a reference only. This module builds a small
index from layout XML and Kotlin/Java click bindings, then maps runtime nodes to
stable automation roles such as input, button, checkbox, switch, tab, and entry.
"""

from __future__ import annotations

import re
import os
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path
from typing import Any


_ANDROID_NS = "{http://schemas.android.com/apk/res/android}"

INPUT_IDS = {
    "chatmessageinput",
    "codeinputbox",
    "editinput",
    "edittext",
    "edcodeinput",
    "et_number",
    "et_pwd",
    "etcontent",
    "etpassword",
    "tvmsgcontent",
}

BUTTON_IDS = {
    "actionbutton",
    "arrowright",
    "ivback",
    "ivclear",
    "ivclose",
    "ivdelete",
    "rightaction",
    "tvcancel",
    "tvconfirm",
    "tvaction",
}

CHECKBOX_IDS = {
    "ckbcheck",
    "ivagree",
    "ivcheck",
    "ivcheckbox",
}

SWITCH_IDS = {
    "switchview",
}

DECORATIVE_ID_MARKERS = (
    "background",
    "backgroundimage",
    "bg",
    "cover",
    "divider",
    "mask",
    "overlay",
    "placeholder",
    "shadow",
)

INPUT_COMPONENTS = (
    "codeinputedittext",
    "fakeinputbox",
    "mentionedittext",
    "nncommoninputbox",
    "nnlongtexteditview",
    "nnpasswordinputbox",
    "nnphoneinputbox",
    "nnverifycodeinputbox",
)

ROLE_PREFIX = {
    "input": "输入框",
    "search": "搜索框",
    "button": "按钮",
    "checkbox": "勾选框",
    "switch": "开关",
    "slider": "滑块",
    "tab": "标签",
    "option": "选项",
    "entry": "入口",
    "rich_text": "文本",
    "clickable": "可点击元素",
    "focusable": "可聚焦元素",
}

TOKEN_LABELS = {
    "account": "账号",
    "agree": "协议",
    "agreement": "协议",
    "back": "返回",
    "cancel": "取消",
    "clear": "清空",
    "code": "验证码",
    "community": "社区",
    "confirm": "确认",
    "content": "内容",
    "country": "国家区号",
    "create": "创建",
    "delete": "删除",
    "desc": "描述",
    "description": "描述",
    "edit": "编辑",
    "exit": "退出",
    "forget": "忘记",
    "game": "游戏",
    "home": "首页",
    "login": "登录",
    "logout": "退出登录",
    "manifesto": "宣言",
    "mine": "我的",
    "mobile": "手机号",
    "name": "名称",
    "number": "手机号",
    "password": "密码",
    "phone": "手机号",
    "pwd": "密码",
    "qq": "QQ",
    "search": "搜索",
    "show": "显示",
    "sms": "短信",
    "submit": "提交",
    "title": "标题",
    "verify": "验证",
    "wechat": "微信",
}


def get_android_source_root() -> Path | None:
    """Return the Android source root if it exists. Never writes to it."""
    candidates = [
        Path("E:/workspace/nn app/nn_community_android"),
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _snake_case(name: str) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(name or ""))
    text = re.sub(r"[^a-zA-Z0-9_]+", "_", text)
    return text.strip("_").lower()


def _strip_activity_suffix(activity_name: str) -> str:
    name = str(activity_name or "").split(".")[-1]
    return re.sub(r"Activity$", "", name)


def _resource_tail(resource_id: str) -> str:
    text = str(resource_id or "").strip()
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    if ":" in text:
        text = text.rsplit(":", 1)[-1]
    return text


def _short_tag(tag: str) -> str:
    return str(tag or "").split("}")[-1].split(".")[-1]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def _clean_android_literal(value: str) -> str:
    text = str(value or "").strip()
    if not text or text.startswith("@"):
        return ""
    return text


def _humanize_resource_name(resource_name: str, role: str = "") -> str:
    snake_name = _snake_case(resource_name)
    tokens = [token for token in snake_name.split("_") if token]
    ignored = {
        "btn", "button", "cb", "cbk", "checkbox", "ed", "edit", "et", "icon",
        "ifv", "img", "input", "iv", "label", "layout", "ll", "rl", "root",
        "text", "tv", "txt", "view", "v",
    }
    words: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in ignored:
            continue
        label = TOKEN_LABELS.get(token)
        if label and label not in seen:
            words.append(label)
            seen.add(label)

    role_label = ROLE_PREFIX.get(role, "元素")
    if words:
        return "".join(words) + role_label
    if snake_name:
        return f"{snake_name}{role_label}"
    return role_label


def _class_name_from_tag(tag: str) -> str:
    short_tag = _short_tag(tag)
    if not short_tag:
        return ""
    if "." in str(tag):
        return str(tag).split("}")[-1]
    if short_tag in {"Button", "EditText", "TextView", "ImageView", "CheckBox", "Switch", "SeekBar"}:
        return f"android.widget.{short_tag}"
    return short_tag


def _iter_android_source_files(root: Path):
    skip_dirs = {
        ".git",
        ".gradle",
        ".idea",
        "build",
        "generated",
        "intermediates",
        "captures",
        "outputs",
        ".cxx",
    }
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name for name in dirnames
            if name not in skip_dirs and not name.startswith(".")
        ]
        current = Path(dirpath)
        rel_path = current.relative_to(root).as_posix()
        if "/src/main/" not in f"/{rel_path}/" and rel_path != ".":
            # Keep walking module roots until src/main is reached.
            pass
        for filename in filenames:
            path = current / filename
            rel = path.relative_to(root).as_posix()
            if "/src/main/" not in rel:
                continue
            yield path, rel


@lru_cache(maxsize=1)
def _build_source_index() -> dict[str, Any]:
    root = get_android_source_root()
    if not root:
        return {"root": None, "xml": {}, "code": {}, "movement": {}}

    xml_index: dict[str, list[dict[str, str]]] = {}
    code_index: dict[str, set[str]] = {}
    movement_index: dict[str, set[str]] = {}

    for xml_file, rel_path in _iter_android_source_files(root):
        if xml_file.suffix != ".xml":
            continue
        if "/src/main/res/" not in rel_path or "/layout" not in rel_path:
            continue
        try:
            tree = ET.parse(xml_file)
        except Exception:
            continue
        for node in tree.iter():
            raw_id = node.attrib.get(f"{_ANDROID_NS}id", "")
            if "@id/" not in raw_id and "@+id/" not in raw_id:
                continue
            resource_id = raw_id.rsplit("/", 1)[-1]
            xml_index.setdefault(resource_id, []).append(
                {
                    "file": rel_path,
                    "tag": _short_tag(node.tag),
                    "text": node.attrib.get(f"{_ANDROID_NS}text", ""),
                    "hint": node.attrib.get(f"{_ANDROID_NS}hint", ""),
                }
            )

    click_pattern = re.compile(
        r"binding(?:\.[A-Za-z0-9_]+)*\.([A-Za-z0-9_]+)\.setOn[A-Za-z0-9_]*ClickListener"
    )
    movement_pattern = re.compile(
        r"binding(?:\.[A-Za-z0-9_]+)*\.([A-Za-z0-9_]+)\.movementMethod"
    )

    for code_file, rel in _iter_android_source_files(root):
        if code_file.suffix not in {".kt", ".java"}:
            continue
        if "/src/main/" not in rel:
            continue
        text = _read_text(code_file)
        for match in click_pattern.finditer(text):
            code_index.setdefault(match.group(1), set()).add(rel)
        for match in movement_pattern.finditer(text):
            movement_index.setdefault(match.group(1), set()).add(rel)

    return {
        "root": root,
        "xml": xml_index,
        "code": {key: sorted(value) for key, value in code_index.items()},
        "movement": {key: sorted(value) for key, value in movement_index.items()},
    }


def _score_source_declaration(
    declaration: dict[str, str],
    activity_name: str,
    runtime_class_name: str,
) -> int:
    score = 0
    file_name = Path(declaration.get("file", "")).name.lower()
    tag_name = declaration.get("tag", "").lower()
    runtime_short = runtime_class_name.split(".")[-1].lower() if runtime_class_name else ""
    activity_key = _snake_case(_strip_activity_suffix(activity_name))

    if activity_key and activity_key in file_name:
        score += 80
    if runtime_short and runtime_short in tag_name:
        score += 35
    if "uikit" in declaration.get("file", "").lower():
        score += 10
    return score


def _guess_interaction_role(
    resource_name: str,
    runtime_class_name: str,
    declared_tag: str,
    has_click_listener: bool,
    has_movement_method: bool,
    clickable: bool,
    focusable: bool,
    checkable: bool,
) -> tuple[str, str]:
    name = str(resource_name or "").lower()
    runtime_short = runtime_class_name.split(".")[-1].lower() if runtime_class_name else ""
    tag = str(declared_tag or "").lower()
    combined = " ".join([name, runtime_short, tag])

    if any(marker in name for marker in DECORATIVE_ID_MARKERS):
        return "static", "Decorative content"
    if name in INPUT_IDS or any(marker in combined for marker in INPUT_COMPONENTS) or "edittext" in combined or name.startswith(("et_", "ed_", "edit")):
        return "input", "Input hotzone"
    if "searchview" in combined or "search_layout" in combined or name.startswith(("search", "llsearch")) or "search" in name:
        return "search", "Search hotzone"
    if "animswitch" in combined or "switchableentry" in combined or name in SWITCH_IDS or "switch" in name:
        return "switch", "Switch hotzone"
    if "seekbar" in combined or "ratingbar" in combined or "slider" in combined or name.startswith(("seekbar", "rating")):
        return "slider", "Slider hotzone"
    if "tablayout" in combined or "tab_layout" in name or name.startswith(("tab", "tvtab")):
        return "tab", "Tab hotzone"
    if checkable or name in CHECKBOX_IDS or "checkbox" in combined or "roundcheckbox" in combined or "rectcheckbox" in combined or "checkablelabel" in combined or "checkableentry" in combined or "cbk" in name or name.startswith(("cb_", "cbk_", "checkbox")):
        return "checkbox", "Checkbox hotzone"
    if "selectablelabel" in combined:
        return "option", "Option hotzone"
    if "arrowentry" in combined or "entryview" in combined:
        return "entry", "Entry hotzone"
    if "button" in combined or name in BUTTON_IDS or name.startswith(("btn", "iv_", "iv")) or "login_by_" in name:
        return "button", "Button hotzone"
    if has_movement_method:
        return "rich_text", "Rich text hotzone"
    if has_click_listener or clickable:
        return "clickable", "Clickable hotzone"
    if focusable:
        return "focusable", "Focusable hotzone"
    return "static", "Static content"


def enrich_candidate_from_source(
    candidate: dict[str, Any],
    activity_name: str = "",
) -> dict[str, Any]:
    """Enrich one runtime UI candidate with read-only source code context."""
    index = _build_source_index()
    if not index.get("root"):
        return {
            "source_declared_tag": "",
            "source_layout_file": "",
            "source_code_file": "",
            "source_summary": "",
            "source_confidence": "none",
            "interaction_role": "unknown",
            "interaction_role_label": "Unknown",
            "is_hotzone": bool(candidate.get("clickable") or candidate.get("focusable") or candidate.get("checkable")),
        }

    resource_name = _resource_tail(str(candidate.get("resource_id") or ""))
    declarations = list(index["xml"].get(resource_name, []))
    click_refs = list(index["code"].get(resource_name, []))
    movement_refs = list(index["movement"].get(resource_name, []))
    runtime_class_name = str(candidate.get("class_name") or "")

    best_decl = None
    if declarations:
        best_decl = max(
            declarations,
            key=lambda item: _score_source_declaration(item, activity_name, runtime_class_name),
        )

    declared_tag = best_decl.get("tag", "") if best_decl else ""
    has_click_listener = bool(click_refs)
    has_movement_method = bool(movement_refs)
    clickable = bool(candidate.get("clickable"))
    focusable = bool(candidate.get("focusable"))
    checkable = bool(candidate.get("checkable"))

    role, role_label = _guess_interaction_role(
        resource_name=resource_name,
        runtime_class_name=runtime_class_name,
        declared_tag=declared_tag,
        has_click_listener=has_click_listener,
        has_movement_method=has_movement_method,
        clickable=clickable,
        focusable=focusable,
        checkable=checkable,
    )

    summary_parts: list[str] = []
    if best_decl:
        summary_parts.append(f"XML {best_decl.get('tag', '-')}")
        summary_parts.append(Path(best_decl.get("file", "")).name)
    if has_click_listener:
        summary_parts.append("code click binding")
    if has_movement_method:
        summary_parts.append("rich text movement")

    source_confidence = "none"
    if best_decl and (has_click_listener or has_movement_method):
        source_confidence = "high"
    elif best_decl:
        source_confidence = "medium"
    elif has_click_listener or has_movement_method:
        source_confidence = "medium"

    return {
        "source_declared_tag": declared_tag,
        "source_layout_file": best_decl.get("file", "") if best_decl else "",
        "source_code_file": (click_refs or movement_refs or [""])[0],
        "source_summary": " | ".join(summary_parts),
        "source_confidence": source_confidence,
        "interaction_role": role,
        "interaction_role_label": role_label,
        "is_hotzone": role != "static" or clickable or focusable or checkable,
        "source_refs": [item.get("file", "") for item in declarations[:3]],
        "source_click_refs": click_refs[:3],
        "source_movement_refs": movement_refs[:3],
    }


def list_source_semantic_candidates(
    keyword: str = "",
    role: str = "",
    limit: int = 200,
    include_static: bool = False,
) -> dict[str, Any]:
    """Build semantic element candidates from Android source without modifying it."""
    index = _build_source_index()
    root = index.get("root")
    if not root:
        return {
            "source_root": "",
            "available": False,
            "candidates": [],
        }

    keyword_text = str(keyword or "").strip().lower()
    role_filter = str(role or "").strip().lower()
    candidates: list[dict[str, Any]] = []

    for resource_name, declarations in sorted(index.get("xml", {}).items()):
        if not declarations:
            continue

        best_decl = declarations[0]
        click_refs = list(index.get("code", {}).get(resource_name, []))
        movement_refs = list(index.get("movement", {}).get(resource_name, []))
        declared_tag = best_decl.get("tag", "")
        class_name = _class_name_from_tag(declared_tag)
        guessed_role, role_label = _guess_interaction_role(
            resource_name=resource_name,
            runtime_class_name=class_name,
            declared_tag=declared_tag,
            has_click_listener=bool(click_refs),
            has_movement_method=bool(movement_refs),
            clickable=bool(click_refs),
            focusable=False,
            checkable=resource_name.lower() in CHECKBOX_IDS,
        )

        if role_filter and guessed_role != role_filter:
            continue
        if not include_static and guessed_role == "static":
            continue

        text = _clean_android_literal(best_decl.get("text", ""))
        hint = _clean_android_literal(best_decl.get("hint", ""))
        display_name = text or hint or _humanize_resource_name(resource_name, guessed_role)
        locator_key = _snake_case(resource_name)
        source_summary_parts = [
            f"XML {declared_tag}" if declared_tag else "",
            Path(best_decl.get("file", "")).name,
            "code click binding" if click_refs else "",
            "rich text movement" if movement_refs else "",
        ]
        source_summary = " | ".join(part for part in source_summary_parts if part)

        haystack = " ".join(
            [
                resource_name,
                locator_key,
                display_name,
                text,
                hint,
                declared_tag,
                best_decl.get("file", ""),
                source_summary,
                guessed_role,
            ]
        ).lower()
        if keyword_text and keyword_text not in haystack:
            continue

        confidence = "high" if click_refs or guessed_role in {"input", "checkbox", "switch"} else "medium"
        if guessed_role in {"static", "focusable"}:
            confidence = "low"

        candidates.append(
            {
                "key": locator_key,
                "name": f"semantic.{locator_key}",
                "display_name": display_name,
                "description": display_name,
                "manual_note": "AI 根据 APP 源码生成，建议首次使用时由人工确认业务含义。",
                "role": guessed_role,
                "role_label": ROLE_PREFIX.get(guessed_role, role_label),
                "confidence": confidence,
                "resource_id": resource_name,
                "class": class_name,
                "text": text,
                "hint": hint,
                "content_desc": "",
                "locator_key": locator_key,
                "source_layout_file": best_decl.get("file", ""),
                "source_code_file": (click_refs or movement_refs or [""])[0],
                "source_summary": source_summary,
                "source_refs": [item.get("file", "") for item in declarations[:3]],
                "source_click_refs": click_refs[:3],
                "source_movement_refs": movement_refs[:3],
            }
        )

    role_rank = {
        "input": 0,
        "button": 1,
        "checkbox": 2,
        "switch": 3,
        "tab": 4,
        "entry": 5,
        "search": 6,
        "clickable": 7,
    }
    confidence_rank = {"high": 0, "medium": 1, "low": 2}
    candidates.sort(
        key=lambda item: (
            confidence_rank.get(item["confidence"], 9),
            role_rank.get(item["role"], 9),
            item["key"],
        )
    )

    return {
        "source_root": str(root),
        "available": True,
        "candidates": candidates[: max(1, min(int(limit or 200), 1000))],
        "total": len(candidates),
    }
