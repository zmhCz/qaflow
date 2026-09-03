from rest_framework import serializers
from .business_load import SCENARIO_DEFINITIONS, build_capability_chain, build_default_config
from .models import BusinessAccount, BusinessLoadTask, DataFactoryRecord
from .tool_list import get_tool_list


class DataFactoryRecordSerializer(serializers.ModelSerializer):
    """数据工厂记录序列化器"""
    user_name = serializers.CharField(source='user.username', read_only=True)
    tool_category_display = serializers.CharField(source='get_tool_category_display', read_only=True)
    tool_scenario_display = serializers.CharField(source='get_tool_scenario_display', read_only=True)
    tool_name_display = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = DataFactoryRecord
        fields = [
            'id', 'user', 'user_name', 'tool_name', 'tool_name_display', 'tool_category', 'tool_category_display',
            'tool_scenario', 'tool_scenario_display', 'input_data', 'output_data',
            'is_saved', 'tags', 'created_at'
        ]
        read_only_fields = ['id', 'user', 'created_at']

    def get_tool_name_display(self, obj):
        """获取工具名称的显示名称"""
        try:
            # 直接在方法内获取工具列表
            tool_list = get_tool_list()
            for tool in tool_list:
                if tool['name'] == obj.tool_name:
                    return tool['display_name']
            return obj.tool_name
        except Exception as e:
            return obj.tool_name


class ToolExecuteSerializer(serializers.Serializer):
    """工具执行序列化器"""
    tool_name = serializers.CharField(required=True)
    tool_category = serializers.CharField(required=True)
    tool_scenario = serializers.CharField(required=True)
    input_data = serializers.JSONField(required=True)
    is_saved = serializers.BooleanField(default=True)
    tags = serializers.ListField(child=serializers.CharField(), required=False, allow_null=True)


class BusinessAccountSerializer(serializers.ModelSerializer):
    """Business account pool serializer."""

    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    locked_by_name = serializers.CharField(source='locked_by.username', read_only=True)
    environment_display = serializers.CharField(source='get_environment_display', read_only=True)
    business_domain_display = serializers.CharField(source='get_business_domain_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    has_password = serializers.SerializerMethodField(read_only=True)
    has_token = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = BusinessAccount
        fields = [
            'id', 'account_no', 'phone', 'user_id', 'nickname', 'password', 'token',
            'environment', 'environment_display', 'business_domain', 'business_domain_display',
            'status', 'status_display', 'purpose', 'tags', 'extra_data', 'last_used_at',
            'locked_at', 'locked_by', 'locked_by_name', 'created_by', 'created_by_name',
            'remark', 'created_at', 'updated_at', 'has_password', 'has_token',
        ]
        read_only_fields = [
            'id', 'locked_at', 'locked_by', 'created_by', 'created_at', 'updated_at',
            'has_password', 'has_token',
        ]
        extra_kwargs = {
            'password': {'write_only': True, 'required': False, 'allow_blank': True},
            'token': {'write_only': True, 'required': False, 'allow_blank': True},
        }

    def get_has_password(self, obj):
        return bool(obj.password)

    def get_has_token(self, obj):
        return bool(obj.token)

    def validate_tags(self, value):
        if value in (None, ''):
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(',') if item.strip()]
        return value


class BusinessAccountImportSerializer(serializers.Serializer):
    """Bulk import business accounts.

    Supported line formats:
    account_no
    account_no,phone,user_id,nickname,password
    start_account_no~end_account_no
    """

    environment = serializers.ChoiceField(choices=BusinessAccount.ENVIRONMENTS, default='test')
    business_domain = serializers.ChoiceField(choices=BusinessAccount.BUSINESS_DOMAINS, default='common')
    purpose = serializers.CharField(required=False, allow_blank=True, default='')
    tags = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    raw_text = serializers.CharField(required=False, allow_blank=True, default='')
    accounts = serializers.ListField(child=serializers.DictField(), required=False, default=list)

    def validate(self, attrs):
        if not attrs.get('raw_text') and not attrs.get('accounts'):
            raise serializers.ValidationError('请填写导入文本或账号列表')
        return attrs


class BusinessAccountAllocateSerializer(serializers.Serializer):
    environment = serializers.ChoiceField(choices=BusinessAccount.ENVIRONMENTS, default='test')
    business_domain = serializers.ChoiceField(choices=BusinessAccount.BUSINESS_DOMAINS, required=False)
    count = serializers.IntegerField(min_value=1, max_value=500, default=1)
    purpose = serializers.CharField(required=False, allow_blank=True, default='')
    tags = serializers.ListField(child=serializers.CharField(), required=False, default=list)


class BusinessAccountReleaseSerializer(serializers.Serializer):
    account_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)


class BusinessLoadTaskSerializer(serializers.ModelSerializer):
    """Business load-test task serializer."""

    scenario_type = serializers.CharField()
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    environment_display = serializers.CharField(source='get_environment_display', read_only=True)
    business_domain_display = serializers.CharField(source='get_business_domain_display', read_only=True)
    scenario_type_display = serializers.CharField(source='get_scenario_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = BusinessLoadTask
        fields = [
            'id', 'name', 'scenario_type', 'scenario_type_display',
            'environment', 'environment_display', 'business_domain', 'business_domain_display',
            'account_count', 'account_tags', 'purpose', 'config', 'capability_chain',
            'metrics', 'logs', 'status', 'status_display', 'created_by', 'created_by_name',
            'started_at', 'finished_at', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'capability_chain', 'metrics', 'logs', 'status', 'created_by',
            'created_by_name', 'started_at', 'finished_at', 'created_at', 'updated_at',
        ]

    def validate_account_tags(self, value):
        if value in (None, ''):
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(',') if item.strip()]
        return value

    def validate(self, attrs):
        scenario_type = attrs.get('scenario_type') or getattr(self.instance, 'scenario_type', '')
        if scenario_type and scenario_type not in SCENARIO_DEFINITIONS:
            raise serializers.ValidationError('不支持的业务压测场景')
        return attrs

    def create(self, validated_data):
        scenario_type = validated_data['scenario_type']
        config = build_default_config(scenario_type)
        config.update(validated_data.get('config') or {})
        self._normalize_team_duration_config(scenario_type, config)
        validated_data['config'] = config
        validated_data['capability_chain'] = build_capability_chain(scenario_type)
        validated_data['status'] = 'ready'
        return super().create(validated_data)

    def update(self, instance, validated_data):
        scenario_type = validated_data.get('scenario_type', instance.scenario_type)
        if 'scenario_type' in validated_data and scenario_type != instance.scenario_type:
            validated_data['capability_chain'] = build_capability_chain(scenario_type)

        if 'config' in validated_data:
            config = build_default_config(scenario_type)
            config.update(validated_data.get('config') or {})
            self._normalize_team_duration_config(scenario_type, config)
            validated_data['config'] = config

        return super().update(instance, validated_data)

    def _normalize_team_duration_config(self, scenario_type, config):
        if scenario_type != 'team_recruit_publish':
            return
        try:
            team_duration_seconds = int(config.get('team_duration_minutes') or 1) * 60
            duration_seconds = int(config.get('duration_seconds') or 0)
        except (TypeError, ValueError):
            team_duration_seconds = 60
            duration_seconds = 0
        if team_duration_seconds > duration_seconds:
            config['duration_seconds'] = team_duration_seconds
