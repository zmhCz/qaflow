# -*- coding: utf-8 -*-
"""Team-readable report summary builders for APP automation executions."""
import glob
import json
import os
import re

from django.conf import settings
from django.utils import timezone


def _local_time(value):
    if not value:
        return '-'
    return timezone.localtime(value).strftime('%Y-%m-%d %H:%M:%S')


def _duration(seconds):
    if not seconds:
        return '-'
    seconds = int(seconds)
    if seconds < 60:
        return f'{seconds}秒'
    return f'{seconds // 60}分{seconds % 60}秒'


def _results_dir(execution_id):
    return os.path.join(
        settings.MEDIA_ROOT,
        'app-automation',
        'allure-results',
        f'execution_{execution_id}',
    )


def _status_text(execution):
    if execution.status == 'completed':
        return {
            'passed': '通过',
            'failed': '失败',
            'skipped': '跳过',
        }.get(execution.result or '', '已完成')
    return {
        'pending': '等待中',
        'running': '执行中',
        'error': '执行异常',
        'stopped': '已停止',
    }.get(execution.status, execution.status or '-')


def _conclusion(execution):
    if execution.status == 'completed' and execution.result == 'passed':
        return {
            'level': 'success',
            'text': '通过',
            'suggestion': '本次执行通过，可作为当前版本回归参考。',
        }
    if execution.status == 'completed' and execution.result == 'failed':
        return {
            'level': 'danger',
            'text': '不通过',
            'suggestion': '存在失败步骤，建议先定位失败原因，再决定是否继续发布或回归。',
        }
    if execution.status == 'error':
        return {
            'level': 'danger',
            'text': '执行异常',
            'suggestion': '执行过程异常，优先排查设备、环境、脚本或平台执行器。',
        }
    if execution.status == 'stopped':
        return {
            'level': 'warning',
            'text': '已停止',
            'suggestion': '本次执行被中断，结果不建议作为质量结论。',
        }
    return {
        'level': 'info',
        'text': _status_text(execution),
        'suggestion': '当前执行尚未形成最终质量结论。',
    }


def _step_type_text(step_type):
    mapping = {
        'click': '点击',
        'touch': '点击',
        'double_click': '双击',
        'long_press': '长按',
        'drag': '拖拽',
        'input': '输入',
        'swipe': '滑动',
        'swipe_to': '滑动查找',
        'wait': '等待',
        'sleep': '等待',
        'assert': '断言',
        'foreach_assert': '列表断言',
        'image_exists_click': '图片存在后点击',
        'image_exists_click_chain': '图片链式点击',
        'click_available_voice_room': '点击可进入语音房',
        'assert_voice_room_type': '断言语音房类型',
        'click_member_hall_entry': '点击全员大厅入口',
        'assert_member_hall_opened': '断言全员大厅已打开',
        'assert_hall_message_sent': '断言大厅消息已发送',
        'assert_logout_confirm_dialog': '断言退出登录确认弹窗',
        'back_until': '返回直到目标页',
        'handle_slider': '滑块处理',
        'slider': '滑块处理',
        'set_variable': '设置变量',
        'unset_variable': '清理变量',
        'extract_output': '提取输出',
        'screenshot': '截图',
        'snapshot': '页面快照',
        'api_request': '接口请求',
        'if': '条件分支',
        'loop': '循环',
        'sequence': '步骤组',
        'try': '异常兜底',
    }
    return mapping.get(step_type or '', step_type or '未知')


def _normalize_ui_flow(test_case):
    if not test_case:
        return []
    ui_flow = test_case.ui_flow or []
    if isinstance(ui_flow, list):
        return ui_flow
    if isinstance(ui_flow, dict):
        for key in ('steps', 'ui_flow', 'flow'):
            value = ui_flow.get(key)
            if isinstance(value, list):
                return value
    return []


def _parse_allure_step_name(name, fallback_index):
    raw_name = name or ''
    match = re.match(r'^(?:步骤|姝ラ)\s*(\d+)\s*[-:：]?\s*(.+)$', raw_name)
    if match:
        return int(match.group(1)), match.group(2).strip()
    return fallback_index, raw_name or f'步骤 {fallback_index}'


def _flatten_allure_steps(steps):
    flattened = []
    for step in steps or []:
        children = step.get('steps') or []
        if children:
            flattened.extend(_flatten_allure_steps(children))
        else:
            flattened.append(step)
    return flattened


def _status_details(step):
    details = step.get('statusDetails') or {}
    return {
        'message': details.get('message') or '',
        'trace': details.get('trace') or '',
    }


