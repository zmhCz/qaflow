"""Composable business load-test task definitions."""

from copy import deepcopy

from django.conf import settings


DEFAULT_BASE_URL = getattr(settings, 'DATA_FACTORY_DEFAULT_BASE_URL', '') or ''
DEFAULT_IM_RUNNER_PATH = getattr(settings, 'DATA_FACTORY_IM_RUNNER_PATH', '') or ''


SCENARIO_DEFINITIONS = {
    'room_list_load': {
        'label': '房间列表压测',
        'description': '批量登录账号后查询社区房间列表，关注接口响应、空列表、分页和错误率。',
        'business_domain': 'room',
        'capabilities': ['login', 'enter_community', 'follow_community', 'fetch_room_list'],
        'default_config': {
            'base_url': DEFAULT_BASE_URL,
            'server_id': 55984,
            'account_count': 10,
            'duration_seconds': 60,
            'request_rate_per_second': 5,
            'page_size': 100,
            'max_rooms': 1000,
            'room_selection_mode': 'auto',
            'target_rooms': [],
            'room_assignment_mode': 'round_robin',
            'dry_run': True,
        },
    },
    'voice_room_online': {
        'label': '语音房在线保活',
        'description': '常驻用户进房并发送心跳，验证房间在线、心跳和恢复能力。',
        'business_domain': 'room',
        'capabilities': [
            'login',
            'enter_community',
            'follow_community',
            'fetch_room_list',
            'enter_room',
            'heartbeat_keepalive',
            'leave_room',
        ],
        'default_config': {
            'base_url': DEFAULT_BASE_URL,
            'server_id': 55984,
            'account_count': 10,
            'resident_user_count': 10,
            'transient_user_count': 0,
            'duration_seconds': 300,
            'users_per_room': 2,
            'room_selection_mode': 'manual',
            'target_rooms': [],
            'room_assignment_mode': 'round_robin',
            'heartbeat_interval_seconds': 30,
            'enter_rate_per_second': 5,
            'dry_run': True,
        },
    },
    'room_enter_leave': {
        'label': '进退房压测',
        'description': '流动用户反复进房、离房或切换房间，验证房间容量、进退房稳定性。',
        'business_domain': 'room',
        'capabilities': [
            'login',
            'enter_community',
            'follow_community',
            'fetch_room_list',
            'enter_room',
            'leave_room',
        ],
        'default_config': {
            'base_url': DEFAULT_BASE_URL,
            'server_id': 55984,
            'account_count': 10,
            'duration_seconds': 180,
            'transient_user_count': 10,
            'users_per_room': 2,
            'room_selection_mode': 'manual',
            'target_rooms': [],
            'room_assignment_mode': 'round_robin',
            'stay_min_seconds': 6,
            'stay_max_seconds': 12,
            'enter_rate_per_second': 5,
            'leave_rate_per_second': 6,
            'dry_run': True,
        },
    },
    'community_follow': {
        'label': '关注社区压测',
        'description': '批量登录并关注社区，验证社区关注链路的幂等性和错误率。',
        'business_domain': 'community',
        'capabilities': ['login', 'enter_community', 'follow_community'],
        'default_config': {
            'base_url': DEFAULT_BASE_URL,
            'server_id': 55984,
            'account_count': 10,
            'request_rate_per_second': 3,
            'dry_run': True,
        },
    },
    'community_activity_simulation': {
        'label': '社区活跃模拟',
        'description': '固定用户占住房间并心跳保活，流动用户持续进出或切换房间，用于制造社区维度的房间列表动态变化。',
        'business_domain': 'community',
        'capabilities': [
            'login',
            'enter_community',
            'follow_community',
            'fetch_room_list',
            'enter_room',
            'heartbeat_keepalive',
            'switch_room',
            'leave_room',
        ],
        'default_config': {
            'base_url': DEFAULT_BASE_URL,
            'server_id': 55984,
            'account_count': 20,
            'resident_user_count': 10,
            'transient_user_count': 10,
            'duration_seconds': 300,
            'users_per_room': 2,
            'room_selection_mode': 'manual',
            'target_rooms': [],
            'room_assignment_mode': 'round_robin',
            'heartbeat_interval_seconds': 30,
            'transient_stay_min_seconds': 3,
            'transient_stay_max_seconds': 5,
            'transient_to_resident_ratio': 80,
            'transient_switch_ratio': 55,
            'enter_rate_per_second': 5,
            'leave_rate_per_second': 6,
            'room_failure_cooldown_seconds': 45,
            'cleanup_after_stop': True,
            'dry_run': True,
        },
    },
    'im_message_flood': {
        'label': 'IM 消息刷屏压测',
        'description': '批量账号登录 IM 网关后，对单聊、群聊、语音房或派对房目标发送文本消息，用于验证 IM 链路吞吐、ACK、断连和限流表现。',
        'business_domain': 'im',
        'capabilities': [
            'login',
            'enter_community',
            'follow_community',
            'enter_room',
            'im_fetch_config',
            'im_connect',
            'im_join_target',
            'im_send_message_loop',
            'im_collect_metrics',
        ],
        'default_config': {
            'base_url': DEFAULT_BASE_URL,
            'account_count': 5,
            'duration_seconds': 30,
            'target_type': 'room',
            'target_id': '',
            'target_name': '',
            'biz_type': 5,
            'message_template': 'QAFlow_IM_{{run_id}}_{{account_no}}_{{sequence}}_{{timestamp}}',
            'interval_ms': 1000,
            'login_interval_ms': 100,
            'auto_reconnect': True,
            'dry_run': True,
            'runner_status': 'cli_adapter',
            'real_traffic_enabled': False,
            'runner_path': DEFAULT_IM_RUNNER_PATH,
            'runner_timeout_seconds': 120,
        },
    },
    'team_recruit_publish': {
        'label': '发布组队压测',
        'description': '按真实业务链路进入社区和语音房，调用发布组队接口后发送组队大厅 IM 卡片通知，并按任务持续时间心跳保活，结束后关闭组队、退出房间。',
        'business_domain': 'team',
        'capabilities': [
            'login',
            'enter_community',
            'follow_community',
            'fetch_room_list',
            'enter_room',
            'heartbeat_keepalive',
            'publish_team',
            'im_send_notification',
            'close_team',
            'leave_room',
        ],
        'default_config': {
            'base_url': DEFAULT_BASE_URL,
            'server_id': 55984,
            'account_count': 1,
            'duration_seconds': 30,
            'room_selection_mode': 'manual',
            'target_rooms': [],
            'room_assignment_mode': 'round_robin',
            'team_message_template': 'QAFlow_team_{{run_id}}_{{account_no}}_{{timestamp}}',
            'team_duration_minutes': 1,
            'team_max_members_num': 2,
            'team_mode': '全部区服',
            'team_publish_concurrency': 1,
            'team_publish_interval_ms': 500,
            'team_publish_reliable_visible': True,
            'team_visibility_wait_seconds': 10,
            'team_keepalive_after_notify': True,
            'runner_status': 'cli_adapter',
            'runner_path': DEFAULT_IM_RUNNER_PATH,
            'runner_timeout_seconds': 120,
            'real_traffic_enabled': True,
            'dry_run': True,
        },
    },
}


