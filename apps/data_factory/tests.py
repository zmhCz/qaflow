from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate
import tempfile
import time
from unittest.mock import Mock, patch

from .business_load import SCENARIO_DEFINITIONS
from .models import BusinessAccount, BusinessLoadTask
from .serializers import BusinessLoadTaskSerializer
from .views import BusinessAccountViewSet, BusinessLoadTaskViewSet


class BusinessAccountImportNormalizeTests(SimpleTestCase):
    def setUp(self):
        self.view = BusinessAccountViewSet()

    def test_numeric_account_range_expands_to_account_no_and_phone(self):
        accounts = self.view._normalize_import_accounts({
            'raw_text': '18800001000~18800001002',
            'accounts': [],
        })

        self.assertEqual(
            accounts,
            [
                {'account_no': '18800001000', 'phone': '18800001000'},
                {'account_no': '18800001001', 'phone': '18800001001'},
                {'account_no': '18800001002', 'phone': '18800001002'},
            ],
        )

    def test_numeric_account_range_preserves_start_width(self):
        accounts = self.view._normalize_import_accounts({
            'raw_text': '001~003',
            'accounts': [],
        })

        self.assertEqual([account['account_no'] for account in accounts], ['001', '002', '003'])
        self.assertEqual([account['phone'] for account in accounts], ['001', '002', '003'])

    def test_invalid_account_range_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.view._normalize_import_accounts({
                'raw_text': '18800001099~18800001000',
                'accounts': [],
            })


class BusinessLoadTaskTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='loader', password='pwd')
        cache.clear()

    def test_parse_im_runner_result_reads_last_structured_marker(self):
        view = BusinessLoadTaskViewSet()
        result = view._parse_im_runner_result(
            'noise\nQAFLOW_RESULT_JSON={"success":true,"send_attempts":2}\n',
            '',
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['send_attempts'], 2)

    def test_parse_im_runner_result_requires_structured_marker(self):
        view = BusinessLoadTaskViewSet()

        with self.assertRaises(ValidationError):
            view._parse_im_runner_result('plain stdout', 'plain stderr')

    def test_normalize_im_runner_accounts_keeps_send_metrics(self):
        view = BusinessLoadTaskViewSet()

        results = view._normalize_im_runner_accounts([
            {
                'account_no': '16000000000',
                'phone': '16000000000',
                'user_id': 88001,
                'connected': True,
                'send_attempts': 3,
                'send_request_success': 2,
                'error': '',
            }
        ])

        self.assertEqual(results[0]['account_no'], '16000000000')
        self.assertEqual(results[0]['send_attempts'], 3)
        self.assertEqual(results[0]['send_request_success'], 2)
        self.assertFalse(results[0]['steps'][1]['success'])

    def test_normalize_im_runner_accounts_does_not_treat_zero_send_as_success(self):
        view = BusinessLoadTaskViewSet()

        results = view._normalize_im_runner_accounts([
            {
                'account_no': '16000000000',
                'phone': '16000000000',
                'connected': True,
                'send_attempts': 0,
                'send_request_success': 0,
                'error': '',
            }
        ])

        self.assertFalse(results[0]['steps'][1]['success'])
        self.assertFalse(results[0]['passed'])

    def test_calculate_success_rate_handles_zero_total(self):
        view = BusinessLoadTaskViewSet()

        self.assertEqual(view._calculate_success_rate(0, 0), 0)
        self.assertEqual(view._calculate_success_rate(3, 4), 75)

    def test_create_room_list_load_task_builds_capability_chain(self):
        serializer = BusinessLoadTaskSerializer(data={
            'name': '房间列表小流量预检查',
            'scenario_type': 'room_list_load',
            'environment': 'test',
            'business_domain': 'room',
            'account_count': 2,
            'purpose': '验证房间列表链路',
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        task = serializer.save(created_by=self.user)

        self.assertEqual(task.status, 'ready')
        self.assertEqual([item['key'] for item in task.capability_chain], [
            'login',
            'enter_community',
            'follow_community',
            'fetch_room_list',
        ])
        self.assertTrue(task.config['dry_run'])

    def test_create_team_recruit_task_builds_capability_chain(self):
        serializer = BusinessLoadTaskSerializer(data={
            'name': '发布组队链路自测',
            'scenario_type': 'team_recruit_publish',
            'environment': 'test',
            'business_domain': 'team',
            'account_count': 1,
            'purpose': '验证发布组队链路',
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        task = serializer.save(created_by=self.user)

        self.assertEqual(task.status, 'ready')
        self.assertEqual(task.business_domain, 'team')
        capability_keys = [item['key'] for item in task.capability_chain]
        self.assertIn('heartbeat_keepalive', capability_keys)
        self.assertIn('publish_team', capability_keys)
        self.assertIn('im_send_notification', capability_keys)
        self.assertIn('close_team', capability_keys)
        self.assertTrue(task.config['team_keepalive_after_notify'])
        self.assertNotIn('team_heartbeat_interval_seconds', task.config)

    def test_create_community_activity_task_builds_activity_capability_chain(self):
        serializer = BusinessLoadTaskSerializer(data={
            'name': '社区活跃模拟小流量',
            'scenario_type': 'community_activity_simulation',
            'environment': 'test',
            'business_domain': 'community',
            'account_count': 4,
            'config': {
                'resident_user_count': 2,
                'transient_user_count': 2,
            },
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        task = serializer.save(created_by=self.user)

        self.assertIn('community_activity_simulation', SCENARIO_DEFINITIONS)
        capability_keys = [item['key'] for item in task.capability_chain]
        self.assertIn('heartbeat_keepalive', capability_keys)
        self.assertIn('switch_room', capability_keys)
        self.assertEqual(task.config['resident_user_count'], 2)
        self.assertEqual(task.config['transient_user_count'], 2)

    def test_team_room_publish_overrides_keepalive_config(self):
        overrides = BusinessLoadTaskViewSet()._normalize_team_room_publish_overrides({
            'team_message_template': 'QAFlow发布组队_{{timestamp}}',
            'team_keepalive_after_notify': False,
        })

        self.assertFalse(overrides['team_keepalive_after_notify'])
        self.assertNotIn('team_heartbeat_interval_seconds', overrides)

    def test_team_recruit_duration_extends_to_team_duration(self):
        serializer = BusinessLoadTaskSerializer(data={
            'name': '发布组队持续时间兜底',
            'scenario_type': 'team_recruit_publish',
            'environment': 'test',
            'business_domain': 'team',
            'account_count': 1,
            'config': {
                'duration_seconds': 30,
                'team_duration_minutes': 5,
            },
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        task = serializer.save(created_by=self.user)

        self.assertEqual(task.config['duration_seconds'], 300)

    def test_team_recruit_precheck_requires_target_room(self):
        BusinessAccount.objects.create(
            account_no='16000000000',
            phone='16000000000',
            environment='test',
            business_domain='common',
            status='available',
            created_by=self.user,
        )
        with tempfile.NamedTemporaryFile() as runner:
            task = BusinessLoadTask.objects.create(
                name='发布组队缺少房间预检查',
                scenario_type='team_recruit_publish',
                environment='test',
                business_domain='team',
                account_count=1,
                created_by=self.user,
                config={
                    'server_id': 60957,
                    'target_rooms': [],
                    'team_message_template': 'QAFlow发布组队_{{timestamp}}',
                    'team_duration_minutes': 1,
                    'team_max_members_num': 2,
                    'runner_path': runner.name,
                    'real_traffic_enabled': True,
                },
                capability_chain=[{'key': 'enter_room'}],
                status='ready',
            )

            result = BusinessLoadTaskViewSet()._build_precheck_result(task)

        self.assertFalse(result['passed'])
        self.assertIn('请选择发布组队所在的语音房', result['message'])

    def test_precheck_reports_missing_accounts(self):
        BusinessAccount.objects.create(
            account_no='18800001000',
            phone='18800001000',
            environment='test',
            business_domain='room',
            status='available',
            created_by=self.user,
        )
        task = BusinessLoadTask.objects.create(
            name='账号不足预检查',
            scenario_type='room_list_load',
            environment='test',
            business_domain='room',
            account_count=2,
            created_by=self.user,
            config={'dry_run': True},
            capability_chain=[],
            status='ready',
        )

        result = BusinessLoadTaskViewSet()._build_precheck_result(task)

        self.assertFalse(result['passed'])
        self.assertEqual(result['available_count'], 1)
        self.assertEqual(result['missing_count'], 1)

    def test_precheck_allows_common_accounts_for_room_tasks(self):
        for index in range(4):
            BusinessAccount.objects.create(
                account_no=f'1880000100{index}',
                phone=f'1880000100{index}',
                environment='test',
                business_domain='common',
                status='available',
                created_by=self.user,
            )
        task = BusinessLoadTask.objects.create(
            name='通用账号复用预检查',
            scenario_type='voice_room_online',
            environment='test',
            business_domain='room',
            account_count=3,
            created_by=self.user,
            config={'dry_run': True},
            capability_chain=[],
            status='ready',
        )

        result = BusinessLoadTaskViewSet()._build_precheck_result(task)

        self.assertTrue(result['passed'])
        self.assertEqual(result['available_count'], 4)
        self.assertEqual(result['missing_count'], 0)
        self.assertEqual(result['account_domains'], ['room', 'common'])

    def test_parse_target_rooms_supports_frontend_room_shape(self):
        rooms = BusinessLoadTaskViewSet()._parse_target_rooms([
            {'channel_id': '1001', 'channel_name': '游戏语音房1', 'channel_type': -98},
            {'channelId': 1002, 'channelName': '游戏语音房2', 'channelType': -98},
        ])

        self.assertEqual([room['channel_id'] for room in rooms], ['1001', '1002'])
        self.assertEqual(rooms[0]['channel_name'], '游戏语音房1')

    def test_assignment_plan_round_robins_selected_rooms(self):
        task = BusinessLoadTask.objects.create(
            name='指定房间分配预览',
            scenario_type='voice_room_online',
            environment='test',
            business_domain='room',
            account_count=2,
            created_by=self.user,
            config={'server_id': 55984, 'room_assignment_mode': 'round_robin'},
            capability_chain=[{'key': 'enter_room'}],
            status='ready',
        )
        planned_accounts = [
            {'account_no': 'a1', 'phone': '18800001001', 'user_id': 'u1', 'nickname': 'n1'},
            {'account_no': 'a2', 'phone': '18800001002', 'user_id': 'u2', 'nickname': 'n2'},
            {'account_no': 'a3', 'phone': '18800001003', 'user_id': 'u3', 'nickname': 'n3'},
        ]
        target_rooms = [
            {'channel_id': 'r1', 'channel_name': '房间1', 'channel_type': -98},
            {'channel_id': 'r2', 'channel_name': '房间2', 'channel_type': -98},
        ]

        result = BusinessLoadTaskViewSet()._build_assignment_plan(task, planned_accounts, target_rooms, 'manual')

        self.assertEqual([item['channel_id'] for item in result['account_room_plan']], ['r1', 'r2', 'r1'])

    def test_community_activity_assignment_marks_resident_and_transient_roles(self):
        task = BusinessLoadTask.objects.create(
            name='社区活跃分配预览',
            scenario_type='community_activity_simulation',
            environment='test',
            business_domain='community',
            account_count=4,
            created_by=self.user,
            config={
                'server_id': 55984,
                'resident_user_count': 2,
                'transient_user_count': 2,
                'room_assignment_mode': 'round_robin',
            },
            capability_chain=[{'key': 'enter_room'}],
            status='ready',
        )
        planned_accounts = [
            {'account_no': 'a1', 'phone': '18800001001'},
            {'account_no': 'a2', 'phone': '18800001002'},
            {'account_no': 'a3', 'phone': '18800001003'},
            {'account_no': 'a4', 'phone': '18800001004'},
        ]
        target_rooms = [
            {'channel_id': 'r1', 'channel_name': '房间1', 'channel_type': -98},
            {'channel_id': 'r2', 'channel_name': '房间2', 'channel_type': -98},
        ]

        result = BusinessLoadTaskViewSet()._build_assignment_plan(task, planned_accounts, target_rooms, 'manual')

        self.assertEqual(
            [item['activity_role_label'] for item in result['account_room_plan']],
            ['固定用户', '固定用户', '流动用户', '流动用户'],
        )

    def test_community_activity_trial_limit_scales_roles_by_ratio(self):
        task = BusinessLoadTask.objects.create(
            name='社区活跃小流量角色缩放',
            scenario_type='community_activity_simulation',
            environment='test',
            business_domain='community',
            account_count=20,
            created_by=self.user,
            config={
                'server_id': 55984,
                'resident_user_count': 10,
                'transient_user_count': 10,
            },
            capability_chain=[{'key': 'enter_room'}],
            status='ready',
        )
        planned_accounts = [
            {'account_no': 'a1', 'phone': '18800001001'},
            {'account_no': 'a2', 'phone': '18800001002'},
            {'account_no': 'a3', 'phone': '18800001003'},
        ]

        result = BusinessLoadTaskViewSet()._build_assignment_plan(task, planned_accounts, [], 'auto')

        self.assertEqual(
            [item['activity_role_label'] for item in result['account_room_plan']],
            ['固定用户', '固定用户', '流动用户'],
        )

    def test_community_activity_room_pool_deduplicates_rooms(self):
        account_plan = [
            {'channel_id': 'r1', 'channel_name': '房间1', 'channel_type': -98},
            {'channel_id': 'r1', 'channel_name': '重复房间1', 'channel_type': -98},
            {'channel_id': 'AUTO', 'channel_name': '运行时自动分配', 'channel_type': -98},
            {'channel_id': 'r2', 'channel_name': '房间2', 'channel_type': -98},
        ]

        room_pool = BusinessLoadTaskViewSet()._build_activity_room_pool(account_plan)

        self.assertEqual([item['channel_id'] for item in room_pool], ['r1', 'r2'])

    def test_normalize_room_preview_keeps_display_fields(self):
        room = BusinessLoadTaskViewSet()._normalize_room_preview({
            'channelId': 1001098493,
            'channelName': '游戏语音房',
            'channelType': -98,
            'channelModel': 3,
            'channelTemplate': 5,
            'memberNum': 3,
            'memberLimit': 10,
            'sortIndexNum': 123,
        })

        self.assertEqual(room['channel_id'], '1001098493')
        self.assertEqual(room['channel_name'], '游戏语音房')
        self.assertEqual(room['channel_type'], -98)
        self.assertEqual(room['channel_model'], 3)
        self.assertEqual(room['room_type_label'], '麦序模式 / 模板 5')
        self.assertEqual(room['sort_index_num'], 123)
        self.assertFalse(room['is_top_room'])
        self.assertEqual(room['online_count'], 3)
        self.assertEqual(room['capacity'], 10)

    def test_build_room_type_label_uses_channel_model_before_channel_type(self):
        view = BusinessLoadTaskViewSet()

        self.assertEqual(view._build_room_type_label(channel_model=1, channel_type=-98), '普通模式')
        self.assertEqual(view._build_room_type_label(channel_model=2, channel_type=-98), '开黑模式')
        self.assertEqual(view._build_room_type_label(channel_model=3, channel_type=-98), '麦序模式')
        self.assertEqual(view._build_room_type_label(channel_type=-98), '社区语音频道')

    def test_merge_top_and_page_rooms_keeps_pinned_rooms_first_and_deduplicates(self):
        rooms = BusinessLoadTaskViewSet()._merge_top_and_page_rooms({
            'topList': [
                {'channelId': 3, 'channelName': '置顶麦序房'},
                {'channelId': 1, 'channelName': '置顶普通房'},
            ],
            'pageList': [
                {'channelId': 1, 'channelName': '普通列表重复房'},
                {'channelId': 2, 'channelName': '普通列表房'},
                {'channelId': 3, 'channelName': '普通列表重复麦序房'},
            ],
        })

        self.assertEqual([item['channelId'] for item in rooms], [3, 1, 2])
        self.assertEqual([item['channelName'] for item in rooms], ['置顶麦序房', '置顶普通房', '普通列表房'])
        self.assertEqual([item['_qaflow_room_source'] for item in rooms], ['topList', 'topList', 'pageList'])
        self.assertEqual([item['_qaflow_is_top_room'] for item in rooms], [True, True, False])

    def test_fetch_room_preview_uses_minus_one_for_first_page_to_get_top_list(self):
        view = BusinessLoadTaskViewSet()

        response = Mock()
        response.raise_for_status.return_value = None
        response.content = b'{"success": true, "retData": {"topList": [], "pageList": []}}'

        with patch('apps.data_factory.views.requests.post', return_value=response) as mocked_post:
            rooms = view._fetch_room_preview('https://business.example.com', 'token', 60957, page_size=100, max_pages=1)

        self.assertEqual(rooms, [])
        self.assertEqual(mocked_post.call_args.kwargs['json']['lastSortIndex'], -1)

    def test_normalize_community_candidate_keeps_server_no_and_server_id(self):
        community = BusinessLoadTaskViewSet()._normalize_community_candidate({
            'serverId': 60957,
            'serverNo': 90007012,
            'serverName': '演示社区',
        })

        self.assertEqual(community['server_id'], 60957)
        self.assertEqual(community['server_no'], 90007012)
        self.assertEqual(community['server_name'], '演示社区')

    def test_normalize_community_candidate_marks_exclusive_room_plugin(self):
        community = BusinessLoadTaskViewSet()._normalize_community_candidate({
            'serverId': 60958,
            'serverNo': 90007013,
            'serverName': '专属房社区',
            'personalServerPluginGroupResp': {
                'personalServerPluginBos': {
                    'personalServerPluginGroupBos': [
                        {
                            'pluginId': 5,
                            'dbId': 88,
                            'name': '房间插件',
                            'subPluginInfoBos': [
                                {'pluginName': '专属房间', 'bizId': 99}
                            ],
                        }
                    ]
                }
            },
        })

        self.assertTrue(community['has_exclusive_rooms'])
        self.assertEqual(community['exclusive_plugin']['biz_id'], 99)

    def test_filter_community_candidates_prefers_exact_server_no_for_numeric_keyword(self):
        communities = [
            {'server_id': 90007012, 'server_no': 20000000, 'server_name': '内部ID碰撞'},
            {'server_id': 60957, 'server_no': 90007012, 'server_name': '演示社区'},
            {'server_id': 88990, 'server_no': 9000701200, 'server_name': '相似社区号'},
        ]

        result = BusinessLoadTaskViewSet()._filter_community_candidates(communities, '90007012')

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['server_id'], 60957)
        self.assertEqual(result[0]['server_no'], 90007012)

    def test_filter_community_candidates_supports_fuzzy_server_name(self):
        communities = [
            {'server_id': 60957, 'server_no': 90007012, 'server_name': '演示社区'},
            {'server_id': 55984, 'server_no': None, 'server_name': '默认测试社区'},
        ]

        result = BusinessLoadTaskViewSet()._filter_community_candidates(communities, '演示')

        self.assertEqual([item['server_name'] for item in result], ['演示社区'])

    def test_start_task_marks_running_and_dispatches_background_execution(self):
        BusinessAccount.objects.create(
            account_no='17701321000',
            phone='17701321000',
            environment='test',
            business_domain='room',
            status='available',
            created_by=self.user,
        )
        task = BusinessLoadTask.objects.create(
            name='正式启动验证',
            scenario_type='room_list_load',
            environment='test',
            business_domain='room',
            account_count=1,
            created_by=self.user,
            config={'dry_run': True, 'server_id': 55984},
            capability_chain=[],
            status='ready',
        )
        request = APIRequestFactory().post('/')
        force_authenticate(request, user=self.user)
        with patch.object(BusinessLoadTaskViewSet, '_start_business_load_background') as mocked_background:
            response = BusinessLoadTaskViewSet.as_view({'post': 'start'})(request, pk=task.id)

        task.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(task.status, 'running')
        self.assertFalse(task.metrics['dry_run'])
        self.assertEqual(task.metrics['last_execution_mode'], 'start')
        mocked_background.assert_called_once_with(task.id)

    def test_persist_team_room_publish_progress_updates_room_stage(self):
        task = BusinessLoadTask.objects.create(
            name='组队进度验证',
            scenario_type='team_recruit_publish',
            environment='test',
            business_domain='team',
            account_count=1,
            created_by=self.user,
            config={'server_id': 55984},
            capability_chain=[],
            status='running',
        )
        result = {
            'channel_id': '1001704498',
            'channel_name': '游戏语音房',
            'room_type_label': '普通模式',
            'passed': False,
            'steps': [{'key': 'publish_team', 'success': True}],
            'room_entry': {'team_published': True},
        }

        BusinessLoadTaskViewSet()._persist_team_room_publish_progress(
            task.id,
            {'channel_id': '1001704498', 'display_order': 1},
            result,
            '招募中',
        )

        task.refresh_from_db()
        record = task.metrics['team_room_publish_records']['1001704498']
        self.assertEqual(record['stage'], '招募中')
        self.assertEqual(record['channel_name'], '游戏语音房')

    def test_team_recruit_worker_count_defaults_to_reliable_serial_publish(self):
        task = BusinessLoadTask(
            name='组队并发验证',
            scenario_type='team_recruit_publish',
            environment='test',
            business_domain='team',
            account_count=20,
            config={'request_rate_per_second': 5},
        )

        worker_count = BusinessLoadTaskViewSet()._get_team_recruit_worker_count(task, 20)

        self.assertEqual(worker_count, 1)

    def test_team_recruit_worker_count_ignores_explicit_concurrency_in_reliable_mode(self):
        task = BusinessLoadTask(
            name='组队显式并发验证',
            scenario_type='team_recruit_publish',
            environment='test',
            business_domain='team',
            account_count=10,
            config={'request_rate_per_second': 5, 'team_publish_concurrency': 7},
        )

        worker_count = BusinessLoadTaskViewSet()._get_team_recruit_worker_count(task, 10)

        self.assertEqual(worker_count, 1)

    def test_team_recruit_worker_count_allows_explicit_concurrency_when_reliable_mode_disabled(self):
        task = BusinessLoadTask(
            name='组队高级并发验证',
            scenario_type='team_recruit_publish',
            environment='test',
            business_domain='team',
            account_count=10,
            config={
                'request_rate_per_second': 5,
                'team_publish_concurrency': 7,
                'team_publish_reliable_visible': False,
            },
        )

        worker_count = BusinessLoadTaskViewSet()._get_team_recruit_worker_count(task, 10)

        self.assertEqual(worker_count, 7)

    def test_team_recruit_visibility_check_marks_missing_room_as_failed(self):
        task = BusinessLoadTask.objects.create(
            name='组队端上可见性验证',
            scenario_type='team_recruit_publish',
            environment='test',
            business_domain='team',
            account_count=2,
            created_by=self.user,
            config={'server_id': 55984, 'team_visibility_wait_seconds': 1},
            capability_chain=[],
            status='running',
        )
        sessions = []
        for channel_id in ['1001', '1002']:
            sessions.append({
                'token': 'token',
                'channel_id': channel_id,
                'plan': {'channel_id': channel_id, 'channel_name': f'房间{channel_id}'},
                'result': {
                    'channel_id': channel_id,
                    'channel_name': f'房间{channel_id}',
                    'steps': [{'key': 'publish_team', 'success': True, 'required': True}],
                    'room_entry': {'team_published': True},
                    'passed': True,
                },
            })

        view = BusinessLoadTaskViewSet()
        with patch.object(view, '_fetch_team_recruit_visible_state', return_value={
            'get_team_visible_ids': {'1001'},
            'page_query_visible_ids': {'1001'},
            'visible_ids': {'1001'},
        }):
            summary = view._verify_team_recruit_visibility(task, 'https://business.example.com', 55984, sessions)

        self.assertFalse(summary['passed'])
        self.assertEqual(summary['visible_count'], 1)
        self.assertEqual(summary['missing_channel_ids'], ['1002'])
        self.assertTrue(sessions[0]['result']['passed'])
        self.assertFalse(sessions[1]['result']['passed'])

    def test_team_recruit_keepalive_scheduler_batches_active_rooms(self):
        task = BusinessLoadTask.objects.create(
            name='组队统一保活调度验证',
            scenario_type='team_recruit_publish',
            environment='test',
            business_domain='team',
            account_count=2,
            created_by=self.user,
            config={
                'duration_seconds': 1,
                'request_rate_per_second': 2,
                'cleanup_after_stop': True,
                'server_id': 55984,
            },
            capability_chain=[],
            status='running',
        )
        now = time.monotonic()
        sessions = []
        for index in range(2):
            result = {
                'index': index + 1,
                'account_no': f'1490000000{index}',
                'phone': f'1490000000{index}',
                'channel_id': str(1000 + index),
                'channel_name': f'房间{index + 1}',
                'room_type_label': '游戏语音房',
                'steps': [
                    {'key': 'publish_team', 'success': True, 'required': True},
                    {'key': 'im_send_notification', 'success': True, 'required': True},
                ],
                'room_entry': {'heartbeat_rounds': 0, 'team_closed': False, 'left': False},
                'passed': True,
            }
            sessions.append({
                'base_url': 'https://business.example.com',
                'server_id': 55984,
                'plan': {'channel_id': str(1000 + index), 'channel_name': f'房间{index + 1}'},
                'result': result,
                'token': f'token-{index}',
                'rid': f'rid-{index}',
                'channel_id': str(1000 + index),
                'channel_type': -98,
                'account_started_at': now,
                'entered_at': now - 30,
                'next_heartbeat_at': now - 1,
                'deadline_at': now + 0.01,
                'rounds': 0,
                'failed_heartbeats': 0,
            })

        view = BusinessLoadTaskViewSet()
        with patch.object(view, '_send_room_heartbeat', return_value=True) as mocked_heartbeat, \
                patch.object(view, '_close_business_team', return_value=True) as mocked_close, \
                patch.object(view, '_leave_business_room', return_value=True) as mocked_leave:
            summary = view._run_team_recruit_keepalive_scheduler(task, sessions, [])

        self.assertEqual(summary['active_count'], 2)
        self.assertEqual(summary['failed_heartbeats'], 0)
        self.assertEqual(mocked_heartbeat.call_count, 2)
        self.assertEqual(mocked_close.call_count, 2)
        self.assertEqual(mocked_leave.call_count, 2)
        for session in sessions:
            result = session['result']
            self.assertEqual(result['team_keepalive_rounds'], 1)
            self.assertTrue(result['room_entry']['team_closed'])
            self.assertTrue(result['room_entry']['left'])
            self.assertTrue(any(step['key'] == 'team_keepalive_completed' for step in result['steps']))

    def test_get_probe_token_reuses_cached_login_token(self):
        view = BusinessLoadTaskViewSet()

        with patch.object(view, '_login_probe_account', return_value=('token-1', 'user-1')) as mocked_login:
            first = view._get_probe_token('https://business.example.com', '16000000000', '0000', 55984)
            second = view._get_probe_token('https://business.example.com', '16000000000', '0000', 60957)

        self.assertEqual(first, ('token-1', 'user-1'))
        self.assertEqual(second, ('token-1', 'user-1'))
        self.assertEqual(mocked_login.call_count, 1)

    def test_create_im_message_flood_task_builds_im_capability_chain(self):
        serializer = BusinessLoadTaskSerializer(data={
            'name': 'IM 刷屏预演',
            'scenario_type': 'im_message_flood',
            'environment': 'test',
            'business_domain': 'im',
            'account_count': 2,
            'purpose': '验证 IM 刷屏配置',
            'config': {
                'target_type': 'room',
                'target_id': '1002578766',
            },
        })

        self.assertTrue(serializer.is_valid(), serializer.errors)
        task = serializer.save(created_by=self.user)

        self.assertEqual(task.status, 'ready')
        self.assertEqual(task.business_domain, 'im')
        self.assertEqual([item['key'] for item in task.capability_chain], [
            'login',
            'enter_community',
            'follow_community',
            'enter_room',
            'im_fetch_config',
            'im_connect',
            'im_join_target',
            'im_send_message_loop',
            'im_collect_metrics',
        ])
        self.assertEqual(task.config['biz_type'], 5)
        self.assertEqual(task.config['runner_status'], 'cli_adapter')

    def test_im_message_flood_precheck_requires_target_id(self):
        BusinessAccount.objects.create(
            account_no='17701321000',
            phone='17701321000',
            environment='test',
            business_domain='im',
            status='available',
            created_by=self.user,
        )
        task = BusinessLoadTask.objects.create(
            name='缺少 IM 目标',
            scenario_type='im_message_flood',
            environment='test',
            business_domain='im',
            account_count=1,
            created_by=self.user,
            config={'target_type': 'room', 'target_id': '', 'interval_ms': 1000},
            capability_chain=[],
            status='ready',
        )

        result = BusinessLoadTaskViewSet()._build_precheck_result(task)

        self.assertFalse(result['passed'])
        self.assertIn('目标房间', result['message'])
        self.assertTrue(result['im_errors'])

    def test_im_message_flood_precheck_builds_message_plan(self):
        BusinessAccount.objects.create(
            account_no='17701321000',
            phone='17701321000',
            user_id='88001',
            environment='test',
            business_domain='im',
            status='available',
            created_by=self.user,
        )
        task = BusinessLoadTask.objects.create(
            name='IM 计划生成',
            scenario_type='im_message_flood',
            environment='test',
            business_domain='im',
            account_count=1,
            created_by=self.user,
            config={
                'target_type': 'group',
                'target_id': '9001139483',
                'target_name': '测试群',
                'message_template': 'QAFlow_{{account_no}}_{{user_id}}_{{sequence}}',
                'interval_ms': 1000,
                'runner_status': 'planned_adapter',
            },
            capability_chain=[{'key': 'im_send_message_loop'}],
            status='ready',
        )

        result = BusinessLoadTaskViewSet()._build_precheck_result(task)

        self.assertTrue(result['passed'])
        self.assertEqual(result['im_target']['target_type_label'], '群聊')
        self.assertEqual(result['account_room_plan'][0]['im_target_id'], '9001139483')
        self.assertEqual(result['account_room_plan'][0]['message_preview'], 'QAFlow_17701321000_88001_1')

    def test_im_room_target_can_be_derived_from_selected_room(self):
        target = BusinessLoadTaskViewSet()._build_im_target({
            'target_type': 'room',
            'target_rooms': [
                {
                    'channel_id': '1001704489',
                    'channel_name': '测试语音房',
                    'channel_type': -98,
                }
            ],
        })

        self.assertEqual(target['target_id'], '1001704489')
        self.assertEqual(target['target_name'], '测试语音房')

    def test_im_runner_accounts_reuse_business_context_credentials(self):
        accounts = BusinessLoadTaskViewSet()._build_im_runner_accounts(
            [{'phone': '18800001001'}],
            [{'phone': '18800001001', 'user_id': 154454847, 'token': 'token-1'}],
        )

        self.assertEqual(accounts, [{
            'phone': '18800001001',
            'user_id': 154454847,
            'token': 'token-1',
        }])

    def test_im_room_cli_trial_stops_before_runner_when_business_context_fails(self):
        view = BusinessLoadTaskViewSet()
        task = BusinessLoadTask.objects.create(
            name='IM 入场失败',
            scenario_type='im_message_flood',
            environment='test',
            business_domain='im',
            account_count=1,
            created_by=self.user,
            config={
                'base_url': 'https://business.example.com',
                'server_id': 55984,
                'target_type': 'room',
                'target_id': '1001704489',
                'target_name': '测试语音房',
                'biz_type': 5,
                'real_traffic_enabled': True,
                'runner_path': 'C:\\Windows\\System32\\cmd.exe',
            },
            capability_chain=[{'key': 'im_send_message_loop'}],
            status='ready',
        )
        account_plan = [{
            'account_no': '17701321000',
            'phone': '17701321000',
            'channel_id': '1001704489',
            'channel_type': -98,
        }]

        with patch.object(view, '_login_business_account', side_effect=ValidationError('登录失败')):
            with patch('apps.data_factory.views.subprocess.run') as mocked_runner:
                result = view._run_im_cli_trial_execution(
                    task,
                    task.config,
                    view._build_im_target(task.config),
                    account_plan,
                    0,
                    timezone.now(),
                )

        self.assertFalse(result['passed'])
        self.assertFalse(result['safety']['runner_called'])
        self.assertEqual(result['summary']['send_attempts'], 0)
        mocked_runner.assert_not_called()

