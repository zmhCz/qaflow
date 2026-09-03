# -*- coding: utf-8 -*-
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

from .constants import DeviceStatus, ExecutionStatus, ExecutionResult, ElementType

User = get_user_model()


class AppProject(models.Model):
    """APP自动化测试项目"""
    STATUS_CHOICES = [
        ('NOT_STARTED', '未开始'),
        ('IN_PROGRESS', '进行中'),
        ('COMPLETED', '已结束'),
    ]

    name = models.CharField(max_length=200, verbose_name='项目名称')
    description = models.TextField(blank=True, default='', verbose_name='项目描述')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='IN_PROGRESS', verbose_name='项目状态')
    android_app_package = models.ForeignKey(
        'AppPackage',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='android_projects',
        verbose_name='Android默认应用包'
    )
    ios_bundle_id = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='iOS Bundle ID'
    )
    start_date = models.DateField(null=True, blank=True, verbose_name='开始日期')
    end_date = models.DateField(null=True, blank=True, verbose_name='结束日期')
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='owned_app_projects', verbose_name='负责人'
    )
    members = models.ManyToManyField(
        User, blank=True,
        related_name='app_projects', verbose_name='团队成员'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'app_projects'
        verbose_name = 'APP自动化项目'
        verbose_name_plural = 'APP自动化项目'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class AppTestConfig(models.Model):
    """APP自动化测试配置"""
    adb_path = models.CharField(
        max_length=500, 
        default='adb', 
        verbose_name='ADB路径',
        help_text='Android Debug Bridge 工具路径，默认为 adb（系统PATH）'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        db_table = 'app_test_config'
        verbose_name = 'APP测试配置'
        verbose_name_plural = 'APP测试配置'
    
    def __str__(self):
        return f"APP测试配置 (ADB: {self.adb_path})"


class AppDevice(models.Model):
    """Android 设备模型 - 整合了设备管理功能"""
    STATUS_CHOICES = [
        (DeviceStatus.AVAILABLE, '可用'),
        (DeviceStatus.LOCKED, '已锁定'),
        (DeviceStatus.ONLINE, '在线'),
        (DeviceStatus.OFFLINE, '离线'),
    ]
    
    CONNECTION_TYPE_CHOICES = [
        ('emulator', '本地模拟器'),
        ('remote_emulator', '远程模拟器'),
        ('real_device', '真实设备'),
    ]
    
    device_id = models.CharField(max_length=255, unique=True, verbose_name='设备序列号')
    name = models.CharField(max_length=255, blank=True, default='', verbose_name='设备名称')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=DeviceStatus.OFFLINE, verbose_name='状态')
    android_version = models.CharField(max_length=50, blank=True, default='', verbose_name='Android版本')
    connection_type = models.CharField(max_length=20, choices=CONNECTION_TYPE_CHOICES, default='emulator', verbose_name='连接类型')
    ip_address = models.CharField(max_length=50, blank=True, default='', verbose_name='IP地址')
    port = models.IntegerField(default=5555, verbose_name='端口')
    
    # 设备锁定相关字段
    locked_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='locked_app_devices', 
        verbose_name='锁定用户'
    )
    locked_at = models.DateTimeField(null=True, blank=True, verbose_name='锁定时间')
    max_allocation_time = models.IntegerField(default=28800, verbose_name='最大分配时间(秒)', help_text='默认8小时')
    
    # 设备规格信息
    device_specs = models.JSONField(default=dict, verbose_name='设备规格', help_text='RAM, CPU, 分辨率等信息')
    description = models.TextField(blank=True, default='', verbose_name='设备描述')
    location = models.CharField(max_length=200, blank=True, default='', verbose_name='设备位置')
    agent = models.ForeignKey(
        'AppExecutionAgent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='devices',
        verbose_name='所属执行机'
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        db_table = 'app_devices'
        verbose_name = 'APP测试设备'
        verbose_name_plural = 'APP测试设备'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['device_id']),
            models.Index(fields=['agent', 'status']),
        ]
    
    def __str__(self):
        return f"{self.name or self.device_id} ({self.get_status_display()})"
    
    def lock(self, user):
        """锁定设备"""
        self.locked_by = user
        self.locked_at = timezone.now()
        self.status = DeviceStatus.LOCKED
        self.save()
    
    def unlock(self):
        """释放设备"""
        self.locked_by = None
        self.locked_at = None
        self.status = DeviceStatus.AVAILABLE
        self.save()
    
    def is_lock_expired(self):
        """检查锁定是否过期"""
        if not self.locked_at:
            return False
        elapsed = (timezone.now() - self.locked_at).total_seconds()
        return elapsed > self.max_allocation_time


class AppExecutionAgent(models.Model):
    """本地执行机 Agent，用于云端平台下发任务、本地电脑连接真机执行。"""

    STATUS_CHOICES = [
        ('online', '在线'),
        ('offline', '离线'),
        ('busy', '执行中'),
        ('disabled', '已停用'),
    ]

    agent_id = models.CharField(max_length=120, unique=True, verbose_name='Agent标识')
    name = models.CharField(max_length=120, verbose_name='Agent名称')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='offline', verbose_name='状态')
    description = models.TextField(blank=True, default='', verbose_name='说明')
    capabilities = models.JSONField(default=dict, blank=True, verbose_name='能力信息')
    last_seen_at = models.DateTimeField(null=True, blank=True, verbose_name='最后心跳时间')
    last_ip = models.GenericIPAddressField(null=True, blank=True, verbose_name='最后访问IP')
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_app_execution_agents',
        verbose_name='创建人'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'app_execution_agents'
        verbose_name = 'APP执行机Agent'
        verbose_name_plural = 'APP执行机Agent'
        ordering = ['-last_seen_at', '-updated_at']
        indexes = [
            models.Index(fields=['agent_id']),
            models.Index(fields=['status', 'last_seen_at']),
        ]

    def __str__(self):
        return f'{self.name} ({self.agent_id})'