def _pick_allure_result_file(execution):
    results_dir = _results_dir(execution.id)
    if not os.path.isdir(results_dir):
        return '', {}

    candidates = []
    for result_file in glob.glob(os.path.join(results_dir, '*-result.json')):
        try:
            with open(result_file, 'r', encoding='utf-8') as file:
                data = json.load(file)
        except Exception:
            continue
        score = 0
        text = json.dumps(data, ensure_ascii=False)
        if 'test_execute_ui_flow' in data.get('fullName', ''):
            score += 5
        if '执行 UI Flow' in text or '鎵ц UI Flow' in text:
            score += 4
        if data.get('status') in ('failed', 'broken'):
            score += 2
        candidates.append((score, result_file, data))

    if not candidates:
        return '', {}
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1], candidates[0][2]


def _allure_ui_step_outline(execution):
    result_file, data = _pick_allure_result_file(execution)
    if not data:
        return None

    top_steps = data.get('steps') or []
    ui_flow_step = next(
        (
            step for step in top_steps
            if step.get('name') in ('执行 UI Flow', '鎵ц UI Flow')
            or 'UI Flow' in (step.get('name') or '')
        ),
        None,
    )
    raw_steps = (ui_flow_step or {}).get('steps') or []
    if not raw_steps:
        return None

    items = []
    failed_step = None
    passed = 0
    failed = 0
    for fallback_index, raw_step in enumerate(_flatten_allure_steps(raw_steps), 1):
        index, parsed_name = _parse_allure_step_name(raw_step.get('name'), fallback_index)
        status = (raw_step.get('status') or '').lower()
        if status == 'passed':
            display_status = 'passed'
            status_text = '通过'
            passed += 1
        elif status in ('failed', 'broken'):
            display_status = 'failed'
            status_text = '失败' if status == 'failed' else '异常'
            failed += 1
        elif status == 'skipped':
            display_status = 'skipped'
            status_text = '跳过'
        else:
            display_status = 'unknown'
            status_text = '未确认'

        start = raw_step.get('start')
        stop = raw_step.get('stop')
        item = {
            'index': index,
            'name': parsed_name,
            'raw_name': raw_step.get('name') or '',
            'type': '',
            'type_text': '',
            'status': display_status,
            'status_text': status_text,
            'duration_ms': max(0, int(stop - start)) if start and stop else None,
            'source': 'allure',
            **_status_details(raw_step),
        }
        items.append(item)
        if display_status == 'failed' and not failed_step:
            failed_step = item

    items.sort(key=lambda item: item.get('index') or 0)
    status_details = data.get('statusDetails') or {}
    return {
        'total': len(items),
        'planned_total': len(items),
        'passed': passed,
        'failed': failed,
        'probable_failed_index': failed_step.get('index') if failed_step else None,
        'failed_step': failed_step,
        'items': items,
        'truncated': False,
        'source': 'allure',
        'note': '步骤状态来自 Allure 原始执行结果，失败位置与 Allure 保持一致。',
        'error_message': (failed_step or {}).get('message') or status_details.get('message') or '',
        'result_file': os.path.basename(result_file),
    }


def _step_name(step, index):
    return step.get('name') or _step_type_text(step.get('type')) or f'步骤 {index}'


def _step_outline(execution):
    allure_outline = _allure_ui_step_outline(execution)
    ui_flow = _normalize_ui_flow(execution.test_case)
    type_by_index = {
        index: step.get('type') or ''
        for index, step in enumerate(ui_flow, 1)
    }
    if allure_outline:
        for item in allure_outline.get('items', []):
            step_type = type_by_index.get(item.get('index')) or ''
            item['type'] = step_type
            item['type_text'] = _step_type_text(step_type) if step_type else '-'
        failed_step = allure_outline.get('failed_step')
        if failed_step:
            step_type = type_by_index.get(failed_step.get('index')) or ''
            failed_step['type'] = step_type
            failed_step['type_text'] = _step_type_text(step_type) if step_type else '-'
        return allure_outline

    total = execution.total_steps or len(ui_flow) or 0
    passed = execution.passed_steps or 0
    failed = execution.failed_steps or 0
    probable_failed_index = passed + 1 if failed and ui_flow else None
    items = []

    for index, step in enumerate(ui_flow[:80], 1):
        step_type = step.get('type') or ''
        status = 'pending'
        status_text = '未执行/未知'
        if failed:
            if index <= passed:
                status = 'passed'
                status_text = '通过'
            elif index == probable_failed_index:
                status = 'failed'
                status_text = '疑似失败'
            else:
                status = 'unknown'
                status_text = '未确认'
        elif total and index <= passed:
            status = 'passed'
            status_text = '通过'

        items.append({
            'index': index,
            'name': _step_name(step, index),
            'type': step_type,
            'type_text': _step_type_text(step_type),
            'status': status,
            'status_text': status_text,
        })

    failed_step = None
    if probable_failed_index and 1 <= probable_failed_index <= len(items):
        failed_step = items[probable_failed_index - 1]

    return {
        'total': total,
        'planned_total': len(ui_flow),
        'passed': passed,
        'failed': failed,
        'probable_failed_index': probable_failed_index,
        'failed_step': failed_step,
        'items': items,
        'truncated': len(ui_flow) > len(items),
        'source': 'inferred',
        'note': '当前基于执行统计推断疑似失败步骤；建议结合截图、XML、logcat 继续确认。' if failed else '',
    }


