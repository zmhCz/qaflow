# -*- coding: utf-8 -*-
"""
UI Flow 执行器 - 将 UI Flow JSON 转换为 Airtest 动作并执行
"""
import os
import time
import logging
import json
import re
import copy
import shlex
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional
from django.conf import settings

from airtest.core.api import (
    Template,
    wait,
    touch,
    sleep,
    swipe,
    snapshot,
    exists,
    double_click,
    G,
    ST,
    text as airtest_text,
)

# 导入 OCR 工具
try:
    from ..utils.ocr_helper import get_ocr_helper
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

try:
    import allure
    ALLURE_AVAILABLE = True
except ImportError:
    ALLURE_AVAILABLE = False

from ..utils.slider_captcha_solver import (
    SLIDER_SOLVER_AVAILABLE,
    SliderCaptchaSolution,
    SliderCaptchaSolver,
)
from ..utils.slider_runtime import SliderCaptchaHandler, SliderHandlerConfig
from ..utils.ui_state import (
    POST_LOGIN_DIALOG_SELECTORS,
    STARTUP_DIALOG_SELECTORS,
    dump_ui_xml as dump_current_ui_xml,
    handle_dialogs,
    node_center as shared_node_center,
    parse_bounds as shared_parse_bounds,
)

logger = logging.getLogger(__name__)
APP_PACKAGE = getattr(settings, "APP_AUTOMATION_TARGET_PACKAGE", "") or "com.example.demo"


def app_rid(name: str) -> str:
    return f"{APP_PACKAGE}:id/{name}"


