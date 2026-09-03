from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class DataFactoryRecord(models.Model):
    """数据工厂使用记录"""

    TOOL_CATEGORIES = (
        ('test_data', '测试数据'),
        ('json', 'JSON工具'),
        ('string', '字符工具'),
        ('encoding', '编码工具'),
        ('random', '随机工具'),
        ('encryption', '加密工具'),
        ('crontab', 'Crontab工具'),
    )

    TOOL_SCENARIOS = (
        ('test_data', '测试数据'),
        ('json', 'JSON工具'),
        ('string', '字符工具'),
        ('encoding', '编码工具'),
        ('random', '随机工具'),
        ('encryption', '加密工具'),
        ('crontab', 'Crontab工具'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='用户')
    tool_name = models.CharField(max_length=100, verbose_name='工具名称')
    tool_category = models.CharField(max_length=20, choices=TOOL_CATEGORIES, verbose_name='工具分类')
    tool_scenario = models.CharField(max_length=20, choices=TOOL_SCENARIOS, verbose_name='使用场景')
    input_data = models.JSONField(verbose_name='输入数据', null=True, blank=True)
    output_data = models.JSONField(verbose_name='输出数据')
    is_saved = models.BooleanField(default=True, verbose_name='是否保存')
    tags = models.JSONField(verbose_name='标签', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'data_factory_record'
        verbose_name = '数据工厂记录'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['tool_category']),
            models.Index(fields=['tool_scenario']),
            # 复合索引优化统计查询
            models.Index(fields=['user', 'tool_category']),
            models.Index(fields=['user', 'tool_scenario']),
            models.Index(fields=['user', 'is_saved']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.tool_name}"


class BusinessAccount(models.Model):
    """Business test account pool for scenario runners."""

    BUSINESS_DOMAINS = (
        ('common', '通用'),
        ('im', 'IM'),
        ('room', '房间'),
        ('mic', '麦序'),
        ('community', '社区'),
        ('team', '组队'),
    )

    ENVIRONMENTS = (
        ('test', '测试环境'),
        ('test1', 'Test1'),
        ('staging', '预发环境'),
        ('dev', '开发环境'),
    )
    STATUSES = (
        ('available', '可用'),
        ('in_use', '占用中'),
        ('disabled', '禁用'),
        ('invalid', '失效'),
    )

    account_no = models.CharField(max_length=64, verbose_name='账号编号')
    phone = models.CharField(max_length=32, blank=True, default='', verbose_name='手机号')
    user_id = models.CharField(max_length=64, blank=True, default='', verbose_name='业务用户ID')
    nickname = models.CharField(max_length=128, blank=True, default='', verbose_name='昵称')
    password = models.CharField(max_length=256, blank=True, default='', verbose_name='密码')
    token = models.TextField(blank=True, default='', verbose_name='Token')
    environment = models.CharField(max_length=32, choices=ENVIRONMENTS, default='test', verbose_name='环境')
    business_domain = models.CharField(max_length=32, choices=BUSINESS_DOMAINS, default='common', verbose_name='业务域')
    status = models.CharField(max_length=32, choices=STATUSES, default='available', verbose_name='状态')
    purpose = models.CharField(max_length=128, blank=True, default='', verbose_name='用途')
    tags = models.JSONField(default=list, blank=True, verbose_name='标签')
    extra_data = models.JSONField(default=dict, blank=True, verbose_name='扩展信息')
    last_used_at = models.DateTimeField(null=True, blank=True, verbose_name='最近使用时间')
    locked_at = models.DateTimeField(null=True, blank=True, verbose_name='占用时间')
    locked_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='locked_business_accounts',
        verbose_name='占用人',
    )
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_business_accounts',
        verbose_name='创建人',
    )
    remark = models.TextField(blank=True, default='', verbose_name='备注')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'data_factory_business_account'
        verbose_name = '业务测试账号'
        verbose_name_plural = verbose_name
        ordering = ['environment', 'business_domain', 'account_no']
        constraints = [
            models.UniqueConstraint(
                fields=['environment', 'account_no'],
                name='uniq_business_account_environment_account_no',
            )
        ]
        indexes = [
            models.Index(fields=['environment', 'business_domain', 'status']),
            models.Index(fields=['account_no']),
            models.Index(fields=['user_id']),
            models.Index(fields=['phone']),
            models.Index(fields=['locked_by', 'status']),
        ]

    def __str__(self):
        return f"{self.environment}/{self.business_domain}/{self.account_no}"


class BusinessLoadTask(models.Model):
    """Composable business load-test task."""

    SCENARIO_TYPES = (
        ('room_list_load', '房间列表压测'),
        ('voice_room_online', '语音房在线保活'),
        ('room_enter_leave', '进退房压测'),
        ('community_follow', '关注社区压测'),
        ('community_activity_simulation', '社区活跃模拟'),
        ('im_message_flood', 'IM 消息刷屏压测'),
        ('team_recruit_publish', '发布组队压测'),
    )

    STATUSES = (
        ('draft', '草稿'),
        ('ready', '待执行'),
        ('running', '执行中'),
        ('completed', '已完成'),
        ('failed', '失败'),
        ('stopped', '已停止'),
    )

    name = models.CharField(max_length=128, verbose_name='任务名称')
    scenario_type = models.CharField(max_length=64, choices=SCENARIO_TYPES, verbose_name='场景类型')
    environment = models.CharField(max_length=32, choices=BusinessAccount.ENVIRONMENTS, default='test', verbose_name='环境')
    business_domain = models.CharField(max_length=32, choices=BusinessAccount.BUSINESS_DOMAINS, default='room', verbose_name='业务域')
    account_count = models.PositiveIntegerField(default=1, verbose_name='账号数量')
    account_tags = models.JSONField(default=list, blank=True, verbose_name='账号筛选标签')
    purpose = models.CharField(max_length=128, blank=True, default='', verbose_name='用途')
    config = models.JSONField(default=dict, blank=True, verbose_name='执行参数')
    capability_chain = models.JSONField(default=list, blank=True, verbose_name='能力链')
    metrics = models.JSONField(default=dict, blank=True, verbose_name='执行指标')
    logs = models.JSONField(default=list, blank=True, verbose_name='执行日志')
    status = models.CharField(max_length=32, choices=STATUSES, default='draft', verbose_name='状态')
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_business_load_tasks',
        verbose_name='创建人',
    )
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='开始时间')
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name='结束时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'data_factory_business_load_task'
        verbose_name = '业务压测任务'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['environment', 'business_domain', 'status']),
            models.Index(fields=['scenario_type', 'status']),
            models.Index(fields=['created_by', '-created_at']),
        ]

    def __str__(self):
        return f"{self.name}({self.get_scenario_type_display()})"