def _profile_from_step(step_outline):
    failed_step = (step_outline or {}).get('failed_step') or {}
    step_type = failed_step.get('type') or ''
    if step_type in ('click', 'touch', 'double_click', 'long_press', 'drag', 'image_exists_click', 'image_exists_click_chain'):
        return 'element'
    if step_type == 'input':
        return 'input'
    if step_type in ('assert', 'foreach_assert'):
        return 'assertion'
    if step_type in ('swipe', 'swipe_to'):
        return 'gesture'
    if step_type in ('wait', 'sleep'):
        return 'timeout'
    if step_type == 'api_request':
        return 'api'
    return ''


def _profiles():
    return {
        'element': {
            'type': '元素定位问题',
            'category': 'element_locator',
            'severity': 'high',
            'owner': '语义元素 / 页面状态',
            'suggestion': '优先确认目标元素是否仍在当前页面，元素定位是否跨设备稳定，是否需要等待或先滑动。',
            'actions': ['查看失败截图确认实际页面', '复验对应语义元素', '补充文本/resource-id/bounds/坐标兜底', '确认前置页面是否正确'],
        },
        'input': {
            'type': '输入失败',
            'category': 'input',
            'severity': 'high',
            'owner': '输入框元素 / 输入法 / 测试数据',
            'suggestion': '确认输入框已获得焦点、输入内容不为空，并检查当前设备对 ADB 输入的兼容性。',
            'actions': ['确认步骤输入值不为空', '确认点击输入框后光标出现', '中文或特殊字符优先使用剪贴板输入兜底', '检查是否被弹窗或键盘遮挡'],
        },
        'assertion': {
            'type': '断言失败',
            'category': 'assertion',
            'severity': 'medium',
            'owner': '业务状态 / 断言条件',
            'suggestion': '动作可能已完成，但页面结果与预期不一致；需要区分业务缺陷、测试数据问题或断言过严。',
            'actions': ['确认实际页面文案/状态', '检查变量渲染后的预期值', '列表场景优先使用滑动查找断言', '避免绑定易变昵称或数量'],
        },
        'timeout': {
            'type': '等待超时',
            'category': 'timeout',
            'severity': 'medium',
            'owner': '页面加载 / 网络 / 等待策略',
            'suggestion': '目标页面或元素未在预期时间内出现，先区分页面慢、网络慢还是前置步骤未生效。',
            'actions': ['适当增加等待时间', '增加页面就绪断言', '检查网络和接口环境', '确认上一步点击是否真的生效'],
        },
        'device': {
            'type': '设备/连接问题',
            'category': 'device',
            'severity': 'critical',
            'owner': '设备 / ADB / 执行环境',
            'suggestion': '通常不代表业务失败，优先恢复设备连接和执行环境后重跑。',
            'actions': ['检查 adb devices 是否在线', '确认设备未锁屏/断线', '重新运行设备健康检查', '必要时重新插拔 USB 或重启设备'],
        },
        'app_crash': {
            'type': 'APP 崩溃/ANR',
            'category': 'app_crash',
            'severity': 'critical',
            'owner': 'APP 稳定性',
            'suggestion': '如果可稳定复现，应作为 APP 稳定性问题优先处理，并附带 logcat 和复现步骤。',
            'actions': ['查看失败截图和 logcat', '确认是否出现系统崩溃弹窗', '记录机型/系统版本/包名版本', '导出排障附件提交给开发'],
        },
        'gesture': {
            'type': '手势/滑动问题',
            'category': 'gesture',
            'severity': 'medium',
            'owner': '手势参数 / 页面滚动容器',
            'suggestion': '滑动类步骤容易受分辨率和滚动容器影响，建议使用比例坐标并在滑动后增加断言确认。',
            'actions': ['检查起止点是否使用比例坐标', '确认滑动区域是可滚动容器', '增加滑动后等待', '必要时改成滑动查找元素'],
        },
        'api': {
            'type': '接口/数据准备问题',
            'category': 'api_data',
            'severity': 'medium',
            'owner': '测试数据 / 接口环境',
            'suggestion': '接口步骤失败通常会影响后续 UI 状态，建议先确认数据是否构造成功。',
            'actions': ['查看接口响应状态码和响应体', '确认环境变量和鉴权信息', '检查测试数据是否可重复创建/清理'],
        },
        'script': {
            'type': '脚本/平台配置问题',
            'category': 'script',
            'severity': 'high',
            'owner': '用例编排 / 平台执行器',
            'suggestion': '多见于步骤配置不完整、动作类型不支持或参数格式错误，优先回到用例编排页检查该步骤。',
            'actions': ['检查步骤类型和必填参数', '确认元素和变量引用存在', '查看平台错误堆栈', '简化为最小复现步骤'],
        },
        'unknown': {
            'type': '执行异常',
            'category': 'unknown',
            'severity': 'medium',
            'owner': '待排查',
            'suggestion': '错误信息不足，建议结合失败截图、Allure 原始报告、排障附件和平台日志继续定位。',
            'actions': ['打开 Allure 原始报告', '查看最后一张截图', '导出排障附件', '必要时重跑确认是否偶发'],
        },
    }


