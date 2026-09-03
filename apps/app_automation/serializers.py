# -*- coding: utf-8 -*-
import re

from rest_framework import serializers
from django.utils import timezone
from django.conf import settings
from .models import (
    AppProject,
    AppTestConfig,
    AppDevice,
    AppExecutionAgent,
    AppElement,
    AppSemanticDictionary,
    AppComponent,
    AppCustomComponent,
    AppComponentPackage,
    AppPackage,
    AppTestCase,
    AppTestCaseFolder,
    AppTestCaseTag,
    AppTestSuite,
    AppTestSuiteCase,
    AppTestExecution,
    AppExplorationRun,
    AppExplorationTask,
    AppExplorationStep,
    AppInspectionReviewRule,
    AppInspectionTargetResult,
    AppPageElement,
    AppPageNode,
    AppPageTransition,
    AppScheduledTask,
    AppNotificationLog,
)
from .utils.exploration_annotations import build_annotated_screenshot
from .utils.exploration_assets import readable_step_action, readable_step_target, technical_step_target
from .utils.exploration_risk_guard import assess_risk_values
from .utils.inspection_metrics import build_target_consistency_metrics


# ========== 项目管理序列化器 ==========

class AppProjectSerializer(serializers.ModelSerializer):
    """APP项目序列化器 - 列表/详情"""
    owner_name = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()
    test_case_count = serializers.SerializerMethodField()
    test_suite_count = serializers.SerializerMethodField()
    android_app_package_name = serializers.CharField(source='android_app_package.name', read_only=True, default='')
    android_app_package_code = serializers.CharField(source='android_app_package.package_name', read_only=True, default='')

    class Meta:
        model = AppProject
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')

    def get_owner_name(self, obj):
        return obj.owner.username if obj.owner else None

    def get_member_count(self, obj):
        return obj.members.count()

    def get_test_case_count(self, obj):
        return obj.test_cases.count()

    def get_test_suite_count(self, obj):
        return obj.test_suites.count()


class AppProjectCreateSerializer(serializers.ModelSerializer):
    """APP项目创建序列化器"""
    class Meta:
        model = AppProject
        fields = ('name', 'description', 'status', 'android_app_package', 'ios_bundle_id', 'start_date', 'end_date', 'members')
        extra_kwargs = {
            'members': {'required': False},
        }


class AppProjectUpdateSerializer(serializers.ModelSerializer):
    """APP项目更新序列化器"""
    class Meta:
        model = AppProject
        fields = ('name', 'description', 'status', 'android_app_package', 'ios_bundle_id', 'start_date', 'end_date', 'members')


# ========== 配置序列化器 ==========