class AppElement(models.Model):
    """APP UI元素管理 - 统一管理图片、坐标、区域元素"""
    
    ELEMENT_TYPE_CHOICES = [
        (ElementType.IMAGE, '图片元素'),
        (ElementType.POS, '坐标元素'),
        (ElementType.REGION, '区域元素'),
        (ElementType.SELECTOR, '定位元素'),
    ]

    project = models.ForeignKey(
        AppProject, on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='elements', verbose_name='所属项目'
    )
    
    # 基础信息
    name = models.CharField(
        max_length=200,
        unique=True,
        verbose_name='元素名称',
        help_text='元素的唯一标识名称'
    )
    
    element_type = models.CharField(
        max_length=10,
        choices=ELEMENT_TYPE_CHOICES,
        verbose_name='元素类型'
    )
    
    # 标签
    tags = models.JSONField(
        default=list,
        verbose_name='标签',
        help_text='标签列表，如：["登录", "大厅", "支付"]'
    )
    
    # 元素配置（根据类型不同，内容不同）
    config = models.JSONField(
        default=dict,
        verbose_name='元素配置',
        help_text="""
        image类型: {
            "image_category": "common",
            "image_path": "common/login.png", 
            "file_hash": "abc123...",
            "image_threshold": 0.7, 
            "rgb": false
        }
        pos类型: {"x": 100, "y": 200}
        region类型: {"x1": 100, "y1": 200, "x2": 300, "y2": 400}
        selector类型: {
            "package": "com.example.demo",
            "activity": "com.example.demo.activity.LoginActivity",
            "resource_id": "com.example.demo:id/btnLogin",
            "class": "android.widget.Button",
            "text": "登录",
            "content_desc": "",
            "hint": "",
            "clickable": true,
            "focusable": true,
            "enabled": true,
            "bounds": "[96,984][984,1128]",
            "locator_key": "btn_login",
            "source_file": "demo_login.yaml"
        }
        """
    )
    
    # 多分辨率配置（可选）
    resolution_configs = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='分辨率配置',
        help_text='不同分辨率下的配置，如：{"1920x1080": {...}, "1280x720": {...}}'
    )
    
    # 使用统计
    usage_count = models.IntegerField(
        default=0,
        verbose_name='使用次数',
        help_text='该元素被用例引用的次数'
    )
    
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='最后使用时间'
    )
    
    # 元数据
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_app_elements',
        verbose_name='创建人'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间'
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='更新时间'
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name='是否启用',
        help_text='软删除标记'
    )
    
    class Meta:
        db_table = 'app_elements'
        verbose_name = 'APP UI元素'
        verbose_name_plural = 'APP UI元素'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['element_type']),
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"[{self.get_element_type_display()}] {self.name}"
    
    def increment_usage(self):
        """增加使用次数"""
        self.usage_count = models.F('usage_count') + 1
        self.last_used_at = timezone.now()
        self.save(update_fields=['usage_count', 'last_used_at'])


class AppSemanticDictionary(models.Model):
    """Semantic naming dictionary for APP automation elements."""

    CATEGORY_CHOICES = [
        ('page', 'Page'),
        ('object', 'Business Object'),
        ('role', 'Control Role'),
        ('purpose', 'Purpose'),
    ]
    GOVERNANCE_STATUS_CHOICES = [
        ('approved', 'Approved'),
        ('pending', 'Pending review'),
        ('merged', 'Merged'),
        ('deprecated', 'Deprecated'),
    ]

    project = models.ForeignKey(
        AppProject,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='semantic_dictionaries',
        verbose_name='Project',
    )
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, verbose_name='Category')
    value = models.CharField(max_length=120, verbose_name='Value')
    label = models.CharField(max_length=120, blank=True, default='', verbose_name='Label')
    description = models.TextField(blank=True, default='', verbose_name='Description')
    governance_status = models.CharField(
        max_length=20,
        choices=GOVERNANCE_STATUS_CHOICES,
        default='approved',
        verbose_name='Governance status',
    )
    merged_to = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='merged_items',
        verbose_name='Merged to',
    )
    source = models.CharField(max_length=40, blank=True, default='manual', verbose_name='Source')
    sort_order = models.IntegerField(default=0, verbose_name='Sort order')
    is_active = models.BooleanField(default=True, verbose_name='Active')
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_app_semantic_dictionaries',
        verbose_name='Created by',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    class Meta:
        db_table = 'app_semantic_dictionaries'
        verbose_name = 'APP semantic dictionary'
        verbose_name_plural = 'APP semantic dictionaries'
        ordering = ['category', 'sort_order', 'value']
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'category', 'value'],
                name='uniq_app_semantic_dict_project_category_value',
            )
        ]
        indexes = [
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['project', 'category']),
            models.Index(fields=['governance_status', 'category']),
        ]

    def __str__(self):
        scope = self.project.name if self.project_id else 'global'
        return f"{scope}/{self.category}/{self.value}"


class AppComponent(models.Model):
    """APP UI组件定义, 用于UI场景编排与校验"""
    name = models.CharField(max_length=100, verbose_name='组件名称')
    type = models.CharField(max_length=50, unique=True, verbose_name='组件类型')
    category = models.CharField(max_length=50, blank=True, default='', verbose_name='类别')
    description = models.TextField(blank=True, default='', verbose_name='描述')
    schema = models.JSONField(default=dict, verbose_name='配置Schema')
    default_config = models.JSONField(default=dict, verbose_name='默认配置')
    enabled = models.BooleanField(default=True, verbose_name='是否启用')
    sort_order = models.IntegerField(default=0, verbose_name='排序')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'app_components'
        verbose_name = 'APP组件定义'
        verbose_name_plural = 'APP组件定义'
        ordering = ['sort_order', '-updated_at']

    def __str__(self):
        return f"{self.name} ({self.type})"


class AppCustomComponent(models.Model):
    """APP UI自定义组件定义, 由基础组件组合而成"""
    name = models.CharField(max_length=100, verbose_name='组件名称')
    type = models.CharField(max_length=50, unique=True, verbose_name='组件类型')
    description = models.TextField(blank=True, default='', verbose_name='描述')
    schema = models.JSONField(default=dict, verbose_name='参数Schema')
    default_config = models.JSONField(default=dict, verbose_name='默认参数')
    steps = models.JSONField(default=list, verbose_name='组合步骤')
    enabled = models.BooleanField(default=True, verbose_name='是否启用')
    sort_order = models.IntegerField(default=0, verbose_name='排序')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'app_custom_components'
        verbose_name = 'APP自定义组件'
        verbose_name_plural = 'APP自定义组件'
        ordering = ['sort_order', '-updated_at']

    def __str__(self):
        return f"{self.name} ({self.type})"