def _failure_profile(execution, step_outline=None):
    raw_message = execution.error_message or (step_outline or {}).get('error_message') or ''
    failed_step_message = ((step_outline or {}).get('failed_step') or {}).get('message') or ''
    message = f'{raw_message}\n{failed_step_message}'.lower()
    inferred = _profile_from_step(step_outline or {})
    profiles = _profiles()

    if not message:
        if execution.failed_steps:
            key = inferred or 'unknown'
        else:
            return {
                'type': '',
                'category': '',
                'severity': 'info',
                'owner': '',
                'suggestion': '',
                'actions': [],
                'is_blocking': False,
            }
    elif any(keyword in message for keyword in ['adb', 'device', 'offline', 'unauthorized', '设备', '连接', 'screenshot']):
        key = 'device'
    elif any(keyword in message for keyword in ['crash', 'anr', '崩溃', '无响应', 'fatal exception']):
        key = 'app_crash'
    elif any(keyword in message for keyword in ['input text', 'sendtext', '输入', 'nullpointerexception']):
        key = 'input'
    elif any(keyword in message for keyword in ['element', 'selector', 'bounds', '定位', '找不到', 'clickable']):
        key = 'element'
    elif any(keyword in message for keyword in ['assert', '断言', 'expected', '预期']):
        key = 'assertion'
    elif any(keyword in message for keyword in ['timeout', 'timed out', '超时']):
        key = 'timeout'
    elif any(keyword in message for keyword in ['swipe', 'gesture', '滑动', '手势']):
        key = 'gesture'
    elif any(keyword in message for keyword in ['api', 'http', 'request', '接口']):
        key = 'api'
    elif any(keyword in message for keyword in ['valueerror', 'unknown action', '未知动作', '配置']):
        key = 'script'
    else:
        key = inferred or 'unknown'

    profile = dict(profiles[key])
    profile['is_blocking'] = profile['severity'] in ('high', 'critical')
    failed_step = (step_outline or {}).get('failed_step')
    if failed_step:
        profile['probable_failed_step'] = failed_step
    return profile


def _logcat_summary(execution, request=None):
    results_dir = _results_dir(execution.id)
    files = []
    if os.path.isdir(results_dir):
        for name in os.listdir(results_dir):
            lower_name = name.lower()
            if 'logcat' in lower_name and lower_name.endswith('.txt'):
                files.append(name)

    download_url = ''
    if files:
        path = f'/api/app-automation/executions/{execution.id}/download-logcat/'
        download_url = request.build_absolute_uri(path) if request else path

    return {
        'available': bool(files),
        'file_count': len(files),
        'download_url': download_url,
    }