class UiFlowRunner:
    """将 ui_flow 转换为 Airtest 动作并执行"""
    
    def __init__(self, image_base_dir: Optional[str] = None, username: Optional[str] = None):
        """
        初始化 UiFlowRunner
        
        Args:
            image_base_dir: 图片元素基础目录
            username: 执行用户名，用于截图目录分组
        """
        if image_base_dir:
            self.image_base_dir = image_base_dir
        else:
            # 使用统一的 Template 目录作为图片基础目录
            self.image_base_dir = os.path.join(settings.BASE_DIR, 'apps', 'app_automation', 'Template')
        
        # 截图保存目录: media/app-automation/screenshots/{username}/
        self.screenshots_dir = os.path.join(
            settings.MEDIA_ROOT, 'app-automation', 'screenshots', username or 'unknown'
        )
        
        os.makedirs(self.image_base_dir, exist_ok=True)
        os.makedirs(self.screenshots_dir, exist_ok=True)
        
        # 上下文变量
        self.context: Dict[str, Any] = {
            'global': {},
            'local': {},
            'outputs': {},
        }
        
        # 运行时配置
        self.runtime: Dict[str, Any] = {
            'retry_times': 3,
            'retry_interval': 0.5,
            'screenshot_evidence': True,
            'allure_enabled': True,
        }
        self.last_run_result: Dict[str, Any] = {
            'total': 0,
            'passed': 0,
            'failed': 0,
            'outputs': {},
        }

        self._current_action_evidence: Optional[Dict[str, Any]] = None
        self._visual_evidence_attachments: List[Dict[str, Any]] = []
        
        # OCR 工具（延迟初始化）
        self._ocr_helper = None
        
        logger.info(f"初始化UiFlowRunner，图片目录: {self.image_base_dir}")
    
    def run(
        self,
        ui_flow: List[Dict[str, Any]],
        variables: Optional[List[Dict[str, Any]]] = None,
        runtime: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        执行 UI Flow
        
        Args:
            ui_flow: UI Flow 配置列表
            variables: 变量列表
            runtime: 运行时配置
            progress_callback: 进度回调函数，签名为 callback(current_step, total_steps, step_name, status)
                其中 status 为 'running' | 'passed' | 'failed'
            
        Returns:
            执行结果字典
        """
        if not isinstance(ui_flow, list):
            raise ValueError("ui_flow 必须是列表")
        
        # 初始化上下文
        self._init_context(variables, runtime)
        
        # 执行所有步骤
        total_steps = len(ui_flow)
        passed_steps = 0
        failed_steps = 0
        
        logger.info(f"开始执行 UI Flow，共 {total_steps} 个步骤")
        
        for idx, step in enumerate(ui_flow, 1):
            step_name = step.get('name', step.get('type', 'unknown'))
            stop_checker = self.runtime.get("stop_checker")
            if callable(stop_checker):
                try:
                    if stop_checker():
                        self.last_run_result = {
                            'total': total_steps,
                            'passed': passed_steps,
                            'failed': failed_steps,
                            'stopped': True,
                            'outputs': self.context.get('outputs', {}),
                        }
                        logger.info("UI Flow stopped before step %s/%s: %s", idx, total_steps, step_name)
                        return self.last_run_result
                except Exception as cb_err:
                    logger.debug(f"停止检查失败: {cb_err}")
            
            # 通知：步骤开始执行
            if progress_callback:
                try:
                    progress_callback(idx, total_steps, step_name, 'running')
                except Exception as cb_err:
                    logger.debug(f"进度回调失败: {cb_err}")
            
            try:
                logger.info(f"执行步骤 {idx}/{total_steps}: {step_name}")
                step_title = f"步骤{idx}-{step_name}"
                if self._allure_enabled():
                    with allure.step(step_title):
                        self._execute_step_with_evidence(idx, step)
                else:
                    self._execute_step_with_evidence(idx, step)
                passed_steps += 1
                
                # 通知：步骤执行成功
                if progress_callback:
                    try:
                        progress_callback(idx, total_steps, step_name, 'passed')
                    except Exception as cb_err:
                        logger.debug(f"进度回调失败: {cb_err}")
                        
            except Exception as e:
                logger.error(f"步骤 {idx} 执行失败: {str(e)}", exc_info=True)
                failed_steps += 1
                self._attach_allure(f"步骤{idx}-{step.get('name', step.get('type', 'unknown'))}-error", step)
                self.last_run_result = {
                    'total': total_steps,
                    'passed': passed_steps,
                    'failed': failed_steps,
                    'outputs': self.context.get('outputs', {}),
                    'error': str(e),
                    'failed_step_index': idx,
                    'failed_step_name': step_name,
                }
                
                # 通知：步骤执行失败
                if progress_callback:
                    try:
                        progress_callback(idx, total_steps, step_name, 'failed')
                    except Exception as cb_err:
                        logger.debug(f"进度回调失败: {cb_err}")
                
                # 如果配置了失败即停止，则抛出异常
                if runtime and runtime.get('stop_on_error', False):
                    raise
        
        logger.info(f"UI Flow 执行完成，通过: {passed_steps}，失败: {failed_steps}")
        
        self.last_run_result = {
            'total': total_steps,
            'passed': passed_steps,
            'failed': failed_steps,
            'outputs': self.context.get('outputs', {}),
        }
        return self.last_run_result
    
    def _init_context(self, variables: Optional[List[Dict[str, Any]]] = None, runtime: Optional[Dict[str, Any]] = None):
        """初始化上下文"""
        self.context = {
            'global': {},
            'local': {},
            'outputs': {},
        }
        
        if runtime:
            self.runtime.update(runtime)

        self._visual_evidence_attachments = []
        self.last_run_result = {
            'total': 0,
            'passed': 0,
            'failed': 0,
            'outputs': {},
        }
        
        if variables:
            self._load_variables(variables)
    
    def _load_variables(self, variables: List[Dict[str, Any]] | Dict[str, Any]):
        """加载变量到上下文"""
        if isinstance(variables, dict):
            runtime_variables = variables.get("runtime_variables")
            if isinstance(runtime_variables, list):
                self._load_variables(runtime_variables)

            scoped_variables = variables.get("scoped_variables")
            if isinstance(scoped_variables, dict):
                for scope, values in scoped_variables.items():
                    if not isinstance(values, dict):
                        continue
                    for name, value in values.items():
                        self._set_variable(str(name), value, str(scope).lower())

            for name, value in variables.items():
                if name in {"runtime_variables", "scoped_variables"}:
                    continue
                if isinstance(value, (str, int, float, bool)) or value is None:
                    self._set_variable(str(name), value, "local")
            return

        for item in variables:
            if not isinstance(item, dict):
                continue
            
            name = item.get('name')
            if not name:
                continue
            
            scope = str(item.get('scope', 'local')).lower()
            value = item.get('value')
            
            self._set_variable(name, value, scope)
    
    def _set_variable(self, name: str, value: Any, scope: str = 'local'):
        """设置变量"""
        if scope not in self.context:
            scope = 'local'
        self.context[scope][name] = value
    
    def _get_variable(self, name: str, scope: Optional[str] = None) -> Any:
        """获取变量"""
        raw_name = str(name or '').strip()
        if not raw_name:
            return None

        if not scope and '.' in raw_name:
            head, tail = raw_name.split('.', 1)
            if head in self.context:
                value = self.context.get(head, {})
                for part in tail.split('.'):
                    if isinstance(value, dict):
                        value = value.get(part)
                    else:
                        value = getattr(value, part, None)
                    if value is None:
                        return None
                return value

        if scope:
            return self.context.get(scope, {}).get(raw_name)
        
        # 按优先级查找：local -> global -> outputs
        for s in ['local', 'global', 'outputs']:
            if raw_name in self.context.get(s, {}):
                return self.context[s][raw_name]
        
        return None
    
    def _render_value(self, value: Any) -> Any:
        """渲染变量值"""
        if isinstance(value, str):
            # 支持 {{variable}} 和 ${variable} 语法
            pattern = re.compile(r'\{\{\s*([^}]+)\s*\}\}|\$\{\s*([^}]+)\s*\}')
            
            def replace_var(match):
                var_name = match.group(1) or match.group(2)
                var_value = self._get_variable(var_name.strip())
                return str(var_value) if var_value is not None else ''
            
            return pattern.sub(replace_var, value)
        
        elif isinstance(value, dict):
            return {k: self._render_value(v) for k, v in value.items()}
        
        elif isinstance(value, list):
            return [self._render_value(item) for item in value]
        
        return value
    
    def _execute_step(self, step: Dict[str, Any]):
        """执行单个步骤，支持基础组件和自定义组件"""
        # 使用 type 字段获取步骤类型
        action_type = step.get('type', '')
        action = action_type.lower() if action_type else ''
        
        # 渲染步骤参数
        step = self._render_value(step)
        
        # 将 config 中的字段合并到顶层，便于各动作方法直接读取
        # 前端保存的数据结构为 { type, name, config: { selector_type, selector, ... } }
        config = step.get('config')
        if isinstance(config, dict):
            for key, value in config.items():
                if key not in step:
                    step[key] = value
        
        # ---- 步骤级重试机制 ----
        retry_times = int(step.get('retry_times', 0))
        retry_interval = float(step.get('retry_interval', self.runtime.get('retry_interval', 0.5)))
        
        if retry_times > 0:
            last_error = None
            for attempt in range(1 + retry_times):
                try:
                    self._dispatch_step(step, action)
                    return  # 成功则直接返回
                except Exception as e:
                    last_error = e
                    if attempt < retry_times:
                        logger.warning(
                            f"步骤 '{step.get('name', action)}' 第 {attempt + 1} 次失败，"
                            f"{retry_interval}s 后重试 (剩余 {retry_times - attempt - 1} 次): {e}"
                        )
                        sleep(retry_interval)
            raise last_error
        else:
            self._dispatch_step(step, action)

    def _execute_step_with_evidence(self, index: int, step: Dict[str, Any]) -> None:
        """Execute one step and attach compact visual evidence for user-visible actions."""
        capture_evidence = self._should_capture_step_evidence(step)
        before_path: Optional[str] = None
        self._current_action_evidence = None

        if capture_evidence:
            before_path = self._capture_screenshot(f"step_{index:02d}_before")

        try:
            self._execute_step(step)
        except Exception:
            if capture_evidence and before_path:
                self._attach_step_evidence(index, step, before_path, None, failed=True)
            raise

        if capture_evidence:
            self._wait_before_after_screenshot(step)
            after_path = self._capture_screenshot(f"step_{index:02d}_after")
            self._attach_step_evidence(index, step, before_path, after_path, failed=False)

    def _should_capture_step_evidence(self, step: Dict[str, Any]) -> bool:
        env_value = os.getenv("APP_STEP_SCREENSHOT_EVIDENCE", "")
        if env_value.lower() in {"0", "false", "no", "off"}:
            return False
        if self.runtime.get("screenshot_evidence") is False:
            return False

        action = str(step.get("type") or "").strip().lower()
        return action in {
            "click",
            "touch",
            "double_click",
            "long_press",
            "input",
            "swipe",
            "swipe_to",
            "keyevent",
            "back",
            "press_key",
            "back_until",
            "image_exists_click",
            "image_exists_click_chain",
            "click_available_voice_room",
            "click_member_hall_entry",
            "click_article_plugin_card",
        }

    def _set_action_evidence(self, **payload: Any) -> None:
        clean_payload = {key: value for key, value in payload.items() if value not in (None, "", [])}
        if clean_payload:
            self._current_action_evidence = clean_payload

    def _step_config_value(self, step: Dict[str, Any], key: str, default: Any = None) -> Any:
        if key in step:
            return step.get(key)
        config = step.get("config")
        if isinstance(config, dict) and key in config:
            return config.get(key)
        return default

    def _allure_enabled(self) -> bool:
        return bool(ALLURE_AVAILABLE and self.runtime.get("allure_enabled", True))

    def _wait_before_after_screenshot(self, step: Dict[str, Any]) -> None:
        """Give page transitions a small settle window before collecting the after screenshot."""
        explicit_wait = self._step_config_value(step, "evidence_after_wait")
        if explicit_wait is None:
            explicit_wait = self._step_config_value(step, "screenshot_after_wait")

        if explicit_wait is not None:
            wait_seconds = float(explicit_wait or 0)
        else:
            action = str(step.get("type") or "").strip().lower()
            if action in {"back", "keyevent", "press_key", "back_until"}:
                wait_seconds = 1.2
            elif action in {"swipe", "swipe_to", "drag"}:
                wait_seconds = 0.6
            elif action in {
                "click",
                "touch",
                "double_click",
                "long_press",
                "image_exists_click",
                "image_exists_click_chain",
                "click_available_voice_room",
                "click_member_hall_entry",
                "click_article_plugin_card",
            }:
                wait_seconds = 0.4
            else:
                wait_seconds = 0

        if wait_seconds > 0:
            sleep(wait_seconds)

    def _attach_step_evidence(
        self,
        index: int,
        step: Dict[str, Any],
        before_path: Optional[str],
        after_path: Optional[str],
        *,
        failed: bool,
    ) -> None:
        step_name = step.get("name") or step.get("type") or f"步骤{index}"
        evidence = dict(self._current_action_evidence or {})
        evidence.update({
            "step_index": index,
            "step_name": step_name,
            "step_type": step.get("type") or "",
        })

        prefix = f"步骤{index}-{step_name}"
        before_label = f"{prefix}-失败前操作位置" if failed else f"{prefix}-操作前位置"
        annotated_before = self._annotate_screenshot(before_path, evidence, before_label) if before_path else None
        evidence_before_path = annotated_before or before_path
        self._attach_image_file(evidence_before_path, before_label)
        if evidence_before_path:
            self._visual_evidence_attachments.append({
                "path": evidence_before_path,
                "name": before_label,
                "step_index": index,
                "step_name": step_name,
                "phase": "error" if failed else "before",
            })
        if after_path:
            self._attach_image_file(after_path, f"{prefix}-操作后页面")
        try:
            if self._allure_enabled():
                allure.attach(
                    json.dumps(evidence, ensure_ascii=False, indent=2),
                    name=f"{prefix}-操作说明",
                    attachment_type=allure.attachment_type.JSON,
                )
        except Exception:
            logger.exception("Allure 操作说明附件写入失败")

    def _attach_image_file(self, path: Optional[str], name: str) -> None:
        if not self._allure_enabled() or not path or not os.path.exists(path):
            return
        try:
            allure.attach.file(path, name=name, attachment_type=allure.attachment_type.PNG)
        except Exception:
            logger.exception("Allure 图片附件写入失败: %s", path)

    def attach_visual_evidence_overview(self, max_items: int = 8) -> None:
        """Attach a compact top-level screenshot index so Allure users do not need to expand every step."""
        if not self._allure_enabled():
            return

        items = [
            item for item in self._visual_evidence_attachments
            if item.get("path") and os.path.exists(str(item.get("path")))
        ][:max_items]
        if not items:
            return

        for item in items:
            name = f"关键截图-步骤{item.get('step_index')}-{item.get('step_name')}"
            self._attach_image_file(str(item.get("path")), name)

        if len(self._visual_evidence_attachments) > len(items):
            try:
                allure.attach(
                    f"已在用例顶层展示前 {len(items)} 张关键截图，其余截图可在具体步骤附件或 QAFlow 标准报告中查看。",
                    name="关键截图说明",
                    attachment_type=allure.attachment_type.TEXT,
                )
            except Exception:
                logger.exception("Allure 关键截图说明附件写入失败")

    def _annotate_screenshot(self, path: Optional[str], evidence: Dict[str, Any], name_prefix: str) -> Optional[str]:
        if not path or not os.path.exists(path):
            return None
        try:
            from PIL import Image, ImageDraw
        except Exception as exc:
            logger.debug("Pillow 不可用，跳过截图标注: %s", exc)
            return None

        try:
            image = Image.open(path).convert("RGB")
            draw = ImageDraw.Draw(image)
            width, height = image.size
            red = (239, 68, 68)
            fill = (239, 68, 68, 80)

            bounds = evidence.get("bounds")
            if isinstance(bounds, str):
                bounds = self._parse_bounds(bounds)
            if isinstance(bounds, (list, tuple)) and len(bounds) >= 4:
                x1, y1, x2, y2 = [int(item) for item in bounds[:4]]
                draw.rectangle((x1, y1, x2, y2), outline=red, width=8)

            center = evidence.get("center") or evidence.get("tap")
            if isinstance(center, (list, tuple)) and len(center) >= 2:
                x, y = int(center[0]), int(center[1])
                radius = max(16, int(min(width, height) * 0.018))
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=red, width=8)
                draw.line((x - radius * 2, y, x + radius * 2, y), fill=red, width=5)
                draw.line((x, y - radius * 2, x, y + radius * 2), fill=red, width=5)

            start = evidence.get("start")
            end = evidence.get("end")
            if isinstance(start, (list, tuple)) and isinstance(end, (list, tuple)) and len(start) >= 2 and len(end) >= 2:
                sx, sy = int(start[0]), int(start[1])
                ex, ey = int(end[0]), int(end[1])
                draw.line((sx, sy, ex, ey), fill=red, width=10)
                arrow = 28
                draw.line((ex, ey, ex - arrow, ey - arrow), fill=red, width=8)
                draw.line((ex, ey, ex + arrow, ey - arrow), fill=red, width=8)

            annotated_path = Path(path).with_name(f"{Path(path).stem}_annotated.png")
            image.save(annotated_path)
            return str(annotated_path)
        except Exception:
            logger.exception("生成标注截图失败: %s", path)
            return None
    
    def _dispatch_step(self, step: Dict[str, Any], action: str):
        """分发步骤到对应的 handler（基础组件）或展开执行（自定义组件）"""
        
        # 自定义组件展开执行
        if step.get('kind') == 'custom':
            self._execute_custom_component(step)
            return
        
        # 根据动作类型执行
        action_map = {
            # 基础动作
            'click': self._action_click_step,
            'touch': self._action_click_step,
            'input': self._action_input,
            'swipe': self._action_swipe,
            'double_click': self._action_double_click,
            'long_press': self._action_long_press,
            'drag': self._action_drag,
            'swipe_to': self._action_swipe_to,
            'keyevent': self._action_keyevent,
            'press_key': self._action_keyevent,
            'back': self._action_keyevent,
            'back_until': self._action_back_until,
            'launch_activity': self._action_launch_activity,
            'ensure_account_logged_in': self._action_ensure_account_logged_in,
            'ensure_logged_out': self._action_ensure_logged_out,
            'clear_runtime_blockers': self._action_clear_runtime_blockers,
            'handle_startup_blockers': self._action_clear_runtime_blockers,
            'ensure_unfollowed_community_home': self._action_ensure_unfollowed_community_home,
            'ensure_followed_community_home': self._action_ensure_followed_community_home,
            'ensure_unfollowed_member_hall': self._action_ensure_unfollowed_member_hall,
            'remember_current_community': self._action_remember_current_community,
            'click_other_followed_community': self._action_click_other_followed_community,
            'assert_current_community_switched': self._action_assert_current_community_switched,
            'assert_logout_confirm_dialog': self._action_assert_logout_confirm_dialog,
            'click_available_voice_room': self._action_click_available_voice_room,
            'assert_voice_room_type': self._action_assert_voice_room_type,
            'click_member_hall_entry': self._action_click_member_hall_entry,
            'assert_member_hall_opened': self._action_assert_member_hall_opened,
            'assert_hall_message_sent': self._action_assert_hall_message_sent,
            'ensure_personal_dynamic_list': self._action_ensure_personal_dynamic_list,
            'remember_first_message_conversation': self._action_remember_first_message_conversation,
            'assert_message_search_results': self._action_assert_message_search_results,
            'assert_article_plugin_card': self._action_assert_article_plugin_card,
            'click_article_plugin_card': self._action_click_article_plugin_card,
            
            # 条件动作
            'image_exists_click': self._action_image_exists_click,
            'image_exists_click_chain': self._action_image_exists_click_chain,
            
            # 工具类
            'set_variable': self._action_set_variable,
            'unset_variable': self._action_unset_variable,
            'extract_output': self._action_extract_output,
            'screenshot': self._action_screenshot,
            'api_request': self._action_api_request,
            
            # 控制流
            'wait': self._action_wait,
            'sleep': self._action_wait,
            'handle_slider': self._action_handle_slider,
            'slider': self._action_handle_slider,
            'if': self._action_if,
            'loop': self._action_loop,
            'sequence': self._action_sequence,
            'try': self._action_try,
            
            # 断言
            'assert': self._action_assert,
            'foreach_assert': self._action_foreach_assert,
        }
        
        handler = action_map.get(action)
        if handler:
            handler(step)
        else:
            # action_map 中找不到，尝试作为自定义组件查找
            if self._try_execute_as_custom(step, action):
                return
            logger.warning(f"未知的动作类型: {action} (步骤: {step.get('name', 'unknown')})")

    # ---------- 自定义组件展开 ----------

    def _load_custom_component_defs(self) -> Dict[str, Any]:
        """从数据库加载所有启用的自定义组件定义，缓存到实例上"""
        if not hasattr(self, '_custom_defs_cache'):
            try:
                from ..models import AppCustomComponent
                defs = {}
                for comp in AppCustomComponent.objects.filter(enabled=True):
                    defs[comp.type] = {
                        'name': comp.name,
                        'steps': comp.steps or [],
                        'schema': comp.schema or {},
                        'default_config': comp.default_config or {},
                    }
                self._custom_defs_cache = defs
                logger.debug(f"已加载 {len(defs)} 个自定义组件定义")
            except Exception as e:
                logger.warning(f"加载自定义组件定义失败: {e}")
                self._custom_defs_cache = {}
        return self._custom_defs_cache

    def _execute_custom_component(self, step: Dict[str, Any]):
        """
        展开并执行自定义组件。
        自定义组件的 steps 是基础组件步骤列表，逐个执行。
        步骤中的参数可通过 config 覆盖默认值。
        """
        comp_type = step.get('type', '')
        comp_name = step.get('name', comp_type)

        # 优先从步骤自带的 steps 字段获取（前端可能直接带了）
        sub_steps = step.get('steps')

        if not sub_steps:
            # 从数据库加载
            defs = self._load_custom_component_defs()
            comp_def = defs.get(comp_type)
            if not comp_def:
                raise ValueError(f"自定义组件 '{comp_type}' 未找到，请检查是否已创建并启用")
            sub_steps = comp_def.get('steps', [])

        if not sub_steps or not isinstance(sub_steps, list):
            logger.warning(f"自定义组件 '{comp_name}' 没有步骤，跳过")
            return

        # 深拷贝，避免修改原始定义
        sub_steps = copy.deepcopy(sub_steps)

        # 将自定义组件的 config 参数注入到子步骤中（作为变量可渲染）
        comp_config = step.get('config', {})
        if isinstance(comp_config, dict):
            for key, value in comp_config.items():
                if key not in ('type', 'name', 'kind', 'steps'):
                    self._set_variable(key, value, 'local')

        logger.info(f"展开自定义组件 '{comp_name}' ({comp_type})，共 {len(sub_steps)} 个子步骤")

        for sub_idx, sub_step in enumerate(sub_steps, 1):
            sub_name = sub_step.get('name', sub_step.get('type', 'unknown'))
            logger.info(f"  自定义组件子步骤 {sub_idx}/{len(sub_steps)}: {sub_name}")
            self._execute_step(sub_step)

    def _try_execute_as_custom(self, step: Dict[str, Any], action: str) -> bool:
        """尝试将未知的 action_type 作为自定义组件执行，成功返回 True"""
        defs = self._load_custom_component_defs()
        if action in defs:
            step['kind'] = 'custom'
            self._execute_custom_component(step)
            return True
        return False

    def _safe_filename(self, text: str) -> str:
        safe = re.sub(r'[^0-9a-zA-Z_\-]+', '_', str(text))
        return safe.strip('_') or "step"

    def _capture_screenshot(self, name_prefix: str) -> Optional[str]:
        filename = f"{self._safe_filename(name_prefix)}_{int(time.time())}.png"
        full_path = os.path.join(self.screenshots_dir, filename)
        try:
            result = snapshot(filename=full_path)
            if isinstance(result, dict):
                path = result.get("screen")
                if path and os.path.exists(path):
                    return path
            if os.path.exists(full_path):
                return full_path
        except Exception as exc:
            logger.warning("Airtest 截图失败，尝试使用 ADB screencap 兜底: %s: %r", type(exc).__name__, exc)
            fallback_path = self._capture_screenshot_via_adb(full_path)
            if fallback_path:
                return fallback_path
            logger.exception("截图失败，ADB 兜底也未成功")
        return None

    def _capture_screenshot_via_adb(self, full_path: str | Path) -> Optional[str]:
        """Capture PNG via adb exec-out when Airtest minicap/javacap stream breaks."""
        try:
            device = getattr(G, "DEVICE", None)
            adb = getattr(device, "adb", None)
            if adb is None:
                return None
            result = adb.cmd(["exec-out", "screencap", "-p"], device=True, ensure_unicode=False, timeout=12)
            if isinstance(result, bytes):
                png_bytes = result
            elif isinstance(result, (list, tuple)):
                chunks = []
                for item in result:
                    if isinstance(item, bytes):
                        chunks.append(item)
                    else:
                        chunks.append(str(item).encode("utf-8", errors="ignore"))
                png_bytes = b"".join(chunks)
            else:
                png_bytes = str(result).encode("latin1", errors="ignore")

            if not png_bytes:
                png_bytes = self._capture_screenshot_bytes_via_subprocess(device, adb)
            if not png_bytes:
                logger.warning("ADB screencap 返回为空")
                return None

            path = Path(full_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(png_bytes)
            if path.exists() and path.stat().st_size > 0:
                return str(path)
        except Exception as exc:
            logger.warning("ADB screencap 兜底失败: %s: %r", type(exc).__name__, exc)
        return None

    def _capture_screenshot_bytes_via_subprocess(self, device: Any, adb: Any) -> bytes:
        adb_path = str(getattr(adb, "adb_path", "") or os.getenv("ADB_PATH") or os.getenv("ADB") or "adb")
        serial = str(getattr(device, "uuid", "") or getattr(adb, "serialno", "") or "").strip()
        command = [adb_path]
        if serial:
            command.extend(["-s", serial])
        command.extend(["exec-out", "screencap", "-p"])
        try:
            completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=12, check=False)
        except Exception as exc:
            logger.warning("subprocess ADB screencap 执行失败: %s: %r", type(exc).__name__, exc)
            return b""
        if completed.returncode != 0:
            logger.warning(
                "subprocess ADB screencap 返回异常: code=%s stderr=%s",
                completed.returncode,
                completed.stderr.decode("utf-8", errors="ignore")[:300],
            )
            return b""
        return completed.stdout or b""

    def _attach_allure(self, name: str, step: Optional[Dict[str, Any]] = None) -> None:
        if not self._allure_enabled():
            return
        if step is not None:
            try:
                allure.attach(
                    json.dumps(step, ensure_ascii=False, indent=2),
                    name=f"{name}-step",
                    attachment_type=allure.attachment_type.JSON
                )
            except Exception:
                logger.exception("Allure JSON 附件写入失败")
        path = self._capture_screenshot(name)
        if path:
            try:
                allure.attach.file(path, name=name, attachment_type=allure.attachment_type.PNG)
            except Exception:
                logger.exception("Allure 截图附件写入失败: %s", path)
        self._attach_runtime_state(name)

    def _attach_runtime_state(self, name: str) -> None:
        """失败时补充 UI 树和设备状态，方便定位元素/页面/设备问题。"""
        if not self._allure_enabled():
            return
        try:
            xml_text = self._dump_ui_xml()
            if xml_text:
                allure.attach(
                    xml_text,
                    name=f"{name}-ui-xml",
                    attachment_type=allure.attachment_type.XML
                )
        except Exception:
            logger.exception("Allure UI XML 附件写入失败")

        state_lines = []
        state_commands = [
            ("前台窗口", "dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'"),
            ("前台 Activity", "dumpsys activity activities | grep -E 'mResumedActivity|topResumedActivity'"),
            ("屏幕尺寸", "wm size"),
            ("屏幕密度", "wm density"),
            ("电池状态", "dumpsys battery"),
        ]
        for title, command in state_commands:
            try:
                output = self._device_shell(command).strip()
            except Exception as exc:
                output = f"采集失败: {exc}"
            if output:
                state_lines.append(f"## {title}\n{output}")

        if state_lines:
            try:
                allure.attach(
                    "\n\n".join(state_lines),
                    name=f"{name}-device-state",
                    attachment_type=allure.attachment_type.TEXT
                )
            except Exception:
                logger.exception("Allure 设备状态附件写入失败")

    def _is_selector_target(self, target: Any) -> bool:
        return isinstance(target, dict) and target.get('_selector_kind') == 'android_selector'

    def _normalize_shell_output(self, result: Any) -> str:
        if result is None:
            return ""
        if isinstance(result, bytes):
            return result.decode("utf-8", errors="ignore")
        if isinstance(result, (list, tuple)):
            return "".join(self._normalize_shell_output(item) for item in result)
        return str(result)

    def _device_shell(self, command: str) -> str:
        if not getattr(G, 'DEVICE', None):
            raise RuntimeError("当前没有可用的设备连接，无法执行 selector 操作")
        result = G.DEVICE.shell(command)
        return self._normalize_shell_output(result)

    def _dump_ui_xml(self) -> str:
        return dump_current_ui_xml(self._device_shell)

    def _load_ui_hierarchy(self) -> ET.Element:
        xml_text = self._dump_ui_xml()
        try:
            return ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise RuntimeError(f"解析 UI 树 XML 失败: {exc}") from exc

    def _parse_inline_selector(self, selector: Any) -> Optional[Dict[str, Any]]:
        if isinstance(selector, dict):
            data = dict(selector)
        else:
            raw = str(selector or "").strip()
            if not raw:
                return None

            data: Dict[str, Any] = {}
            if raw.startswith("{") and raw.endswith("}"):
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        data = parsed
                except json.JSONDecodeError:
                    data = {}

            if not data and "=" in raw:
                for part in raw.split(","):
                    if "=" not in part:
                        continue
                    key, value = part.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    if key:
                        data[key] = value

            if not data:
                if ":id/" in raw or raw.startswith("id/") or "/" in raw:
                    data["resource_id"] = raw
                else:
                    data["text"] = raw

        data = {key: value for key, value in data.items() if value not in (None, "", [])}
        if not any(data.get(key) for key in ("resource_id", "text", "content_desc", "class", "hint")):
            return None

        data["_selector_kind"] = "android_selector"
        return data

    def _parse_bounds(self, bounds: str) -> Optional[tuple]:
        return shared_parse_bounds(bounds)

    def _node_center(self, node_attrs: Dict[str, Any]) -> Optional[tuple]:
        return shared_node_center(node_attrs)

    def _normalize_text_value(self, value: Any) -> str:
        return str(value or "").strip()

    def _safe_log_text(self, value: Any) -> str:
        text = self._normalize_text_value(value)
        return "".join(
            f"\\u{ord(char):04x}" if 0xE000 <= ord(char) <= 0xF8FF else char
            for char in text
        )

    def _text_matches(self, actual: Any, expected: Any) -> bool:
        actual_text = self._normalize_text_value(actual)
        expected_text = self._normalize_text_value(expected)
        if not expected_text:
            return True
        if not actual_text:
            return False
        return actual_text == expected_text or expected_text in actual_text

    def _score_selector_node(self, attrs: Dict[str, Any], selector: Dict[str, Any]) -> int:
        score = 0
        has_primary_locator = False
        matched_primary_locator = False
        matched_resource_id = False

        resource_id = self._normalize_text_value(selector.get("resource_id"))
        if resource_id:
            has_primary_locator = True
            actual = self._normalize_text_value(attrs.get("resource-id"))
            tail_actual = actual.split("/")[-1]
            tail_expected = resource_id.split("/")[-1]
            if actual == resource_id or tail_actual == tail_expected:
                score += 12
                matched_primary_locator = True
                matched_resource_id = True
            else:
                return -1

        class_name = self._normalize_text_value(selector.get("class"))
        if class_name:
            has_primary_locator = True
            actual = self._normalize_text_value(attrs.get("class"))
            if actual == class_name or actual.endswith(class_name):
                score += 4
                matched_primary_locator = True
            elif not matched_resource_id:
                return -1

        package_name = self._normalize_text_value(selector.get("package"))
        if package_name:
            has_primary_locator = True
            actual = self._normalize_text_value(attrs.get("package"))
            if actual == package_name:
                score += 2
                matched_primary_locator = True
            elif not matched_resource_id:
                return -1

        text_value = self._normalize_text_value(selector.get("text"))
        if text_value:
            if self._text_matches(attrs.get("text"), text_value) or self._text_matches(attrs.get("content-desc"), text_value):
                score += 6
                matched_primary_locator = True
            else:
                return -1

        content_desc = self._normalize_text_value(selector.get("content_desc"))
        if content_desc:
            if self._text_matches(attrs.get("content-desc"), content_desc):
                score += 5
                matched_primary_locator = True
            else:
                return -1

        hint_value = self._normalize_text_value(selector.get("hint"))
        if hint_value:
            hint_candidates = [attrs.get("hint"), attrs.get("text"), attrs.get("content-desc")]
            if any(self._text_matches(candidate, hint_value) for candidate in hint_candidates):
                score += 3
                matched_primary_locator = True
            else:
                return -1

        enabled = selector.get("enabled")
        if enabled is not None:
            actual = self._normalize_text_value(attrs.get("enabled")).lower()
            if actual == str(bool(enabled)).lower():
                score += 1

        clickable = selector.get("clickable")
        if clickable is not None:
            actual = self._normalize_text_value(attrs.get("clickable")).lower()
            if actual == str(bool(clickable)).lower():
                score += 1

        focusable = selector.get("focusable")
        if focusable is not None:
            actual = self._normalize_text_value(attrs.get("focusable")).lower()
            if actual == str(bool(focusable)).lower():
                score += 1

        if has_primary_locator and not matched_primary_locator:
            return -1

        return score

    def _selector_bounds_rank(self, attrs: Dict[str, Any], selector: Dict[str, Any]) -> tuple[int, int, int]:
        selector_bounds = self._parse_bounds(self._normalize_text_value(selector.get("bounds")))
        actual_bounds = self._parse_bounds(self._normalize_text_value(attrs.get("bounds")))
        if not selector_bounds or not actual_bounds:
            return (0, 0, 0)

        sx1, sy1, sx2, sy2 = selector_bounds
        ax1, ay1, ax2, ay2 = actual_bounds

        overlap_width = max(0, min(sx2, ax2) - max(sx1, ax1))
        overlap_height = max(0, min(sy2, ay2) - max(sy1, ay1))
        overlap_area = overlap_width * overlap_height

        selector_center = ((sx1 + sx2) // 2, (sy1 + sy2) // 2)
        actual_center = ((ax1 + ax2) // 2, (ay1 + ay2) // 2)
        center_distance = abs(selector_center[0] - actual_center[0]) + abs(selector_center[1] - actual_center[1])

        selector_area = max(1, (sx2 - sx1) * (sy2 - sy1))
        actual_area = max(1, (ax2 - ax1) * (ay2 - ay1))
        area_delta = abs(selector_area - actual_area)

        return (overlap_area, -center_distance, -area_delta)

    def _find_selector_node(self, selector: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        root = self._load_ui_hierarchy()
        best_match = None
        best_score = -1
        best_bounds_rank = (-1, float("-inf"), float("-inf"))

        for node in root.iter("node"):
            attrs = dict(node.attrib)
            score = self._score_selector_node(attrs, selector)
            if score < 0:
                continue

            bounds_rank = self._selector_bounds_rank(attrs, selector)
            if score > best_score or (score == best_score and bounds_rank > best_bounds_rank):
                best_score = score
                best_bounds_rank = bounds_rank
                best_match = attrs

        return best_match

    def _wait_for_selector(self, selector: Dict[str, Any], timeout: float) -> Optional[Dict[str, Any]]:
        deadline = time.time() + max(float(timeout or 0), 0)
        last_error = None
        while True:
            try:
                node = self._find_selector_node(selector)
                if node:
                    return node
            except Exception as exc:
                last_error = exc
                logger.warning("selector lookup failed, will retry or fallback: %s", exc)
            if time.time() >= deadline:
                if last_error:
                    logger.warning("selector lookup timed out after UI dump errors: %s", last_error)
                return None
            time.sleep(0.4)

    def _resolve_selector_node(self, selector: Dict[str, Any], timeout: float, allow_bounds_fallback: bool = False) -> Optional[Dict[str, Any]]:
        if allow_bounds_fallback and selector.get("strategy") == "manual_bounds" and selector.get("bounds"):
            logger.info("manual_bounds selector 直接使用采集 bounds: %s", selector)
            return {"bounds": selector.get("bounds"), "_fallback": True, "_manual_bounds": True}

        node = self._wait_for_selector(selector, timeout)
        if node:
            return node

        if allow_bounds_fallback and selector.get("bounds"):
            logger.warning("selector 实时匹配失败，回退使用采集 bounds: %s", selector)
            return {"bounds": selector.get("bounds"), "_fallback": True}

        return None

    def _target_exists(self, target: Any) -> bool:
        if self._is_selector_target(target):
            try:
                return self._find_selector_node(target) is not None
            except Exception as exc:
                logger.debug("selector exists check failed: %s", exc)
                return False
        return exists(target) is not None

    def _tap_target(self, target: Any, timeout: float = 10, duration: Optional[float] = None):
        if self._is_selector_target(target):
            node = self._resolve_selector_node(target, timeout, allow_bounds_fallback=True)
            if not node:
                raise ValueError(f"未找到 selector 元素: {target}")
            center = self._node_center(node)
            if not center:
                raise ValueError(f"selector 元素缺少 bounds，无法点击: {target}")
            x, y = center
            self._set_action_evidence(
                action="tap",
                center=[x, y],
                bounds=node.get("bounds"),
                selector=target,
            )
            if duration and duration > 0.8:
                self._device_shell(f"input swipe {x} {y} {x} {y} {int(duration * 1000)}")
            else:
                self._device_shell(f"input tap {x} {y}")
            return

        if isinstance(target, (list, tuple)) and len(target) >= 2:
            self._set_action_evidence(action="tap", center=[int(target[0]), int(target[1])])

        if duration is not None:
            touch(target, duration=duration)
        else:
            touch(target)

    def _wait_for_target(self, target: Any, timeout: float):
        if self._is_selector_target(target):
            node = self._wait_for_selector(target, timeout)
            if not node:
                raise RuntimeError(f"等待 selector 元素超时: {target}")
            return node
        return wait(target, timeout=timeout)

    def _inline_android_selector(
        self,
        resource_id: str = "",
        text: str = "",
        class_name: str = "",
    ) -> Dict[str, Any]:
        return {
            "_selector_kind": "android_selector",
            "resource_id": resource_id,
            "text": text,
            "class": class_name,
        }

    def _selector_node_exists(self, selector: Dict[str, Any]) -> bool:
        try:
            return self._find_selector_node(selector) is not None
        except Exception as exc:
            logger.debug("selector exists failed: %s", exc)
            return False

    def _main_home_ready(self) -> bool:
        home = self._inline_android_selector(app_rid("fragment_container"))
        bottom = self._inline_android_selector(app_rid("bottomNavigationBar"))
        if self._selector_node_exists(home) and self._selector_node_exists(bottom):
            return True

        focus = self._current_focus_info()
        if focus.get("package_name") != APP_PACKAGE:
            return False
        if self._login_page_visible():
            return False

        # UI 改版后部分首页容器 id 可能变化，底部固定 Tab 文案更适合作为主页弱信号。
        main_signals = (
            self._inline_android_selector(app_rid("bottomNavigationBar")),
            self._inline_android_selector(text="商城"),
            self._inline_android_selector(text="消息"),
        )
        return any(self._selector_node_exists(selector) for selector in main_signals)

    def _wait_for_main_home_ready(self, timeout: float = 15) -> bool:
        deadline = time.time() + max(float(timeout or 0), 0)
        while True:
            if self._main_home_ready():
                return True
            if time.time() >= deadline:
                return False
            sleep(0.5)

    def _dismiss_downline_notice_if_present(self) -> bool:
        title_selector = self._inline_android_selector(
            app_rid("dialog_hint_title"),
            text="下线通知",
        )
        if not self._selector_node_exists(title_selector):
            return False

        confirm_selector = self._inline_android_selector(app_rid("dialog_hint_confirm"))
        logger.info("检测到下线通知，点击重新登录")
        self._tap_target(confirm_selector, timeout=3)
        sleep(1.2)
        return True

    def _dismiss_server_switch_guide_if_present(self) -> bool:
        guide_selectors = (
            self._inline_android_selector(app_rid("serverSwitchGuideRoot")),
            self._inline_android_selector(text="右滑打开侧边栏"),
        )
        if not any(self._selector_node_exists(selector) for selector in guide_selectors):
            return False

        logger.info("检测到社区侧边栏新手引导，按引导右滑并返回首页")
        try:
            width, height = G.DEVICE.get_current_resolution()
            start_x = max(24, int(width * 0.08))
            end_x = min(width - 24, int(width * 0.72))
            y = int(height * 0.55)
        except Exception:
            start_x, end_x, y = 80, 780, 1200
        self._device_shell(f"input swipe {start_x} {y} {end_x} {y} 500")
        sleep(1)
        drawer_selector = self._inline_android_selector(app_rid("leftDrawerContainer"))
        if self._selector_node_exists(drawer_selector):
            self._device_shell("input keyevent BACK")
            sleep(0.8)
        return True

    def _action_clear_runtime_blockers(self, step: Dict[str, Any]):
        """显式清理重置场景下的启动弹窗/业务引导层。"""
        timeout = float(step.get("timeout", step.get("duration", 4)) or 4)
        handled_dialog = self._dismiss_startup_dialogs_if_present(timeout=timeout)
        handled_guide = self._dismiss_server_switch_guide_if_present()
        if handled_dialog or handled_guide:
            logger.info("已清理启动遮挡: dialog=%s, guide=%s", handled_dialog, handled_guide)
        else:
            logger.info("未发现需要清理的启动遮挡")

    def _current_community_tab_text(self) -> str:
        """读取底部左侧当前社区 Tab 文案，社区名是动态的，不能绑定固定 text。"""
        root = self._load_ui_hierarchy()
        candidates: list[tuple[int, str]] = []
        for node in root.iter("node"):
            attrs = dict(node.attrib)
            if attrs.get("resource-id") != app_rid("main_tab_item_text"):
                continue
            text = self._normalize_text_value(attrs.get("text"))
            bounds = self._parse_bounds(attrs.get("bounds", ""))
            if not text or not bounds or text in {"商城", "消息"}:
                continue
            x1, _, x2, _ = bounds
            center_x = (x1 + x2) // 2
            if center_x <= 360:
                candidates.append((center_x, text))

        if not candidates:
            return ""
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def _community_display_key(self, name: Any, visible_prefix_length: int = 4) -> str:
        """Normalize community names for places where the APP truncates the display text."""
        text = self._normalize_text_value(name)
        if not text:
            return ""
        for marker in ("...", "…", "···", "。。。"):
            if marker in text:
                text = text.split(marker, 1)[0]
                break
        return text[: max(int(visible_prefix_length or 4), 1)]

    def _community_name_matches_display(
        self,
        full_name: Any,
        display_name: Any,
        visible_prefix_length: int = 4,
    ) -> bool:
        """Match a full community name with a bottom-tab display that may only show a prefix."""
        full_text = self._normalize_text_value(full_name)
        display_text = self._normalize_text_value(display_name)
        if not full_text or not display_text:
            return False
        if full_text == display_text:
            return True

        truncated_markers = ("...", "…", "···", "。。。")
        display_is_truncated = (
            any(marker in display_text for marker in truncated_markers)
            or len(display_text) <= int(visible_prefix_length or 4)
        )
        if not display_is_truncated:
            return False

        display_key = self._community_display_key(display_text, visible_prefix_length)
        if not display_key:
            return False

        return full_text.startswith(display_key)

    def _visible_drawer_community_nodes(self) -> list[dict[str, Any]]:
        """读取社区抽屉里当前可见的已关注社区名称节点。"""
        root = self._load_ui_hierarchy()
        nodes: list[dict[str, Any]] = []
        seen: set[str] = set()
        for node in root.iter("node"):
            attrs = dict(node.attrib)
            if attrs.get("resource-id") != app_rid("tvServerName"):
                continue
            text = self._normalize_text_value(attrs.get("text"))
            bounds = self._parse_bounds(attrs.get("bounds", ""))
            if not text or not bounds or text in seen:
                continue
            x1, y1, x2, y2 = bounds
            if x2 <= 0 or x1 >= 780 or y2 <= 0:
                continue
            seen.add(text)
            nodes.append({**attrs, "_text": text, "_bounds_tuple": bounds})
        nodes.sort(key=lambda item: (item["_bounds_tuple"][1], item["_bounds_tuple"][0]))
        return nodes

    def _action_remember_current_community(self, step: Dict[str, Any]):
        """在打开社区抽屉前记录当前社区名称，作为切换断言基准。"""
        timeout = float(step.get("timeout", 5) or 5)
        deadline = time.time() + max(timeout, 0)
        current_name = ""
        while True:
            current_name = self._current_community_tab_text()
            if current_name:
                self._set_variable("previous_community_name", current_name, "local")
                logger.info("已记录当前社区: %s", current_name)
                return
            if time.time() >= deadline:
                break
            sleep(0.5)
        raise RuntimeError("未读取到底部当前社区名称，无法执行社区切换用例")

    def _action_click_other_followed_community(self, step: Dict[str, Any]):
        """在关注社区抽屉中选择一个非当前社区，避免固定依赖某个社区是否已关注。"""
        visible_prefix_length = int(step.get("visible_prefix_length", 4) or 4)
        current_name = self._normalize_text_value(
            self._get_variable("previous_community_name") or self._current_community_tab_text()
        )
        if not current_name:
            raise RuntimeError("切换前社区名称为空，请先执行“记录当前社区”步骤")

        nodes = self._visible_drawer_community_nodes()
        target_node = next(
            (
                node for node in nodes
                if not self._community_name_matches_display(
                    node["_text"],
                    current_name,
                    visible_prefix_length,
                )
            ),
            None,
        )
        if not target_node:
            visible_names = "、".join(node["_text"] for node in nodes) or "无"
            raise RuntimeError(
                f"社区抽屉中未找到可切换的其他已关注社区。当前社区: {current_name or '-'}，"
                f"可见社区: {visible_names}"
            )

        target_name = target_node["_text"]
        center = self._node_center(target_node)
        if not center:
            raise RuntimeError(f"目标社区项缺少 bounds，无法点击: {target_name}")

        self._set_variable("previous_community_name", current_name, "local")
        self._set_variable("selected_community_name", target_name, "local")
        logger.info("从关注列表切换社区: %s -> %s", current_name or "-", target_name)
        self._set_action_evidence(
            action="tap",
            target_name=target_name,
            center=[center[0], center[1]],
            bounds=target_node.get("bounds"),
        )
        self._device_shell(f"input tap {center[0]} {center[1]}")

    def _community_preview_follow_visible(self) -> bool:
        return self._selector_node_exists(
            self._inline_android_selector(app_rid("previewLayout"))
        )

    def _community_exit_entry_visible(self) -> bool:
        return self._selector_node_exists(
            self._inline_android_selector(app_rid("cv_exit"))
        )

    def _open_community_more_menu(self, timeout: float = 5) -> bool:
        selector = self._inline_android_selector(app_rid("ivMore"))
        if not self._tap_selector_if_visible(selector, timeout=timeout):
            selector = self._inline_android_selector(app_rid("iv_more"))
            if not self._tap_selector_if_visible(selector, timeout=1):
                return False
        sleep(0.8)
        return self._selector_node_exists(
            self._inline_android_selector(app_rid("bottomPopupContainer"))
        )

    def _exit_current_community_if_possible(self) -> bool:
        """退出当前关注社区，仅用于为关注/取消关注用例准备稳定状态。"""
        if not self._open_community_more_menu(timeout=4):
            return False
        if not self._community_exit_entry_visible():
            self._device_shell("input keyevent BACK")
            sleep(0.5)
            return False

        self._tap_target(self._inline_android_selector(app_rid("cv_exit")), timeout=3)
        sleep(0.8)
        confirm_selector = self._inline_android_selector(app_rid("dialog_hint_confirm"))
        if not self._tap_selector_if_visible(confirm_selector, timeout=5):
            raise AssertionError("退出当前社区失败：确认按钮未出现")
        sleep(2)
        return True

    def _tap_global_community_search_entry(self) -> bool:
        """点击顶部全局搜索入口，避开房间列表里的同 resource-id 筛选框。"""
        try:
            root = self._load_ui_hierarchy()
        except Exception as exc:
            logger.debug("读取全局搜索入口失败: %s", exc)
            return False

        candidates: list[tuple[int, int, dict[str, Any]]] = []
        for node in root.iter("node"):
            attrs = dict(node.attrib)
            if attrs.get("resource-id") != app_rid("tvHintText"):
                continue
            text = self._normalize_text_value(attrs.get("text"))
            bounds = self._parse_bounds(attrs.get("bounds", ""))
            if not bounds:
                continue
            x1, y1, x2, y2 = bounds
            is_global_text = "搜索社区" in text or "用户名称" in text
            is_top_area = y2 <= 360
            if is_global_text or is_top_area:
                candidates.append((0 if is_global_text else 1, y1, attrs))

        if not candidates:
            return False

        _, _, target = sorted(candidates, key=lambda item: (item[0], item[1]))[0]
        center = self._node_center(target)
        if not center:
            return False
        self._set_action_evidence(
            action="tap",
            target_name=self._normalize_text_value(target.get("text")) or "全局搜索入口",
            center=[center[0], center[1]],
            bounds=target.get("bounds"),
        )
        self._device_shell(f"input tap {center[0]} {center[1]}")
        return True

    def _search_and_open_community(self, keyword: Any, timeout: float = 12) -> None:
        keyword_text = self._normalize_input_value(keyword)
        if not keyword_text:
            raise ValueError("搜索社区需要 community_id/community_no/keyword")

        package_name = APP_PACKAGE
        self._action_launch_activity({
            "package": package_name,
            "activity": "",
            "force_stop": True,
            "duration": 2,
        })
        self._action_ensure_account_logged_in({
            "phone": self._get_variable("phone"),
            "password": self._get_variable("password"),
            "timeout": 20,
        })
        self._dismiss_server_switch_guide_if_present()
        try:
            width, height = G.DEVICE.get_current_resolution()
            self._device_shell(f"input tap {int(width * 0.16)} {int(height * 0.965)}")
        except Exception:
            self._device_shell("input tap 180 2324")
        sleep(0.5)

        if not self._tap_global_community_search_entry():
            raise AssertionError("进入社区搜索失败：未找到首页搜索入口")

        input_selector = self._inline_android_selector(app_rid("etContent"))
        if not self._wait_for_selector(input_selector, timeout=5):
            raise AssertionError("进入社区搜索失败：未找到搜索输入框")
        self._input_into_target(input_selector, keyword_text, clear_first=True, timeout=5)

        submit_selector = self._inline_android_selector(app_rid("tvSearch"))
        if not self._tap_selector_if_visible(submit_selector, timeout=3):
            raise AssertionError("搜索社区失败：未找到搜索按钮")
        sleep(2)

        result_list = self._inline_android_selector(app_rid("recyclerView"))
        if not self._wait_for_selector(result_list, timeout=timeout):
            raise AssertionError(f"搜索社区失败：未找到搜索结果列表，keyword={keyword_text}")

        result_item = self._inline_android_selector(app_rid("rootView"))
        if not self._tap_selector_if_visible(result_item, timeout=5):
            raise AssertionError(f"搜索社区失败：未找到可点击的社区结果，keyword={keyword_text}")
        sleep(2)
        if not self._wait_for_main_home_ready(timeout=timeout):
            raise AssertionError(f"搜索社区后未进入社区首页，keyword={keyword_text}")
        self._set_variable("target_community_keyword", keyword_text, "local")

    def _community_keywords_from_step(self, step: Dict[str, Any]) -> list[str]:
        raw = (
            step.get("community_keywords")
            or step.get("community_ids")
            or step.get("community_no")
            or step.get("community_id")
            or step.get("keyword")
            or getattr(settings, "APP_AUTOMATION_TEST_COMMUNITY_KEYWORD", "")
        )
        if isinstance(raw, str):
            return [item.strip() for item in re.split(r"[,，\s]+", raw) if item.strip()]
        if isinstance(raw, (list, tuple)):
            return [str(item).strip() for item in raw if str(item).strip()]
        return [str(raw).strip()]

    def _action_ensure_unfollowed_community_home(self, step: Dict[str, Any]):
        """进入未关注社区首页；若目标已关注，则先退出再重新进入。"""
        last_error = ""
        for keyword in self._community_keywords_from_step(step):
            try:
                logger.info("尝试准备未关注社区首页: %s", keyword)
                self._search_and_open_community(keyword, timeout=float(step.get("timeout", 12) or 12))
                if self._community_preview_follow_visible():
                    logger.info("已进入未关注社区首页: %s", keyword)
                    return
                if self._exit_current_community_if_possible():
                    self._search_and_open_community(keyword, timeout=float(step.get("timeout", 12) or 12))
                    if self._community_preview_follow_visible():
                        logger.info("退出后重新进入未关注社区首页: %s", keyword)
                        return
                last_error = f"{keyword} 不显示未关注预览条，且无法通过退出社区准备未关注态"
            except Exception as exc:
                last_error = f"{keyword}: {exc}"
                logger.warning("准备未关注社区失败: %s", last_error)
        raise AssertionError(f"未能准备未关注社区首页。最后状态: {last_error}")

    def _action_ensure_followed_community_home(self, step: Dict[str, Any]):
        """进入已关注社区首页；若目标未关注，则先关注，供退出社区用例使用。"""
        last_error = ""
        for keyword in self._community_keywords_from_step(step):
            try:
                logger.info("尝试准备已关注社区首页: %s", keyword)
                self._search_and_open_community(keyword, timeout=float(step.get("timeout", 12) or 12))
                if self._community_preview_follow_visible():
                    follow_selector = self._inline_android_selector(app_rid("btnJoinServer"))
                    if not self._tap_selector_if_visible(follow_selector, timeout=5):
                        raise AssertionError("准备已关注社区失败：未找到关注社区按钮")
                    sleep(2)
                if self._open_community_more_menu(timeout=5):
                    has_exit = self._community_exit_entry_visible()
                    self._device_shell("input keyevent BACK")
                    sleep(0.5)
                    if has_exit:
                        logger.info("已进入可退出的已关注社区首页: %s", keyword)
                        return
                    last_error = f"{keyword} 已进入但没有退出社区入口，可能是管理/官方社区"
                else:
                    last_error = f"{keyword} 已进入但更多菜单未打开"
            except Exception as exc:
                last_error = f"{keyword}: {exc}"
                logger.warning("准备已关注社区失败: %s", last_error)
        raise AssertionError(f"未能准备可退出的已关注社区首页。最后状态: {last_error}")

    def _action_ensure_unfollowed_member_hall(self, step: Dict[str, Any]):
        """进入指定未关注社区的全员大厅，用于校验未关注态触发关注弹窗。"""
        self._action_ensure_unfollowed_community_home(step)
        self._action_click_member_hall_entry({
            **step,
            "timeout": step.get("hall_entry_timeout", step.get("timeout", 10)),
            "duration": step.get("hall_entry_wait", 0.8),
        })
        self._action_assert_member_hall_opened({
            **step,
            "timeout": step.get("hall_open_timeout", 8),
        })

    def _action_assert_current_community_switched(self, step: Dict[str, Any]):
        """断言底部当前社区 Tab 已切换。

        如果配置了 expected/community_name 或上一步选择了目标社区，则校验切换到指定社区；
        否则只校验当前社区已经不同于切换/退出前记录的社区。
        """
        visible_prefix_length = int(step.get("visible_prefix_length", 4) or 4)
        expected_name = (
            step.get("expected")
            or step.get("community_name")
            or self._get_variable("selected_community_name")
        )
        expected_name = self._normalize_text_value(expected_name)
        previous_name = self._normalize_text_value(self._get_variable("previous_community_name"))
        if not previous_name:
            raise RuntimeError("切换前社区名称为空，不能判定社区切换是否真实发生")
        if expected_name and self._community_name_matches_display(expected_name, previous_name, visible_prefix_length):
            raise AssertionError(f"社区切换断言失败: 选择的社区仍是原社区 '{previous_name}'")

        previous_key = self._community_display_key(previous_name, visible_prefix_length)
        expected_key = self._community_display_key(expected_name, visible_prefix_length)
        if expected_name and expected_key and expected_key == previous_key:
            raise AssertionError(
                f"社区切换断言失败: 切换前社区 '{previous_name}' 与目标社区 '{expected_name}' "
                f"前 {visible_prefix_length} 个字相同，底部 TAB 截断展示无法可靠区分"
            )

        timeout = float(step.get("timeout", 8) or 8)
        deadline = time.time() + max(timeout, 0)
        actual_name = ""
        while True:
            actual_name = self._current_community_tab_text()
            still_previous = self._community_name_matches_display(
                previous_name,
                actual_name,
                visible_prefix_length,
            )
            if expected_name:
                matches_expected = self._community_name_matches_display(
                    expected_name,
                    actual_name,
                    visible_prefix_length,
                )
                if matches_expected and not still_previous:
                    logger.info(
                        "社区切换断言通过: 目标社区=%s, 底部展示=%s",
                        expected_name,
                        actual_name,
                    )
                    return
            elif actual_name and not still_previous:
                logger.info(
                    "社区变化断言通过: 切换前社区=%s, 当前社区=%s",
                    previous_name,
                    actual_name,
                )
                return
            if time.time() >= deadline:
                break
            sleep(0.5)

        if expected_name:
            raise AssertionError(
                f"社区切换断言失败: 期望底部当前社区显示为 '{expected_name}' 或其前 {visible_prefix_length} 字，"
                f"实际为 '{actual_name or '-'}'，"
                f"切换前社区: {previous_name or '-'}"
            )
        raise AssertionError(
            f"社区变化断言失败: 期望当前社区不同于退出前社区 '{previous_name}'，"
            f"实际仍为 '{actual_name or '-'}'"
        )

    def _action_assert_logout_confirm_dialog(self, step: Dict[str, Any]):
        """一次性校验退出登录确认弹窗，避免同一弹窗重复 dump UI。"""
        timeout = float(step.get("timeout", step.get("duration", 4)) or 4)
        expected_text = str(step.get("expected") or "确认退出？").strip()
        deadline = time.time() + max(timeout, 0)
        last_state: dict[str, bool] = {}

        while True:
            ui_source = self._get_ui_source_safe()
            last_state = {
                "message": expected_text in ui_source,
                "cancel": "dialog_hint_cancel" in ui_source or "取消" in ui_source,
                "confirm": "dialog_hint_confirm" in ui_source or "确认" in ui_source,
            }
            if all(last_state.values()):
                logger.info("退出登录确认弹窗断言通过: %s", last_state)
                return
            if time.time() >= deadline:
                break
            sleep(0.3)

        raise AssertionError(f"退出登录确认弹窗断言失败: expected={expected_text}, state={last_state}")

    def _dismiss_startup_dialogs_if_present(self, timeout: float = 4.0) -> bool:
        """关闭启动/青少年模式/权限类弹窗，避免遮挡主页识别。"""
        try:
            handled_count = handle_dialogs(
                shell=self._device_shell,
                dump_xml=self._dump_ui_xml,
                selectors=STARTUP_DIALOG_SELECTORS,
                timeout=timeout,
                interval=0.4,
                idle_rounds_to_stop=2,
                settle_seconds=0.8,
            )
        except Exception as exc:
            logger.debug("启动弹窗处理失败，继续后续判断: %s", exc)
            return False
        return handled_count > 0

    def _login_page_visible(self) -> bool:
        """判断当前是否真的停留在登录页，避免已登录场景误触发登录流程。"""
        login_signals = (
            self._inline_android_selector(app_rid("et_number")),
            self._inline_android_selector(app_rid("etPassword")),
            self._inline_android_selector(app_rid("tvPasswordLogin")),
            self._inline_android_selector(app_rid("btnLogin")),
        )
        return any(self._selector_node_exists(selector) for selector in login_signals)

    def _perform_password_login(self, phone: Any, password: Any, timeout: float = 20) -> None:
        phone_value = self._normalize_input_value(phone)
        password_value = self._normalize_input_value(password)
        if not phone_value or not password_value:
            raise ValueError("ensure_account_logged_in 需要 phone/password")

        phone_selector = self._inline_android_selector(app_rid("et_number"))
        password_selector = self._inline_android_selector(app_rid("etPassword"))
        switch_selector = self._inline_android_selector(app_rid("tvPasswordLogin"))
        agree_selector = self._inline_android_selector(app_rid("cbkAgree"))
        submit_selector = self._inline_android_selector(app_rid("btnLogin"))
        home_selector = self._inline_android_selector(app_rid("fragment_container"))

        if self._selector_node_exists(switch_selector):
            logger.info("切换到密码登录页")
            self._tap_target(switch_selector, timeout=3)
            sleep(0.8)

        if not self._selector_node_exists(phone_selector):
            raise RuntimeError("未发现登录手机号输入框，无法执行账号密码登录")

        logger.info("执行账号密码登录: phone=%s", phone_value)
        self._input_into_target(phone_selector, phone_value, clear_first=True, timeout=5)

        if not self._selector_node_exists(password_selector):
            raise RuntimeError("未发现密码输入框，无法执行账号密码登录")
        self._input_into_target(password_selector, password_value, clear_first=True, timeout=5)

        if self._selector_node_exists(agree_selector):
            self._tap_target(agree_selector, timeout=3)
            sleep(0.3)

        self._tap_target(submit_selector, timeout=5)
        sleep(1)
        self._action_handle_slider({
            "timeout": 6,
            "post_login_timeout": timeout,
            "success_selector": home_selector,
            "success_selector_type": "selector",
            "max_attempts": 4,
        })

        if not self._wait_for_main_home_ready(timeout):
            raise RuntimeError("账号密码登录后未进入 APP 首页")
        self._dismiss_server_switch_guide_if_present()

    def _action_ensure_account_logged_in(self, step: Dict[str, Any]):
        """Ensure the APP is on a logged-in home page, handling downline notice and login page."""
        if self._main_home_ready():
            logger.info("当前已处于登录后的首页状态")
            return

        self._dismiss_downline_notice_if_present()
        if self._main_home_ready():
            logger.info("处理下线通知后已回到首页")
            return

        if not self._login_page_visible():
            focus = self._current_focus_info()
            if focus.get("package_name") == APP_PACKAGE:
                if self._wait_for_main_home_ready(timeout=5):
                    logger.info("当前已处于 APP 内，等待后识别为登录后的首页状态")
                    return
                logger.info(
                    "当前已在目标 APP 内且未发现登录页控件，按已登录处理；"
                    "如果后续步骤失败，应按页面起点或遮挡问题排查"
                )
                return
            raise RuntimeError(
                f"当前前台不是目标 APP，无法确认登录态。前台信息: {focus.get('raw') or '-'}"
            )

        phone = step.get("phone") or self._get_variable("phone")
        password = step.get("password") or self._get_variable("password")
        self._perform_password_login(phone, password, timeout=float(step.get("timeout", 20) or 20))

    def _return_to_main_or_login(self, max_backs: int = 4) -> bool:
        for _ in range(max(0, int(max_backs))):
            if self._login_page_visible() or self._main_home_ready():
                return True
            self._device_shell("input keyevent KEYCODE_BACK")
            sleep(0.8)
        return self._login_page_visible() or self._main_home_ready()

    def _tap_bottom_message_tab(self) -> None:
        """切到消息 Tab，底部主导航是固定区域，selector 失败时用坐标兜底。"""
        if self._tap_text_if_visible("消息", timeout=2):
            return
        try:
            width, height = G.DEVICE.get_current_resolution()
            x, y = int(width * 0.84), int(height * 0.965)
        except Exception:
            x, y = 900, 2324
        self._set_action_evidence(action="tap", target_name="消息 Tab", center=[x, y])
        self._device_shell(f"input tap {x} {y}")

    def _open_message_settings_drawer(self) -> None:
        """打开消息页右上角设置侧边栏，兼容 menu selector 暂时不可见的情况。"""
        menu_selector = self._inline_android_selector(app_rid("menu"))
        if self._tap_selector_if_visible(menu_selector, timeout=3):
            sleep(1)
            return

        try:
            width, height = G.DEVICE.get_current_resolution()
            x, y = int(width * 0.92), int(height * 0.085)
        except Exception:
            x, y = 996, 204
        logger.info("未通过 selector 找到消息页设置入口，使用右上角坐标兜底: %s,%s", x, y)
        self._set_action_evidence(action="tap", target_name="消息页设置入口", center=[x, y])
        self._device_shell(f"input tap {x} {y}")
        sleep(1)

    def _action_ensure_logged_out(self, step: Dict[str, Any]):
        """Make login cases suite-safe by reaching the login page first."""
        package_name = step.get("package") or step.get("package_name") or APP_PACKAGE
        if self._login_page_visible():
            logger.info("当前已处于登录页，无需退出登录")
            return

        self._action_launch_activity({
            "package": package_name,
            "activity": "",
            "force_stop": True,
            "duration": 2,
        })
        self._dismiss_downline_notice_if_present()
        if self._login_page_visible():
            logger.info("冷启动后已处于登录页")
            return

        if not self._main_home_ready():
            self._return_to_main_or_login(max_backs=4)
        if self._login_page_visible():
            logger.info("返回后已处于登录页")
            return
        if not self._main_home_ready():
            raise AssertionError("确认登出失败：无法回到首页或登录页")

        self._tap_bottom_message_tab()
        sleep(1)

        self._open_message_settings_drawer()

        drawer_selector = self._inline_android_selector(app_rid("rightDrawerContainer"))
        if not self._selector_node_exists(drawer_selector):
            raise AssertionError("确认登出失败：设置侧边栏未展开")

        logout_tapped = False
        for attempt in range(4):
            if self._tap_text_if_visible("退出登录", timeout=1.5):
                logout_tapped = True
                break
            logger.info("未看到退出登录入口，第 %s 次向上滑动侧边栏", attempt + 1)
            self._device_shell("input swipe 700 1900 700 760 650")
            sleep(0.8)
        if not logout_tapped:
            raise AssertionError("确认登出失败：侧边栏内未找到退出登录入口")

        confirm_selector = self._inline_android_selector(app_rid("dialog_hint_confirm"))
        if not self._tap_selector_if_visible(confirm_selector, timeout=5):
            raise AssertionError("确认登出失败：退出登录确认按钮未出现")
        sleep(2)

        if not self._login_page_visible():
            raise AssertionError("确认登出失败：确认退出后未回到登录页")

    def _dynamic_list_visible(self) -> bool:
        return self._selector_node_exists(
            self._inline_android_selector(app_rid("rv_my_moments"))
        )

    def _wait_for_dynamic_list(self, timeout: float = 8) -> bool:
        deadline = time.time() + max(float(timeout or 0), 0)
        while True:
            if self._dynamic_list_visible():
                return True
            if time.time() >= deadline:
                return False
            sleep(0.5)

    def _tap_text_if_visible(self, text_value: str, timeout: float = 3) -> bool:
        selector = self._inline_android_selector(text=text_value)
        if not self._wait_for_selector(selector, timeout):
            return False
        self._tap_target(selector, timeout=timeout)
        return True

    def _tap_selector_if_visible(self, selector: Dict[str, Any], timeout: float = 3) -> bool:
        if not self._wait_for_selector(selector, timeout):
            return False
        self._tap_target(selector, timeout=timeout)
        return True

    def _action_ensure_personal_dynamic_list(self, step: Dict[str, Any]):
        """Navigate to the personal dynamic list without relying on a page title."""
        timeout = float(step.get("timeout", step.get("duration", 12)) or 12)
        if self._wait_for_dynamic_list(timeout=1):
            logger.info("当前已在个人动态列表页")
            return

        package_name = step.get("package") or step.get("package_name") or APP_PACKAGE
        self._action_launch_activity({
            "package": package_name,
            "activity": "",
            "force_stop": True,
            "duration": 2,
        })
        self._action_ensure_account_logged_in({
            "phone": step.get("phone") or self._get_variable("phone"),
            "password": step.get("password") or self._get_variable("password"),
            "timeout": 20,
        })
        if self._wait_for_dynamic_list(timeout=1):
            logger.info("冷启动后已在个人动态列表页")
            return

        # From the main shell, the personal dynamic list is reached through the
        # message tab's profile header. Do not use the settings drawer's
        # "编辑资料" row here; that opens ProfileEditActivity instead.
        if not self._tap_text_if_visible("消息", timeout=5):
            raise AssertionError("进入个人动态列表失败：未找到底部消息 Tab")
        sleep(1)

        entry_attempts: list[tuple[str, Any]] = [
            ("消息页头像", self._inline_android_selector(app_rid("avatar"))),
            ("消息页昵称", self._inline_android_selector(app_rid("nickname"))),
            ("消息页个人头部区域", (120, 204)),
        ]
        last_state = ""
        for name, target in entry_attempts:
            logger.info("尝试进入个人动态列表: %s", name)
            if self._is_selector_target(target):
                tapped = self._tap_selector_if_visible(target, timeout=2)
            else:
                x, y = target
                self._set_action_evidence(action="tap", target_name=name, center=[x, y])
                self._device_shell(f"input tap {x} {y}")
                tapped = True
            if not tapped:
                continue
            if self._wait_for_dynamic_list(timeout=timeout):
                logger.info("已进入个人动态列表: %s", name)
                return
            try:
                root = self._load_ui_hierarchy()
                texts = [
                    self._normalize_text_value(node.attrib.get("text"))
                    for node in root.iter("node")
                    if self._normalize_text_value(node.attrib.get("text"))
                ]
                last_state = "、".join(texts[:8])
            except Exception as exc:
                last_state = str(exc)
            self._device_shell("input keyevent KEYCODE_BACK")
            sleep(0.8)

        raise AssertionError(f"进入个人动态列表失败：未找到动态列表容器，最后页面文本={last_state or '-'}")

    def _iter_node_texts(self, node: ET.Element) -> list[str]:
        texts: list[str] = []
        for child in node.iter("node"):
            for key in ("text", "content-desc", "hint"):
                value = self._normalize_text_value(child.attrib.get(key))
                if value:
                    texts.append(value)
        return texts

    def _nearest_clickable_room_row(
        self,
        node: ET.Element,
        parent_map: dict[ET.Element, ET.Element],
    ) -> Optional[ET.Element]:
        current = node
        while current in parent_map:
            current = parent_map[current]
            attrs = current.attrib
            bounds = self._parse_bounds(attrs.get("bounds", ""))
            if not bounds:
                continue
            x1, y1, x2, y2 = bounds
            if (
                attrs.get("clickable") == "true"
                and (x2 - x1) >= 800
                and (y2 - y1) >= 100
                and y1 >= 650
                and y2 <= 2240
            ):
                return current
        return None

    def _voice_room_row_info(self, row: ET.Element, room_name: str) -> dict[str, Any]:
        texts = self._iter_node_texts(row)
        resource_ids = [
            self._normalize_text_value(child.attrib.get("resource-id"))
            for child in row.iter("node")
        ]
        joined_text = " ".join(texts)
        joined_resource_ids = " ".join(resource_ids).lower()

        is_full = "已满" in joined_text
        is_locked = (
            "已锁" in joined_text
            or "lock" in joined_resource_ids
            or "password" in joined_resource_ids
            or "密码" in joined_text
        )
        # 互动语音房列表右侧是类似无穷符号的业务图标，当前可访问树中通常体现为 ifvLiveRoomSymbol。
        is_interactive = "ifvliveroomsymbol" in joined_resource_ids
        room_type = "interactive" if is_interactive else "normal"

        bounds = self._parse_bounds(row.attrib.get("bounds", ""))
        return {
            "name": room_name,
            "type": room_type,
            "is_full": is_full,
            "is_locked": is_locked,
            "bounds": bounds,
            "texts": texts,
        }

    def _has_ancestor_resource(self, node: ET.Element, parent_map: dict[ET.Element, ET.Element], resource_tail: str) -> bool:
        current = node
        while current in parent_map:
            current = parent_map[current]
            resource_id = self._normalize_text_value(current.attrib.get("resource-id"))
            if resource_id.endswith(resource_tail):
                return True
        return False

    def _nearest_clickable_ancestor(
        self,
        node: ET.Element,
        parent_map: dict[ET.Element, ET.Element],
    ) -> Optional[ET.Element]:
        current = node
        while current in parent_map:
            current = parent_map[current]
            attrs = current.attrib
            bounds = self._parse_bounds(attrs.get("bounds", ""))
            if attrs.get("clickable") == "true" and bounds:
                return current
        return None

    def _article_card_info(self, row: ET.Element, tag_node: ET.Element) -> dict[str, Any]:
        tag_text = " ".join(self._iter_node_texts(tag_node)).strip()
        title = ""
        for child in row.iter("node"):
            attrs = child.attrib
            if self._normalize_text_value(attrs.get("resource-id")).endswith("/tvTitle"):
                title = self._normalize_text_value(attrs.get("text"))
                if title:
                    break
        return {
            "tag": tag_text,
            "title": title,
            "bounds": self._parse_bounds(row.attrib.get("bounds", "")),
        }

    def _entry_row_info(self, row: ET.Element, icon_node: Optional[ET.Element] = None) -> dict[str, Any]:
        title = ""
        for child in row.iter("node"):
            attrs = child.attrib
            if self._normalize_text_value(attrs.get("resource-id")).endswith("/tvTitle"):
                title = self._normalize_text_value(attrs.get("text"))
                if title:
                    break

        icon_text = ""
        icon_bounds = None
        if icon_node is not None:
            icon_text = self._normalize_text_value(icon_node.attrib.get("text"))
            icon_bounds = self._parse_bounds(icon_node.attrib.get("bounds", ""))

        return {
            "title": title,
            "icon_text": icon_text,
            "icon_bounds": icon_bounds,
            "bounds": self._parse_bounds(row.attrib.get("bounds", "")),
            "texts": self._iter_node_texts(row),
        }

    def _find_member_hall_rows(self) -> list[tuple[int, ET.Element, dict[str, Any]]]:
        """Find member hall entry by the stable icon before the row title, not by row position."""
        root = self._load_ui_hierarchy()
        parent_map = {child: parent for parent in root.iter() for child in parent}
        rows: list[tuple[int, ET.Element, dict[str, Any]]] = []
        seen_bounds: set[tuple[int, int, int, int]] = set()

        for node in root.iter("node"):
            attrs = node.attrib
            resource_id = self._normalize_text_value(attrs.get("resource-id"))
            icon_text = self._normalize_text_value(attrs.get("text"))
            if not resource_id.endswith("/ifvTitleIcon") or icon_text != "\ue651":
                continue
            if not self._has_ancestor_resource(node, parent_map, "/rvRooms"):
                continue

            row = self._nearest_clickable_ancestor(node, parent_map)
            if row is None:
                continue
            bounds = self._parse_bounds(row.attrib.get("bounds", ""))
            if not bounds or bounds in seen_bounds:
                continue
            x1, y1, x2, y2 = bounds
            if (x2 - x1) < 700 or (y2 - y1) < 80:
                continue

            seen_bounds.add(bounds)
            rows.append((y1, row, self._entry_row_info(row, node)))

        rows.sort(key=lambda item: item[0])
        return rows

    def _visible_home_entry_candidates(self) -> list[dict[str, Any]]:
        root = self._load_ui_hierarchy()
        parent_map = {child: parent for parent in root.iter() for child in parent}
        candidates: list[dict[str, Any]] = []
        seen_bounds: set[tuple[int, int, int, int]] = set()
        for node in root.iter("node"):
            attrs = node.attrib
            resource_id = self._normalize_text_value(attrs.get("resource-id"))
            if not resource_id.endswith("/ifvTitleIcon"):
                continue
            row = self._nearest_clickable_ancestor(node, parent_map)
            if row is None:
                continue
            info = self._entry_row_info(row, node)
            bounds = info.get("bounds")
            if not bounds or bounds in seen_bounds:
                continue
            seen_bounds.add(bounds)
            candidates.append(info)
        candidates.sort(key=lambda item: (item.get("bounds") or (0, 0, 0, 0))[1])
        return candidates

    def _wait_for_member_hall_row(self, timeout: float) -> tuple[ET.Element, dict[str, Any]]:
        deadline = time.time() + max(float(timeout or 0), 0)
        last_candidates: list[dict[str, Any]] = []
        while True:
            rows = self._find_member_hall_rows()
            if rows:
                _, row, info = rows[0]
                return row, info
            try:
                last_candidates = self._visible_home_entry_candidates()
            except Exception as exc:
                logger.debug("读取首页入口候选失败: %s", exc)
            if time.time() >= deadline:
                raise RuntimeError(
                    "未找到全员大厅入口：没有发现 ifvTitleIcon=\\ue651 的可点击整行。"
                    f"当前可见入口候选={last_candidates}"
                )
            sleep(0.4)

    def _action_click_member_hall_entry(self, step: Dict[str, Any]):
        """Click member hall entry by its leading icon to avoid hitting exclusive-room plugins."""
        timeout = float(step.get("timeout", 10) or 10)
        row, info = self._wait_for_member_hall_row(timeout)
        center = self._node_center(dict(row.attrib))
        if not center:
            raise ValueError(f"全员大厅入口缺少 bounds，无法点击: {info}")
        x, y = center
        logger.info(
            "点击全员大厅入口: icon=%s title=%s bounds=%s center=(%s,%s)",
            self._safe_log_text(info.get("icon_text")),
            info.get("title"),
            info.get("bounds"),
            x,
            y,
        )
        self._set_variable("last_member_hall_title", info.get("title", ""), "outputs")
        self._set_variable("last_member_hall_bounds", info.get("bounds"), "outputs")
        self._set_action_evidence(
            action="tap",
            target_name=info.get("title") or "全员大厅入口",
            icon_text=self._safe_log_text(info.get("icon_text")),
            center=[x, y],
            bounds=info.get("bounds"),
        )
        self._device_shell(f"input tap {x} {y}")
        post_wait = float(step.get("post_wait", step.get("duration", 0.5)) or 0)
        if post_wait > 0:
            sleep(post_wait)

    def _action_assert_member_hall_opened(self, step: Dict[str, Any]):
        """Assert we entered the chat-style member hall and did not accidentally enter a voice room."""
        timeout = float(step.get("timeout", 8) or 8)
        deadline = time.time() + max(timeout, 0)
        last_state: dict[str, Any] = {}

        positive_resource_tails = ("/chat_layout", "/rv_chat", "/chat_message_input", "/input_layout")
        room_detail_tails = ("/roomContainer", "/iv_quit", "/rv_mic", "/bottom_panel", "/tv_room_name")
        home_entry_tails = ("/rvRooms", "/ifvTitleIcon")

        while True:
            root = self._load_ui_hierarchy()
            resource_ids = [
                self._normalize_text_value(node.attrib.get("resource-id"))
                for node in root.iter("node")
            ]
            texts = [
                self._normalize_text_value(node.attrib.get("text"))
                for node in root.iter("node")
                if self._normalize_text_value(node.attrib.get("text"))
            ]

            positive_hits = [
                tail for tail in positive_resource_tails
                if any(resource_id.endswith(tail) for resource_id in resource_ids)
            ]
            room_hits = [
                tail for tail in room_detail_tails
                if any(resource_id.endswith(tail) for resource_id in resource_ids)
            ]
            home_hits = [
                tail for tail in home_entry_tails
                if any(resource_id.endswith(tail) for resource_id in resource_ids)
            ]
            last_state = {
                "positive_hits": positive_hits,
                "room_detail_hits": room_hits,
                "home_hits": home_hits,
                "title_candidates": [text for text in texts if text][:8],
            }

            if room_hits:
                raise AssertionError(f"全员大厅断言失败：疑似进入语音房/专属房详情页，命中={room_hits}")
            if len(positive_hits) >= 2:
                logger.info("全员大厅断言通过: %s", last_state)
                return
            if time.time() >= deadline:
                break
            sleep(0.5)

        if last_state.get("home_hits") and not last_state.get("positive_hits"):
            raise AssertionError(f"全员大厅断言失败：点击后仍疑似停留在社区首页，状态={last_state}")
        raise AssertionError(f"全员大厅断言失败：未发现大厅聊天区稳定控件，状态={last_state}")

    def _action_assert_hall_message_sent(self, step: Dict[str, Any]):
        """Assert the just-sent member hall text appears in the chat message list."""
        expected_text = self._normalize_text_value(
            step.get("expected")
            or step.get("message")
            or self._get_variable("last_input_value", "outputs")
            or self._get_variable("last_input_value")
        )
        if not expected_text:
            raise RuntimeError("全员大厅消息断言缺少 expected/message，且未读取到上一步输入内容")

        timeout = float(step.get("timeout", 8) or 8)
        deadline = time.time() + max(timeout, 0)
        last_visible_messages: list[str] = []
        while True:
            root = self._load_ui_hierarchy()
            visible_messages = []
            for node in root.iter("node"):
                attrs = dict(node.attrib)
                if attrs.get("resource-id") != app_rid("tv_text"):
                    continue
                text_value = self._normalize_text_value(attrs.get("text"))
                if text_value:
                    visible_messages.append(text_value)

            last_visible_messages = visible_messages[-8:]
            if expected_text in visible_messages:
                logger.info("全员大厅消息发送断言通过: %s", expected_text)
                return

            if time.time() >= deadline:
                break
            sleep(0.5)

        raise AssertionError(
            f"全员大厅消息发送断言失败: 未在消息列表中找到 '{expected_text}'，"
            f"当前可见消息: {'、'.join(last_visible_messages) or '-'}"
        )

    def _action_remember_first_message_conversation(self, step: Dict[str, Any]):
        """Capture the first visible conversation nickname from the message list."""
        timeout = float(step.get("timeout", 8) or 8)
        deadline = time.time() + max(timeout, 0)
        last_candidates: list[str] = []

        while True:
            root = self._load_ui_hierarchy()
            parent_map = {child: parent for parent in root.iter() for child in parent}
            candidates = []

            for node in root.iter("node"):
                attrs = dict(node.attrib)
                resource_id = self._normalize_text_value(attrs.get("resource-id"))
                if not resource_id.endswith("/NickBadgeViewName"):
                    continue
                if not self._has_ancestor_resource(node, parent_map, "/rv_conversation"):
                    continue

                name = self._normalize_text_value(attrs.get("text"))
                bounds = self._parse_bounds(attrs.get("bounds", ""))
                if not name or not bounds:
                    continue
                if name in {"系统通知"}:
                    continue
                _, y1, _, _ = bounds
                candidates.append((y1, name))

            candidates.sort(key=lambda item: item[0])
            last_candidates = [name for _, name in candidates[:5]]
            if candidates:
                keyword = candidates[0][1]
                self._set_variable("message_search_keyword", keyword, "outputs")
                logger.info("记录首条消息会话搜索关键词: %s", keyword)
                return

            if time.time() >= deadline:
                break
            sleep(0.5)

        raise AssertionError(f"未找到可用于搜索的消息会话昵称，候选={last_candidates}")

    def _action_assert_message_search_results(self, step: Dict[str, Any]):
        """Assert message search returns non-empty results for the current keyword."""
        expected_text = self._normalize_text_value(
            step.get("expected")
            or step.get("keyword")
            or self._get_variable("last_input_value", "outputs")
            or self._get_variable("last_input_value")
        )
        timeout = float(step.get("timeout", 8) or 8)
        deadline = time.time() + max(timeout, 0)
        last_state: dict[str, Any] = {}

        while True:
            root = self._load_ui_hierarchy()
            visible_texts = []
            result_count_text = ""
            has_result_list = False

            for node in root.iter("node"):
                attrs = dict(node.attrib)
                resource_id = self._normalize_text_value(attrs.get("resource-id"))
                text_value = self._normalize_text_value(attrs.get("text"))

                if text_value:
                    visible_texts.append(text_value)
                if resource_id.endswith("/searchResultCount"):
                    result_count_text = text_value
                if resource_id.endswith("/rv_content"):
                    has_result_list = True

            joined_text = " ".join(visible_texts)
            is_empty = "暂无搜索结果" in joined_text or "搜索结果-0个结果" in joined_text
            has_expected = bool(expected_text and expected_text in joined_text)
            has_positive_count = bool(re.search(r"搜索结果-[1-9]\d*个结果", result_count_text or ""))
            last_state = {
                "expected": expected_text,
                "result_count": result_count_text,
                "has_result_list": has_result_list,
                "has_expected": has_expected,
                "visible_texts": visible_texts[:20],
            }

            if not is_empty and has_result_list and (has_expected or has_positive_count):
                logger.info("消息搜索结果断言通过: %s", last_state)
                return

            if time.time() >= deadline:
                break
            sleep(0.5)

        raise AssertionError(f"消息搜索结果断言失败：未检索到有效会话结果，状态={last_state}")

    def _find_article_plugin_cards(self) -> list[tuple[int, ET.Element, dict[str, Any]]]:
        """Find article plugin rows by the tag/symbol before title, not by title or screen position."""
        root = self._load_ui_hierarchy()
        parent_map = {child: parent for parent in root.iter() for child in parent}
        candidates: list[tuple[int, ET.Element, dict[str, Any]]] = []
        seen_bounds: set[tuple[int, int, int, int]] = set()

        for node in root.iter("node"):
            resource_id = self._normalize_text_value(node.attrib.get("resource-id"))
            if not resource_id.endswith("/ctvTitleTag"):
                continue
            if not self._has_ancestor_resource(node, parent_map, "/rvRooms"):
                continue

            row = self._nearest_clickable_ancestor(node, parent_map)
            if row is None:
                continue
            bounds = self._parse_bounds(row.attrib.get("bounds", ""))
            if not bounds or bounds in seen_bounds:
                continue
            seen_bounds.add(bounds)

            _, y1, _, _ = bounds
            candidates.append((y1, row, self._article_card_info(row, node)))

        candidates.sort(key=lambda item: item[0])
        return candidates

    def _wait_for_article_plugin_card(self, timeout: float) -> tuple[ET.Element, dict[str, Any]]:
        deadline = time.time() + max(float(timeout or 0), 0)
        last_candidates: list[dict[str, Any]] = []
        while True:
            candidates = self._find_article_plugin_cards()
            last_candidates = [item[2] for item in candidates]
            if candidates:
                _, row, info = candidates[0]
                return row, info
            if time.time() >= deadline:
                raise RuntimeError(f"未找到文章插件卡片：没有发现 ctvTitleTag 标签控件，候选={last_candidates}")
            sleep(0.4)

    def _action_assert_article_plugin_card(self, step: Dict[str, Any]):
        """Assert article plugin exists by its business tag/symbol control."""
        timeout = float(step.get("timeout", 10) or 10)
        _, info = self._wait_for_article_plugin_card(timeout)
        logger.info("文章插件卡片存在: tag=%s title=%s bounds=%s", info.get("tag"), info.get("title"), info.get("bounds"))
        self._set_variable("last_article_tag", info.get("tag", ""), "outputs")
        self._set_variable("last_article_title", info.get("title", ""), "outputs")

    def _action_click_article_plugin_card(self, step: Dict[str, Any]):
        """Click article plugin row anchored by ctvTitleTag, avoiding unrelated homepage plugins."""
        timeout = float(step.get("timeout", 10) or 10)
        row, info = self._wait_for_article_plugin_card(timeout)
        center = self._node_center(dict(row.attrib))
        if not center:
            raise ValueError(f"文章插件卡片缺少 bounds，无法点击: {info}")
        x, y = center
        logger.info(
            "点击文章插件卡片: tag=%s title=%s bounds=%s center=(%s,%s)",
            info.get("tag"), info.get("title"), info.get("bounds"), x, y,
        )
        self._set_variable("last_article_tag", info.get("tag", ""), "outputs")
        self._set_variable("last_article_title", info.get("title", ""), "outputs")
        self._set_action_evidence(
            action="tap",
            target_name=info.get("title") or info.get("tag") or "文章插件卡片",
            center=[x, y],
            bounds=info.get("bounds"),
        )
        self._device_shell(f"input tap {x} {y}")
        post_wait = float(step.get("post_wait", step.get("duration", 0.5)) or 0)
        if post_wait > 0:
            sleep(post_wait)

    def _action_click_available_voice_room(self, step: Dict[str, Any]):
        """点击首个可进入语音房整行，跳过已满/已锁，并记录房间模板。"""
        preferred_type = str(step.get("room_type") or step.get("value") or "any").strip().lower()
        timeout = float(step.get("timeout", 10) or 10)
        max_swipes = int(step.get("max_swipes", 3) or 0)
        scroll_count = 0
        deadline = time.time() + max(timeout, 0)
        last_candidates: list[dict[str, Any]] = []
        scanned_candidates: list[dict[str, Any]] = []

        while True:
            root = self._load_ui_hierarchy()
            parent_map = {child: parent for parent in root.iter() for child in parent}
            candidates: list[tuple[int, ET.Element, dict[str, Any]]] = []
            seen_bounds: set[tuple[int, int, int, int]] = set()

            for node in root.iter("node"):
                attrs = node.attrib
                resource_id = self._normalize_text_value(attrs.get("resource-id"))
                if not resource_id.endswith("/tvRoomName"):
                    continue
                room_name = self._normalize_text_value(attrs.get("text"))
                row = self._nearest_clickable_room_row(node, parent_map)
                if row is None:
                    continue
                info = self._voice_room_row_info(row, room_name)
                bounds = info.get("bounds")
                if not bounds or bounds in seen_bounds:
                    continue
                seen_bounds.add(bounds)
                scanned_candidates.append(info)
                if info["is_full"] or info["is_locked"]:
                    logger.info(
                        "跳过不可进入语音房: name=%s type=%s full=%s locked=%s bounds=%s",
                        info["name"], info["type"], info["is_full"], info["is_locked"], bounds,
                    )
                    continue
                if preferred_type in {"normal", "interactive"} and info["type"] != preferred_type:
                    continue
                _, y1, _, _ = bounds
                candidates.append((y1, row, info))

            candidates.sort(key=lambda item: item[0])
            last_candidates = [item[2] for item in candidates]
            if candidates:
                _, row, info = candidates[0]
                center = self._node_center(dict(row.attrib))
                if not center:
                    raise ValueError(f"语音房行缺少 bounds，无法点击: {info}")
                x, y = center
                logger.info(
                    "点击可进入语音房: name=%s type=%s bounds=%s center=(%s,%s)",
                    info["name"], info["type"], info["bounds"], x, y,
                )
                self._set_variable("last_voice_room_name", info["name"], "outputs")
                self._set_variable("last_voice_room_type", info["type"], "outputs")
                self._set_action_evidence(
                    action="tap",
                    target_name=info["name"],
                    target_type=info["type"],
                    center=[x, y],
                    bounds=info["bounds"],
                )
                self._device_shell(f"input tap {x} {y}")
                post_wait = float(step.get("post_wait", step.get("duration", 0.5)) or 0)
                if post_wait > 0:
                    sleep(post_wait)
                return

            if time.time() >= deadline:
                raise RuntimeError(
                    f"未找到可进入语音房: preferred_type={preferred_type}, "
                    f"当前候选={last_candidates}, 已扫描={scanned_candidates[-12:]}"
                )

            if preferred_type in {"normal", "interactive"} and scroll_count < max_swipes:
                try:
                    width, height = G.DEVICE.get_current_resolution()
                    start_x = int(width * 0.5)
                    start_y = int(height * 0.78)
                    end_y = int(height * 0.48)
                except Exception:
                    start_x, start_y, end_y = 540, 1880, 1160
                scroll_count += 1
                logger.info(
                    "当前屏未找到 %s 语音房，第 %s/%s 次下滑继续查找",
                    preferred_type,
                    scroll_count,
                    max_swipes,
                )
                self._device_shell(f"input swipe {start_x} {start_y} {start_x} {end_y} 450")
                sleep(0.6)
                continue
            sleep(0.4)

    def _action_assert_voice_room_type(self, step: Dict[str, Any]):
        """Assert the room template selected by click_available_voice_room."""
        expected_type = str(step.get("room_type") or step.get("expected") or step.get("value") or "").strip().lower()
        if expected_type not in {"normal", "interactive"}:
            raise ValueError("assert_voice_room_type 需要配置 expected/room_type 为 normal 或 interactive")

        actual_type = str(self._get_variable("last_voice_room_type", "outputs") or "").strip().lower()
        room_name = self._get_variable("last_voice_room_name", "outputs") or "-"
        if actual_type != expected_type:
            raise AssertionError(
                f"房型断言失败: 期望 {expected_type}, 实际 {actual_type or '-'}, 房间={room_name}"
            )

        logger.info("房型断言成功: 房间=%s, type=%s", room_name, actual_type)

    def _get_ui_source_safe(self) -> str:
        try:
            return self._dump_ui_xml()
        except Exception as exc:
            logger.debug("获取 UI 树失败: %s", exc)
            return ""

    def _capture_snapshot_path(self, name_prefix: str) -> Path:
        filename = f"{self._safe_filename(name_prefix)}_{int(time.time() * 1000)}.png"
        full_path = Path(self.screenshots_dir) / filename
        try:
            result = snapshot(filename=str(full_path))
            if isinstance(result, dict):
                screen_path = result.get("screen")
                if screen_path and os.path.exists(screen_path):
                    return Path(screen_path)
            if full_path.exists():
                return full_path
        except Exception as exc:
            logger.warning("Airtest 滑块截图失败，尝试使用 ADB screencap 兜底: %s: %r", type(exc).__name__, exc)
            fallback_path = self._capture_screenshot_via_adb(full_path)
            if fallback_path:
                return Path(fallback_path)
            raise RuntimeError(f"滑块截图失败，Airtest={type(exc).__name__}: {exc!r}，ADB 兜底失败") from exc
        return full_path

    def _attach_file_if_possible(self, path: Path, name: str, attachment_type=None) -> None:
        if not self._allure_enabled() or not path.exists():
            return
        try:
            allure.attach.file(str(path), name=name, attachment_type=attachment_type)
        except Exception:
            logger.exception("Allure 文件附件写入失败: %s", path)

    def _is_slider_present(self, ui_source: Optional[str] = None) -> bool:
        source = (ui_source or self._get_ui_source_safe() or "").lower()
        if not source:
            return False
        slider_signals = (
            "tcimgarea",
            "slidebg",
            "tcaptcha",
            "secverify",
            "instructiontext",
            "drag the slider",
            "拖动下方滑块完成拼图",
            'text="slider"',
            'resource-id="reload"',
        )
        return any(signal in source for signal in slider_signals)

    def _wait_for_slider_present(self, timeout: float, interval: float = 0.35) -> str:
        deadline = time.time() + max(float(timeout or 0), 0.0)
        while True:
            ui_source = self._get_ui_source_safe()
            if self._is_slider_present(ui_source):
                return ui_source
            if time.time() >= deadline:
                return ""
            time.sleep(interval)

    def _wait_for_slider_cleared(
        self,
        timeout: float,
        success_target: Any = None,
        interval: float = 0.4,
    ) -> bool:
        deadline = time.time() + max(float(timeout or 0), 0.0)
        while True:
            if success_target is not None:
                try:
                    if self._target_exists(success_target):
                        return True
                except Exception as exc:
                    logger.debug("检查滑块成功目标失败: %s", exc)

            ui_source = self._get_ui_source_safe()
            if ui_source and not self._is_slider_present(ui_source):
                return True

            if time.time() >= deadline:
                return False
            time.sleep(interval)

    def _solve_slider_captcha(
        self,
        *,
        attempt: int,
        solve_timeout: float,
        confidence_threshold: float,
        x_offset: int,
    ) -> SliderCaptchaSolution:
        if not SLIDER_SOLVER_AVAILABLE:
            raise RuntimeError("滑块求解依赖不可用，请检查 opencv / numpy 环境。")

        solver = SliderCaptchaSolver()
        deadline = time.time() + max(float(solve_timeout or 0), 4.0)
        last_error = "slider solve did not start"

        while True:
            screenshot_path = self._capture_snapshot_path(f"slider_attempt_{attempt}")
            debug_path = screenshot_path.with_name(f"{screenshot_path.stem}_match.png")
            page_source = self._get_ui_source_safe()
            if not self._is_slider_present(page_source):
                raise RuntimeError("Slider captcha is no longer present.")

            try:
                solution = solver.solve(
                    screenshot_path,
                    page_source,
                    debug_image_path=debug_path,
                    confidence_threshold=confidence_threshold,
                    x_offset=x_offset,
                )
                if self._allure_enabled():
                    self._attach_file_if_possible(
                        screenshot_path,
                        name=f"slider-attempt-{attempt}",
                        attachment_type=allure.attachment_type.PNG,
                    )
                    self._attach_file_if_possible(
                        debug_path,
                        name=f"slider-match-{attempt}",
                        attachment_type=allure.attachment_type.PNG,
                    )
                return solution
            except RuntimeError as exc:
                last_error = str(exc)
                lowered = last_error.lower()
                transient_markers = (
                    "not ready",
                    "still loading",
                    "placeholder",
                    "unable to locate slider",
                    "captcha crop is empty",
                    "search crop is empty",
                    "confidence is too low",
                )
                if not any(marker in lowered for marker in transient_markers):
                    raise
                logger.info("滑块识别重试中，第 %s 次尝试: %s", attempt, last_error)
                if time.time() >= deadline:
                    break
                time.sleep(0.5)

            if time.time() >= deadline:
                break

        raise RuntimeError(last_error)

    def _perform_slider_solution_drag(
        self,
        solution: SliderCaptchaSolution,
        *,
        duration_ms: int,
        overshoot_px: int,
    ) -> None:
        start_x = int(solution.start_x)
        start_y = int(solution.start_y)
        end_x = int(min(solution.captcha_bounds[2] - 20, solution.end_x + max(0, overshoot_px)))
        end_y = int(solution.end_y)
        logger.info(
            "执行滑块拖动: (%s,%s) -> (%s,%s), duration_ms=%s, confidence=%.3f, distance_x=%s",
            start_x,
            start_y,
            end_x,
            end_y,
            duration_ms,
            solution.confidence,
            solution.distance_x,
        )
        try:
            self._device_shell(f"input swipe {start_x} {start_y} {end_x} {end_y} {int(duration_ms)}")
        except Exception:
            logger.exception("ADB 滑块拖动失败，回退到 Airtest swipe")
            swipe((start_x, start_y), (end_x, end_y), duration=max(duration_ms / 1000.0, 0.2))
        time.sleep(0.3)

    def _tap_slider_reload(self) -> bool:
        reload_selector = {
            "_selector_kind": "android_selector",
            "resource_id": "reload",
        }
        node = self._find_selector_node(reload_selector)
        if not node:
            logger.info("未找到滑块刷新按钮，跳过刷新")
            return False
        center = self._node_center(node)
        if not center:
            logger.info("滑块刷新按钮缺少 bounds，跳过刷新")
            return False
        x, y = center
        logger.info("点击滑块刷新按钮: (%s,%s)", x, y)
        self._device_shell(f"input tap {x} {y}")
        time.sleep(0.6)
        return True

    def _tap_login_privacy_dialog_if_present(self) -> bool:
        return handle_dialogs(
            shell=self._device_shell,
            dump_xml=self._dump_ui_xml,
            selectors=POST_LOGIN_DIALOG_SELECTORS,
            timeout=0.1,
            interval=0.1,
            idle_rounds_to_stop=1,
            settle_seconds=0.8,
        ) > 0

    def _tap_post_login_popup_if_present(self) -> bool:
        return self._tap_login_privacy_dialog_if_present()

    def _wait_for_post_login_ready(
        self,
        success_target: Any = None,
        timeout: float = 8.0,
        interval: float = 0.35,
    ) -> bool:
        if success_target is None:
            return True

        deadline = time.time() + max(float(timeout or 0), 0.0)
        while True:
            try:
                if self._target_exists(success_target):
                    return True
            except Exception as exc:
                logger.debug("post-login success target check failed: %s", exc)

            handled = False
            if self._tap_login_privacy_dialog_if_present():
                handled = True
            if handled:
                continue

            if time.time() >= deadline:
                return False
            time.sleep(interval)


    def _clear_focused_text(self, length_hint: int = 0):
        length_hint = int(length_hint or 0)
        if length_hint <= 0:
            logger.debug("跳过清空输入框：当前文本长度为 0")
            return

        delete_times = length_hint + 4
        for _ in range(delete_times):
            try:
                self._device_shell("input keyevent KEYCODE_DEL")
            except Exception:
                break

    def _normalize_input_value(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    def _format_adb_input_text(self, value: str) -> str:
        # Android input text uses %s for spaces. Shell quoting protects &, (), etc.
        text = value.replace("%", "%25").replace(" ", "%s")
        return shlex.quote(text)

    def _send_text_to_focused(self, value: Any):
        text_value = self._normalize_input_value(value)
        if text_value == "":
            raise ValueError("输入步骤缺少输入内容，请在用例编排中填写 value/text")

        if any(ord(char) > 127 for char in text_value):
            try:
                ime_list = self._device_shell("ime list -s")
                if "com.netease.nie.yosemite/.ime.ImeService" in ime_list:
                    self._device_shell("ime set com.netease.nie.yosemite/.ime.ImeService")
            except Exception as ime_exc:
                logger.debug("切换 Yosemite 输入法失败，继续尝试 Airtest 输入: %s", ime_exc)
            try:
                airtest_text(text_value)
                return
            except Exception as airtest_exc:
                logger.warning("Airtest 中文输入失败，尝试 adb input text fallback: %s", airtest_exc)

        adb_text = self._format_adb_input_text(text_value)
        try:
            self._device_shell(f"input text {adb_text}")
            return
        except Exception as adb_exc:
            logger.warning("adb input text 失败，尝试 Airtest text fallback: %s", adb_exc)

        try:
            airtest_text(text_value)
        except Exception as airtest_exc:
            raise RuntimeError(f"输入文本失败，请检查输入内容或当前焦点: {text_value!r}") from airtest_exc

    def _input_into_target(self, target: Any, value: Any, clear_first: bool = True, timeout: float = 10):
        if self._is_selector_target(target):
            node = self._resolve_selector_node(target, timeout, allow_bounds_fallback=True)
            if not node:
                raise ValueError(f"未找到 selector 元素，无法输入: {target}")
            self._tap_target(target, timeout=timeout)
            time.sleep(0.3)
            if clear_first:
                current_text = self._normalize_text_value(node.get("text"))
                self._clear_focused_text(len(current_text))
            self._send_text_to_focused(value)
            return

        if isinstance(target, (list, tuple)) and len(target) >= 2:
            x, y = int(target[0]), int(target[1])
            self._set_action_evidence(action="input", center=[x, y])
            self._device_shell(f"input tap {x} {y}")
            time.sleep(0.3)
            self._send_text_to_focused(value)
            return

        self._send_text_to_focused(value)

    def _resolve_selector(self, step: Dict[str, Any]) -> Any:
        """
        解析选择器
        
        支持的类型:
        - element_id: 从数据库加载元素
        - image: 图片元素
        - pos: 坐标点
        - region: 区域
        """
        # 优先使用 element_id
        element_id = step.get('element_id')
        if element_id:
            return self._resolve_element_by_id(element_id)
        
        selector_type = step.get('selector_type', 'image')
        selector = step.get('selector', '')

        if selector_type == 'selector':
            return self._parse_inline_selector(selector)
        
        if selector_type == 'image':
            # 图片选择器
            if not selector:
                logger.warning(f"图片选择器的 selector 为空，请检查步骤配置: {step.get('name', step.get('type', 'unknown'))}")
                return None
            
            image_scope = step.get('image_scope', 'common')
            image_path = os.path.join(self.image_base_dir, image_scope, selector)
            
            if not os.path.isfile(image_path):
                logger.warning(f"图片文件不存在: {image_path}")
                return None
            
            threshold = step.get('image_threshold', 0.7)
            return Template(image_path, threshold=threshold)
        
        elif selector_type == 'pos':
            # 坐标选择器
            if isinstance(selector, str):
                parts = [p.strip() for p in selector.split(',')]
                if len(parts) >= 2:
                    return (int(parts[0]), int(parts[1]))
            elif isinstance(selector, (list, tuple)) and len(selector) >= 2:
                return (int(selector[0]), int(selector[1]))
            
            logger.warning(f"无效的坐标格式: {selector}")
            return None
        
        elif selector_type == 'region':
            # 区域选择器（用于 exists 等）
            if isinstance(selector, str):
                parts = [p.strip() for p in selector.split(',')]
                if len(parts) >= 4:
                    return (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
            elif isinstance(selector, (list, tuple)) and len(selector) >= 4:
                return tuple(int(x) for x in selector[:4])
            
            logger.warning(f"无效的区域格式: {selector}")
            return None
        
        logger.warning(f"未知的选择器类型: {selector_type}")
        return None
    
    def _resolve_element_by_id(self, element_id: int) -> Any:
        """从数据库加载元素"""
        try:
            from apps.app_automation.models import AppElement
            
            element = AppElement.objects.filter(id=element_id, is_active=True).first()
            if not element:
                logger.warning(f"未找到元素: element_id={element_id}")
                return None
            
            # 记录使用次数
            element.increment_usage()
            
            # 根据元素类型返回选择器
            if element.element_type == 'image':
                image_rel_path = element.config.get('image_path', '')
                if not image_rel_path:
                    logger.warning(f"元素 {element_id} 的 image_path 为空")
                    return None
                
                image_path = os.path.join(self.image_base_dir, image_rel_path)
                
                if not os.path.isfile(image_path):
                    logger.warning(f"图片文件不存在: {image_path}")
                    return None
                
                threshold = element.config.get('image_threshold', 0.7)
                return Template(image_path, threshold=threshold)
            
            elif element.element_type == 'pos':
                x = element.config.get('x')
                y = element.config.get('y')
                return (x, y)
            
            elif element.element_type == 'region':
                x1 = element.config.get('x1')
                y1 = element.config.get('y1')
                x2 = element.config.get('x2')
                y2 = element.config.get('y2')
                return (x1, y1, x2, y2)

            elif element.element_type == 'selector':
                selector_data = {
                    "_selector_kind": "android_selector",
                    "resource_id": element.config.get("resource_id"),
                    "text": element.config.get("text"),
                    "content_desc": element.config.get("content_desc"),
                    "class": element.config.get("class"),
                    "hint": element.config.get("hint"),
                    "package": element.config.get("package"),
                    "activity": element.config.get("activity"),
                    "bounds": element.config.get("bounds"),
                    "locator_key": element.config.get("locator_key"),
                    "strategy": element.config.get("strategy"),
                    "enabled": element.config.get("enabled"),
                    "clickable": element.config.get("clickable"),
                    "focusable": element.config.get("focusable"),
                }
                if any(selector_data.get(key) for key in ("resource_id", "text", "content_desc", "class", "hint", "bounds")):
                    return selector_data
                logger.warning("selector 元素缺少可用定位字段: element_id=%s", element_id)
                return None

        except Exception as e:
            logger.error(f"解析元素失败: element_id={element_id}, 错误: {e}", exc_info=True)
            return None
    
    def _action_touch(self, step: Dict[str, Any]):
        """点击动作"""
        target = self._resolve_selector(step)
        if target is None:
            step_name = step.get('name', step.get('type', 'unknown'))
            raise ValueError(f"步骤 '{step_name}' 无法解析选择器，请检查元素配置（selector 或 element_id）")
        logger.info(f"执行点击: {target}")
        self._tap_target(target, timeout=step.get('timeout', 10))

    def _action_click_step(self, step: Dict[str, Any]):
        """Idempotent click wrapper with optional skip_if guard."""
        skip_if_target = None
        skip_if_selector = step.get("skip_if_selector")
        skip_if_selector_type = step.get("skip_if_selector_type")
        skip_if_element_id = step.get("skip_if_element_id")
        if skip_if_selector or skip_if_element_id:
            skip_if_target = self._resolve_selector(
                {
                    "selector": skip_if_selector,
                    "selector_type": skip_if_selector_type or "selector",
                    "element_id": skip_if_element_id,
                }
            )
        if skip_if_target is not None:
            try:
                if self._target_exists(skip_if_target):
                    logger.info("Click step skipped because skip_if target exists")
                    return
            except Exception as exc:
                logger.debug("Click step skip_if check failed: %s", exc)
        self._action_touch(step)
    
    def _action_double_click(self, step: Dict[str, Any]):
        """双击动作"""
        target = self._resolve_selector(step)
        if target:
            logger.info(f"执行双击: {target}")
            if self._is_selector_target(target):
                self._tap_target(target, timeout=step.get('timeout', 10))
                time.sleep(0.15)
                self._tap_target(target, timeout=step.get('timeout', 10))
            else:
                double_click(target)
    
    def _action_swipe(self, step: Dict[str, Any]):
        """滑动动作"""
        import json
        
        start = step.get('start')
        end = step.get('end')
        duration = step.get('duration', 0.5)
        
        # 处理 pos 定位方式的 selector
        if not start and not end:
            selector = step.get('selector')
            selector_type = step.get('selector_type')
            if selector and selector_type == 'pos':
                try:
                    if isinstance(selector, str):
                        locator = json.loads(selector)
                    else:
                        locator = selector
                    if isinstance(locator, list) and len(locator) >= 2:
                        start = tuple(locator[0])
                        end = tuple(locator[1])
                    else:
                        raise ValueError(f"Invalid locator for swipe: {locator}")
                except (json.JSONDecodeError, ValueError) as e:
                    raise ValueError(f"Failed to parse swipe locator: {selector}, error: {e}")
        
        if isinstance(start, str):
            start = tuple(int(x) for x in start.split(','))
        if isinstance(end, str):
            end = tuple(int(x) for x in end.split(','))
        
        if not start or not end:
            raise ValueError(f"Missing start or end coordinates for swipe: start={start}, end={end}")
        
        logger.info(f"执行滑动: {start} -> {end}")
        self._set_action_evidence(
            action="swipe",
            start=[int(start[0]), int(start[1])],
            end=[int(end[0]), int(end[1])],
        )
        swipe(start, end, duration=duration)
    
    def _action_wait(self, step: Dict[str, Any]):
        """等待：有 selector 时等待元素出现，没有时纯等待 timeout 秒"""
        target = self._resolve_selector(step)
        timeout = step.get('timeout', step.get('duration', 3))
        
        if target:
            logger.info(f"等待元素出现: {target}, 超时: {timeout}s")
            self._wait_for_target(target, timeout=timeout)
        else:
            timeout = step.get('duration', step.get('timeout', 3))
            logger.info(f"等待 {timeout} 秒")
            sleep(timeout)

    def _action_keyevent(self, step: Dict[str, Any]):
        """发送 Android 按键，常用于让用例自行返回上一页。"""
        key = str(step.get('keyevent') or step.get('key') or 'BACK').strip().upper()
        if not key.startswith('KEYCODE_'):
            key = f'KEYCODE_{key}'
        logger.info("发送 Android 按键: %s", key)
        self._set_action_evidence(action="keyevent", key=key)
        self._device_shell(f"input keyevent {shlex.quote(key)}")
        post_wait = float(step.get('post_wait', step.get('duration', 0.5)) or 0)
        if post_wait > 0:
            sleep(post_wait)

    def _action_back_until(self, step: Dict[str, Any]):
        """Press BACK until the expected target page/element appears, avoiding keyboard-only back false positives."""
        target = self._resolve_selector({
            "element_id": step.get("target_element_id") or step.get("element_id"),
            "selector": step.get("target_selector") or step.get("selector"),
            "selector_type": step.get("target_selector_type") or step.get("selector_type") or "selector",
            "image_scope": step.get("target_image_scope") or step.get("image_scope") or "common",
            "image_threshold": step.get("target_image_threshold") or step.get("image_threshold") or 0.7,
        })
        if target is None:
            raise ValueError("back_until 需要配置目标元素 target_selector 或 target_element_id")

        if self._target_exists(target):
            logger.info("目标元素已存在，跳过返回动作")
            self._set_action_evidence(action="back_until", key="KEYCODE_BACK", result="target_already_visible")
            return

        max_backs = max(1, int(step.get("max_backs", 3) or 3))
        interval = float(step.get("interval", step.get("duration", 0.8)) or 0.8)
        timeout = float(step.get("timeout", 10) or 10)
        deadline = time.time() + max(timeout, interval * max_backs)

        for attempt in range(1, max_backs + 1):
            logger.info("第 %s/%s 次返回，等待目标元素出现", attempt, max_backs)
            self._set_action_evidence(
                action="back_until",
                key="KEYCODE_BACK",
                attempt=attempt,
                max_backs=max_backs,
                target=target,
            )
            self._device_shell("input keyevent KEYCODE_BACK")
            sleep(interval)
            if self._target_exists(target):
                logger.info("返回成功，目标元素已出现")
                return
            if time.time() >= deadline:
                break

        raise AssertionError(f"返回后未到达目标页面，目标元素仍未出现: {target}")

    def _action_launch_activity(self, step: Dict[str, Any]):
        """启动指定 Activity；force_stop=True 表示保留数据的冷启动。"""
        package_name = str(step.get('package') or step.get('package_name') or '').strip()
        activity = str(step.get('activity') or step.get('main_activity') or '').strip()
        if not package_name:
            raise ValueError("launch_activity 需要配置 package")

        if step.get('force_stop') is True:
            logger.info("强停应用后冷启动，保留登录态和应用数据: %s", package_name)
            self._device_shell(f"am force-stop {shlex.quote(package_name)}")
            time.sleep(0.4)

        if activity:
            component = f"{package_name}/{activity}"
            logger.info("启动 Activity: %s", component)
            self._device_shell(f"am start -n {shlex.quote(component)}")
        else:
            logger.info("通过 monkey 启动应用: %s", package_name)
            self._device_shell(f"monkey -p {shlex.quote(package_name)} -c android.intent.category.LAUNCHER 1")

        post_wait = float(step.get('post_wait', step.get('duration', 1.5)) or 0)
        if post_wait > 0:
            sleep(post_wait)
    
    def _action_handle_slider(self, step: Dict[str, Any]):
        """Handle post-login privacy dialog and slider captcha."""
        success_target = None
        success_selector = step.get("success_selector")
        success_selector_type = step.get("success_selector_type")
        success_element_id = step.get("success_element_id")
        if success_selector or success_element_id:
            success_step = {
                "selector": success_selector,
                "selector_type": success_selector_type or "selector",
                "element_id": success_element_id,
            }
            success_target = self._resolve_selector(success_step)
            if success_target is not None:
                try:
                    if self._target_exists(success_target):
                        logger.info("Home target already exists, skip post-login transition handling")
                        return
                except Exception as exc:
                    logger.debug("Home target pre-check failed: %s", exc)

        raw_attempt_offsets = step.get("attempt_x_offsets", [0, 12, -12, 20])
        if isinstance(raw_attempt_offsets, (list, tuple)):
            attempt_x_offsets = tuple(int(offset) for offset in raw_attempt_offsets)
        else:
            attempt_x_offsets = (0, 12, -12, 20)

        handler = SliderCaptchaHandler(
            capture_snapshot_path=self._capture_snapshot_path,
            get_ui_source_safe=self._get_ui_source_safe,
            attach_file_if_possible=self._attach_file_if_possible,
            target_exists=self._target_exists,
            tap_login_privacy_dialog_if_present=self._tap_login_privacy_dialog_if_present,
            wait_for_post_login_ready=self._wait_for_post_login_ready,
            device_shell=self._device_shell,
            find_selector_node=self._find_selector_node,
            node_center=self._node_center,
        )
        handler.handle(
            SliderHandlerConfig(
                success_target=success_target,
                appearance_timeout=float(step.get("timeout", step.get("appearance_timeout", 6))),
                settle_timeout=float(step.get("settle_timeout", 5)),
                solve_timeout=float(step.get("solve_timeout", 8)),
                max_attempts=max(1, int(step.get("max_attempts", 4))),
                confidence_threshold=float(step.get("confidence_threshold", 0.2)),
                duration_ms=int(step.get("duration_ms", 1200)),
                overshoot_px=int(step.get("overshoot_px", 8)),
                post_login_timeout=float(step.get("post_login_timeout", 8)),
                x_offset=int(step.get("x_offset", 0)),
                attempt_x_offsets=attempt_x_offsets,
                reload_between_attempts=bool(step.get("reload_between_attempts", True)),
            )
        )


    def _action_snapshot(self, step: Dict[str, Any]):
        """截图"""
        name = step.get('name', f'snapshot_{int(time.time())}')
        filename = f"{name}.png"
        
        filepath = os.path.join(self.screenshots_dir, filename)
        
        logger.info(f"截图保存: {filepath}")
        snapshot(filename=filepath)
    
    def _action_text(self, step: Dict[str, Any]):
        """输入文本"""
        text_value = step.get('text', '')
        logger.info(f"输入文本: {text_value}")
        airtest_text(text_value)
    
    def _action_set_variable(self, step: Dict[str, Any]):
        """设置变量"""
        name = step.get('name')
        value = step.get('value')
        scope = step.get('scope', 'local')
        
        if name:
            self._set_variable(name, value, scope)
            logger.info(f"设置变量: {scope}.{name} = {value}")
    
    def _action_assert(self, step: Dict[str, Any]):
        """
        断言入口，根据 assert_type 分发到具体实现。
        支持 timeout 参数：断言失败后在 timeout 秒内持续重试（适配页面加载延迟）。
        
        支持的 assert_type:
        - text:   OCR 识别文本，支持 exact/contains/regex 匹配
        - number: OCR 识别数字（自动去除逗号等格式符号），精确匹配
        - regex:  OCR 识别文本，用正则表达式匹配（text + match_mode=regex 的快捷方式）
        - range:  OCR 识别数字，判断是否在 [min, max] 范围内
        - exists: 判断图片元素是否存在于屏幕上
        - image:  在屏幕上查找期望图片是否存在（图片对比断言）
        - page/activity: 判断当前前台包名和 Activity 是否符合预期
        """
        assert_type = step.get('assert_type', 'text')
        timeout = float(step.get('timeout', 0))
        retry_interval = float(step.get('retry_interval', 1))
        
        assert_map = {
            'text': self._assert_text,
            'number': self._assert_number,
            'regex': self._assert_regex,
            'range': self._assert_range,
            'exists': self._assert_exists,
            'image': self._assert_image,
            'page': self._assert_activity,
            'activity': self._assert_activity,
        }
        
        handler = assert_map.get(assert_type)
        if not handler:
            raise ValueError(f"未知的断言类型: {assert_type}，支持: {', '.join(assert_map.keys())}")
        
        # 无超时：直接执行一次
        if timeout <= 0:
            handler(step)
            return
        
        # 有超时：在 timeout 秒内持续重试
        deadline = time.time() + timeout
        last_error = None
        attempt = 0
        while True:
            attempt += 1
            try:
                handler(step)
                if attempt > 1:
                    logger.info(f"断言在第 {attempt} 次尝试后通过")
                return  # 断言通过
            except (AssertionError, Exception) as e:
                last_error = e
                if time.time() >= deadline:
                    break
                remaining = deadline - time.time()
                wait_time = min(retry_interval, remaining)
                if wait_time > 0:
                    logger.debug(
                        f"断言未通过 (第 {attempt} 次)，{wait_time:.1f}s 后重试: {e}"
                    )
                    sleep(wait_time)
        
        raise last_error
    
    # ---------- 断言内部实现 ----------
    
    def _parse_ocr_region(self, step: Dict[str, Any]) -> tuple:
        """
        从步骤配置中解析 OCR 区域坐标 (x1, y1, x2, y2)。
        同时支持 selector 和 ocr_selector 字段名。
        """
        selector = step.get('ocr_selector') or step.get('selector')
        selector_type = step.get('ocr_selector_type') or step.get('selector_type', 'region')
        
        if not selector:
            raise ValueError("断言需要 selector 或 ocr_selector 参数来指定 OCR 区域")
        
        if selector_type != 'region':
            raise ValueError(f"OCR 断言仅支持 selector_type=region，当前: {selector_type}")
        
        if isinstance(selector, str):
            parts = [int(p.strip()) for p in selector.split(',')]
            if len(parts) != 4:
                raise ValueError(f"region 格式错误，需要 4 个值 (x1,y1,x2,y2): {selector}")
            return tuple(parts)
        elif isinstance(selector, (list, tuple)) and len(selector) >= 4:
            return tuple(int(x) for x in selector[:4])
        else:
            raise ValueError(f"无法解析 region: {selector}")
    
    def _region_hit(self, node_bounds: tuple, region: tuple) -> bool:
        ax1, ay1, ax2, ay2 = node_bounds
        rx1, ry1, rx2, ry2 = region
        cx = (ax1 + ax2) / 2
        cy = (ay1 + ay2) / 2
        if rx1 <= cx <= rx2 and ry1 <= cy <= ry2:
            return True

        overlap_width = max(0, min(ax2, rx2) - max(ax1, rx1))
        overlap_height = max(0, min(ay2, ry2) - max(ay1, ry1))
        overlap_area = overlap_width * overlap_height
        if overlap_area <= 0:
            return False

        node_area = max(1, (ax2 - ax1) * (ay2 - ay1))
        region_area = max(1, (rx2 - rx1) * (ry2 - ry1))
        return overlap_area / min(node_area, region_area) >= 0.25

    def _read_ui_text_in_region(self, region: tuple) -> str:
        """Read accessible text/content-desc from nodes inside a screen region."""
        try:
            root = self._load_ui_hierarchy()
        except Exception as exc:
            logger.debug("UI text region lookup failed, will not block assertion: %s", exc)
            return ""

        items = []
        seen = set()
        for node in root.iter("node"):
            attrs = dict(node.attrib)
            bounds = self._parse_bounds(attrs.get("bounds", ""))
            if not bounds or not self._region_hit(bounds, region):
                continue

            texts = [
                self._normalize_text_value(attrs.get("text")),
                self._normalize_text_value(attrs.get("content-desc")),
                self._normalize_text_value(attrs.get("hint")),
            ]
            for text_value in texts:
                if not text_value or text_value in seen:
                    continue
                seen.add(text_value)
                x1, y1, _, _ = bounds
                items.append((y1, x1, text_value))

        items.sort(key=lambda item: (item[0], item[1]))
        text = " ".join(item[2] for item in items).strip()
        if text:
            logger.info("UI region text result: '%s'", text)
        return text

    def _assert_text_matches(self, actual_text: str, expected: str, match_mode: str) -> bool:
        if match_mode == 'exact':
            return actual_text == expected
        if match_mode == 'contains':
            return expected in actual_text
        if match_mode == 'regex':
            return re.search(expected, actual_text) is not None
        raise ValueError(f"Unsupported match_mode: {match_mode}")

    def _ocr_recognize_text(self, region: tuple) -> str:
        """OCR 识别指定区域的文本"""
        ocr = self._get_ocr_helper()
        return ocr.recognize_region_text(region)
    
    def _ocr_recognize_number(self, region: tuple) -> int:
        """OCR 识别指定区域的数字（自动去除逗号等格式符号）"""
        ocr = self._get_ocr_helper()
        return ocr.recognize_region_number(region)
    
    def _assert_text(self, step: Dict[str, Any]):
        region = self._parse_ocr_region(step)
        expected = step.get('expected', '')
        match_mode = step.get('match_mode', 'contains')
        text_source = str(step.get('text_source') or step.get('source') or 'auto').lower()
        allow_ocr_fallback = (
            text_source == 'ocr'
            or step.get('ocr_fallback') is True
            or os.getenv('APP_ASSERT_TEXT_OCR_FALLBACK') == '1'
        )

        actual_text = ""
        if text_source != 'ocr':
            actual_text = self._read_ui_text_in_region(region)

        passed = self._assert_text_matches(actual_text, expected, match_mode) if actual_text else False
        if not passed and allow_ocr_fallback:
            if not OCR_AVAILABLE:
                raise RuntimeError("文本断言需要 OCR 支持，请安装 easyocr")
            logger.info("UI text assertion did not pass, fallback to OCR for region: %s", region)
            actual_text = self._ocr_recognize_text(region)
            passed = self._assert_text_matches(actual_text, expected, match_mode)

        if not passed:
            raise AssertionError(f"文本断言失败: 期望 '{expected}' ({match_mode}), 实际 '{actual_text}'")

        logger.info("文本断言成功: '%s' (%s) 匹配 '%s'", expected, match_mode, actual_text)
        return

        """文本断言：OCR 识别文本，支持 exact/contains/regex 匹配"""
        if not OCR_AVAILABLE:
            raise RuntimeError("文本断言需要 OCR 支持，请安装 easyocr")
        
        region = self._parse_ocr_region(step)
        expected = step.get('expected', '')
        match_mode = step.get('match_mode', 'contains')
        
        actual_text = self._ocr_recognize_text(region)
        
        if match_mode == 'exact':
            passed = actual_text == expected
        elif match_mode == 'contains':
            passed = expected in actual_text
        elif match_mode == 'regex':
            passed = re.search(expected, actual_text) is not None
        else:
            raise ValueError(f"不支持的 match_mode: {match_mode}")
        
        if not passed:
            raise AssertionError(f"文本断言失败: 期望 '{expected}' ({match_mode}), 实际 '{actual_text}'")
        
        logger.info(f"文本断言成功: '{expected}' ({match_mode}) 匹配 '{actual_text}'")
    
    def _assert_number(self, step: Dict[str, Any]):
        """数值断言：OCR 识别数字（去逗号），与期望值精确匹配"""
        if not OCR_AVAILABLE:
            raise RuntimeError("数值断言需要 OCR 支持，请安装 easyocr")
        
        region = self._parse_ocr_region(step)
        expected_raw = step.get('expected', '0')
        
        # 期望值也做去逗号处理，兼容用户填 "3,000,000" 或 "3000000"
        try:
            expected_num = int(str(expected_raw).replace(',', '').replace(' ', ''))
        except (ValueError, TypeError):
            raise ValueError(f"number 断言的期望值无法转为数字: {expected_raw}")
        
        actual_num = self._ocr_recognize_number(region)
        
        if actual_num != expected_num:
            raise AssertionError(f"数值断言失败: 期望 {expected_num}, 实际 {actual_num}")
        
        logger.info(f"数值断言成功: 期望 {expected_num}, 实际 {actual_num}")
    
    def _assert_regex(self, step: Dict[str, Any]):
        """正则断言：OCR 识别文本，用正则表达式匹配"""
        if not OCR_AVAILABLE:
            raise RuntimeError("正则断言需要 OCR 支持，请安装 easyocr")
        
        region = self._parse_ocr_region(step)
        pattern = step.get('expected', '')
        
        if not pattern:
            raise ValueError("regex 断言需要在 expected 字段填写正则表达式")
        
        actual_text = self._ocr_recognize_text(region)
        
        match = re.search(pattern, actual_text)
        if not match:
            raise AssertionError(f"正则断言失败: 模式 '{pattern}' 未匹配到文本 '{actual_text}'")
        
        logger.info(f"正则断言成功: 模式 '{pattern}' 匹配到 '{match.group()}' (全文: '{actual_text}')")
    
    def _assert_range(self, step: Dict[str, Any]):
        """范围断言：OCR 识别数字，判断是否在 [min, max] 范围内"""
        if not OCR_AVAILABLE:
            raise RuntimeError("范围断言需要 OCR 支持，请安装 easyocr")
        
        region = self._parse_ocr_region(step)
        
        min_val = step.get('min')
        max_val = step.get('max')
        
        if min_val is None and max_val is None:
            raise ValueError("range 断言需要至少设置 min 或 max 之一")
        
        # 转换为数值
        try:
            min_num = int(str(min_val).replace(',', '').replace(' ', '')) if min_val is not None else None
        except (ValueError, TypeError):
            raise ValueError(f"range 断言的 min 值无法转为数字: {min_val}")
        try:
            max_num = int(str(max_val).replace(',', '').replace(' ', '')) if max_val is not None else None
        except (ValueError, TypeError):
            raise ValueError(f"range 断言的 max 值无法转为数字: {max_val}")
        
        actual_num = self._ocr_recognize_number(region)
        
        if min_num is not None and actual_num < min_num:
            raise AssertionError(f"范围断言失败: 实际值 {actual_num} 小于最小值 {min_num}")
        if max_num is not None and actual_num > max_num:
            raise AssertionError(f"范围断言失败: 实际值 {actual_num} 大于最大值 {max_num}")
        
        range_desc = f"[{min_num if min_num is not None else '-∞'}, {max_num if max_num is not None else '+∞'}]"
        logger.info(f"范围断言成功: 实际值 {actual_num} 在范围 {range_desc} 内")
    
    def _assert_exists(self, step: Dict[str, Any]):
        """存在性断言：判断图片元素是否存在于屏幕上"""
        target = self._resolve_selector(step)
        expected_exists = step.get('expected_exists', True)
        
        result = self._target_exists(target)
        
        if expected_exists and not result:
            raise AssertionError(f"期望元素存在，但实际不存在")
        elif not expected_exists and result:
            raise AssertionError(f"期望元素不存在，但实际存在")
        
        logger.info(f"存在性断言成功: 期望存在={expected_exists}, 实际存在={result}")
    
    def _assert_image(self, step: Dict[str, Any]):
        """图片断言：在屏幕上查找期望图片是否存在"""
        expected_image = step.get('expected', '')
        image_scope = step.get('expected_image_scope') or step.get('image_scope', 'common')
        threshold = step.get('image_threshold', 0.7)
        
        if not expected_image:
            raise ValueError("image 断言需要在 expected 字段填写图片文件名")
        
        image_path = os.path.join(self.image_base_dir, image_scope, expected_image)
        
        if not os.path.isfile(image_path):
            raise ValueError(f"期望图片文件不存在: {image_path}")
        
        target = Template(image_path, threshold=threshold)
        result = exists(target)
        
        if result is None:
            raise AssertionError(f"图片断言失败: 未在屏幕上找到图片 '{expected_image}' (阈值: {threshold})")
        
        logger.info(f"图片断言成功: 在屏幕上找到图片 '{expected_image}', 位置: {result}")

    def _current_focus_info(self) -> Dict[str, str]:
        """获取当前前台包名和 Activity。"""
        output = ""
        commands = [
            "dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'",
            "dumpsys activity activities | grep -E 'mResumedActivity|topResumedActivity'",
        ]
        for command in commands:
            try:
                output = self._device_shell(command)
            except Exception as exc:
                logger.debug("获取前台页面信息失败: %s", exc)
                output = ""
            if output and output.strip():
                break

        package_name = ""
        activity = ""
        text = output or ""

        focus_match = re.search(r'([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)', text)
        if focus_match:
            package_name = focus_match.group(1)
            activity = focus_match.group(2)

        if not package_name:
            package_match = re.search(r'\b([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+)\b', text)
            if package_match:
                package_name = package_match.group(1)

        return {
            'package_name': package_name,
            'activity': activity,
            'raw': text.strip(),
        }

    def _match_expected_value(self, actual: str, expected: str, match_mode: str) -> bool:
        actual_text = str(actual or '')
        expected_text = str(expected or '')
        if not expected_text:
            return True
        if match_mode == 'exact':
            return actual_text == expected_text
        if match_mode == 'contains':
            return expected_text in actual_text
        if match_mode == 'regex':
            return re.search(expected_text, actual_text) is not None
        raise ValueError(f"不支持的 match_mode: {match_mode}")

    def _assert_activity(self, step: Dict[str, Any]):
        """页面/Activity 断言：校验当前前台包名和 Activity。"""
        expected_package = str(step.get('package_name') or step.get('expected_package') or '').strip()
        expected_activity = str(step.get('activity') or step.get('expected_activity') or step.get('expected') or '').strip()
        match_mode = step.get('match_mode', 'contains')

        if not expected_package and not expected_activity:
            raise ValueError("页面断言需要填写 package_name 或 activity/expected")

        focus = self._current_focus_info()
        actual_package = focus.get('package_name') or ''
        actual_activity = focus.get('activity') or ''

        if expected_package and actual_package != expected_package:
            raise AssertionError(
                f"页面断言失败: 期望包名 '{expected_package}', 实际 '{actual_package or '-'}'; "
                f"当前 Activity: {actual_activity or '-'}"
            )

        if expected_activity and not self._match_expected_value(actual_activity, expected_activity, match_mode):
            raise AssertionError(
                f"页面断言失败: 期望 Activity '{expected_activity}' ({match_mode}), "
                f"实际 '{actual_activity or '-'}'; 当前包名: {actual_package or '-'}"
            )

        logger.info(
            "页面断言成功: package=%s, activity=%s, expected_package=%s, expected_activity=%s",
            actual_package,
            actual_activity,
            expected_package or '-',
            expected_activity or '-',
        )
    
    # ============ 新增动作方法 ============
    
    def _action_click(self, step: Dict[str, Any]):
        """点击动作（重命名自 _action_touch）"""
        self._action_touch(step)
    
    def _action_input(self, step: Dict[str, Any]):
        """输入文本"""
        target = self._resolve_selector(step)
        value = step.get('value')
        if value is None:
            value = step.get('input_value')
        if value is None:
            value = step.get('text')
        if value is None:
            value = ''
        
        # 解析变量表达式（如随机数函数）
        from apps.core.variable_resolver import resolve_variables
        value = resolve_variables(value)
        value = self._normalize_input_value(value)
        if value == "":
            step_name = step.get('name') or step.get('type') or '输入文本'
            raise ValueError(f"步骤 '{step_name}' 缺少输入内容，请在用例编排里填写 value/text")
        
        send_enter = step.get('send_enter', False)
        
        
        logger.info(f"输入文本: {value}")
        self._input_into_target(
            target,
            value,
            clear_first=step.get('clear_first', True),
            timeout=step.get('timeout', 10),
        )
        self._set_variable("last_input_value", value, "outputs")
        
        # 如果需要发送回车键（用于搜索）
        if send_enter:
            time.sleep(0.2)
            try:
                from airtest.core.api import keyevent
                keyevent("KEYCODE_ENTER")
                logger.info("发送回车键")
            except ImportError:
                # 如果没有keyevent，尝试发送换行符
                airtest_text('\n')
                logger.info("发送换行符模拟回车")
    
    def _action_long_press(self, step: Dict[str, Any]):
        """长按"""
        target = self._resolve_selector(step)
        duration = step.get('duration', 2)
        
        if target:
            logger.info(f"长按: {target}, 时长: {duration}秒")
            self._tap_target(target, timeout=step.get('timeout', 10), duration=duration)
    
    def _action_drag(self, step: Dict[str, Any]):
        """拖拽：从起点拖拽到终点"""
        # 解析起点
        start_config = {
            'selector': step.get('start_selector'),
            'selector_type': step.get('start_selector_type', 'image'),
            'image_scope': step.get('image_scope', 'common')
        }
        start = self._resolve_selector(start_config)
        
        # 解析终点
        end_config = {
            'selector': step.get('end_selector'),
            'selector_type': step.get('end_selector_type', 'image'),
            'image_scope': step.get('image_scope', 'common')
        }
        end = self._resolve_selector(end_config)
        
        duration = step.get('duration', 0.8)
        
        if start and end:
            logger.info(f"拖拽: {start} -> {end}")
            self._set_action_evidence(action="drag", start=list(start), end=list(end))
            swipe(start, end, duration=duration)
    
    def _action_swipe_to(self, step: Dict[str, Any]):
        """滑动直到目标元素出现"""
        target_config = {
            'selector': step.get('target_selector'),
            'selector_type': step.get('target_selector_type', 'image'),
            'image_scope': step.get('image_scope', 'common')
        }
        target = self._resolve_selector(target_config)
        
        direction = step.get('direction', 'up')
        max_swipes = step.get('max_swipes', 5)
        interval = step.get('interval', 0.5)
        
        for i in range(max_swipes):
            if self._target_exists(target):
                logger.info(f"找到目标元素，停止滑动")
                return
            
            logger.info(f"第 {i+1}/{max_swipes} 次滑动: {direction}")
            swipe_vector = G.DEVICE.get_current_resolution()
            
            if direction == 'up':
                start_point = (swipe_vector[0]//2, swipe_vector[1]*0.7)
                end_point = (swipe_vector[0]//2, swipe_vector[1]*0.3)
            elif direction == 'down':
                start_point = (swipe_vector[0]//2, swipe_vector[1]*0.3)
                end_point = (swipe_vector[0]//2, swipe_vector[1]*0.7)
            elif direction == 'left':
                start_point = (swipe_vector[0]*0.7, swipe_vector[1]//2)
                end_point = (swipe_vector[0]*0.3, swipe_vector[1]//2)
            elif direction == 'right':
                start_point = (swipe_vector[0]*0.3, swipe_vector[1]//2)
                end_point = (swipe_vector[0]*0.7, swipe_vector[1]//2)
            else:
                raise ValueError(f"不支持的滑动方向: {direction}")

            self._set_action_evidence(
                action="swipe_to",
                direction=direction,
                start=[int(start_point[0]), int(start_point[1])],
                end=[int(end_point[0]), int(end_point[1])],
            )
            swipe(start_point, end_point)
            
            time.sleep(interval)
        
        logger.warning(f"滑动 {max_swipes} 次后仍未找到目标元素")
    
    def _action_image_exists_click(self, step: Dict[str, Any]):
        """主定位存在则点击主定位，否则点击备用定位"""
        # 主定位
        main_config = {
            'selector': step.get('selector'),
            'selector_type': step.get('selector_type', 'image'),
            'image_scope': step.get('image_scope', 'common'),
            'image_threshold': step.get('image_threshold', 0.7)
        }
        main_target = self._resolve_selector(main_config)
        
        # 备用定位
        fallback_config = {
            'selector': step.get('fallback_selector'),
            'selector_type': step.get('fallback_selector_type', 'image'),
            'image_scope': step.get('fallback_image_scope', 'common'),
            'image_threshold': step.get('fallback_image_threshold', 0.7)
        }
        fallback_target = self._resolve_selector(fallback_config)
        
        if main_target and self._target_exists(main_target):
            logger.info(f"主定位存在，点击主定位")
            self._tap_target(main_target, timeout=step.get('timeout', 10))
        elif fallback_target:
            logger.info(f"主定位不存在，点击备用定位")
            self._tap_target(fallback_target, timeout=step.get('timeout', 10))
    
    def _action_image_exists_click_chain(self, step: Dict[str, Any]):
        """主定位存在则依次点击主定位和备用定位，否则只点击备用定位"""
        # 主定位
        main_config = {
            'selector': step.get('selector'),
            'selector_type': step.get('selector_type', 'image'),
            'image_scope': step.get('image_scope', 'common')
        }
        main_target = self._resolve_selector(main_config)
        
        # 备用定位
        fallback_config = {
            'selector': step.get('fallback_selector'),
            'selector_type': step.get('fallback_selector_type', 'image'),
            'image_scope': step.get('fallback_image_scope', 'common')
        }
        fallback_target = self._resolve_selector(fallback_config)
        
        if main_target and self._target_exists(main_target):
            logger.info(f"主定位存在，依次点击主定位和备用定位")
            self._tap_target(main_target, timeout=step.get('timeout', 10))
            time.sleep(0.5)
        
        if fallback_target:
            self._tap_target(fallback_target, timeout=step.get('timeout', 10))
    
    def _action_unset_variable(self, step: Dict[str, Any]):
        """删除变量"""
        name = step.get('name')
        scope = step.get('scope', 'local')
        
        if name and scope in self.context and name in self.context[scope]:
            del self.context[scope][name]
            logger.info(f"删除变量: {scope}.{name}")
    
    def _action_extract_output(self, step: Dict[str, Any]):
        """
        从变量中按路径提取字段并保存为新变量。
        
        配置示例:
            source: "local.response"      # 来源变量，格式: scope.var_name
            path: "body.data.token"       # 提取路径，支持多级 key 和列表索引 [0]
            name: "token"                 # 保存为新变量名
            scope: "local"                # 保存到哪个作用域
        """
        source = step.get('source', '')
        path = step.get('path', '')
        name = step.get('name')
        scope = step.get('scope', 'local')
        
        if not name:
            raise ValueError("extract_output 需要 name 参数（保存的变量名）")
        if not source:
            raise ValueError("extract_output 需要 source 参数（来源变量）")
        
        # 解析 source: "scope.var_name" 或直接 "var_name"
        source_value = self._get_variable(source)
        if source_value is None:
            # 尝试按 scope.name 格式解析
            parts = source.split('.', 1)
            if len(parts) == 2 and parts[0] in self.context:
                source_value = self.context[parts[0]].get(parts[1])
        
        if source_value is None:
            raise ValueError(f"来源变量不存在: {source}")
        
        # 按 path 逐级提取
        if path:
            current = source_value
            for key in self._parse_path(path):
                if isinstance(current, dict):
                    current = current.get(key)
                elif isinstance(current, (list, tuple)):
                    try:
                        current = current[int(key)]
                    except (ValueError, IndexError):
                        current = None
                else:
                    current = None
                
                if current is None:
                    raise ValueError(f"提取失败: 路径 '{path}' 在 '{key}' 处找不到值")
            
            extracted = current
        else:
            extracted = source_value
        
        self._set_variable(name, extracted, scope)
        logger.info(f"提取成功: {source}.{path} -> {scope}.{name} = {extracted}")
    
    @staticmethod
    def _parse_path(path: str) -> List[str]:
        """解析提取路径，支持 'a.b.c' 和 'a[0].b' 格式"""
        keys = []
        for part in path.split('.'):
            if '[' in part:
                # 处理 "items[0]" -> ["items", "0"]
                base, rest = part.split('[', 1)
                if base:
                    keys.append(base)
                for idx_part in rest.split('['):
                    idx_part = idx_part.rstrip(']')
                    if idx_part:
                        keys.append(idx_part)
            else:
                if part:
                    keys.append(part)
        return keys
    
    def _action_screenshot(self, step: Dict[str, Any]):
        """截图（重命名自 _action_snapshot）"""
        self._action_snapshot(step)
    
    def _action_api_request(self, step: Dict[str, Any]):
        """
        执行HTTP请求，支持状态码校验、自动/手动响应解析和字段提取。
        
        配置项:
            method: GET / POST / PUT / DELETE / PATCH
            url: 请求地址（支持变量渲染）
            headers / params / json / data: 请求参数
            timeout: 超时秒数，默认10
            response_type: auto(自动判断) / json / text / binary
            expected_status: 期望的 HTTP 状态码，如 200
            save_as: 将完整响应结果保存为变量名
            scope: 变量保存的作用域，默认 local
            extracts: 字段提取列表
                - path: "body.data.token"
                  name: "token"
                  scope: "local"
        """
        import requests as req_lib
        
        method = step.get('method', 'GET').upper()
        url = self._render_value(step.get('url', ''))
        headers = step.get('headers', {})
        params = step.get('params', {})
        json_data = step.get('json', {})
        data = step.get('data', {})
        timeout = step.get('timeout', 10)
        save_as = step.get('save_as', '')
        scope = step.get('scope', 'local')
        response_type = step.get('response_type', 'auto')
        expected_status = step.get('expected_status')
        extracts = step.get('extracts', [])
        
        if not url:
            raise ValueError("api_request 缺少 url 参数")
        
        # 渲染 headers/params 中的变量
        if isinstance(headers, dict):
            headers = {k: self._render_value(v) if isinstance(v, str) else v
                       for k, v in headers.items()}
        if isinstance(params, dict):
            params = {k: self._render_value(v) if isinstance(v, str) else v
                      for k, v in params.items()}
        
        logger.info(f"HTTP请求: {method} {url}")
        
        try:
            response = req_lib.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_data if json_data else None,
                data=data if data else None,
                timeout=timeout
            )
        except Exception as e:
            logger.error(f"HTTP请求失败: {str(e)}")
            raise
        
        # 解析响应体
        body = self._parse_response_body(response, response_type)
        
        result = {
            'status_code': response.status_code,
            'headers': dict(response.headers),
            'body': body
        }
        
        logger.info(f"HTTP响应: {response.status_code}")
        
        # 状态码校验
        if expected_status is not None:
            expected_status = int(expected_status)
            if response.status_code != expected_status:
                raise AssertionError(
                    f"HTTP状态码断言失败: 期望 {expected_status}, "
                    f"实际 {response.status_code}"
                )
        
        # 保存完整结果
        if save_as:
            self._set_variable(save_as, result, scope)
        
        # 字段提取
        if extracts and isinstance(extracts, list):
            for extract in extracts:
                if not isinstance(extract, dict):
                    continue
                e_path = extract.get('path', '')
                e_name = extract.get('name', '')
                e_scope = extract.get('scope', scope)
                if not e_name:
                    logger.warning(f"extracts 配置缺少 name，跳过: {extract}")
                    continue
                
                # 从 result 中按路径提取
                current = result
                try:
                    for key in self._parse_path(e_path):
                        if isinstance(current, dict):
                            current = current[key]
                        elif isinstance(current, (list, tuple)):
                            current = current[int(key)]
                        else:
                            raise KeyError(key)
                except (KeyError, IndexError, ValueError, TypeError) as e:
                    raise ValueError(
                        f"api_request extracts 提取失败: path='{e_path}' "
                        f"在 '{key}' 处出错: {e}"
                    )
                self._set_variable(e_name, current, e_scope)
                logger.info(f"api_request 提取: {e_path} -> {e_scope}.{e_name} = {current}")
    
    @staticmethod
    def _parse_response_body(response, response_type: str = 'auto'):
        """根据 response_type 解析响应体"""
        if response_type == 'json':
            try:
                return response.json()
            except Exception:
                return response.text
        elif response_type == 'text':
            return response.text
        elif response_type == 'binary':
            import base64
            return base64.b64encode(response.content).decode('ascii')
        else:
            # auto: 根据 Content-Type 自动判断
            content_type = response.headers.get('Content-Type', '')
            if 'json' in content_type or 'javascript' in content_type:
                try:
                    return response.json()
                except Exception:
                    return response.text
            return response.text
    
    def _action_if(self, step: Dict[str, Any]):
        """条件分支，支持丰富的操作符"""
        left = self._render_value(step.get('left', ''))
        right = self._render_value(step.get('right', ''))
        operator = step.get('operator', '==')
        then_steps = step.get('then_steps', [])
        else_steps = step.get('else_steps', [])
        
        condition = self._eval_condition(left, operator, right)
        
        logger.info(f"条件判断: {left} {operator} {right} = {condition}")
        
        # 执行分支
        if condition:
            for sub_step in then_steps:
                self._execute_step(sub_step)
        else:
            for sub_step in else_steps:
                self._execute_step(sub_step)
    
    @staticmethod
    def _eval_condition(left, operator: str, right) -> bool:
        """
        评估条件表达式。
        
        支持的操作符:
            ==, !=, >, >=, <, <=,
            in, not in, not_in,
            contains, notcontains, not_contains,
            regex, match,
            truthy, exists,
            falsy, not_exists,
            startswith, endswith
        """
        op = operator.strip().lower()
        
        # 相等判断
        if op == '==':
            return str(left) == str(right)
        if op == '!=':
            return str(left) != str(right)
        
        # 数值比较
        if op in ('>', '>=', '<', '<='):
            try:
                l_val, r_val = float(left), float(right)
            except (ValueError, TypeError):
                return False
            if op == '>':
                return l_val > r_val
            if op == '>=':
                return l_val >= r_val
            if op == '<':
                return l_val < r_val
            return l_val <= r_val
        
        # 包含判断
        if op == 'in':
            return str(left) in str(right)
        if op in ('not in', 'not_in'):
            return str(left) not in str(right)
        if op == 'contains':
            return str(right) in str(left)
        if op in ('notcontains', 'not_contains'):
            return str(right) not in str(left)
        
        # 正则匹配
        if op in ('regex', 'match'):
            try:
                return bool(re.search(str(right), str(left)))
            except re.error:
                return False
        
        # 真值 / 假值
        if op in ('truthy', 'exists'):
            return bool(left)
        if op in ('falsy', 'not_exists'):
            return not bool(left)
        
        # 前缀 / 后缀
        if op == 'startswith':
            return str(left).startswith(str(right))
        if op == 'endswith':
            return str(left).endswith(str(right))
        
        logger.warning(f"未知的条件操作符: {operator}，默认返回 False")
        return False
    
    def _action_loop(self, step: Dict[str, Any]):
        """循环：支持计数/条件/遍历三种模式"""
        mode = step.get('mode', 'count')
        steps = step.get('steps', [])
        max_loops = step.get('max_loops', 10)
        interval = step.get('interval', 0)
        
        if mode == 'count':
            # 计数循环
            times = step.get('times', 1)
            logger.info(f"计数循环: {times} 次")
            for i in range(times):
                logger.info(f"循环第 {i+1}/{times} 次")
                for sub_step in steps:
                    self._execute_step(sub_step)
                if interval > 0:
                    time.sleep(interval)
        
        elif mode == 'foreach':
            # 遍历循环
            items = step.get('items', [])
            item_var = step.get('item_var', 'item')
            item_scope = step.get('item_scope', 'local')
            
            logger.info(f"遍历循环: {len(items)} 个元素")
            for idx, item in enumerate(items):
                logger.info(f"循环第 {idx+1}/{len(items)} 次, {item_var}={item}")
                self._set_variable(item_var, item, item_scope)
                for sub_step in steps:
                    self._execute_step(sub_step)
                if interval > 0:
                    time.sleep(interval)
        
        elif mode == 'condition':
            # 条件循环
            left = step.get('left', '')
            operator = step.get('operator', '==')
            right = step.get('right', '')
            
            logger.info(f"条件循环: {left} {operator} {right}")
            loop_count = 0
            while loop_count < max_loops:
                left_val = self._render_value(left)
                right_val = self._render_value(right)
                
                # 评估条件
                condition = False
                if operator == '==':
                    condition = left_val == right_val
                elif operator == '!=':
                    condition = left_val != right_val
                
                if not condition:
                    break
                
                loop_count += 1
                logger.info(f"条件循环第 {loop_count} 次")
                for sub_step in steps:
                    self._execute_step(sub_step)
                if interval > 0:
                    time.sleep(interval)
    
    def _action_sequence(self, step: Dict[str, Any]):
        """顺序执行子步骤"""
        steps = step.get('steps', [])
        logger.info(f"顺序执行 {len(steps)} 个子步骤")
        for sub_step in steps:
            self._execute_step(sub_step)
    
    def _action_try(self, step: Dict[str, Any]):
        """异常处理：try/catch/finally"""
        try_steps = step.get('try_steps', [])
        catch_steps = step.get('catch_steps', [])
        finally_steps = step.get('finally_steps', [])
        error_var = step.get('error_var', 'error')
        error_scope = step.get('error_scope', 'local')
        
        logger.info("执行 try 块")
        try:
            for sub_step in try_steps:
                self._execute_step(sub_step)
        except Exception as e:
            logger.warning(f"捕获异常: {str(e)}")
            self._set_variable(error_var, str(e), error_scope)
            for sub_step in catch_steps:
                self._execute_step(sub_step)
        finally:
            logger.info("执行 finally 块")
            for sub_step in finally_steps:
                self._execute_step(sub_step)
    
    def _get_ocr_helper(self):
        """获取或创建 OCR Helper 实例"""
        if self._ocr_helper is None:
            if not OCR_AVAILABLE:
                raise RuntimeError("OCR 功能不可用，请安装: pip install easyocr opencv-python")
            self._ocr_helper = get_ocr_helper(languages=['ch_sim', 'en'], use_gpu=False)
        return self._ocr_helper
    
    
    def _action_foreach_assert(self, step: Dict[str, Any]):
        """循环点击断言（OCR）"""
        if not OCR_AVAILABLE:
            logger.warning("foreach_assert 需要 OCR 支持，请安装 easyocr")
            return
        
        try:
            # 从 config 中获取配置
            config = step.get('config', {})
            
            # 解析参数
            expected_list = config.get('expected_list', [])
            max_loops = config.get('max_loops', 5)
            interval = config.get('interval', 0.5)
            timeout = config.get('timeout', 5)
            match_mode = config.get('match_mode', 'contains')
            assert_type = config.get('assert_type', 'text')
            
            # 点击选择器
            click_selector_type = config.get('click_selector_type', 'image')
            click_selector = config.get('click_selector')
            click_config = {
                'selector_type': click_selector_type,
                'selector': click_selector,
                'image_scope': config.get('image_scope', 'common'),
                'image_threshold': config.get('image_threshold', 0.7)
            }
            click_target = self._resolve_selector(click_config)
            
            # OCR 区域选择器
            ocr_selector_type = config.get('ocr_selector_type', 'region')
            ocr_selector = config.get('ocr_selector')
            
            if not click_target:
                raise ValueError("foreach_assert 需要有效的 click_selector")
            if not ocr_selector:
                raise ValueError("foreach_assert 需要 ocr_selector 参数")
            
            # 解析 OCR 区域坐标
            if ocr_selector_type == 'region':
                if isinstance(ocr_selector, str):
                    parts = [int(p.strip()) for p in ocr_selector.split(',')]
                    if len(parts) != 4:
                        raise ValueError(f"OCR region 格式错误: {ocr_selector}")
                    ocr_region = tuple(parts)
                else:
                    ocr_region = tuple(ocr_selector)
            else:
                raise ValueError(f"foreach_assert 仅支持 ocr_selector_type=region")
            
            # OCR 识别
            ocr = self._get_ocr_helper()
            
            # 循环点击并断言
            matched_count = 0
            min_match = int(step.get('min_match', 1) or 0)
            for i in range(max_loops):
                logger.info(f"循环点击断言 第 {i+1}/{max_loops} 次")
                
                # 点击
                self._tap_target(click_target, timeout=timeout)
                time.sleep(interval)
                
                # OCR 识别
                if assert_type == 'number':
                    actual_value = ocr.recognize_region_number(ocr_region)
                else:
                    actual_value = ocr.recognize_region_text(ocr_region)
                
                # 检查是否匹配期望列表中的任何值
                matched = False
                for expected in expected_list:
                    if assert_type == 'number':
                        expected_num = int(str(expected).replace(',', ''))
                        if actual_value == expected_num:
                            matched = True
                            break
                    else:
                        if match_mode == 'exact':
                            if actual_value == expected:
                                matched = True
                                break
                        elif match_mode == 'contains':
                            if expected in actual_value:
                                matched = True
                                break
                
                if matched:
                    matched_count += 1
                    logger.info(f"第 {i+1} 次匹配成功: {actual_value} 在期望列表中")
                else:
                    logger.warning(f"第 {i+1} 次未匹配: {actual_value} 不在期望列表中")
            
            logger.info(f"循环点击断言完成: 共 {max_loops} 次，匹配 {matched_count} 次")
            if matched_count < min_match:
                raise AssertionError(
                    f"循环点击断言失败: 期望至少匹配 {min_match} 次，实际 {matched_count} 次"
                )
            
        except Exception as e:
            logger.error(f"foreach_assert 执行失败: {str(e)}")
            raise