class AppComponentPackage(models.Model):
    """APP UI组件包(用于导入/安装组件定义)"""
    SOURCE_CHOICES = [
        ('upload', '上传'),
        ('market', '市场'),
        ('local', '本地'),
    ]

    name = models.CharField(max_length=100, verbose_name='包名称')
    version = models.CharField(max_length=50, blank=True, default='', verbose_name='版本')
    description = models.TextField(blank=True, default='', verbose_name='描述')
    author = models.CharField(max_length=100, blank=True, default='', verbose_name='作者')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='upload', verbose_name='来源')
    manifest = models.JSONField(default=dict, verbose_name='包清单')
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='created_app_packages',
        verbose_name='创建人'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'app_component_packages'
        verbose_name = 'APP组件包'
        verbose_name_plural = 'APP组件包'
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.name} ({self.version})"


class AppPackage(models.Model):
    """应用包名管理"""
    
    name = models.CharField(
        max_length=100,
        verbose_name='应用名称',
        help_text='友好的应用名称，如：Android设置'
    )
    
    package_name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name='应用包名',
        help_text='Android包名，如：com.android.settings'
    )
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_app_package_names',
        verbose_name='创建人'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间'
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='更新时间'
    )
    
    class Meta:
        db_table = 'app_packages'
        verbose_name = 'APP应用包名'
        verbose_name_plural = 'APP应用包名管理'
        ordering = ['name']
        indexes = [
            models.Index(fields=['package_name']),
            models.Index(fields=['name']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.package_name})"


class AppTestSuite(models.Model):
    """APP测试套件"""
    EXECUTION_STATUS_CHOICES = [
        ('not_run', '未执行'),
        ('running', '执行中'),
        ('completed', '已完成'),
        ('error', '执行异常'),
        ('stopped', '已停止'),
    ]
    EXECUTION_RESULT_CHOICES = [
        ('passed', '通过'),
        ('failed', '失败'),
        ('skipped', '跳过'),
    ]

    project = models.ForeignKey(
        AppProject, on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='test_suites', verbose_name='所属项目'
    )
    name = models.CharField(max_length=200, verbose_name='套件名称')
    description = models.TextField(blank=True, default='', verbose_name='套件描述')
    test_cases = models.ManyToManyField(
        'AppTestCase',
        through='AppTestSuiteCase',
        verbose_name='测试用例',
        blank=True
    )

    # 执行统计
    execution_status = models.CharField(
        max_length=20,
        choices=EXECUTION_STATUS_CHOICES,
        default='not_run',
        verbose_name='执行状态'
    )
    execution_result = models.CharField(
        max_length=20,
        choices=EXECUTION_RESULT_CHOICES,
        null=True,
        blank=True,
        default=None,
        verbose_name='测试结果'
    )
    passed_count = models.IntegerField(default=0, verbose_name='通过用例数')
    failed_count = models.IntegerField(default=0, verbose_name='失败用例数')
    last_run_at = models.DateTimeField(null=True, blank=True, verbose_name='最后执行时间')

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_app_test_suites',
        verbose_name='创建人'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'app_test_suites'
        verbose_name = 'APP测试套件'
        verbose_name_plural = 'APP测试套件'
        ordering = ['-updated_at']

    def __str__(self):
        return self.name

    @property
    def test_case_count(self):
        return self.suite_cases.count()


class AppTestSuiteCase(models.Model):
    """APP测试套件与用例的关联模型"""
    test_suite = models.ForeignKey(
        AppTestSuite,
        on_delete=models.CASCADE,
        related_name='suite_cases',
        verbose_name='测试套件'
    )
    test_case = models.ForeignKey(
        'AppTestCase',
        on_delete=models.CASCADE,
        related_name='suite_memberships',
        verbose_name='测试用例'
    )
    order = models.IntegerField(default=0, verbose_name='执行顺序')

    class Meta:
        db_table = 'app_test_suite_cases'
        verbose_name = 'APP套件用例关联'
        verbose_name_plural = 'APP套件用例关联'
        ordering = ['order']
        unique_together = ['test_suite', 'test_case']

    def __str__(self):
        return f'{self.test_suite.name} - {self.test_case.name}'


class AppTestCaseFolder(models.Model):
    """APP automated test case business folder."""

    project = models.ForeignKey(
        AppProject,
        on_delete=models.CASCADE,
        related_name='test_case_folders',
        verbose_name='所属项目'
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='父目录'
    )
    name = models.CharField(max_length=120, verbose_name='目录名称')
    description = models.TextField(blank=True, default='', verbose_name='目录说明')
    order = models.IntegerField(default=0, verbose_name='排序')
    level = models.IntegerField(default=1, verbose_name='层级')
    is_system = models.BooleanField(default=False, verbose_name='系统目录')
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_app_test_case_folders',
        verbose_name='创建人'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'app_test_case_folders'
        verbose_name = 'APP用例业务目录'
        verbose_name_plural = 'APP用例业务目录'
        ordering = ['project_id', 'parent_id', 'order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'parent', 'name'],
                name='uniq_app_case_folder_project_parent_name',
            ),
        ]
        indexes = [
            models.Index(fields=['project', 'parent']),
            models.Index(fields=['project', 'level']),
        ]

    def save(self, *args, **kwargs):
        self.level = (self.parent.level + 1) if self.parent else 1
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class AppTestCaseTag(models.Model):
    """Project-scoped controlled tag for APP test case governance."""

    project = models.ForeignKey(
        AppProject,
        on_delete=models.CASCADE,
        related_name='test_case_tags',
        verbose_name='所属项目'
    )
    name = models.CharField(max_length=80, verbose_name='标签名称')
    color = models.CharField(max_length=20, blank=True, default='', verbose_name='标签颜色')
    description = models.TextField(blank=True, default='', verbose_name='标签说明')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_app_test_case_tags',
        verbose_name='创建人'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'app_test_case_tags'
        verbose_name = 'APP用例标签'
        verbose_name_plural = 'APP用例标签'
        ordering = ['project_id', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'name'],
                name='uniq_app_case_tag_project_name',
            ),
        ]
        indexes = [
            models.Index(fields=['project', 'is_active']),
        ]

    def __str__(self):
        return self.name