def _artifact_summary(execution, request=None):
    results_dir = _results_dir(execution.id)
    result_file, data = _pick_allure_result_file(execution)
    attachments = []

    def attachment_url(path):
        if not request or not path or not os.path.isfile(path):
            return ''
        try:
            rel_path = os.path.relpath(path, settings.MEDIA_ROOT).replace(os.sep, '/')
        except ValueError:
            return ''
        media_url = getattr(settings, 'MEDIA_URL', '/media/')
        return request.build_absolute_uri(f"{media_url.rstrip('/')}/{rel_path}")

    def collect_from_step(step):
        step_index, step_name = _parse_allure_step_name(step.get('name'), 0)
        for attachment in step.get('attachments') or []:
            item = dict(attachment)
            item['_step_index'] = step_index or None
            item['_step_name'] = step_name
            attachments.append(item)
        for child in step.get('steps') or []:
            collect_from_step(child)

    if data:
        for attachment in data.get('attachments') or []:
            attachments.append(attachment)
        for step in data.get('steps') or []:
            collect_from_step(step)

    existing = []
    for attachment in attachments:
        source = attachment.get('source') or ''
        path = os.path.abspath(os.path.join(results_dir, source)) if source else ''
        if path and os.path.isfile(path) and path.startswith(os.path.abspath(results_dir)):
            is_screenshot = 'image' in (attachment.get('type') or '') or source.lower().endswith(('.png', '.jpg', '.jpeg'))
            existing.append({
                'name': attachment.get('name') or os.path.basename(source),
                'source': source,
                'type': attachment.get('type') or '',
                'size': os.path.getsize(path),
                'url': attachment_url(path) if is_screenshot else '',
                'is_screenshot': is_screenshot,
                'step_index': attachment.get('_step_index'),
                'step_name': attachment.get('_step_name') or '',
            })

    lower_text = '\n'.join(f"{item['name']} {item['source']} {item['type']}".lower() for item in existing)
    counts = {
        'total': len(existing),
        'screenshots': sum(1 for item in existing if 'image' in item['type'] or item['source'].lower().endswith(('.png', '.jpg', '.jpeg'))),
        'xml': sum(1 for item in existing if item['source'].lower().endswith('.xml') or 'xml' in item['name'].lower()),
        'logcat': lower_text.count('logcat'),
    }
    download_url = ''
    if existing:
        path = f'/api/app-automation/executions/{execution.id}/download-evidence/'
        download_url = request.build_absolute_uri(path) if request else path
    return {
        'available': bool(existing),
        'counts': counts,
        'items': existing[:40],
        'screenshots': [item for item in existing if item.get('is_screenshot')][:80],
        'download_url': download_url,
        'result_file': os.path.basename(result_file) if result_file else '',
    }


def _screenshot_phase(name):
    text = str(name or '')
    if '失败前' in text or 'error' in text.lower():
        return 'error'
    if '操作前' in text or 'before' in text.lower():
        return 'before'
    if '操作后' in text or 'after' in text.lower():
        return 'after'
    return 'screenshot'


def _visual_evidence_summary(artifacts):
    screenshots = [
        item for item in (artifacts or {}).get('screenshots') or []
        if item.get('url') and not str(item.get('name') or '').startswith('关键截图-')
    ]
    if not screenshots:
        return {
            'available': False,
            'total': 0,
            'groups': [],
            'has_more': False,
        }

    grouped = {}
    for item in screenshots:
        step_index = item.get('step_index') or 0
        key = step_index or item.get('name') or item.get('source')
        if key not in grouped:
            grouped[key] = {
                'step_index': step_index,
                'step_name': item.get('step_name') or item.get('name') or '执行截图',
                'items': [],
            }
        grouped[key]['items'].append({
            'name': item.get('name') or '',
            'phase': _screenshot_phase(item.get('name')),
            'url': item.get('url') or '',
            'size': item.get('size') or 0,
        })

    phase_order = {'before': 1, 'error': 2, 'after': 3, 'screenshot': 4}
    groups = list(grouped.values())
    for group in groups:
        group['items'].sort(key=lambda item: phase_order.get(item.get('phase'), 9))
    groups.sort(key=lambda group: group.get('step_index') or 9999)

    max_groups = 6
    return {
        'available': True,
        'total': len(screenshots),
        'groups': groups[:max_groups],
        'has_more': len(groups) > max_groups,
    }