class AppTestConfigSerializer(serializers.ModelSerializer):
    """APP测试配置序列化器"""
    
    class Meta:
        model = AppTestConfig
        fields = ['id', 'adb_path', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class AppDeviceSerializer(serializers.ModelSerializer):
    """APP设备序列化器"""
    locked_by_name = serializers.SerializerMethodField()
    agent_name = serializers.CharField(source='agent.name', read_only=True, default='')
    agent_status = serializers.CharField(source='agent.status', read_only=True, default='')
    
    class Meta:
        model = AppDevice
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')
    
    def get_locked_by_name(self, obj):
        return obj.locked_by.username if obj.locked_by else None


class AppElementSerializer(serializers.ModelSerializer):
    """APP元素序列化器"""
    created_by_name = serializers.SerializerMethodField()
    element_type_display = serializers.CharField(source='get_element_type_display', read_only=True)
    preview_url = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    display_description = serializers.SerializerMethodField()
    manual_note = serializers.SerializerMethodField()
    
    class Meta:
        model = AppElement
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'usage_count', 'last_used_at')
    
    def get_created_by_name(self, obj):
        return obj.created_by.username if obj.created_by else None
    
    def get_preview_url(self, obj):
        """获取图片预览 URL"""
        if obj.element_type == 'image' and obj.config:
            image_path = obj.config.get('image_path')
            if image_path:
                from .utils.image_helpers import get_element_image_url
                return get_element_image_url(image_path)
        return None

    def get_display_name(self, obj):
        """返回适合给人看的元素中文名称。"""
        if obj.element_type != 'selector':
            return obj.name

        description = str((obj.config or {}).get('description') or '').strip()
        if description:
            return description

        return self._build_selector_description(obj)

    def get_manual_note(self, obj):
        """返回人工补充说明。"""
        return str((obj.config or {}).get('manual_note') or '').strip()

    def get_display_description(self, obj):
        """返回更适合页面展示和搜索的说明文案。"""
        if obj.element_type == 'image':
            image_path = (obj.config or {}).get('image_path', '')
            return image_path or '图片元素'

        if obj.element_type == 'pos':
            x = (obj.config or {}).get('x')
            y = (obj.config or {}).get('y')
            return f'坐标元素 ({x}, {y})' if x is not None and y is not None else '坐标元素'

        if obj.element_type == 'region':
            config = obj.config or {}
            coords = [config.get('x1'), config.get('y1'), config.get('x2'), config.get('y2')]
            if all(item is not None for item in coords):
                return f'区域元素 ({coords[0]}, {coords[1]}, {coords[2]}, {coords[3]})'
            return '区域元素'

        manual_note = self.get_manual_note(obj)
        if manual_note:
            return manual_note

        return self._build_selector_meta(obj)

    def _build_selector_description(self, obj):
        config = obj.config or {}
        locator_key = str(config.get('locator_key') or '').strip().lower()
        resource_id = str(config.get('resource_id') or '').strip()
        description = str(config.get('description') or '').strip()
        hint = str(config.get('hint') or '').strip()
        text = str(config.get('text') or '').strip()
        content_desc = str(config.get('content_desc') or '').strip()

        exact_map = {
            'cbk_agree': '协议勾选框',
            'et_number': '手机号输入框',
            'et_password': '密码输入框',
            'etpassword': '密码输入框',
            'btn_login': '登录按钮',
            'btnlogin': '登录按钮',
            'btn_get_code': '获取验证码按钮',
            'btngetcode': '获取验证码按钮',
            'tv_password_login': '密码登录切换',
            'tvpasswordlogin': '密码登录切换',
            'ed_code_input': '验证码输入框',
            'edcodeinput': '验证码输入框',
            'edit_verify_code': '验证码组件',
            'editverifycode': '验证码组件',
            'tv_agreement': '协议文案',
            'tvagreement': '协议文案',
            'tv_country': '国家区号',
            'tvcountry': '国家区号',
            'ifv_back': '返回按钮',
            'ifvback': '返回按钮',
            'iv_clear': '清空按钮',
            'ivclear': '清空按钮',
            'iv_pwd_show': '密码显隐按钮',
            'ivpwdshow': '密码显隐按钮',
            'top_bar': '顶部栏',
            'topbar': '顶部栏',
            'tv_title': '页面标题',
            'tvtitle': '页面标题',
            'tv_tip': '提示文案',
            'tvtip': '提示文案',
            'tv_forget_password': '忘记密码',
            'tvforgetpassword': '忘记密码',
            'login_by_wechat': '微信登录',
            'login_by_qq': 'QQ登录',
        }

        if locator_key in exact_map:
            return exact_map[locator_key]

        resource_tail = resource_id.split('/')[-1].split(':')[-1].strip().lower() if resource_id else ''
        if resource_tail in exact_map:
            return exact_map[resource_tail]

        for raw_value in (hint, text, content_desc):
            clean_value = raw_value.strip()
            if clean_value:
                return clean_value

        readable = self._humanize_locator_key(locator_key or resource_tail or obj.name)
        if readable:
            return readable

        if description:
            return description

        return '定位元素'

    def _build_selector_meta(self, obj):
        config = obj.config or {}
        summary_parts = []

        resource_id = str(config.get('resource_id') or '').strip()
        text = str(config.get('text') or '').strip()
        hint = str(config.get('hint') or '').strip()
        content_desc = str(config.get('content_desc') or '').strip()
        class_name = str(config.get('class') or '').strip()
        bounds = str(config.get('bounds') or '').strip()

        if resource_id:
            summary_parts.append(resource_id)
        if text:
            summary_parts.append(f'text={text}')
        elif hint:
            summary_parts.append(f'hint={hint}')
        elif content_desc:
            summary_parts.append(f'desc={content_desc}')
        if class_name:
            summary_parts.append(class_name)
        if bounds:
            summary_parts.append(bounds)

        return ' | '.join(summary_parts) if summary_parts else self._build_selector_description(obj)

    def _humanize_locator_key(self, locator_key):
        token_text = locator_key.replace('.', '_').replace('-', '_')
        tokens = [token for token in token_text.split('_') if token]
        if not tokens:
            return ''

        prefix = tokens[0].lower()
        body_tokens = [self._translate_token(token) for token in tokens[1:] if self._translate_token(token)]
        body = ''.join(dict.fromkeys(body_tokens))

        prefix_map = {
            'btn': '按钮',
            'et': '输入框',
            'ed': '输入框',
            'edit': '输入框',
            'input': '输入框',
            'tv': '文本',
            'txt': '文本',
            'label': '标签',
            'iv': '图标',
            'img': '图标',
            'icon': '图标',
            'ic': '图标',
            'cbk': '勾选框',
            'checkbox': '勾选框',
            'top': '顶部区域',
            'layout': '布局区域',
            'rv': '列表',
        }

        suffix = prefix_map.get(prefix, '元素')
        if body:
            return f'{body}{suffix}'
        return suffix

    def _translate_token(self, token):
        token_map = {
            'agree': '协议',
            'agreement': '协议',
            'number': '手机号',
            'phone': '手机号',
            'mobile': '手机号',
            'password': '密码',
            'pwd': '密码',
            'login': '登录',
            'code': '验证码',
            'verify': '验证码',
            'country': '国家区号',
            'title': '标题',
            'tip': '提示',
            'back': '返回',
            'clear': '清空',
            'show': '显示',
            'forget': '忘记',
            'wechat': '微信',
            'qq': 'QQ',
            'top': '顶部',
            'bar': '栏',
            'server': '社区',
            'community': '社区',
            'create': '创建',
            'confirm': '确认',
            'search': '搜索',
            'game': '游戏',
            'name': '名称',
        }
        return token_map.get(token.lower(), '')
    
    def validate_config(self, value):
        """验证配置项"""
        element_type = self.initial_data.get('element_type')
        
        if element_type == 'image':
            if not value.get('image_path'):
                raise serializers.ValidationError('图片元素必须包含 image_path 字段')
            
            # 如果有 file_hash，可以进行重复检测（在视图层处理更合适）
            file_hash = value.get('file_hash')
            if file_hash:
                # 检查是否有其他元素使用相同哈希（排除自身）
                instance_id = self.instance.id if self.instance else None
                existing = AppElement.objects.filter(
                    config__file_hash=file_hash
                ).exclude(id=instance_id).first()
                
                if existing:
                    raise serializers.ValidationError(
                        f'相同的图片已被元素 "{existing.name}" (ID: {existing.id}) 使用。'
                        f'建议复制该元素或上传不同的图片。'
                    )
        
        elif element_type == 'pos':
            # 坐标类型需要 x, y
            if 'x' not in value or 'y' not in value:
                raise serializers.ValidationError('坐标元素必须包含 x 和 y 字段')
        
        elif element_type == 'region':
            # 区域类型需要 x1, y1, x2, y2
            required_fields = ['x1', 'y1', 'x2', 'y2']
            missing_fields = [f for f in required_fields if f not in value]
            if missing_fields:
                raise serializers.ValidationError(
                    f'区域元素缺少必需字段: {", ".join(missing_fields)}'
                )
        elif element_type == 'selector':
            selector_fields = ['resource_id', 'text', 'content_desc', 'class', 'hint']
            if not any(value.get(field) for field in selector_fields):
                raise serializers.ValidationError(
                    '定位元素至少需要提供 resource_id、text、content_desc、class、hint 中的一个字段'
                )
        
        return value
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        return data


class AppPackageSerializer(serializers.ModelSerializer):
    """APP应用包名序列化器"""
    created_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = AppPackage
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')
    
    def get_created_by_name(self, obj):
        return obj.created_by.username if obj.created_by else None


class AppSemanticDictionarySerializer(serializers.ModelSerializer):
    """Serializer for semantic naming dictionaries."""
    created_by_name = serializers.SerializerMethodField()
    project_name = serializers.CharField(source='project.name', read_only=True, default='')
    display_label = serializers.SerializerMethodField()

    class Meta:
        model = AppSemanticDictionary
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by')

    def get_created_by_name(self, obj):
        return obj.created_by.username if obj.created_by else None

    def get_display_label(self, obj):
        return obj.label or obj.value

    def validate_value(self, value):
        value = str(value or '').strip()
        if not value:
            raise serializers.ValidationError('Value is required.')
        if '.' in value:
            raise serializers.ValidationError('Value cannot contain dot "." because it is used as the name separator.')
        return value

    def validate(self, attrs):
        project = attrs.get('project', getattr(self.instance, 'project', None))
        category = attrs.get('category', getattr(self.instance, 'category', None))
        value = attrs.get('value', getattr(self.instance, 'value', ''))

        queryset = AppSemanticDictionary.objects.filter(
            project=project,
            category=category,
            value=value,
        )
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError('Dictionary value already exists in the same scope and category.')
        return attrs