class AppTestCase(models.Model):
    """APP测试用例"""
    CASE_TYPE_CHOICES = [
        ('smoke', '冒烟'),
        ('regression', '回归'),
        ('core', '核心链路'),
        ('negative', '异常场景'),
        ('special', '专项'),
    ]
    PRIORITY_CHOICES = [
        ('P0', 'P0'),
        ('P1', 'P1'),
        ('P2', 'P2'),
        ('P3', 'P3'),
    ]
    LIFECYCLE_CHOICES = [
        ('draft', '草稿'),
        ('active', '可用'),
        ('maintenance', '维护中'),
        ('deprecated', '已废弃'),
    ]
    SOURCE_CHOICES = [
        ('manual', '人工创建'),
        ('recording', '录制生成'),
        ('ai_generated', 'AI生成'),
        ('ai_exploration', 'AI探索转化'),
        ('imported', '导入'),
    ]
    DATA_IMPACT_CHOICES = [
        ('readonly', '只读'),
        ('mutates', '会改数据'),
        ('self_healing', '可闭环恢复'),
        ('destructive', '破坏性'),
    ]

    project = models.ForeignKey(
        AppProject, on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='test_cases', verbose_name='所属项目'
    )
    folder = models.ForeignKey(
        AppTestCaseFolder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='test_cases',
        verbose_name='业务目录'
    )
    name = models.CharField(max_length=200, verbose_name='用例名称')
    description = models.TextField(blank=True, default='', verbose_name='用例描述')
    app_package = models.ForeignKey(
        AppPackage, 
        on_delete=models.CASCADE, 
        related_name='test_cases',
        null=True,
        blank=True,
        verbose_name='应用包名'
    )
    ui_flow = models.JSONField(default=dict, verbose_name='UI流程定义', help_text='UI Flow JSON配置')
    variables = models.JSONField(default=list, verbose_name='变量定义', help_text='测试变量列表')
    
    # 用例配置
    timeout = models.IntegerField(default=300, verbose_name='超时时间(秒)', help_text='默认5分钟')
    retry_count = models.IntegerField(default=0, verbose_name='失败重试次数')

    # 资产治理
    case_type = models.CharField(
        max_length=30,
        choices=CASE_TYPE_CHOICES,
        default='regression',
        verbose_name='用例类型'
    )
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='P1',
        verbose_name='优先级'
    )
    lifecycle_status = models.CharField(
        max_length=30,
        choices=LIFECYCLE_CHOICES,
        default='active',
        verbose_name='生命周期'
    )
    data_impact = models.CharField(
        max_length=30,
        choices=DATA_IMPACT_CHOICES,
        default='readonly',
        verbose_name='数据影响'
    )
    source = models.CharField(
        max_length=30,
        choices=SOURCE_CHOICES,
        default='manual',
        verbose_name='来源'
    )
    maintainer = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='maintained_app_test_cases',
        verbose_name='维护人'
    )
    tags = models.ManyToManyField(
        AppTestCaseTag,
        blank=True,
        related_name='test_cases',
        verbose_name='标签'
    )
    
    # 元数据
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_app_test_cases',
        verbose_name='创建人'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        db_table = 'app_test_cases'
        verbose_name = 'APP测试用例'
        verbose_name_plural = 'APP测试用例'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['project', 'folder']),
            models.Index(fields=['project', 'priority']),
            models.Index(fields=['project', 'lifecycle_status']),
            models.Index(fields=['project', 'case_type']),
            models.Index(fields=['maintainer']),
        ]
    
    def __str__(self):
        return self.name


class AppTestExecution(models.Model):
    """APP测试执行记录"""
    STATUS_CHOICES = [
        (ExecutionStatus.PENDING, '等待中'),
        (ExecutionStatus.RUNNING, '执行中'),
        (ExecutionStatus.COMPLETED, '已完成'),
        (ExecutionStatus.ERROR, '执行异常'),
        (ExecutionStatus.STOPPED, '已停止'),
    ]

    RESULT_CHOICES = [
        (ExecutionResult.PASSED, '通过'),
        (ExecutionResult.FAILED, '失败'),
        (ExecutionResult.SKIPPED, '跳过'),
    ]
    EXECUTION_MODE_CHOICES = [
        ('server', '服务器执行'),
        ('agent', '本地Agent执行'),
    ]
    
    test_case = models.ForeignKey(
        AppTestCase, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='executions', 
        verbose_name='测试用例'
    )
    test_suite = models.ForeignKey(
        AppTestSuite,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='executions',
        verbose_name='所属套件'
    )
    device = models.ForeignKey(
        AppDevice, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='executions', 
        verbose_name='执行设备'
    )
    user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='app_test_executions', 
        verbose_name='执行用户'
    )
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default=ExecutionStatus.PENDING, 
        verbose_name='执行状态'
    )
    result = models.CharField(
        max_length=20,
        choices=RESULT_CHOICES,
        null=True,
        blank=True,
        default=None,
        verbose_name='测试结果'
    )
    task_id = models.CharField(
        max_length=255, 
        blank=True, 
        default='', 
        verbose_name='Celery任务ID', 
        help_text='用于停止任务'
    )
    progress = models.IntegerField(default=0, verbose_name='执行进度(0-100)')
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='开始时间')
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name='结束时间')
    duration = models.FloatField(default=0, verbose_name='执行时长(秒)')
    report_path = models.CharField(max_length=500, blank=True, default='', verbose_name='Allure报告路径')
    error_message = models.TextField(blank=True, default='', verbose_name='错误信息')
    execution_mode = models.CharField(
        max_length=20,
        choices=EXECUTION_MODE_CHOICES,
        default='server',
        verbose_name='执行模式'
    )
    agent = models.ForeignKey(
        AppExecutionAgent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='executions',
        verbose_name='执行Agent'
    )
    agent_claimed_at = models.DateTimeField(null=True, blank=True, verbose_name='Agent领取时间')
    agent_last_heartbeat_at = models.DateTimeField(null=True, blank=True, verbose_name='Agent最近回报时间')
    agent_message = models.CharField(max_length=500, blank=True, default='', verbose_name='Agent执行消息')
    agent_payload = models.JSONField(default=dict, blank=True, verbose_name='Agent回传数据')
    performance_metrics = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='APP性能指标'
    )
    
    # 执行结果统计
    total_steps = models.IntegerField(default=0, verbose_name='总步骤数')
    passed_steps = models.IntegerField(default=0, verbose_name='通过步骤数')
    failed_steps = models.IntegerField(default=0, verbose_name='失败步骤数')
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        db_table = 'app_test_executions'
        verbose_name = 'APP测试执行记录'
        verbose_name_plural = 'APP测试执行记录'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['execution_mode', 'status']),
            models.Index(fields=['agent', 'status']),
        ]
    
    def __str__(self):
        return f"{self.test_case.name} - {self.get_status_display()}"
    
    @property
    def case_name(self):
        """用例名称"""
        return self.test_case.name if self.test_case else ''
    
    @property
    def device_name(self):
        """设备名称"""
        return self.device.device_id if self.device else ''
    
    @property
    def user_name(self):
        """用户名"""
        return self.user.username if self.user else ''
    
    @property
    def pass_rate(self):
        """通过率"""
        if self.total_steps == 0:
            return 0
        return round((self.passed_steps / self.total_steps) * 100, 2)