def _performance_summary(metrics):
    metrics = metrics or {}
    if not metrics.get('enabled'):
        return {'enabled': False, 'items': [], 'warnings': [], 'analysis': [], 'series': []}

    items = []
    warnings = []
    analysis = []
    cpu = metrics.get('cpu') or {}
    memory = metrics.get('memory_pss_mb') or {}
    battery_temp = metrics.get('battery_temperature_c') or {}
    battery_level = metrics.get('battery_level') or {}

    for value, label, unit in [
        (cpu.get('avg'), 'CPU 平均', '%'),
        (cpu.get('max'), 'CPU 峰值', '%'),
        (memory.get('avg'), '内存平均', 'MB'),
        (memory.get('max'), '内存峰值', 'MB'),
        (battery_temp.get('max'), '最高温度', '℃'),
    ]:
        if value not in (None, ''):
            items.append({'label': label, 'value': value, 'unit': unit})

    cpu_max = cpu.get('max') or 0
    cpu_avg = cpu.get('avg') or 0
    memory_avg = memory.get('avg') or 0
    memory_max = memory.get('max') or 0
    temp_max = battery_temp.get('max') or 0

    battery_drop = None
    if battery_level.get('max') is not None and battery_level.get('min') is not None:
        battery_drop = round(battery_level.get('max') - battery_level.get('min'), 2)

    if cpu_max >= 80:
        warnings.append('CPU 峰值偏高')
        analysis.append('CPU 峰值超过 80%，建议关注页面渲染、轮询、动画或后台任务。')
    elif cpu_avg >= 45:
        warnings.append('CPU 平均值偏高')
        analysis.append('CPU 平均值偏高，长流程执行时可能出现发热或掉帧。')
    elif cpu.get('avg') is not None:
        analysis.append('CPU 使用整体处于可接受范围。')

    if memory_avg and memory_max and memory_max - memory_avg >= max(memory_avg * 0.35, 120):
        warnings.append('内存波动偏大')
        analysis.append('内存峰值明显高于平均值，建议观察是否存在资源未释放或图片缓存增长。')
    elif memory.get('avg') is not None:
        analysis.append('内存走势暂未发现明显异常。')

    if temp_max >= 42:
        warnings.append('设备温度偏高')
        analysis.append('设备温度较高，性能结论可能受到机身温度和降频影响。')

    if battery_drop is not None and battery_drop >= 3:
        warnings.append('电量下降较快')
        analysis.append(f'本次执行电量下降约 {battery_drop}%，建议长时间回归时关注功耗。')

    samples = metrics.get('samples') or []
    series = []
    for index, sample in enumerate(samples[-120:]):
        label = sample.get('timestamp') or str(index + 1)
        series.append({
            'label': label[11:19] if 'T' in label and len(label) >= 19 else str(index + 1),
            'cpu': sample.get('cpu_percent'),
            'memory': sample.get('memory_pss_mb'),
            'temperature': sample.get('battery_temperature_c'),
            'battery': sample.get('battery_level'),
        })

    return {
        'enabled': True,
        'items': items,
        'warnings': warnings,
        'analysis': analysis,
        'series': series,
        'sample_count': metrics.get('sample_count') or len(samples),
        'duration': metrics.get('duration'),
        'errors': metrics.get('errors') or [],
    }


def build_execution_report_summary(execution, request=None):
    test_case = execution.test_case
    project = getattr(test_case, 'project', None)
    app_package = getattr(test_case, 'app_package', None)
    device = execution.device
    step_outline = _step_outline(execution)
    total = step_outline.get('total') or execution.total_steps or 0
    passed = step_outline.get('passed') if step_outline.get('source') == 'allure' else execution.passed_steps
    failed = step_outline.get('failed') if step_outline.get('source') == 'allure' else execution.failed_steps
    passed = passed or 0
    failed = failed or 0
    pass_rate = round((passed / total) * 100, 2) if total else 0
    report_url = ''
    if execution.report_path:
        path = f'/api/app-automation/executions/{execution.id}/report/'
        report_url = request.build_absolute_uri(path) if request else path

    conclusion = _conclusion(execution)
    diagnosis = _failure_profile(execution, step_outline)
    artifacts = _artifact_summary(execution, request=request)
    failure_message = (
        execution.error_message
        or step_outline.get('error_message')
        or diagnosis.get('probable_failed_step', {}).get('message')
        or ''
    )
    summary = {
        'id': execution.id,
        'title': f'APP 自动化执行报告 - {execution.case_name or "未命名用例"}',
        'case_name': execution.case_name or '-',
        'suite_name': execution.test_suite.name if execution.test_suite else '',
        'project_name': project.name if project else '-',
        'app_name': app_package.name if app_package else '-',
        'package_name': app_package.package_name if app_package else '',
        'device_name': execution.device_name or '-',
        'device_model': getattr(device, 'model', '') if device else '',
        'executor': execution.user_name or '-',
        'status': execution.status,
        'result': execution.result or '',
        'status_text': _status_text(execution),
        'conclusion': conclusion,
        'started_at': _local_time(execution.started_at),
        'finished_at': _local_time(execution.finished_at),
        'duration_text': _duration(execution.duration),
        'steps': {
            'total': total,
            'passed': passed,
            'failed': failed,
            'pass_rate': pass_rate,
        },
        'failure': {
            'type': diagnosis.get('type', ''),
            'message': failure_message,
        },
        'diagnosis': diagnosis,
        'step_outline': step_outline,
        'artifacts': artifacts,
        'visual_evidence': _visual_evidence_summary(artifacts),
        'performance': _performance_summary(execution.performance_metrics),
        'logcat': _logcat_summary(execution, request=request),
        'report_url': report_url,
    }
    summary['wecom_markdown'] = build_wecom_markdown(summary)
    return summary


