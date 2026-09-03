# -*- coding: utf-8 -*-
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.app_automation.models import (
    AppDevice,
    AppExecutionAgent,
    AppPackage,
    AppProject,
    AppTestCase,
    AppTestExecution,
)


class AppExecutionAgentApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='agent_owner', password='pass123456')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.package = AppPackage.objects.create(
            name='Demo App',
            package_name='com.example.qaflow.demo',
            created_by=self.user,
        )
        self.project = AppProject.objects.create(
            name='Agent Demo Project',
            owner=self.user,
            android_app_package=self.package,
        )
        self.case = AppTestCase.objects.create(
            project=self.project,
            name='Agent dry-run case',
            app_package=self.package,
            ui_flow={'steps': [{'type': 'assert_text', 'name': '示例断言'}]},
            created_by=self.user,
        )

    def test_agent_can_sync_device_claim_and_report_execution(self):
        heartbeat_response = self.client.post('/api/app-automation/execution-agents/heartbeat/', {
            'agent_id': 'local-laptop',
            'name': '本地笔记本',
            'devices': [{
                'device_id': 'demo-device-001',
                'name': '演示设备',
                'status': 'online',
                'android_version': '14',
                'connection_type': 'real_device',
            }],
            'capabilities': {'dry_run': True, 'adb': True},
        }, format='json')

        self.assertEqual(heartbeat_response.status_code, 200)
        self.assertTrue(AppExecutionAgent.objects.filter(agent_id='local-laptop').exists())
        device = AppDevice.objects.get(device_id='demo-device-001')
        self.assertEqual(device.agent.agent_id, 'local-laptop')

        execute_response = self.client.post(f'/api/app-automation/test-cases/{self.case.id}/execute/', {
            'device_id': 'demo-device-001',
            'execution_mode': 'agent',
        }, format='json')

        self.assertEqual(execute_response.status_code, 200)
        execution_id = execute_response.data['execution']['id']
        execution = AppTestExecution.objects.get(id=execution_id)
        self.assertEqual(execution.execution_mode, 'agent')
        self.assertEqual(execution.status, 'pending')

        claim_response = self.client.post('/api/app-automation/execution-agents/claim/', {
            'agent_id': 'local-laptop',
            'device_ids': ['demo-device-001'],
        }, format='json')

        self.assertEqual(claim_response.status_code, 200)
        self.assertEqual(claim_response.data['data']['execution_id'], execution_id)
        execution.refresh_from_db()
        self.assertEqual(execution.status, 'running')
        self.assertEqual(execution.agent.agent_id, 'local-laptop')

        status_response = self.client.post(
            f'/api/app-automation/execution-agents/executions/{execution_id}/status/',
            {
                'agent_id': 'local-laptop',
                'status': 'completed',
                'result': 'passed',
                'progress': 100,
                'message': 'dry-run passed',
                'total_steps': 1,
                'passed_steps': 1,
                'failed_steps': 0,
            },
            format='json',
        )

        self.assertEqual(status_response.status_code, 200)
        execution.refresh_from_db()
        self.assertEqual(execution.status, 'completed')
        self.assertEqual(execution.result, 'passed')
        self.assertEqual(execution.progress, 100)
        self.assertEqual(execution.passed_steps, 1)
