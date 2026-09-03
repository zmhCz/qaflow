# -*- coding: utf-8 -*-
"""
元素拾取器单元测试
测试 ElementPicker 类的核心逻辑
"""
import pytest
from apps.app_automation.utils.element_picker import ElementPicker, analyze_element_for_picker


class TestElementPicker:
    """元素拾取器测试类"""

    def setup_method(self):
        """每个测试方法执行前的初始化"""
        self.picker = ElementPicker()

    def test_recommend_locators_with_resource_id(self):
        """测试带有 resource_id 的元素推荐"""
        element = {
            'resource_id': 'com.example:id/login_btn',
            'text': 'Login',
            'class_name': 'android.widget.Button',
            'content_desc': 'Login button',
            'bounds': '[100,200][300,400]',
        }

        strategies = self.picker.recommend_locators(element)

        # 应该推荐所有可用的策略
        assert len(strategies) >= 4

        # resource_id 应该排第一（最可靠）
        assert strategies[0]['type'] == 'resource_id'
        assert strategies[0]['value'] == 'com.example:id/login_btn'
        assert strategies[0]['confidence'] == 0.95

        # content_desc 应该排第二
        assert strategies[1]['type'] == 'content_desc'
        assert strategies[1]['confidence'] == 0.85

        # text 排第三
        assert strategies[2]['type'] == 'text'
        assert strategies[2]['confidence'] == 0.75

    def test_recommend_locators_without_resource_id(self):
        """测试没有 resource_id 的元素推荐"""
        element = {
            'text': 'Submit',
            'class_name': 'android.widget.Button',
            'bounds': '[100,200][300,400]',
        }

        strategies = self.picker.recommend_locators(element)

        # text 应该排第一
        assert strategies[0]['type'] == 'text'
        assert strategies[0]['value'] == 'Submit'

    def test_recommend_locators_only_bounds(self):
        """测试只有 bounds 的元素（最差情况）"""
        element = {
            'class_name': 'android.widget.FrameLayout',
            'bounds': '[100,200][300,400]',
        }

        strategies = self.picker.recommend_locators(element)

        # 应该至少返回 class 和 bounds
        assert len(strategies) >= 2

        # bounds 应该排最后
        # Generic layout containers should be less reliable than bounds.
        assert strategies[0]['type'] == 'bounds'
        assert strategies[0]['confidence'] == 0.2
        assert strategies[-1]['type'] == 'class'
        assert strategies[-1]['confidence'] < strategies[0]['confidence']

    def test_recommend_locators_long_text_penalty(self):
        """测试长文本的可靠性降低"""
        element_short_text = {
            'text': 'OK',
        }

        element_long_text = {
            'text': 'This is a very long text that exceeds 30 characters',
        }

        strategies_short = self.picker.recommend_locators(element_short_text)
        strategies_long = self.picker.recommend_locators(element_long_text)

        # 长文本的 confidence 应该更低
        short_confidence = strategies_short[0]['confidence']
        long_confidence = strategies_long[0]['confidence']

        assert long_confidence < short_confidence
        assert long_confidence == 0.75 * 0.8  # 长文本惩罚系数 0.8

    def test_get_best_locator(self):
        """测试获取最佳 locator"""
        element = {
            'resource_id': 'com.example:id/btn',
            'text': 'Click me',
        }

        best = self.picker.get_best_locator(element)

        assert best is not None
        assert best['type'] == 'resource_id'
        assert best['confidence'] == 0.95

    def test_get_best_locator_empty_element(self):
        """测试空元素返回 None"""
        element = {}

        best = self.picker.get_best_locator(element)

        assert best is None

    def test_generate_selector_config_auto_best(self):
        """测试自动生成最佳 selector 配置"""
        element = {
            'resource_id': 'com.example:id/username',
            'text': 'Username',
            'class_name': 'android.widget.EditText',
            'bounds': '[50,100][400,180]',
            'package_name': 'com.example.app',
            'clickable': True,
            'enabled': True,
        }

        config = self.picker.generate_selector_config(element)

        # selector_type 应该是 resource_id（最佳）
        assert config['selector_type'] == 'resource_id'

        # 应该包含所有可用属性作为备选
        assert config['resource_id'] == 'com.example:id/username'
        assert config['text'] == 'Username'
        assert config['class'] == 'android.widget.EditText'
        assert config['bounds'] == '[50,100][400,180]'
        assert config['package'] == 'com.example.app'
        assert config['clickable'] is True
        assert config['enabled'] is True

    def test_generate_selector_config_preferred_type(self):
        """测试用户指定 locator 类型"""
        element = {
            'resource_id': 'com.example:id/btn',
            'text': 'Submit',
            'class_name': 'android.widget.Button',
        }

        # 用户指定使用 text
        config = self.picker.generate_selector_config(element, preferred_type='text')

        assert config['selector_type'] == 'text'

    def test_generate_selector_config_invalid_preferred_type(self):
        """测试用户指定的 locator 类型不可用时回退"""
        element = {
            'text': 'OK',
            'class_name': 'android.widget.Button',
        }

        # 用户指定使用 resource_id，但元素没有 resource_id
        # 应该回退到可用的策略（text）
        config = self.picker.generate_selector_config(element, preferred_type='resource_id')

        # 应该回退到 text
        assert config['selector_type'] == 'text'

    def test_generate_selector_config_no_strategies(self):
        """测试没有任何可用策略时抛出异常"""
        element = {}

        with pytest.raises(ValueError, match="无法为该元素生成任何可用的 locator 策略"):
            self.picker.generate_selector_config(element)

    def test_normalize_text(self):
        """测试文本标准化"""
        assert self.picker._normalize_text('  hello  ') == 'hello'
        assert self.picker._normalize_text('') == ''
        assert self.picker._normalize_text(None) == ''
        assert self.picker._normalize_text(123) == '123'

    def test_get_short_class(self):
        """测试类名简化"""
        assert self.picker._get_short_class('android.widget.Button') == 'Button'
        assert self.picker._get_short_class('Button') == 'Button'
        assert self.picker._get_short_class('') == ''

    def test_analyze_element_for_picker(self):
        """测试完整的元素分析"""
        element = {
            'resource_id': 'com.example:id/search_btn',
            'text': 'Search',
            'class_name': 'android.widget.ImageButton',
            'content_desc': 'Search button',
            'clickable': True,
            'focusable': True,
        }

        analysis = analyze_element_for_picker(element)

        # 应该包含所有必要字段
        assert 'element' in analysis
        assert 'display_name' in analysis
        assert 'short_class' in analysis
        assert 'strategies' in analysis
        assert 'best_locator' in analysis
        assert 'has_resource_id' in analysis
        assert 'is_interactive' in analysis

        # 验证内容
        assert analysis['has_resource_id'] is True
        assert analysis['is_interactive'] is True
        assert analysis['short_class'] == 'ImageButton'
        assert len(analysis['strategies']) >= 4

        # best_locator 应该是 resource_id
        assert analysis['best_locator']['type'] == 'resource_id'

    def test_analyze_element_for_picker_non_interactive(self):
        """测试非交互元素的分析"""
        element = {
            'text': 'Label text',
            'class_name': 'android.widget.TextView',
            'clickable': False,
            'focusable': False,
        }

        analysis = analyze_element_for_picker(element)

        assert analysis['is_interactive'] is False
        assert analysis['has_resource_id'] is False

    def test_layout_container_low_confidence(self):
        """测试布局容器的可靠性被降低"""
        element = {
            'class_name': 'android.widget.LinearLayout',
            'bounds': '[0,0][1080,1920]',
        }

        strategies = self.picker.recommend_locators(element)

        # 找到 class 策略
        class_strategy = next(s for s in strategies if s['type'] == 'class')

        # 布局容器的 confidence 应该被降低
        assert class_strategy['confidence'] < 0.5 * 0.5  # 基础 0.5 * 惩罚系数 0.3

    def test_hint_locator(self):
        """测试 hint 属性的推荐"""
        element = {
            'hint': 'Enter your email',
            'class_name': 'android.widget.EditText',
        }

        strategies = self.picker.recommend_locators(element)

        # 应该包含 hint 策略
        hint_strategy = next((s for s in strategies if s['type'] == 'hint'), None)
        assert hint_strategy is not None
        assert hint_strategy['value'] == 'Enter your email'
        assert hint_strategy['confidence'] == 0.70


