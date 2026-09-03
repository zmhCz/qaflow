# -*- coding: utf-8 -*-
"""Tests for APP exploration execution health hints."""

from datetime import timedelta
from types import SimpleNamespace

from django.utils import timezone

from apps.app_automation.serializers import AppExplorationTaskSerializer


def _task(status, *, updated_delta=0, started_delta=0, max_duration=300, summary=None):
    now = timezone.now()
    return SimpleNamespace(
        status=status,
        updated_at=now - timedelta(seconds=updated_delta),
        created_at=now - timedelta(seconds=max(updated_delta, started_delta, 1)),
        started_at=now - timedelta(seconds=started_delta) if started_delta else None,
        max_duration=max_duration,
        summary=summary or {},
    )


def test_execution_health_marks_stale_pending_task():
    serializer = AppExplorationTaskSerializer()
    health = serializer.get_execution_health(_task('pending', updated_delta=180))

    assert health['is_active'] is True
    assert health['is_stale'] is True
    assert health['level'] == 'warning'
    assert '等待中' in health['message']


def test_execution_health_marks_running_task_over_max_duration():
    serializer = AppExplorationTaskSerializer()
    health = serializer.get_execution_health(_task('running', updated_delta=10, started_delta=500, max_duration=300))

    assert health['is_stale'] is True
    assert health['level'] == 'danger'
    assert '最大时长' in health['message']


def test_execution_health_keeps_fresh_running_task_normal():
    serializer = AppExplorationTaskSerializer()
    health = serializer.get_execution_health(_task('running', updated_delta=10, started_delta=30, max_duration=300))

    assert health['is_active'] is True
    assert health['is_stale'] is False
    assert health['level'] == 'normal'