class AppTestCaseTagSerializer(serializers.ModelSerializer):
    """APP test case controlled tag serializer."""
    usage_count = serializers.SerializerMethodField()

    class Meta:
        model = AppTestCaseTag
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')

    def get_usage_count(self, obj):
        return obj.test_cases.count()

    def validate_name(self, value):
        value = str(value or '').strip()
        if not value:
            raise serializers.ValidationError('标签名称不能为空。')
        return value

    def validate(self, attrs):
        project = attrs.get('project', getattr(self.instance, 'project', None))
        name = attrs.get('name', getattr(self.instance, 'name', ''))
        queryset = AppTestCaseTag.objects.filter(project=project, name=name)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if project and name and queryset.exists():
            raise serializers.ValidationError('同一项目下已存在同名标签。')
        return attrs


class AppTestCaseFolderSerializer(serializers.ModelSerializer):
    """APP test case folder serializer."""
    parent_name = serializers.CharField(source='parent.name', read_only=True, default='')
    case_count = serializers.SerializerMethodField()

    class Meta:
        model = AppTestCaseFolder
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'level', 'is_system')

    def get_case_count(self, obj):
        return obj.test_cases.exclude(lifecycle_status='deprecated').count()

    def validate_name(self, value):
        value = str(value or '').strip()
        if not value:
            raise serializers.ValidationError('目录名称不能为空。')
        return value

    def validate(self, attrs):
        project = attrs.get('project', getattr(self.instance, 'project', None))
        parent = attrs.get('parent', getattr(self.instance, 'parent', None))
        name = attrs.get('name', getattr(self.instance, 'name', ''))
        if self.instance and parent and parent.pk == self.instance.pk:
            raise serializers.ValidationError('目录不能选择自己作为父目录。')
        if parent and project and parent.project_id != project.id:
            raise serializers.ValidationError('父目录必须属于当前项目。')
        if parent and parent.level >= 5:
            raise serializers.ValidationError('目录最多支持 5 级。')
        queryset = AppTestCaseFolder.objects.filter(project=project, parent=parent, name=name)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if project and name and queryset.exists():
            raise serializers.ValidationError('同一项目同级目录下已存在同名目录。')
        return attrs


class AppTestCaseSerializer(serializers.ModelSerializer):
    """APP测试用例序列化器"""
    created_by_name = serializers.SerializerMethodField()
    maintainer_name = serializers.CharField(source='maintainer.username', read_only=True, default='')
    app_package_name = serializers.CharField(source='app_package.name', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True, default='')
    folder_name = serializers.CharField(source='folder.name', read_only=True, default='')
    case_type_display = serializers.CharField(source='get_case_type_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    lifecycle_status_display = serializers.CharField(source='get_lifecycle_status_display', read_only=True)
    data_impact_display = serializers.CharField(source='get_data_impact_display', read_only=True)
    source_display = serializers.CharField(source='get_source_display', read_only=True)
    tag_details = AppTestCaseTagSerializer(source='tags', many=True, read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        source='tags',
        queryset=AppTestCaseTag.objects.all(),
        many=True,
        required=False,
        write_only=True,
    )
    latest_execution = serializers.SerializerMethodField()
    suite_names = serializers.SerializerMethodField()
    step_count = serializers.SerializerMethodField()
    
    class Meta:
        model = AppTestCase
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')
    
    def get_created_by_name(self, obj):
        return obj.created_by.username if obj.created_by else None

    def validate(self, attrs):
        project = attrs.get('project', getattr(self.instance, 'project', None))
        folder = attrs.get('folder', getattr(self.instance, 'folder', None))
        tags = attrs.get('tags')
        if folder and project and folder.project_id != project.id:
            raise serializers.ValidationError('业务目录必须属于当前项目。')
        if tags is not None and project:
            invalid = [tag.name for tag in tags if tag.project_id != project.id]
            if invalid:
                raise serializers.ValidationError(f'标签必须属于当前项目: {", ".join(invalid)}')
        return attrs

    def get_latest_execution(self, obj):
        execution = obj.executions.order_by('-created_at').first()
        if not execution:
            return {
                'status': 'not_run',
                'status_text': '未执行',
                'result': '',
                'result_text': '未执行',
                'finished_at': '',
                'failure_reason': '',
                'duration': 0,
            }
        if execution.status == 'completed':
            result_text = {
                'passed': '通过',
                'failed': '失败',
                'skipped': '跳过',
            }.get(execution.result or '', '已完成')
        else:
            result_text = {
                'pending': '等待中',
                'running': '执行中',
                'error': '执行异常',
                'stopped': '已停止',
            }.get(execution.status, execution.status or '-')
        failure_reason = ''
        if execution.status == 'error':
            failure_reason = '环境/执行异常'
        elif execution.result == 'failed':
            failure_reason = '用例步骤失败'
        return {
            'id': execution.id,
            'status': execution.status,
            'status_text': result_text,
            'result': execution.result or '',
            'result_text': result_text,
            'finished_at': timezone.localtime(execution.finished_at).strftime('%Y-%m-%d %H:%M:%S') if execution.finished_at else '',
            'failure_reason': failure_reason,
            'duration': execution.duration or 0,
        }

    def get_suite_names(self, obj):
        return [
            item.test_suite.name
            for item in obj.suite_memberships.select_related('test_suite').all()[:10]
            if item.test_suite
        ]

    def get_step_count(self, obj):
        ui_flow = obj.ui_flow or []
        if isinstance(ui_flow, list):
            return len(ui_flow)
        if isinstance(ui_flow, dict):
            for key in ('steps', 'ui_flow', 'flow'):
                value = ui_flow.get(key)
                if isinstance(value, list):
                    return len(value)
        return 0


class AppTestExecutionSerializer(serializers.ModelSerializer):
    """APP测试执行记录序列化器"""
    case_name = serializers.CharField(read_only=True)
    device_name = serializers.CharField(read_only=True)
    user_name = serializers.CharField(read_only=True)
    agent_name = serializers.CharField(source='agent.name', read_only=True, default='')
    pass_rate = serializers.FloatField(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    result_display = serializers.CharField(source='get_result_display', read_only=True, default=None)
    execution_mode_display = serializers.CharField(source='get_execution_mode_display', read_only=True)
    
    class Meta:
        model = AppTestExecution
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'started_at', 'finished_at', 'duration')


class AppExecutionAgentSerializer(serializers.ModelSerializer):
    """本地执行机 Agent 序列化器。"""
    device_count = serializers.SerializerMethodField()
    online_device_count = serializers.SerializerMethodField()
    running_execution_count = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source='created_by.username', read_only=True, default='')

    class Meta:
        model = AppExecutionAgent
        fields = (
            'id',
            'agent_id',
            'name',
            'status',
            'health_status',
            'health_summary',
            'health_checks',
            'health_checked_at',
            'description',
            'capabilities',
            'token_prefix',
            'token_created_at',
            'token_last_used_at',
            'last_seen_at',
            'last_ip',
            'created_by',
            'created_by_name',
            'created_at',
            'updated_at',
            'device_count',
            'online_device_count',
            'running_execution_count',
        )
        read_only_fields = (
            'created_at',
            'updated_at',
            'last_seen_at',
            'last_ip',
            'created_by',
        )

    def get_device_count(self, obj):
        return obj.devices.count()

    def get_online_device_count(self, obj):
        return obj.devices.filter(status__in=['online', 'available', 'locked']).count()

    def get_running_execution_count(self, obj):
        return obj.executions.filter(status='running').count()


