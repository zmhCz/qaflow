# -*- coding: utf-8 -*-
"""Tests for controlled inspection target review closure."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from unittest.mock import Mock, patch

from apps.app_automation.models import (
    AppDevice,
    AppExplorationRun,
    AppExplorationStep,
    AppExplorationTask,
    AppInspectionReviewRule,
    AppInspectionTargetResult,
    AppPackage,
    AppProject,
)


class InspectionTargetReviewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='reviewer', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.project = AppProject.objects.create(name='QAFlow', owner=self.user)
        self.package = AppPackage.objects.create(
            name='Community',
            package_name='com.demo.community',
            created_by=self.user,
        )
        self.device = AppDevice.objects.create(
            device_id='device-001',
            name='Pixel',
            status='available',
            connection_type='real_device',
        )
        self.task = AppExplorationTask.objects.create(
            project=self.project,
            app_package=self.package,
            device=self.device,
            name='社区首页 - 目标巡检',
            strategy='target_inspection',
            status='completed',
            created_by=self.user,
        )
        self.run = AppExplorationRun.objects.create(
            task=self.task,
            device=self.device,
            app_package=self.package,
            status='completed',
            result='warning',
            strategy='target_inspection',
        )
        self.step = AppExplorationStep.objects.create(
            task=self.task,
            run=self.run,
            step_index=1,
            action_type='tap',
            target_text='消息',
            bounds='[10,10][100,100]',
        )
        self.target_result = AppInspectionTargetResult.objects.create(
            task=self.task,
            run=self.run,
            step=self.step,
            target_name='消息 Tab',
            status='found_unconfirmed',
            bounds='[10,10][100,100]',
            x=55,
            y=55,
            before_screenshot='before.png',
            after_screenshot='after.png',
        )

    def test_review_target_persists_manual_conclusion_and_rule(self):
        response = self.client.post(
            f'/api/app-automation/exploration-tasks/{self.task.id}/review-target/',
            {
                'target_result_id': self.target_result.id,
                'resolution': 'normal_behavior',
                'note': 'Switch 状态变化即可，不要求页面跳转。',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.target_result.refresh_from_db()
        self.assertEqual(self.target_result.review_resolution, 'normal_behavior')
        self.assertEqual(self.target_result.reviewed_by, self.user)
        self.assertIn('Switch 状态变化', self.target_result.review_note)
        self.assertTrue(AppInspectionReviewRule.objects.filter(
            task=self.task,
            target_name='消息 Tab',
            status='found_unconfirmed',
            resolution='normal_behavior',
            enabled=True,
        ).exists())

    def test_report_marks_later_matching_target_as_rule_suppressed(self):
        AppInspectionReviewRule.objects.create(
            task=self.task,
            target_name='消息 Tab',
            status='found_unconfirmed',
            resolution='normal_behavior',
            note='后续同类状态切换归档。',
            created_by=self.user,
        )
        self.target_result.review_resolution = ''
        self.target_result.review_note = ''
        self.target_result.reviewed_by = None
        self.target_result.reviewed_at = None
        self.target_result.save(update_fields=['review_resolution', 'review_note', 'reviewed_by', 'reviewed_at'])

        response = self.client.get(f'/api/app-automation/exploration-tasks/{self.task.id}/report/')

        self.assertEqual(response.status_code, 200)
        result = response.data['data']['target_results'][0]
        self.assertTrue(result['is_review_suppressed'])
        self.assertEqual(result['effective_review']['source'], 'rule')
        self.assertEqual(result['effective_review']['resolution'], 'normal_behavior')
        self.assertEqual(response.data['data']['insights']['target_review_stats']['rule_hit_count'], 1)

    @override_settings(DEBUG=True)
    def test_run_consistency_creates_three_pending_runs(self):
        with patch('apps.app_automation.views.exploration_views.run_execution_precheck', return_value={'can_submit': True}), \
                patch('apps.app_automation.views.exploration_views._start_consistency_subprocess') as subprocess_mock:
            response = self.client.post(
                f'/api/app-automation/exploration-tasks/{self.task.id}/run-consistency/',
                {},
                format='json',
            )

        self.assertEqual(response.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'pending')
        self.assertEqual(self.task.summary['consistency_batch_total'], 3)
        self.assertEqual(self.task.runs.count(), 4)
        self.assertEqual(
            list(self.task.runs.order_by('-id').values_list('status', flat=True)[:3]),
            ['pending', 'pending', 'pending'],
        )
        subprocess_mock.assert_called_once()

    def test_run_consistency_rejects_non_target_inspection_task(self):
        self.task.strategy = 'smoke'
        self.task.save(update_fields=['strategy', 'updated_at'])

        response = self.client.post(
            f'/api/app-automation/exploration-tasks/{self.task.id}/run-consistency/',
            {},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('只支持目标巡检', response.data['message'])
