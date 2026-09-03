# -*- coding: utf-8 -*-
"""Agent execution helpers.

These helpers keep the first Agent implementation lightweight while giving each
queued job a stable snapshot and lease metadata.
"""
from __future__ import annotations

from django.utils import timezone


AGENT_PROTOCOL_VERSION = '2026-09-p0'
DEFAULT_LEASE_SECONDS = 90


def build_execution_snapshot(test_case, device=None, package_name=''):
    """Freeze the executable case payload at submit time."""
    resolved_package = package_name or ''
    if not resolved_package and test_case:
        if test_case.app_package:
            resolved_package = test_case.app_package.package_name
        elif test_case.project and test_case.project.android_app_package:
            resolved_package = test_case.project.android_app_package.package_name

    return {
        'protocol_version': AGENT_PROTOCOL_VERSION,
        'snapshot_at': timezone.now().isoformat(),
        'test_case': {
            'id': test_case.id if test_case else None,
            'name': test_case.name if test_case else '',
            'updated_at': test_case.updated_at.isoformat() if test_case and test_case.updated_at else '',
            'timeout': test_case.timeout if test_case else 300,
            'retry_count': test_case.retry_count if test_case else 0,
            'ui_flow': test_case.ui_flow if test_case else {},
            'variables': test_case.variables if test_case else [],
        },
        'device': {
            'id': device.id if device else None,
            'device_id': device.device_id if device else '',
            'name': device.name if device else '',
            'agent_id': device.agent.agent_id if device and device.agent else '',
        },
        'package_name': resolved_package,
    }


def lease_deadline(seconds=DEFAULT_LEASE_SECONDS):
    return timezone.now() + timezone.timedelta(seconds=seconds)