class AppExplorationStepSerializer(serializers.ModelSerializer):
    """Serializer for a single exploratory testing step."""
    screenshot_url = serializers.SerializerMethodField()
    after_screenshot_url = serializers.SerializerMethodField()
    annotated_screenshot_url = serializers.SerializerMethodField()
    display_action = serializers.SerializerMethodField()
    display_target = serializers.SerializerMethodField()
    technical_target = serializers.SerializerMethodField()

    class Meta:
        model = AppExplorationStep
        fields = '__all__'
        read_only_fields = ('created_at',)

    def _build_media_url(self, path):
        if not path:
            return ''
        request = self.context.get('request')
        media_url = getattr(settings, 'MEDIA_URL', '/media/')
        relative_path = str(path).replace('\\', '/').lstrip('/')
        if relative_path.startswith('media/'):
            relative_path = relative_path[len('media/'):]
        url = f'{media_url.rstrip("/")}/{relative_path}'
        return request.build_absolute_uri(url) if request else url

    def get_screenshot_url(self, obj):
        return self._build_media_url(obj.before_screenshot)

    def get_after_screenshot_url(self, obj):
        return self._build_media_url(obj.after_screenshot)

    def get_annotated_screenshot_url(self, obj):
        return self._build_media_url(build_annotated_screenshot(obj))

    def get_display_action(self, obj):
        return readable_step_action(obj)

    def get_display_target(self, obj):
        return readable_step_target(obj)

    def get_technical_target(self, obj):
        return technical_step_target(obj)


class AppInspectionTargetResultSerializer(serializers.ModelSerializer):
    """Serializer for one controlled inspection target result."""
    before_screenshot_url = serializers.SerializerMethodField()
    after_screenshot_url = serializers.SerializerMethodField()
    step_index = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()
    effective_review = serializers.SerializerMethodField()
    is_review_suppressed = serializers.SerializerMethodField()

    class Meta:
        model = AppInspectionTargetResult
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'reviewed_at')

    def _build_media_url(self, path):
        if not path:
            return ''
        request = self.context.get('request')
        media_url = getattr(settings, 'MEDIA_URL', '/media/')
        relative_path = str(path).replace('\\', '/').lstrip('/')
        if relative_path.startswith('media/'):
            relative_path = relative_path[len('media/'):]
        url = f'{media_url.rstrip("/")}/{relative_path}'
        return request.build_absolute_uri(url) if request else url

    def get_before_screenshot_url(self, obj):
        return self._build_media_url(obj.before_screenshot)

    def get_after_screenshot_url(self, obj):
        return self._build_media_url(obj.after_screenshot)

    def get_step_index(self, obj):
        return obj.step.step_index if obj.step_id and obj.step else None

    def get_reviewed_by_name(self, obj):
        return obj.reviewed_by.username if obj.reviewed_by_id and obj.reviewed_by else ''

    def _manual_review_payload(self, obj):
        if not obj.review_resolution:
            return None
        return {
            'source': 'manual',
            'resolution': obj.review_resolution,
            'note': obj.review_note,
            'reviewed_at': obj.reviewed_at.isoformat() if obj.reviewed_at else '',
            'reviewed_by': self.get_reviewed_by_name(obj),
        }

    def _matching_review_rule(self, obj):
        if not obj.task_id or not obj.target_name:
            return None
        rules = AppInspectionReviewRule.objects.filter(
            task_id=obj.task_id,
            target_name=obj.target_name,
            enabled=True,
        ).order_by('-updated_at')
        for rule in rules:
            if rule.status and rule.status != obj.status:
                continue
            return rule
        return None

    def get_effective_review(self, obj):
        manual = self._manual_review_payload(obj)
        if manual:
            return manual
        rule = self._matching_review_rule(obj)
        if not rule:
            return None
        return {
            'source': 'rule',
            'rule_id': rule.id,
            'resolution': rule.resolution,
            'note': rule.note,
            'reviewed_at': rule.updated_at.isoformat() if rule.updated_at else '',
            'reviewed_by': rule.created_by.username if rule.created_by_id and rule.created_by else '',
        }

    def get_is_review_suppressed(self, obj):
        review = self.get_effective_review(obj) or {}
        return review.get('resolution') in {'normal_behavior', 'rule_exception', 'target_should_remove'}