class AppExplorationTask(models.Model):
    """APP exploratory testing task.

    This is intentionally separated from deterministic test executions. The
    exploration flow is non-deterministic and is used to discover risks and
    produce reusable path drafts.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('error', 'Error'),
        ('stopped', 'Stopped'),
    ]
    RESULT_CHOICES = [
        ('passed', 'No issue found'),
        ('warning', 'Issues found'),
        ('failed', 'Execution failed'),
    ]

    project = models.ForeignKey(
        AppProject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exploration_tasks',
        verbose_name='Project',
    )
    app_package = models.ForeignKey(
        AppPackage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exploration_tasks',
        verbose_name='App package',
    )
    device = models.ForeignKey(
        AppDevice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exploration_tasks',
        verbose_name='Device',
    )
    name = models.CharField(max_length=200, verbose_name='Task name')
    objective = models.TextField(blank=True, default='', verbose_name='Objective')
    start_note = models.TextField(blank=True, default='', verbose_name='Start note')
    entry_keywords = models.JSONField(default=list, blank=True, verbose_name='Entry keywords')
    start_actions = models.JSONField(default=list, blank=True, verbose_name='Start navigation actions')
    max_steps = models.IntegerField(default=20, verbose_name='Max steps')
    max_duration = models.IntegerField(default=300, verbose_name='Max duration seconds')
    blacklist_keywords = models.JSONField(default=list, blank=True, verbose_name='Blacklist keywords')
    strategy = models.CharField(max_length=50, default='rule_mvp', verbose_name='Strategy')
    source_task = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='derived_tasks',
        verbose_name='Source exploration task',
    )
    source_type = models.CharField(max_length=50, blank=True, default='', verbose_name='Source type')
    source_summary = models.JSONField(default=dict, blank=True, verbose_name='Source summary')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Status')
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, null=True, blank=True, default=None, verbose_name='Result')
    task_id = models.CharField(max_length=255, blank=True, default='', verbose_name='Celery task ID')
    progress = models.IntegerField(default=0, verbose_name='Progress')
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='Started at')
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name='Finished at')
    duration = models.FloatField(default=0, verbose_name='Duration seconds')
    total_steps = models.IntegerField(default=0, verbose_name='Total steps')
    explored_pages = models.IntegerField(default=0, verbose_name='Explored pages')
    issue_count = models.IntegerField(default=0, verbose_name='Issue count')
    summary = models.JSONField(default=dict, blank=True, verbose_name='Summary')
    error_message = models.TextField(blank=True, default='', verbose_name='Error message')

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_app_exploration_tasks',
        verbose_name='Created by',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    class Meta:
        db_table = 'app_exploration_tasks'
        verbose_name = 'APP exploration task'
        verbose_name_plural = 'APP exploration tasks'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['project']),
        ]

    def __str__(self):
        return self.name

    @property
    def project_name(self):
        return self.project.name if self.project else ''

    @property
    def package_name(self):
        return self.app_package.package_name if self.app_package else ''

    @property
    def device_name(self):
        return (self.device.name or self.device.device_id) if self.device else ''

    @property
    def created_by_name(self):
        return self.created_by.username if self.created_by else ''

    @property
    def source_task_name(self):
        return self.source_task.name if self.source_task else ''

    def latest_run(self):
        return self.runs.order_by('-created_at').first()

    def report_steps(self):
        latest_run = self.latest_run()
        if latest_run:
            return self.steps.filter(run=latest_run).order_by('step_index')
        return self.steps.filter(run__isnull=True).order_by('step_index')


class AppExplorationRun(models.Model):
    """One execution batch for an APP exploration task."""

    STATUS_CHOICES = AppExplorationTask.STATUS_CHOICES
    RESULT_CHOICES = AppExplorationTask.RESULT_CHOICES

    task = models.ForeignKey(
        AppExplorationTask,
        on_delete=models.CASCADE,
        related_name='runs',
        verbose_name='Exploration task',
    )
    device = models.ForeignKey(
        AppDevice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exploration_runs',
        verbose_name='Device',
    )
    app_package = models.ForeignKey(
        AppPackage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exploration_runs',
        verbose_name='App package',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Status')
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, null=True, blank=True, default=None, verbose_name='Result')
    celery_task_id = models.CharField(max_length=255, blank=True, default='', verbose_name='Celery task ID')
    strategy = models.CharField(max_length=50, blank=True, default='', verbose_name='Strategy')
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='Started at')
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name='Finished at')
    duration = models.FloatField(default=0, verbose_name='Duration seconds')
    total_steps = models.IntegerField(default=0, verbose_name='Total steps')
    explored_pages = models.IntegerField(default=0, verbose_name='Explored pages')
    issue_count = models.IntegerField(default=0, verbose_name='Issue count')
    summary = models.JSONField(default=dict, blank=True, verbose_name='Summary')
    error_message = models.TextField(blank=True, default='', verbose_name='Error message')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    class Meta:
        db_table = 'app_exploration_runs'
        verbose_name = 'APP exploration run'
        verbose_name_plural = 'APP exploration runs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['task', '-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['strategy']),
        ]

    def __str__(self):
        return f'{self.task_id} run #{self.id or "new"}'


class AppExplorationStep(models.Model):
    """Single step generated by an exploratory testing task."""

    ACTION_CHOICES = [
        ('tap', 'Tap'),
        ('swipe', 'Swipe'),
        ('back', 'Back'),
        ('wait', 'Wait'),
        ('stop', 'Stop'),
    ]

    task = models.ForeignKey(
        AppExplorationTask,
        on_delete=models.CASCADE,
        related_name='steps',
        verbose_name='Task',
    )
    run = models.ForeignKey(
        AppExplorationRun,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='steps',
        verbose_name='Execution run',
    )
    step_index = models.IntegerField(verbose_name='Step index')
    action_type = models.CharField(max_length=20, choices=ACTION_CHOICES, verbose_name='Action type')
    action_label = models.CharField(max_length=255, blank=True, default='', verbose_name='Action label')
    target_text = models.CharField(max_length=255, blank=True, default='', verbose_name='Target text')
    target_resource_id = models.CharField(max_length=255, blank=True, default='', verbose_name='Target resource id')
    target_class = models.CharField(max_length=255, blank=True, default='', verbose_name='Target class')
    bounds = models.CharField(max_length=100, blank=True, default='', verbose_name='Bounds')
    x = models.IntegerField(null=True, blank=True, verbose_name='X')
    y = models.IntegerField(null=True, blank=True, verbose_name='Y')
    before_activity = models.CharField(max_length=255, blank=True, default='', verbose_name='Before activity')
    after_activity = models.CharField(max_length=255, blank=True, default='', verbose_name='After activity')
    before_signature = models.CharField(max_length=64, blank=True, default='', verbose_name='Before signature')
    after_signature = models.CharField(max_length=64, blank=True, default='', verbose_name='After signature')
    changed = models.BooleanField(default=False, verbose_name='Page changed')
    before_screenshot = models.CharField(max_length=500, blank=True, default='', verbose_name='Before screenshot')
    after_screenshot = models.CharField(max_length=500, blank=True, default='', verbose_name='After screenshot')
    page_source_path = models.CharField(max_length=500, blank=True, default='', verbose_name='Page source path')
    issue_type = models.CharField(max_length=50, blank=True, default='', verbose_name='Issue type')
    issue_message = models.TextField(blank=True, default='', verbose_name='Issue message')
    logcat_excerpt = models.TextField(blank=True, default='', verbose_name='Logcat excerpt')
    raw = models.JSONField(default=dict, blank=True, verbose_name='Raw data')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')

    class Meta:
        db_table = 'app_exploration_steps'
        verbose_name = 'APP exploration step'
        verbose_name_plural = 'APP exploration steps'
        ordering = ['task_id', 'run_id', 'step_index']
        unique_together = ['task', 'run', 'step_index']
        indexes = [
            models.Index(fields=['task', 'step_index']),
            models.Index(fields=['run', 'step_index']),
            models.Index(fields=['issue_type']),
        ]

    def __str__(self):
        return f'{self.task_id} #{self.step_index} {self.action_type}'


class AppInspectionTargetResult(models.Model):
    """Evidence and result for one target in controlled inspection mode."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('found_effective', 'Found and effective'),
        ('found_unconfirmed', 'Found but unconfirmed'),
        ('not_found', 'Not found'),
        ('risk_skipped', 'Risk skipped'),
        ('anchor_recovery_failed', 'Anchor recovery failed'),
        ('error', 'Error'),
    ]
    REVIEW_RESOLUTION_CHOICES = [
        ('valid_issue', 'Valid issue'),
        ('normal_behavior', 'Normal behavior'),
        ('element_needs_update', 'Element needs update'),
        ('target_should_remove', 'Target should remove'),
        ('wrong_start_page', 'Wrong start page'),
        ('rule_exception', 'Rule exception'),
    ]

    task = models.ForeignKey(
        AppExplorationTask,
        on_delete=models.CASCADE,
        related_name='inspection_target_results',
        verbose_name='Exploration task',
    )
    run = models.ForeignKey(
        AppExplorationRun,
        on_delete=models.CASCADE,
        related_name='target_results',
        verbose_name='Execution run',
    )
    step = models.ForeignKey(
        AppExplorationStep,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inspection_results',
        verbose_name='Evidence step',
    )
    target_name = models.CharField(max_length=255, verbose_name='Target name')
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default='pending', verbose_name='Status')
    action_type = models.CharField(max_length=30, blank=True, default='tap', verbose_name='Action type')
    bounds = models.CharField(max_length=100, blank=True, default='', verbose_name='Bounds')
    x = models.IntegerField(null=True, blank=True, verbose_name='X')
    y = models.IntegerField(null=True, blank=True, verbose_name='Y')
    before_activity = models.CharField(max_length=255, blank=True, default='', verbose_name='Before activity')
    after_activity = models.CharField(max_length=255, blank=True, default='', verbose_name='After activity')
    before_signature = models.CharField(max_length=64, blank=True, default='', verbose_name='Before signature')
    after_signature = models.CharField(max_length=64, blank=True, default='', verbose_name='After signature')
    changed = models.BooleanField(default=False, verbose_name='State changed')
    before_screenshot = models.CharField(max_length=500, blank=True, default='', verbose_name='Before screenshot')
    after_screenshot = models.CharField(max_length=500, blank=True, default='', verbose_name='After screenshot')
    evidence = models.JSONField(default=dict, blank=True, verbose_name='Evidence')
    risk = models.JSONField(default=dict, blank=True, verbose_name='Risk')
    error_message = models.TextField(blank=True, default='', verbose_name='Error message')
    review_resolution = models.CharField(
        max_length=40,
        choices=REVIEW_RESOLUTION_CHOICES,
        blank=True,
        default='',
        verbose_name='Review resolution',
    )
    review_note = models.TextField(blank=True, default='', verbose_name='Review note')
    review_context = models.JSONField(default=dict, blank=True, verbose_name='Review context')
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_app_inspection_targets',
        verbose_name='Reviewed by',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name='Reviewed at')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    class Meta:
        db_table = 'app_inspection_target_results'
        verbose_name = 'APP inspection target result'
        verbose_name_plural = 'APP inspection target results'
        ordering = ['run_id', 'id']
        indexes = [
            models.Index(fields=['task', 'run']),
            models.Index(fields=['status']),
            models.Index(fields=['target_name']),
            models.Index(fields=['review_resolution']),
        ]

    def __str__(self):
        return f'{self.target_name} - {self.status}'