class TestElementPickerIntegration:
    """元素拾取器集成测试（需要真实 UI 层级数据）"""

    def test_real_element_analysis(self):
        """测试真实元素的分析（使用模拟数据）"""
        # 模拟从 device_views.py 的 page_state 接口返回的候选元素
        real_element = {
            'name': '登录按钮',
            'description': 'Button | login_btn',
            'package_name': 'com.example.app',
            'class_name': 'android.widget.Button',
            'resource_id': 'com.example:id/login_btn',
            'text': '登录',
            'content_desc': '',
            'hint': '',
            'clickable': True,
            'focusable': True,
            'checkable': False,
            'long_clickable': False,
            'scrollable': False,
            'bounds': {
                'x1': 96,
                'y1': 1800,
                'x2': 984,
                'y2': 1920,
                'width': 888,
                'height': 120,
            },
            'raw_bounds': '[96,1800][984,1920]',
        }

        analysis = analyze_element_for_picker(real_element)

        # 验证分析结果
        assert analysis['has_resource_id'] is True
        assert analysis['is_interactive'] is True
        assert len(analysis['strategies']) >= 4

        # 生成配置
        picker = ElementPicker()
        config = picker.generate_selector_config(real_element)

        assert config['selector_type'] == 'resource_id'
        assert config['resource_id'] == 'com.example:id/login_btn'
        assert config['text'] == '登录'
        assert config['clickable'] is True


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