class AppPageElementSerializer(serializers.ModelSerializer):
    """Serializer for reusable page-map control snapshots."""
    page_business_name = serializers.CharField(source='page.business_name', read_only=True, default='')
    page_title = serializers.CharField(source='page.title', read_only=True, default='')
    page_activity = serializers.CharField(source='page.activity', read_only=True, default='')
    page_signature = serializers.CharField(source='page.page_signature', read_only=True, default='')
    page_screenshot = serializers.CharField(source='page.representative_screenshot', read_only=True, default='')
    page_screenshot_url = serializers.SerializerMethodField()
    page_screen_size = serializers.JSONField(source='page.screen_size', read_only=True, default=list)
    candidate_name = serializers.SerializerMethodField()
    candidate_score = serializers.SerializerMethodField()
    candidate_reason = serializers.SerializerMethodField()
    candidate_level = serializers.SerializerMethodField()
    candidate_level_label = serializers.SerializerMethodField()
    candidate_action = serializers.SerializerMethodField()
    candidate_governance_status = serializers.SerializerMethodField()
    candidate_governance_status_label = serializers.SerializerMethodField()

    class Meta:
        model = AppPageElement
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')

    def get_candidate_score(self, obj):
        if self.get_candidate_governance_status(obj) == 'ignored':
            return 0
        score = 0
        if obj.clickable:
            score += 35
        if obj.text or obj.content_desc:
            score += 30
        if obj.resource_id:
            score += 25
        if obj.role in ('button', 'input', 'switch'):
            score += 10
        if obj.risk_level in ('', 'low'):
            score += 10
        if obj.seen_count >= 2:
            score += 10
        if self._is_generic_container(obj):
            score -= 15 if obj.clickable else 35
        if obj.risk_level in ('medium', 'high'):
            score -= 20
        return min(score, 100)

    def get_candidate_reason(self, obj):
        reasons = []
        if self.get_candidate_governance_status(obj) == 'ignored':
            reasons.append('已标记无需维护')
        if obj.semantic_element_id:
            reasons.append('已入库')
        if obj.clickable:
            reasons.append('可点击')
        if obj.text or obj.content_desc:
            reasons.append('有可读文案')
        if obj.resource_id:
            reasons.append('有 resource-id')
        if obj.role in ('button', 'input', 'switch'):
            reasons.append(f'常用交互控件：{obj.role}')
        if self._is_generic_container(obj):
            reasons.append('疑似通用容器，需人工确认')
        if obj.seen_count >= 2:
            reasons.append('多次出现')
        if obj.risk_level and obj.risk_level != 'low':
            reasons.append(f'风险：{obj.risk_level}')
        return ' / '.join(reasons) or '普通控件快照'

    def get_candidate_name(self, obj):
        return _build_page_element_candidate_name(obj)

    def get_candidate_level(self, obj):
        if self.get_candidate_governance_status(obj) == 'ignored':
            return 'ignored'
        if obj.semantic_element_id:
            return 'promoted'
        score = self.get_candidate_score(obj)
        if obj.risk_level in ('forbidden', 'high'):
            return 'not_recommended'
        if obj.clickable:
            return 'review' if score < 75 or self._is_generic_container(obj) else 'recommended'
        if score < 45:
            return 'not_recommended'
        if score >= 75 and not self._is_generic_container(obj):
            return 'recommended'
        return 'review'

    def get_candidate_level_label(self, obj):
        return {
            'promoted': '已入库',
            'ignored': '已忽略',
            'recommended': '建议入库',
            'review': '需确认',
            'not_recommended': '不建议',
        }.get(self.get_candidate_level(obj), '需确认')

    def get_candidate_action(self, obj):
        return {
            'promoted': '已经生成语义元素，可先验证后复用。',
            'ignored': '已从默认候选列表隐藏，如需维护可先恢复。',
            'recommended': '文案或 resource-id 较明确，适合批量入库。',
            'review': '可入库，但建议结合截图确认业务含义。',
            'not_recommended': '更像容器或低价值节点，除非业务需要，否则不建议入库。',
        }.get(self.get_candidate_level(obj), '')

    def get_candidate_governance_status(self, obj):
        raw = obj.raw if isinstance(obj.raw, dict) else {}
        return str(raw.get('governance_status') or '').strip()

    def get_candidate_governance_status_label(self, obj):
        return {
            'ignored': '无需维护',
        }.get(self.get_candidate_governance_status(obj), '')

    def _is_generic_container(self, obj):
        tail = str(obj.resource_id or '').rsplit('/', 1)[-1].lower()
        class_name = str(obj.class_name or '').lower()
        if obj.text or obj.content_desc:
            return False
        if obj.role in ('button', 'input', 'switch'):
            return False
        return _is_generic_resource_tail(tail) or class_name.endswith(('layout', 'viewgroup'))

    def get_page_screenshot_url(self, obj):
        path = obj.page.representative_screenshot if obj.page_id and obj.page else ''
        if not path:
            return ''
        request = self.context.get('request')
        media_url = getattr(settings, 'MEDIA_URL', '/media/')
        relative_path = str(path).replace('\\', '/').lstrip('/')
        if relative_path.startswith('media/'):
            relative_path = relative_path[len('media/'):]
        url = f'{media_url.rstrip("/")}/{relative_path}'
        return request.build_absolute_uri(url) if request else url


def _build_page_element_candidate_name(obj):
    for value in (obj.text, obj.content_desc):
        text = str(value or '').strip()
        if text:
            return text[:80]

    tail = str(obj.resource_id or '').rsplit('/', 1)[-1].strip()
    if tail:
        if _is_generic_resource_tail(tail):
            readable_container = _humanize_container_tail(tail)
            if obj.clickable and readable_container:
                return f'{readable_container}可点击区域'[:80]
            return '通用容器'
        readable = _humanize_resource_tail(tail)
        if readable:
            return readable[:80]
        return tail[:80]

    role_name = {
        'button': '按钮',
        'input': '输入框',
        'switch': '开关',
        'image': '图片',
        'text': '文本',
        'clickable': '可点击区域',
    }.get(obj.role)
    return role_name or '未命名控件'


def _humanize_resource_tail(value):
    text = str(value or '').strip()
    if not text:
        return ''
    snake = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', text).replace('-', '_')
    tokens = [token.lower() for token in re.split(r'[_\s]+', snake) if token]
    if not tokens:
        return ''

    prefix_map = {
        'btn': '按钮',
        'button': '按钮',
        'tv': '文本',
        'txt': '文本',
        'et': '输入框',
        'ed': '输入框',
        'edit': '输入框',
        'input': '输入框',
        'iv': '图标',
        'img': '图片',
        'icon': '图标',
        'cb': '勾选框',
        'cbk': '勾选框',
        'switch': '开关',
        'tab': 'Tab',
        'rv': '列表',
    }
    word_map = {
        'login': '登录',
        'logout': '退出登录',
        'search': '搜索',
        'create': '创建',
        'confirm': '确认',
        'cancel': '取消',
        'back': '返回',
        'close': '关闭',
        'clear': '清空',
        'community': '社区',
        'club': '社区',
        'name': '名称',
        'nick': '昵称',
        'nickname': '昵称',
        'phone': '手机号',
        'mobile': '手机号',
        'password': '密码',
        'pwd': '密码',
        'code': '验证码',
        'avatar': '头像',
        'title': '标题',
        'message': '消息',
        'notice': '通知',
        'follow': '关注',
        'list': '列表',
        'item': '条目',
        'setting': '设置',
        'profile': '个人中心',
        'mine': '我的',
        'game': '游戏',
    }
    prefix = prefix_map.get(tokens[0], '')
    body_tokens = tokens[1:] if prefix else tokens
    body = ''.join(word_map.get(token, token) for token in body_tokens)
    if body and prefix:
        return f'{body}{prefix}'
    if body:
        return body
    return prefix or text