class AppInspectionReviewRule(models.Model):
    """Reusable human review rule for recurring target-inspection conclusions."""

    RESOLUTION_CHOICES = AppInspectionTargetResult.REVIEW_RESOLUTION_CHOICES

    task = models.ForeignKey(
        AppExplorationTask,
        on_delete=models.CASCADE,
        related_name='inspection_review_rules',
        verbose_name='Exploration task',
    )
    target_name = models.CharField(max_length=255, verbose_name='Target name')
    status = models.CharField(max_length=40, blank=True, default='', verbose_name='Matched status')
    resolution = models.CharField(max_length=40, choices=RESOLUTION_CHOICES, verbose_name='Review resolution')
    note = models.TextField(blank=True, default='', verbose_name='Review note')
    enabled = models.BooleanField(default=True, verbose_name='Enabled')
    created_from_result = models.ForeignKey(
        AppInspectionTargetResult,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_review_rules',
        verbose_name='Created from target result',
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_app_inspection_review_rules',
        verbose_name='Created by',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    class Meta:
        db_table = 'app_inspection_review_rules'
        verbose_name = 'APP inspection review rule'
        verbose_name_plural = 'APP inspection review rules'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['task', 'target_name']),
            models.Index(fields=['resolution']),
            models.Index(fields=['enabled']),
        ]

    def __str__(self):
        return f'{self.target_name} - {self.resolution}'


