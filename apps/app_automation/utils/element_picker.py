# -*- coding: utf-8 -*-
"""
元素拾取器工具类
为可视化元素拾取提供 locator 推荐、评分等核心逻辑
"""
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class ElementPicker:
    """
    元素拾取器：分析 UI 元素属性，推荐最佳 locator 策略

    使用场景：
    1. 用户在截图上点击某个元素
    2. 系统根据坐标从 UI 层级中找到对应节点
    3. ElementPicker 分析该节点的所有属性（resource_id/text/class/bounds）
    4. 推荐若干个可用的定位策略，并按可靠性排序
    """

    # Locator 可靠性权重（分值越高越可靠）
    STRATEGY_WEIGHTS = {
        'resource_id': 0.95,      # 最可靠：开发指定的唯一 ID
        'content_desc': 0.85,     # 较可靠：无障碍描述
        'text': 0.75,             # 中等：文本内容（可能随版本变化）
        'hint': 0.70,             # 中等偏低：输入框提示文本
        'class': 0.50,            # 较低：类名通用性强
        'bounds': 0.20,           # 最不可靠：屏幕坐标（分辨率变化即失效）
    }

    def __init__(self):
        pass

    def recommend_locators(self, element: Dict) -> List[Dict]:
        """
        为一个 UI 元素推荐多个 locator 策略，按可靠性排序

        Args:
            element: 元素属性字典，包含 resource_id/text/content_desc/class/bounds 等

        Returns:
            推荐策略列表，每项包含：
            {
                "type": "resource_id",
                "value": "com.example:id/login_btn",
                "confidence": 0.95,
                "reason": "唯一资源ID，推荐优先使用"
            }
        """
        strategies = []

        # 1. Resource ID (最优先)
        resource_id = self._normalize_text(element.get('resource_id'))
        if resource_id:
            strategies.append({
                'type': 'resource_id',
                'value': resource_id,
                'confidence': self.STRATEGY_WEIGHTS['resource_id'],
                'reason': '唯一资源ID，推荐优先使用',
                'priority': 1,
            })

        # 2. Content Description (次优)
        content_desc = self._normalize_text(element.get('content_desc'))
        if content_desc:
            strategies.append({
                'type': 'content_desc',
                'value': content_desc,
                'confidence': self.STRATEGY_WEIGHTS['content_desc'],
                'reason': '无障碍描述，较为稳定',
                'priority': 2,
            })

        # 3. Text (常用但可能变化)
        text = self._normalize_text(element.get('text'))
        if text:
            # 如果文本过长（超过30字符），降低可靠性
            confidence = self.STRATEGY_WEIGHTS['text']
            reason = '文本内容定位'
            if len(text) > 30:
                confidence *= 0.8
                reason += '（文本较长，可能不稳定）'

            strategies.append({
                'type': 'text',
                'value': text,
                'confidence': confidence,
                'reason': reason,
                'priority': 3,
            })

        # 4. Hint (输入框提示)
        hint = self._normalize_text(element.get('hint'))
        if hint:
            strategies.append({
                'type': 'hint',
                'value': hint,
                'confidence': self.STRATEGY_WEIGHTS['hint'],
                'reason': '输入框提示文本',
                'priority': 4,
            })

        # 5. Class Name (通用性强，可靠性低)
        class_name = self._normalize_text(element.get('class_name'))
        if class_name:
            # 如果页面中同类元素很多，进一步降低可靠性
            confidence = self.STRATEGY_WEIGHTS['class']
            reason = f'类名定位（{self._get_short_class(class_name)}）'

            # 如果是常见布局容器，直接排除
            if class_name in {
                'android.widget.FrameLayout',
                'android.widget.LinearLayout',
                'android.widget.RelativeLayout',
                'android.view.ViewGroup',
            }:
                confidence *= 0.3
                reason += '（布局容器，不推荐）'

            strategies.append({
                'type': 'class',
                'value': class_name,
                'confidence': confidence,
                'reason': reason,
                'priority': 5,
            })

        # 6. Bounds (最后的备选)
        bounds = element.get('bounds') or element.get('raw_bounds')
        if bounds:
            strategies.append({
                'type': 'bounds',
                'value': str(bounds),
                'confidence': self.STRATEGY_WEIGHTS['bounds'],
                'reason': '坐标定位（分辨率变化时可能失效）',
                'priority': 6,
            })

        # 按可靠性排序（confidence 降序）
        strategies.sort(key=lambda s: (-s['confidence'], s['priority']))

        return strategies

    def get_best_locator(self, element: Dict) -> Optional[Dict]:
        """
        获取最佳 locator 策略（可靠性最高的一个）

        Args:
            element: 元素属性字典

        Returns:
            最佳策略字典，如果没有可用策略则返回 None
        """
        strategies = self.recommend_locators(element)
        return strategies[0] if strategies else None

    def generate_selector_config(self, element: Dict, preferred_type: Optional[str] = None) -> Dict:
        """
        生成用于存储到 AppElement.config 的 selector 配置

        Args:
            element: 元素属性字典
            preferred_type: 用户指定的优先 locator 类型（如果为 None，则自动选最佳）

        Returns:
            selector 配置字典，格式：
            {
                "selector_type": "resource_id",
                "resource_id": "com.example:id/login_btn",
                "text": "登录",  # 作为备选
                "class": "android.widget.Button",  # 作为备选
                "bounds": "[100,200][300,400]"  # 作为最后备选
            }
        """
        strategies = self.recommend_locators(element)

        # 如果用户指定了类型，优先使用
        if preferred_type:
            selected = next((s for s in strategies if s['type'] == preferred_type), None)
            if not selected and strategies:
                # 如果指定的类型不可用，回退到最佳策略
                logger.warning(f"指定的 locator 类型 {preferred_type} 不可用，回退到 {strategies[0]['type']}")
                selected = strategies[0]
        else:
            # 自动选择最佳
            selected = strategies[0] if strategies else None

        if not selected:
            raise ValueError("无法为该元素生成任何可用的 locator 策略")

        # 构造 config
        config = {
            'selector_type': selected['type'],
        }

        # 填充所有可用属性作为备选
        for strategy in strategies:
            config[strategy['type']] = strategy['value']

        # 额外补充元素的其他属性
        if element.get('package_name'):
            config['package'] = element['package_name']
        if element.get('clickable'):
            config['clickable'] = element['clickable']
        if element.get('enabled'):
            config['enabled'] = element['enabled']

        return config

    def validate_locator(self, candidates: List[Dict], selector: Dict) -> Tuple[bool, Optional[Dict], int]:
        """
        在候选元素列表中验证 selector 是否能唯一定位到目标

        Args:
            candidates: 当前页面的所有元素候选列表
            selector: 要验证的 selector 配置

        Returns:
            (是否匹配成功, 匹配到的元素, 匹配得分)
        """
        from ..views.device_views import find_best_candidate_for_selector

        matched_candidate, score = find_best_candidate_for_selector(candidates, selector)
        return matched_candidate is not None, matched_candidate, score

    @staticmethod
    def _normalize_text(value) -> str:
        """标准化文本：去除首尾空格"""
        return str(value or '').strip()

    @staticmethod
    def _get_short_class(class_name: str) -> str:
        """获取类名的短名称（去除包名前缀）"""
        return class_name.split('.')[-1] if class_name else ''


def analyze_element_for_picker(element: Dict) -> Dict:
    """
    分析元素并返回适合前端展示的结构化数据

    Args:
        element: 原始元素属性字典

    Returns:
        包含 locator 推荐、元素信息、最佳策略的结构化数据
    """
    picker = ElementPicker()
    strategies = picker.recommend_locators(element)
    best_locator = strategies[0] if strategies else None

    # 提取关键信息用于前端展示
    short_class = picker._get_short_class(element.get('class_name', ''))
    display_name = (
        element.get('text') or
        element.get('content_desc') or
        element.get('resource_id', '').split('/')[-1] or
        short_class or
        '未命名元素'
    )

    return {
        'element': element,
        'display_name': display_name[:50],
        'short_class': short_class,
        'strategies': strategies,
        'best_locator': best_locator,
        'has_resource_id': bool(element.get('resource_id')),
        'is_interactive': any([
            element.get('clickable'),
            element.get('focusable'),
            element.get('checkable'),
            element.get('long_clickable'),
            element.get('scrollable'),
        ]),
    }