def _humanize_container_tail(value):
    snake = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', str(value or '')).replace('-', '_').lower()
    tokens = [token for token in re.split(r'[_\s]+', snake) if token]
    ignored = {'fl', 'll', 'rl', 'cl', 'layout', 'container', 'wrapper', 'root', 'content', 'holder'}
    meaningful_tokens = [token for token in tokens if token not in ignored]
    word_map = {
        'notice': '通知',
        'message': '消息',
        'community': '社区',
        'game': '游戏',
        'profile': '个人中心',
        'mine': '我的',
        'search': '搜索',
        'activity': '活动',
        'follow': '关注',
        'tab': 'Tab',
        'setting': '设置',
        'banner': 'Banner',
        'create': '创建',
        'publish': '发布',
        'list': '列表',
        'item': '条目',
        'entry': '入口',
    }
    return ''.join(word_map.get(token, token) for token in meaningful_tokens)


def _generic_resource_tokens():
    return {
        'content', 'drawerlayout', 'root', 'container', 'layout', 'view',
        'recyclerview', 'scrollview', 'nestedscrollview', 'framelayout',
        'linearlayout', 'relativelayout', 'constraintlayout',
    }


def _is_generic_resource_tail(value):
    tail = str(value or '').strip().lower()
    if not tail:
        return False
    if tail in _generic_resource_tokens():
        return True
    snake = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', str(value or '')).replace('-', '_').lower()
    tokens = {token for token in re.split(r'[_\s]+', snake) if token}
    generic_markers = {'wrapper', 'container', 'layout', 'root', 'content', 'holder'}
    prefix_markers = {'fl', 'll', 'rl', 'cl', 'layout'}
    return bool(tokens & generic_markers) or bool(tokens & prefix_markers and len(tokens) <= 2)


class AppPageNodeSerializer(serializers.ModelSerializer):
    """Serializer for persisted page-map nodes."""
    project_name = serializers.CharField(source='project.name', read_only=True, default='')
    package_name = serializers.CharField(source='app_package.package_name', read_only=True, default='')
    element_count = serializers.SerializerMethodField()
    clickable_count = serializers.SerializerMethodField()
    outgoing_count = serializers.SerializerMethodField()
    elements = serializers.SerializerMethodField()

    class Meta:
        model = AppPageNode
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')

    def get_element_count(self, obj):
        return obj.elements.count()

    def get_clickable_count(self, obj):
        return obj.elements.filter(clickable=True).count()

    def get_outgoing_count(self, obj):
        return obj.outgoing_transitions.count()

    def get_elements(self, obj):
        queryset = obj.elements.order_by('-clickable', '-seen_count', 'role', 'id')[:30]
        return AppPageElementSerializer(queryset, many=True, context=self.context).data