def _suite_conclusion(status, result, counts):
    if status == 'running':
        return {
            'level': 'warning',
            'text': '执行中',
            'suggestion': '套件仍在执行，可刷新查看已完成用例进度。',
        }
    if status == 'stopped':
        return {
            'level': 'warning',
            'text': '已停止',
            'suggestion': '本轮套件被中断，结果不建议作为完整回归结论。',
        }
    if status == 'error':
        return {
            'level': 'danger',
            'text': '执行异常',
            'suggestion': '套件执行链路异常，优先排查设备、执行器和平台任务状态。',
        }
    if result == 'passed' and counts.get('total'):
        return {
            'level': 'success',
            'text': '整套通过',
            'suggestion': '本轮套件全部通过，可作为当前版本回归参考。',
        }
    if result == 'failed' or counts.get('failed') or counts.get('error'):
        return {
            'level': 'danger',
            'text': '整套不通过',
            'suggestion': '存在失败或异常用例，建议先处理首个失败用例，再回归整套。',
        }
    if not counts.get('executed'):
        return {
            'level': 'info',
            'text': '暂无结果',
            'suggestion': '当前套件尚未产生可用执行结果。',
        }
    return {
        'level': 'warning',
        'text': '结果不完整',
        'suggestion': '本轮存在跳过、停止或未完成用例，建议补齐执行后再下结论。',
    }


def build_suite_report_summary(suite, executions, request=None):
    """Build a suite-level report summary from the latest ordered execution round."""
    executions = list(executions or [])
    total_cases = suite.suite_cases.count()
    finished_statuses = {'completed', 'error', 'stopped'}

    counts = {
        'total': total_cases,
        'executed': sum(1 for item in executions if item.status in finished_statuses),
        'passed': sum(1 for item in executions if item.status == 'completed' and item.result == 'passed'),
        'failed': sum(1 for item in executions if item.status == 'completed' and item.result == 'failed'),
        'skipped': sum(1 for item in executions if item.status == 'completed' and item.result == 'skipped'),
        'error': sum(1 for item in executions if item.status == 'error'),
        'stopped': sum(1 for item in executions if item.status == 'stopped'),
        'running': sum(1 for item in executions if item.status == 'running'),
        'pending': sum(1 for item in executions if item.status == 'pending'),
    }
    pass_rate = round((counts['passed'] / total_cases) * 100, 2) if total_cases else 0

    started_values = [item.started_at or item.created_at for item in executions if item.started_at or item.created_at]
    finished_values = [item.finished_at for item in executions if item.finished_at]
    wall_duration = 0
    if started_values and finished_values:
        wall_duration = max(0, (max(finished_values) - min(started_values)).total_seconds())
    duration_sum = sum(float(item.duration or 0) for item in executions)

    step_total = sum(int(item.total_steps or 0) for item in executions)
    step_passed = sum(int(item.passed_steps or 0) for item in executions)
    step_failed = sum(int(item.failed_steps or 0) for item in executions)

    first_failure = {}
    case_results = []
    for index, execution in enumerate(executions, 1):
        failed_like = (
            execution.status == 'error'
            or execution.status == 'stopped'
            or (execution.status == 'completed' and execution.result in ('failed', 'skipped'))
        )
        step_outline = _step_outline(execution) if failed_like else {}
        failed_step = (step_outline or {}).get('failed_step') or {}
        report_url = ''
        if execution.report_path:
            path = f'/api/app-automation/executions/{execution.id}/report/'
            report_url = request.build_absolute_uri(path) if request else path
        logcat = _logcat_summary(execution, request=request)
        artifacts = _artifact_summary(execution, request=request)
        row = {
            'index': index,
            'execution_id': execution.id,
            'case_name': execution.case_name or '-',
            'device_name': execution.device_name or '-',
            'status': execution.status,
            'result': execution.result or '',
            'status_text': _status_text(execution),
            'started_at': _local_time(execution.started_at),
            'finished_at': _local_time(execution.finished_at),
            'duration_text': _duration(execution.duration),
            'total_steps': execution.total_steps or 0,
            'passed_steps': execution.passed_steps or 0,
            'failed_steps': execution.failed_steps or 0,
            'pass_rate': execution.pass_rate,
            'error_message': execution.error_message or (step_outline or {}).get('error_message') or '',
            'failed_step': failed_step,
            'report_url': report_url,
            'has_logcat': bool(logcat.get('available')),
            'has_artifacts': bool(artifacts.get('available')),
        }
        case_results.append(row)
        if failed_like and not first_failure:
            first_failure = row

    suite_logcat_url = ''
    suite_evidence_url = ''
    if suite.id:
        logcat_path = f'/api/app-automation/test-suites/{suite.id}/download-logcat/'
        evidence_path = f'/api/app-automation/test-suites/{suite.id}/download-evidence/'
        suite_logcat_url = request.build_absolute_uri(logcat_path) if request else logcat_path
        suite_evidence_url = request.build_absolute_uri(evidence_path) if request else evidence_path

    summary = {
        'id': suite.id,
        'title': f'APP 自动化套件报告 - {suite.name}',
        'suite_name': suite.name,
        'project_name': suite.project.name if suite.project else '-',
        'status': suite.execution_status,
        'result': suite.execution_result or '',
        'status_text': dict(suite.EXECUTION_STATUS_CHOICES).get(suite.execution_status, suite.execution_status),
        'result_text': dict(suite.EXECUTION_RESULT_CHOICES).get(suite.execution_result, suite.execution_result or '-'),
        'conclusion': _suite_conclusion(suite.execution_status, suite.execution_result, counts),
        'started_at': _local_time(min(started_values) if started_values else None),
        'finished_at': _local_time(max(finished_values) if finished_values else None),
        'duration_text': _duration(wall_duration or duration_sum),
        'duration_sum_text': _duration(duration_sum),
        'cases': {
            **counts,
            'pass_rate': pass_rate,
            'progress': min(100, round((counts['executed'] / total_cases) * 100)) if total_cases else 0,
        },
        'steps': {
            'total': step_total,
            'passed': step_passed,
            'failed': step_failed,
            'pass_rate': round((step_passed / step_total) * 100, 2) if step_total else 0,
        },
        'first_failure': first_failure,
        'case_results': case_results,
        'artifacts': {
            'download_url': suite_evidence_url,
            'logcat_download_url': suite_logcat_url,
            'case_logcat_count': sum(1 for item in case_results if item.get('has_logcat')),
            'case_artifact_count': sum(1 for item in case_results if item.get('has_artifacts')),
        },
    }
    summary['wecom_markdown'] = build_suite_wecom_markdown(summary)
    return summary