class AppPageNode(models.Model):
    """Persistent page node discovered during APP exploration."""

    project = models.ForeignKey(
        AppProject,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='page_nodes',
        verbose_name='Project',
    )
    app_package = models.ForeignKey(
        AppPackage,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='page_nodes',
        verbose_name='App package',
    )
    platform = models.CharField(max_length=20, default='android', verbose_name='Platform')
    app_identifier = models.CharField(max_length=255, blank=True, default='', verbose_name='App identifier')
    app_version = models.CharField(max_length=100, blank=True, default='', verbose_name='App version')
    activity = models.CharField(max_length=255, blank=True, default='', verbose_name='Activity')
    page_signature = models.CharField(max_length=64, verbose_name='Page signature')
    semantic_signature = models.CharField(max_length=64, blank=True, default='', verbose_name='Semantic signature')
    business_name = models.CharField(max_length=255, blank=True, default='', verbose_name='Business page name')
    title = models.CharField(max_length=255, blank=True, default='', verbose_name='Page title')
    representative_screenshot = models.CharField(max_length=500, blank=True, default='', verbose_name='Representative screenshot')
    screen_size = models.JSONField(default=list, blank=True, verbose_name='Screen size')
    first_seen_run = models.ForeignKey(
        AppExplorationRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='first_seen_page_nodes',
        verbose_name='First seen run',
    )
    last_seen_run = models.ForeignKey(
        AppExplorationRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='last_seen_page_nodes',
        verbose_name='Last seen run',
    )
    visit_count = models.IntegerField(default=0, verbose_name='Visit count')
    raw = models.JSONField(default=dict, blank=True, verbose_name='Raw page data')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    class Meta:
        db_table = 'app_page_nodes'
        verbose_name = 'APP page node'
        verbose_name_plural = 'APP page nodes'
        unique_together = ['project', 'app_package', 'platform', 'page_signature']
        indexes = [
            models.Index(fields=['project', 'app_package', 'platform']),
            models.Index(fields=['page_signature']),
            models.Index(fields=['semantic_signature']),
            models.Index(fields=['activity']),
        ]

    def __str__(self):
        return self.business_name or self.title or self.activity or self.page_signature


class AppPageElement(models.Model):
    """Control snapshot discovered on a persistent page node."""

    page = models.ForeignKey(
        AppPageNode,
        on_delete=models.CASCADE,
        related_name='elements',
        verbose_name='Page node',
    )
    semantic_element = models.ForeignKey(
        AppElement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='page_element_snapshots',
        verbose_name='Linked semantic element',
    )
    element_signature = models.CharField(max_length=64, verbose_name='Element signature')
    text = models.CharField(max_length=255, blank=True, default='', verbose_name='Text')
    content_desc = models.CharField(max_length=255, blank=True, default='', verbose_name='Content desc')
    resource_id = models.CharField(max_length=255, blank=True, default='', verbose_name='Resource id')
    class_name = models.CharField(max_length=255, blank=True, default='', verbose_name='Class name')
    role = models.CharField(max_length=80, blank=True, default='', verbose_name='Control role')
    bounds = models.CharField(max_length=100, blank=True, default='', verbose_name='Bounds')
    normalized_bounds = models.JSONField(default=dict, blank=True, verbose_name='Normalized bounds')
    clickable = models.BooleanField(default=False, verbose_name='Clickable')
    enabled = models.BooleanField(default=True, verbose_name='Enabled')
    risk_level = models.CharField(max_length=30, blank=True, default='', verbose_name='Risk level')
    first_seen_run = models.ForeignKey(
        AppExplorationRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='first_seen_page_elements',
        verbose_name='First seen run',
    )
    last_seen_run = models.ForeignKey(
        AppExplorationRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='last_seen_page_elements',
        verbose_name='Last seen run',
    )
    seen_count = models.IntegerField(default=0, verbose_name='Seen count')
    raw = models.JSONField(default=dict, blank=True, verbose_name='Raw element data')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    class Meta:
        db_table = 'app_page_elements'
        verbose_name = 'APP page element'
        verbose_name_plural = 'APP page elements'
        unique_together = ['page', 'element_signature']
        indexes = [
            models.Index(fields=['page', 'role']),
            models.Index(fields=['resource_id']),
            models.Index(fields=['text']),
            models.Index(fields=['risk_level']),
        ]

    def __str__(self):
        return self.text or self.content_desc or self.resource_id or self.element_signature


class AppPageTransition(models.Model):
    """Observed transition between two page nodes."""

    project = models.ForeignKey(
        AppProject,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='page_transitions',
        verbose_name='Project',
    )
    app_package = models.ForeignKey(
        AppPackage,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='page_transitions',
        verbose_name='App package',
    )
    from_page = models.ForeignKey(
        AppPageNode,
        on_delete=models.CASCADE,
        related_name='outgoing_transitions',
        verbose_name='From page',
    )
    to_page = models.ForeignKey(
        AppPageNode,
        on_delete=models.CASCADE,
        related_name='incoming_transitions',
        verbose_name='To page',
    )
    trigger_element = models.ForeignKey(
        AppPageElement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='triggered_transitions',
        verbose_name='Trigger element',
    )
    action_type = models.CharField(max_length=30, default='tap', verbose_name='Action type')
    trigger_text = models.CharField(max_length=255, blank=True, default='', verbose_name='Trigger text')
    trigger_resource_id = models.CharField(max_length=255, blank=True, default='', verbose_name='Trigger resource id')
    trigger_bounds = models.CharField(max_length=100, blank=True, default='', verbose_name='Trigger bounds')
    success_count = models.IntegerField(default=0, verbose_name='Success count')
    failure_count = models.IntegerField(default=0, verbose_name='Failure count')
    confidence = models.FloatField(default=0, verbose_name='Confidence')
    last_seen_run = models.ForeignKey(
        AppExplorationRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='last_seen_page_transitions',
        verbose_name='Last seen run',
    )
    raw = models.JSONField(default=dict, blank=True, verbose_name='Raw transition data')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    class Meta:
        db_table = 'app_page_transitions'
        verbose_name = 'APP page transition'
        verbose_name_plural = 'APP page transitions'
        unique_together = ['from_page', 'to_page', 'action_type', 'trigger_text', 'trigger_resource_id', 'trigger_bounds']
        indexes = [
            models.Index(fields=['project', 'app_package']),
            models.Index(fields=['from_page', 'to_page']),
            models.Index(fields=['confidence']),
        ]

    def __str__(self):
        return f'{self.from_page_id} -> {self.to_page_id} ({self.action_type})'