CAPABILITY_DEFINITIONS = {
    'login': {
        'label': '账号登录',
        'source': 'business_load.adapters.voice_room::login',
        'endpoint': '/webapi/u-nnpc/registerLogin',
    },
    'enter_community': {
        'label': '进入社区',
        'source': 'business_load.adapters.voice_room::enter_community',
        'endpoint': '/webapi/nchannel/channel/business/enterPersonalTopicServerByIdV2',
    },
    'follow_community': {
        'label': '关注社区',
        'source': 'business_load.adapters.voice_room::follow_community',
        'endpoint': '/webapi/nchannel/channel/business/joinPersonalServer',
    },
    'fetch_room_list': {
        'label': '查询房间列表',
        'source': 'business_load.adapters.voice_room::fetch_room_list',
        'endpoint': '/webapi/nchannel/server/channel/pageQuery',
        'cursor_field': 'sortIndexNum',
        'dedupe_field': 'channelId',
        'note': '实测 sortIndex 可能为空，分页应使用 sortIndexNum，并按 channelId 去重。',
    },
    'enter_room': {
        'label': '进入房间',
        'source': 'business_load.adapters.voice_room::enter_room',
        'endpoint': '/webapi/nchannel/channel/business/enterPersonalTopicChannelValidate/{serverId}/{channelId}',
    },
    'leave_room': {
        'label': '离开房间',
        'source': 'business_load.adapters.voice_room::leave_room',
        'endpoint': '/webapi/nchannel/channel/business/leavePersonalServerTopicChannel',
    },
    'heartbeat_keepalive': {
        'label': '心跳保活',
        'source': 'business_load.adapters.voice_room::heartbeat',
        'endpoint': '/webapi/nn-status/client/channel/heartBeat',
    },
    'switch_room': {
        'label': '流动切房',
        'source': 'business_load.scheduler::transient_loop',
        'endpoint': 'enter_room / leave_room',
    },
    'im_fetch_config': {
        'label': '获取 IM 网关',
        'source': 'business_load.adapters.im::fetch_config',
        'endpoint': '/imapi/api/getClientConfig?sourceGroup=gateway_group_public',
    },
    'im_connect': {
        'label': '建立 TCP 连接',
        'source': 'business_load.adapters.im::connect',
        'endpoint': 'tcp://{gateway_host}:{gateway_port}',
    },
    'im_join_target': {
        'label': '进入/订阅目标',
        'source': 'business_load.adapters.im::join_target',
        'endpoint': 'IM Cmd JoinGroup/JoinRoom/JoinPartyRoom',
    },
    'im_send_message_loop': {
        'label': '循环发送消息',
        'source': 'business_load.adapters.im::send_message_loop',
        'endpoint': 'IM SendMsg',
    },
    'im_collect_metrics': {
        'label': '采集发送指标',
        'source': 'business_load.adapters.im::collect_metrics',
        'endpoint': 'event://stress-stats',
    },
    'publish_team': {
        'label': '发布组队',
        'source': 'nn_biz_room/RoomApiService.kt::addTeam',
        'endpoint': '/webapi/nchannel/channel/business/addTeam',
    },
    'im_send_notification': {
        'label': '发送组队大厅通知',
        'source': 'business_load.adapters.im::send_notification',
        'endpoint': 'IM NotifyMessage(Group)',
    },
    'close_team': {
        'label': '关闭组队',
        'source': 'nn_biz_room/RoomApiService.kt::closeTeam',
        'endpoint': '/webapi/nchannel/channel/business/closeTeam',
    },
}


def get_scenario_options():
    """Return scenario options for frontend selectors."""
    return [
        {
            'value': value,
            'label': definition['label'],
            'description': definition['description'],
            'business_domain': definition['business_domain'],
            'default_config': deepcopy(definition['default_config']),
            'capabilities': build_capability_chain(value),
        }
        for value, definition in SCENARIO_DEFINITIONS.items()
    ]


def build_default_config(scenario_type):
    definition = SCENARIO_DEFINITIONS.get(scenario_type)
    if not definition:
        return {}
    return deepcopy(definition['default_config'])


def build_capability_chain(scenario_type):
    definition = SCENARIO_DEFINITIONS.get(scenario_type)
    if not definition:
        return []

    chain = []
    for order, capability_key in enumerate(definition['capabilities'], start=1):
        capability = CAPABILITY_DEFINITIONS.get(capability_key, {})
        chain.append({
            'key': capability_key,
            'order': order,
            'label': capability.get('label', capability_key),
            'endpoint': capability.get('endpoint', ''),
            'source': capability.get('source', ''),
            'cursor_field': capability.get('cursor_field', ''),
            'dedupe_field': capability.get('dedupe_field', ''),
            'note': capability.get('note', ''),
        })
    return chain