class AppPageTransitionSerializer(serializers.ModelSerializer):
    """Serializer for observed page transitions."""
    from_page_title = serializers.CharField(source='from_page.title', read_only=True, default='')
    to_page_title = serializers.CharField(source='to_page.title', read_only=True, default='')
    from_page_business_name = serializers.CharField(source='from_page.business_name', read_only=True, default='')
    to_page_business_name = serializers.CharField(source='to_page.business_name', read_only=True, default='')
    from_activity = serializers.CharField(source='from_page.activity', read_only=True, default='')
    to_activity = serializers.CharField(source='to_page.activity', read_only=True, default='')

    class Meta:
        model = AppPageTransition
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class AppExplorationRunSerializer(serializers.ModelSerializer):
    """Serializer for an APP exploration execution batch."""

    class Meta:
        model = AppExplorationRun
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class AppExplorationTaskSerializer(serializers.ModelSerializer):
    """Serializer for exploratory testing task list/detail."""
    project_name = serializers.CharField(read_only=True)
    package_name = serializers.CharField(read_only=True)
    device_name = serializers.CharField(read_only=True)
    created_by_name = serializers.CharField(read_only=True)
    source_task_name = serializers.CharField(read_only=True)
    steps = serializers.SerializerMethodField()
    latest_run = serializers.SerializerMethodField()
    run_history = serializers.SerializerMethodField()
    target_run_history = serializers.SerializerMethodField()
    target_results = serializers.SerializerMethodField()
    target_consistency = serializers.SerializerMethodField()
    execution_health = serializers.SerializerMethodField()

    class Meta:
        model = AppExplorationTask
        fields = '__all__'
        read_only_fields = (
            'created_by',
            'created_at',
            'updated_at',
            'started_at',
            'finished_at',
            'duration',
            'status',
            'result',
            'task_id',
            'progress',
            'total_steps',
            'explored_pages',
            'issue_count',
            'summary',
            'error_message',
        )

    def get_steps(self, obj):
        return AppExplorationStepSerializer(
            obj.report_steps(),
            many=True,
            context=self.context,
        ).data

    def get_latest_run(self, obj):
        latest_run = obj.latest_run()
        if not latest_run:
            return None
        return AppExplorationRunSerializer(latest_run, context=self.context).data

    def get_run_history(self, obj):
        runs = obj.runs.order_by('-created_at')[:10]
        return AppExplorationRunSerializer(runs, many=True, context=self.context).data

    def get_target_run_history(self, obj):
        runs = list(obj.runs.order_by('-created_at')[:5])
        history = []
        for run in runs:
            target_results = run.target_results.select_related('step').order_by('id')
            history.append({
                'run': AppExplorationRunSerializer(run, context=self.context).data,
                'target_results': AppInspectionTargetResultSerializer(
                    target_results,
                    many=True,
                    context=self.context,
                ).data,
            })
        return history

    def get_target_results(self, obj):
        latest_run = obj.latest_run()
        if not latest_run:
            return []
        queryset = latest_run.target_results.select_related('step').order_by('id')
        return AppInspectionTargetResultSerializer(queryset, many=True, context=self.context).data

    def get_target_consistency(self, obj):
        runs = (
            obj.runs
            .prefetch_related('target_results__step')
            .order_by('-created_at')[:3]
        )
        return build_target_consistency_metrics(runs, run_limit=3)

    def get_execution_health(self, obj):
        status_value = str(obj.status or '').lower()
        if status_value not in {'pending', 'running'}:
            return {
                'is_active': False,
                'is_stale': False,
                'level': 'normal',
                'message': '',
                'suggestion': '',
                'active_seconds': 0,
                'idle_seconds': 0,
            }

        now = timezone.now()
        updated_at = obj.updated_at or obj.created_at or now
        started_at = obj.started_at or obj.created_at or updated_at
        idle_seconds = max(int((now - updated_at).total_seconds()), 0)
        active_seconds = max(int((now - started_at).total_seconds()), 0)
        summary = obj.summary if isinstance(obj.summary, dict) else {}
        stage = str(summary.get('current_stage') or '')
        max_duration = int(obj.max_duration or 0)

        is_stale = False
        level = 'normal'
        message = stage or ('等待执行批次启动' if status_value == 'pending' else '执行中')
        suggestion = '继续等待执行状态同步。'

        if status_value == 'pending' and idle_seconds >= 120:
            is_stale = True
            level = 'warning'
            message = '任务长时间停留在等待中，可能没有被执行器消费。'
            suggestion = '建议刷新列表；如果仍不变化，停止后重新执行，并检查设备连接和后台服务。'
        elif status_value == 'running' and max_duration and active_seconds > max_duration + 120:
            is_stale = True
            level = 'danger'
            message = '任务运行时间已超过最大时长，可能卡在设备操作或执行器回收。'
            suggestion = '建议先查看日志；确认无进展后停止任务并重跑。'
        elif status_value == 'running' and idle_seconds >= 180:
            is_stale = True
            level = 'warning'
            message = '任务执行状态长时间未更新，可能卡在设备、ADB 或页面等待。'
            suggestion = '建议检查设备在线状态，必要时停止后重新执行。'

        return {
            'is_active': True,
            'is_stale': is_stale,
            'level': level,
            'message': message,
            'suggestion': suggestion,
            'active_seconds': active_seconds,
            'idle_seconds': idle_seconds,
            'current_stage': stage,
        }

    def validate_blacklist_keywords(self, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(',') if item.strip()]
        if not isinstance(value, list):
            raise serializers.ValidationError('Blacklist keywords must be a list.')
        return [str(item).strip() for item in value if str(item).strip()]

    def validate_entry_keywords(self, value):
        if value in (None, ''):
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(',') if item.strip()]
        if not isinstance(value, list):
            raise serializers.ValidationError('Entry keywords must be a list.')
        return [str(item).strip() for item in value if str(item).strip()]

    def validate_start_actions(self, value):
        if value in (None, ''):
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError('Start actions must be a list.')
        allowed_types = {'tap_text', 'tap_resource_id', 'tap_pos', 'wait', 'swipe', 'back'}
        normalized = []
        for index, item in enumerate(value, 1):
            if not isinstance(item, dict):
                raise serializers.ValidationError(f'Start action #{index} must be an object.')
            action_type = str(item.get('type') or '').strip()
            if not action_type:
                continue
            if action_type not in allowed_types:
                raise serializers.ValidationError(f'Unsupported start action type: {action_type}.')
            risk = assess_risk_values([
                item.get('value'),
                item.get('text'),
                item.get('target'),
                item.get('resource_id'),
            ])
            if risk and risk.get('level') == 'forbidden':
                raise serializers.ValidationError(
                    f'Start action #{index} 命中禁止风险词「{risk.get("keyword")}」，不允许作为自动起始导航。'
                )
            normalized.append(item)
        return normalized

    def validate_max_steps(self, value):
        if value < 1 or value > 200:
            raise serializers.ValidationError('Max steps must be between 1 and 200.')
        return value

    def validate_max_duration(self, value):
        if value < 10 or value > 7200:
            raise serializers.ValidationError('Max duration must be between 10 and 7200 seconds.')
        return value


class AppComponentSerializer(serializers.ModelSerializer):
    """UI组件定义序列化器"""
    
    class Meta:
        model = AppComponent
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class AppCustomComponentSerializer(serializers.ModelSerializer):
    """自定义组件定义序列化器"""
    
    class Meta:
        model = AppCustomComponent
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class AppComponentPackageSerializer(serializers.ModelSerializer):
    """组件包序列化器"""
    created_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = AppComponentPackage
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')
    
    def get_created_by_name(self, obj):
        return obj.created_by.username if obj.created_by else None


# ========== 测试套件序列化器 ==========

class AppTestSuiteCaseSerializer(serializers.ModelSerializer):
    """套件-用例关联序列化器"""
    test_case = serializers.SerializerMethodField()
    test_case_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = AppTestSuiteCase
        fields = ('id', 'test_case', 'test_case_id', 'order')

    def get_test_case(self, obj):
        tc = obj.test_case
        return {
            'id': tc.id,
            'name': tc.name,
            'description': tc.description,
            'app_package_name': tc.app_package.name if tc.app_package else '',
            'updated_at': tc.updated_at,
        }


class AppTestSuiteSerializer(serializers.ModelSerializer):
    """测试套件列表序列化器"""
    created_by_name = serializers.SerializerMethodField()
    test_case_count = serializers.SerializerMethodField()
    executed_case_count = serializers.SerializerMethodField()
    suite_progress = serializers.SerializerMethodField()
    suite_cases = AppTestSuiteCaseSerializer(many=True, read_only=True)
    execution_status_display = serializers.CharField(
        source='get_execution_status_display', read_only=True
    )
    execution_result_display = serializers.CharField(
        source='get_execution_result_display', read_only=True, default=None
    )

    class Meta:
        model = AppTestSuite
        fields = (
            'id', 'name', 'description', 'project',
            'execution_status', 'execution_status_display',
            'execution_result', 'execution_result_display',
            'passed_count', 'failed_count', 'last_run_at',
            'test_case_count', 'executed_case_count', 'suite_progress', 'suite_cases',
            'created_by', 'created_by_name',
            'created_at', 'updated_at',
        )
        read_only_fields = (
            'created_at', 'updated_at',
            'execution_status', 'execution_result',
            'passed_count', 'failed_count', 'last_run_at',
        )

    def get_created_by_name(self, obj):
        return obj.created_by.username if obj.created_by else None

    def get_test_case_count(self, obj):
        return obj.suite_cases.count()

    def get_executed_case_count(self, obj):
        total = obj.suite_cases.count()
        if total <= 0:
            return 0
        latest_executions = obj.executions.order_by('-created_at')[:total]
        finished_statuses = {'completed', 'error', 'stopped'}
        return sum(1 for item in latest_executions if item.status in finished_statuses)

    def get_suite_progress(self, obj):
        total = obj.suite_cases.count()
        if total <= 0:
            return 0
        return min(100, round(self.get_executed_case_count(obj) / total * 100))