class AppScheduledTask(models.Model):
    """APP自动化定时任务"""
    TASK_TYPE_CHOICES = [
        ('TEST_SUITE', '测试套件执行'),
        ('TEST_CASE', '测试用例执行'),
    ]
    STATUS_CHOICES = [
        ('ACTIVE', '激活'),
        ('PAUSED', '暂停'),
        ('COMPLETED', '已完成'),
        ('FAILED', '失败'),
    ]
    TRIGGER_TYPE_CHOICES = [
        ('CRON', 'Cron表达式'),
        ('INTERVAL', '固定间隔'),
        ('ONCE', '单次执行'),
    ]
    NOTIFICATION_TYPE_CHOICES = [
        ('email', '邮箱通知'),
        ('webhook', 'Webhook机器人'),
        ('both', '两者都发送'),
    ]

    project = models.ForeignKey(
        'AppProject', on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='scheduled_tasks', verbose_name='所属项目'
    )
    name = models.CharField(max_length=200, verbose_name='任务名称')
    description = models.TextField(blank=True, default='', verbose_name='任务描述')
    task_type = models.CharField(max_length=20, choices=TASK_TYPE_CHOICES, verbose_name='任务类型')
    trigger_type = models.CharField(max_length=20, choices=TRIGGER_TYPE_CHOICES, verbose_name='触发器类型')

    # 调度配置
    cron_expression = models.CharField(max_length=100, blank=True, default='', verbose_name='Cron表达式')
    interval_seconds = models.IntegerField(null=True, blank=True, verbose_name='间隔秒数')
    execute_at = models.DateTimeField(null=True, blank=True, verbose_name='执行时间')

    # APP 特有配置
    device = models.ForeignKey(
        AppDevice, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='scheduled_tasks', verbose_name='执行设备'
    )
    app_package = models.ForeignKey(
        AppPackage, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='scheduled_tasks', verbose_name='应用包名'
    )
    test_suite = models.ForeignKey(
        AppTestSuite, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='scheduled_tasks', verbose_name='测试套件'
    )
    test_case = models.ForeignKey(
        AppTestCase, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='scheduled_tasks', verbose_name='测试用例'
    )

    # 通知配置
    notify_on_success = models.BooleanField(default=False, verbose_name='成功时通知')
    notify_on_failure = models.BooleanField(default=False, verbose_name='失败时通知')
    notification_type = models.CharField(
        max_length=20, blank=True, default='',
        choices=NOTIFICATION_TYPE_CHOICES, verbose_name='通知类型'
    )
    notify_emails = models.JSONField(default=list, blank=True, verbose_name='通知邮箱列表')

    # 状态与统计
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE', verbose_name='任务状态')
    last_run_time = models.DateTimeField(null=True, blank=True, verbose_name='最后运行时间')
    next_run_time = models.DateTimeField(null=True, blank=True, verbose_name='下次运行时间')
    total_runs = models.IntegerField(default=0, verbose_name='总运行次数')
    successful_runs = models.IntegerField(default=0, verbose_name='成功次数')
    failed_runs = models.IntegerField(default=0, verbose_name='失败次数')
    last_result = models.JSONField(default=dict, verbose_name='最后执行结果')
    error_message = models.TextField(blank=True, default='', verbose_name='错误信息')

    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='创建者')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'app_scheduled_tasks'
        verbose_name = 'APP定时任务'
        verbose_name_plural = 'APP定时任务'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.get_task_type_display()})"

    def calculate_next_run(self):
        from datetime import timedelta
        from croniter import croniter
        now = timezone.now()
        if self.trigger_type == 'CRON' and self.cron_expression:
            try:
                cron = croniter(self.cron_expression, now)
                return cron.get_next(type(now))
            except Exception:
                return None
        elif self.trigger_type == 'INTERVAL' and self.interval_seconds:
            return now + timedelta(seconds=self.interval_seconds)
        elif self.trigger_type == 'ONCE' and self.execute_at:
            return self.execute_at if self.execute_at > now else None
        return None

    def should_run_now(self):
        if self.status != 'ACTIVE':
            return False
        if not self.next_run_time:
            return False
        return timezone.now() >= self.next_run_time


class AppNotificationLog(models.Model):
    """APP自动化通知日志"""
    NOTIFICATION_TYPES = [
        ('task_execution', '定时任务执行'),
        ('test_suite_execution', '测试套件执行'),
        ('system_alert', '系统警告'),
        ('manual', '手动通知'),
    ]
    STATUS_CHOICES = [
        ('pending', '待发送'),
        ('sending', '发送中'),
        ('success', '发送成功'),
        ('failed', '发送失败'),
        ('cancelled', '已取消'),
    ]

    task = models.ForeignKey(
        AppScheduledTask, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='notification_logs', verbose_name='关联任务'
    )
    task_name = models.CharField(max_length=200, verbose_name='任务名称')
    task_type = models.CharField(max_length=20, blank=True, default='', verbose_name='任务类型快照')
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES, verbose_name='通知类型')
    sender_name = models.CharField(max_length=100, verbose_name='发件人姓名')
    sender_email = models.EmailField(verbose_name='发件人邮箱')
    recipient_info = models.JSONField(default=list, verbose_name='收件人信息')
    webhook_bot_info = models.JSONField(default=dict, blank=True, verbose_name='Webhook机器人信息')
    notification_content = models.TextField(verbose_name='通知内容')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='发送状态')
    error_message = models.TextField(blank=True, default='', verbose_name='错误信息')
    response_info = models.JSONField(default=dict, blank=True, verbose_name='响应信息')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name='发送时间')
    retry_count = models.IntegerField(default=0, verbose_name='重试次数')
    is_retried = models.BooleanField(default=False, verbose_name='是否已重试')

    class Meta:
        db_table = 'app_notification_logs'
        verbose_name = 'APP通知日志'
        verbose_name_plural = 'APP通知日志'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['notification_type']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.task_name} - {self.get_notification_type_display()} - {self.status}"

    def get_recipient_names(self):
        if not self.recipient_info:
            return '未知收件人'
        if isinstance(self.recipient_info, list):
            names = []
            for rec in self.recipient_info:
                email = rec.get('email', '')
                name = rec.get('name', '')
                names.append(f"{name}({email})" if name and email else (email or name or '未知'))
            return ', '.join(names)
        return '未知收件人'

    def get_retry_status(self):
        return f"已重试 {self.retry_count} 次" if self.is_retried else "未重试"
