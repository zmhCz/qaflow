from django.contrib import admin

from .models import BusinessAccount, BusinessLoadTask, DataFactoryRecord


@admin.register(DataFactoryRecord)
class DataFactoryRecordAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'tool_name', 'tool_category', 'tool_scenario', 'is_saved', 'created_at')
    list_filter = ('tool_category', 'tool_scenario', 'is_saved', 'created_at')
    search_fields = ('tool_name', 'user__username')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(BusinessAccount)
class BusinessAccountAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'environment', 'business_domain', 'account_no', 'phone',
        'user_id', 'nickname', 'status', 'locked_by', 'updated_at',
    )
    list_filter = ('environment', 'business_domain', 'status', 'created_at')
    search_fields = ('account_no', 'phone', 'user_id', 'nickname', 'purpose', 'remark')
    readonly_fields = ('created_at', 'updated_at', 'last_used_at', 'locked_at')


@admin.register(BusinessLoadTask)
class BusinessLoadTaskAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'name', 'scenario_type', 'environment', 'business_domain',
        'account_count', 'status', 'created_by', 'updated_at',
    )
    list_filter = ('scenario_type', 'environment', 'business_domain', 'status', 'created_at')
    search_fields = ('name', 'purpose')
    readonly_fields = ('created_at', 'updated_at', 'started_at', 'finished_at')