class AppTestSuiteCreateSerializer(serializers.ModelSerializer):
    """测试套件创建序列化器"""
    test_case_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        write_only=True,
        default=[]
    )

    class Meta:
        model = AppTestSuite
        fields = ('id', 'name', 'description', 'project', 'test_case_ids')
        read_only_fields = ('id',)

    def create(self, validated_data):
        test_case_ids = validated_data.pop('test_case_ids', [])
        suite = AppTestSuite.objects.create(**validated_data)
        for idx, tc_id in enumerate(test_case_ids):
            AppTestSuiteCase.objects.create(
                test_suite=suite,
                test_case_id=tc_id,
                order=idx
            )
        return suite


class AppTestSuiteUpdateSerializer(serializers.ModelSerializer):
    """测试套件更新序列化器"""
    class Meta:
        model = AppTestSuite
        fields = ('name', 'description', 'project')


# ========== 定时任务序列化器 ==========

class AppScheduledTaskSerializer(serializers.ModelSerializer):
    """APP定时任务序列化器"""
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    device_name = serializers.SerializerMethodField()
    app_package_name = serializers.CharField(source='app_package.name', read_only=True, default='')
    test_suite_name = serializers.CharField(source='test_suite.name', read_only=True, default='')
    test_case_name = serializers.CharField(source='test_case.name', read_only=True, default='')
    task_type_display = serializers.CharField(source='get_task_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    trigger_type_display = serializers.CharField(source='get_trigger_type_display', read_only=True)
    notification_type_display = serializers.SerializerMethodField()

    class Meta:
        model = AppScheduledTask
        fields = [
            'id', 'name', 'description', 'project',
            'task_type', 'task_type_display',
            'trigger_type', 'trigger_type_display',
            'cron_expression', 'interval_seconds', 'execute_at',
            'device', 'device_name',
            'app_package', 'app_package_name',
            'test_suite', 'test_suite_name',
            'test_case', 'test_case_name',
            'notify_on_success', 'notify_on_failure',
            'notification_type', 'notification_type_display', 'notify_emails',
            'status', 'status_display',
            'last_run_time', 'next_run_time',
            'total_runs', 'successful_runs', 'failed_runs',
            'last_result', 'error_message',
            'created_by', 'created_by_name',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'created_by', 'last_run_time', 'next_run_time',
            'total_runs', 'successful_runs', 'failed_runs',
            'last_result', 'error_message',
            'created_at', 'updated_at',
        ]

    def get_device_name(self, obj):
        if obj.device:
            return obj.device.name or obj.device.device_id
        return ''

    def get_notification_type_display(self, obj):
        return obj.get_notification_type_display() if obj.notification_type else '-'

    def validate(self, attrs):
        trigger_type = attrs.get('trigger_type')
        if trigger_type == 'CRON' and not attrs.get('cron_expression'):
            raise serializers.ValidationError('Cron表达式不能为空')
        if trigger_type == 'INTERVAL':
            if not attrs.get('interval_seconds'):
                raise serializers.ValidationError('间隔秒数不能为空')
            if attrs['interval_seconds'] < 60:
                raise serializers.ValidationError('间隔秒数不能小于60秒')
        if trigger_type == 'ONCE':
            if not attrs.get('execute_at'):
                raise serializers.ValidationError('执行时间不能为空')
            if attrs['execute_at'] <= timezone.now():
                raise serializers.ValidationError('执行时间必须大于当前时间')

        task_type = attrs.get('task_type')
        if task_type == 'TEST_SUITE' and not attrs.get('test_suite'):
            raise serializers.ValidationError('请选择测试套件')
        if task_type == 'TEST_CASE' and not attrs.get('test_case'):
            raise serializers.ValidationError('请选择测试用例')

        return attrs

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        instance = super().create(validated_data)
        instance.next_run_time = instance.calculate_next_run()
        instance.save(update_fields=['next_run_time'])
        return instance

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        instance.next_run_time = instance.calculate_next_run()
        instance.save(update_fields=['next_run_time'])
        return instance


class AppNotificationLogSerializer(serializers.ModelSerializer):
    """APP通知日志序列化器"""
    recipient_names = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    notification_type_display = serializers.CharField(source='get_notification_type_display', read_only=True)
    retry_status = serializers.SerializerMethodField()
    task_type_display = serializers.SerializerMethodField()
    actual_notification_type_display = serializers.SerializerMethodField()

    class Meta:
        model = AppNotificationLog
        fields = [
            'id', 'task', 'task_name',
            'notification_type', 'notification_type_display',
            'actual_notification_type_display', 'task_type_display',
            'sender_name', 'sender_email',
            'recipient_names', 'webhook_bot_info', 'notification_content',
            'status', 'status_display', 'error_message', 'response_info',
            'created_at', 'sent_at', 'retry_count', 'retry_status',
        ]
        read_only_fields = ['created_at', 'sent_at']

    def get_recipient_names(self, obj):
        return obj.get_recipient_names()

    def get_retry_status(self, obj):
        return obj.get_retry_status()

    def get_task_type_display(self, obj):
        if obj.task_type:
            choices = dict(AppScheduledTask.TASK_TYPE_CHOICES)
            return choices.get(obj.task_type, obj.task_type)
        return '未记录'

    def get_actual_notification_type_display(self, obj):
        if obj.webhook_bot_info:
            bot_type = obj.webhook_bot_info.get('type', '') or obj.webhook_bot_info.get('bot_type', '')
            type_map = {'wechat': '企微机器人', 'feishu': '飞书机器人', 'dingtalk': '钉钉机器人'}
            return type_map.get(bot_type, 'Webhook机器人')
        if obj.recipient_info and isinstance(obj.recipient_info, list) and len(obj.recipient_info) > 0:
            return '邮箱通知'
        return '-'
