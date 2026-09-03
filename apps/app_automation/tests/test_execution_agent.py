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
            'health_status': 'warning',
            'health_summary': '环境部分可用：dry-run 模式',
            'health_checks': [{
                'code': 'dry_run_device',
                'name': '演示设备',
                'status': 'warning',
                'message': '当前使用 fake-device 验证链路',
                'suggestion': '连接真实 Android 手机后重新运行 Agent',
            }],
        }, format='json')

        self.assertEqual(heartbeat_response.status_code, 200)
        self.assertTrue(AppExecutionAgent.objects.filter(agent_id='local-laptop').exists())
        agent = AppExecutionAgent.objects.get(agent_id='local-laptop')
        self.assertEqual(agent.health_status, 'warning')
        self.assertEqual(agent.health_checks[0]['code'], 'dry_run_device')
        self.assertEqual(heartbeat_response.data['data']['health_status'], 'warning')
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
        self.assertEqual(execution.agent.agent_id, 'local-laptop')
        self.assertEqual(execution.execution_snapshot['test_case']['name'], 'Agent dry-run case')

        claim_response = self.client.post('/api/app-automation/execution-agents/claim/', {
            'agent_id': 'local-laptop',
            'device_ids': ['demo-device-001'],
        }, format='json')

        self.assertEqual(claim_response.status_code, 200)
        self.assertEqual(claim_response.data['data']['execution_id'], execution_id)
        execution.refresh_from_db()
        self.assertEqual(execution.status, 'running')
        self.assertEqual(execution.agent.agent_id, 'local-laptop')
        self.assertTrue(claim_response.data['data']['lease_token'])
        self.assertEqual(claim_response.data['data']['attempt_no'], 1)
        lease_token = claim_response.data['data']['lease_token']

        invalid_status_response = self.client.post(
            f'/api/app-automation/execution-agents/executions/{execution_id}/status/',
            {
                'agent_id': 'local-laptop',
                'status': 'completed',
                'result': 'passed',
                'progress': 100,
                'message': 'missing lease should fail',
            },
            format='json',
        )
        self.assertEqual(invalid_status_response.status_code, 409)

        status_response = self.client.post(
            f'/api/app-automation/execution-agents/executions/{execution_id}/status/',
            {
                'agent_id': 'local-laptop',
                'status': 'running',
                'progress': 30,
                'message': 'dry-run running',
                'total_steps': 1,
                'lease_token': lease_token,
                'attempt_no': 1,
                'event_seq': 1,
            },
            format='json',
        )
        self.assertEqual(status_response.status_code, 200)

        duplicate_response = self.client.post(
            f'/api/app-automation/execution-agents/executions/{execution_id}/status/',
            {
                'agent_id': 'local-laptop',
                'status': 'running',
                'progress': 60,
                'message': 'duplicate event should be ignored',
                'lease_token': lease_token,
                'attempt_no': 1,
                'event_seq': 1,
            },
            format='json',
        )
        self.assertEqual(duplicate_response.status_code, 200)
        self.assertTrue(duplicate_response.data['data']['idempotent'])
        execution.refresh_from_db()
        self.assertEqual(execution.progress, 30)

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
                'lease_token': lease_token,
                'attempt_no': 1,
                'event_seq': 2,
            },
            format='json',
        )

        self.assertEqual(status_response.status_code, 200)
        execution.refresh_from_db()
        self.assertEqual(execution.status, 'completed')
        self.assertEqual(execution.result, 'passed')
        self.assertEqual(execution.progress, 100)
        self.assertEqual(execution.passed_steps, 1)

    def test_agent_token_can_authenticate_heartbeat(self):
        token_response = self.client.post('/api/app-automation/execution-agents/generate-token/', {
            'agent_id': 'token-agent',
            'name': '令牌执行机',
        }, format='json')
        self.assertEqual(token_response.status_code, 200)
        agent_token = token_response.data['data']['agent_token']
        self.assertTrue(agent_token.startswith('qfa_'))
        self.assertNotIn('token_hash', token_response.data['data']['agent'])

        anonymous_client = APIClient()
        heartbeat_response = anonymous_client.post(
            '/api/app-automation/execution-agents/heartbeat/',
            {
                'agent_id': 'token-agent',
                'name': '令牌执行机',
                'devices': [],
                'capabilities': {'dry_run': True},
                'health_status': 'warning',
                'health_summary': '未连接真机',
                'health_checks': [],
            },
            format='json',
            HTTP_X_QAFLOW_AGENT_TOKEN=agent_token,
        )
        self.assertEqual(heartbeat_response.status_code, 200)
        agent = AppExecutionAgent.objects.get(agent_id='token-agent')
        self.assertEqual(agent.created_by, self.user)
        self.assertIsNotNone(agent.token_last_used_at)