def build_suite_wecom_markdown(summary):
    conclusion = summary.get('conclusion') or {}
    color = {
        'success': 'info',
        'warning': 'warning',
        'danger': 'warning',
        'info': 'comment',
    }.get(conclusion.get('level'), 'comment')
    cases = summary.get('cases') or {}
    first_failure = summary.get('first_failure') or {}
    lines = [
        f"## {summary.get('title')}",
        f"> 结论：<font color=\"{color}\">{conclusion.get('text', '-')}</font>",
        f"> 建议：{conclusion.get('suggestion', '-')}",
        '',
        f"- 套件：{summary.get('suite_name', '-')}",
        f"- 项目：{summary.get('project_name', '-')}",
        f"- 进度：{cases.get('executed', 0)} / {cases.get('total', 0)}",
        f"- 通过：{cases.get('passed', 0)}，失败：{cases.get('failed', 0)}，异常：{cases.get('error', 0)}",
        f"- 通过率：{cases.get('pass_rate', 0)}%",
        f"- 总耗时：{summary.get('duration_text', '-')}",
    ]
    if first_failure:
        lines.append(
            f"- 首个问题：第 {first_failure.get('index')} 条「{first_failure.get('case_name')}」"
        )
    return '\n'.join(lines)


def build_wecom_markdown(summary):
    conclusion = summary.get('conclusion') or {}
    color = {
        'success': 'info',
        'warning': 'warning',
        'danger': 'warning',
        'info': 'comment',
    }.get(conclusion.get('level'), 'comment')
    steps = summary.get('steps') or {}
    failure = summary.get('failure') or {}
    lines = [
        f"## {summary.get('title')}",
        f"> 结论：<font color=\"{color}\">{conclusion.get('text', '-')}</font>",
        f"> 建议：{conclusion.get('suggestion', '-')}",
        '',
        f"- 用例：{summary.get('case_name', '-')}",
        f"- 项目：{summary.get('project_name', '-')}",
        f"- 设备：{summary.get('device_name', '-')}",
        f"- 执行人：{summary.get('executor', '-')}",
        f"- 耗时：{summary.get('duration_text', '-')}",
        f"- 步骤：通过 {steps.get('passed', 0)} / 失败 {steps.get('failed', 0)} / 总计 {steps.get('total', 0)}",
        f"- 通过率：{steps.get('pass_rate', 0)}%",
    ]
    if failure.get('type'):
        lines.append(f"- 失败归因：{failure.get('type')}")
    diagnosis = summary.get('diagnosis') or {}
    if diagnosis.get('suggestion'):
        lines.append(f"- 排查建议：{diagnosis.get('suggestion')}")
    performance = summary.get('performance') or {}
    if performance.get('enabled'):
        warnings = performance.get('warnings') or []
        lines.append(f"- 性能风险：{'、'.join(warnings) if warnings else '暂未发现明显异常'}")
    if summary.get('report_url'):
        lines.append(f"- 完整报告：[点击查看]({summary.get('report_url')})")
    return '\n'.join(lines)
