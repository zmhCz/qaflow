# -*- coding: utf-8 -*-
"""Shared risk guard for APP exploratory testing.

Exploration should be conservative: if an action looks destructive or
account-affecting, skip it and make the reason visible in the report.
"""

from __future__ import annotations

from typing import Iterable


RISK_SEMANTIC_GROUPS = [
    {
        'group': '退出/离开',
        'level': 'forbidden',
        'keywords': ['退出', '退出登录', '退出社区', '退出房间', '离开', '离开房间', '登出', 'logout', 'signout', 'leave'],
    },
    {
        'group': '账号注销',
        'level': 'forbidden',
        'keywords': ['注销', '注销账号', '注销账户', '销户', 'delete account', 'close account'],
    },
    {
        'group': '删除/清空',
        'level': 'forbidden',
        'keywords': ['删除', '移除', '清空', '清除', '销毁', 'delete', 'remove', 'clear'],
    },
    {
        'group': '支付/交易',
        'level': 'forbidden',
        'keywords': ['支付', '购买', '充值', '提现', '退款', '扣款', '订阅', 'pay', 'buy', 'purchase', 'recharge'],
    },
    {
        'group': '关系解绑',
        'level': 'forbidden',
        'keywords': ['解绑', '解除绑定', '取消绑定', 'unbound', 'unbind'],
    },
    {
        'group': '解散/关闭',
        'level': 'forbidden',
        'keywords': ['解散', '关闭社区', '关闭房间', '解散房间', 'dismiss', 'disband'],
    },
    {
        'group': '发布/提交',
        'level': 'caution',
        'keywords': ['提交', '发布', '保存', '确认发布', '完成', 'submit', 'publish', 'save'],
    },
    {
        'group': '授权/允许',
        'level': 'caution',
        'keywords': ['授权', '允许', '同意', '永久拒绝', '始终允许', 'allow', 'agree', 'permission'],
    },
    {
        'group': '确认动作',
        'level': 'caution',
        'keywords': ['确认', '确定', '继续', 'confirm', 'ok', 'continue'],
    },
]

DEFAULT_BLACKLIST_KEYWORDS = [
    '退出',
    '退出登录',
    '删除',
    '支付',
    '购买',
    '充值',
    '提现',
    '注销',
    '解散',
    '清空',
    '解绑',
]

FORBIDDEN_RISK_KEYWORDS = [
    keyword
    for group in RISK_SEMANTIC_GROUPS
    if group['level'] == 'forbidden'
    for keyword in group['keywords']
]

CAUTION_RISK_KEYWORDS = [
    keyword
    for group in RISK_SEMANTIC_GROUPS
    if group['level'] == 'caution'
    for keyword in group['keywords']
]


def normalize_risk_text(value: object) -> str:
    return str(value or '').strip().lower().replace(' ', '')


def assess_risk_values(values: Iterable[object], custom_keywords: Iterable[object] | None = None) -> dict | None:
    joined = normalize_risk_text(' '.join(str(value or '') for value in values if value))
    if not joined:
        return None

    for keyword in custom_keywords or []:
        text = normalize_risk_text(keyword)
        if text and text in joined:
            return {
                'level': 'forbidden',
                'keyword': str(keyword).strip(),
                'group': '自定义黑名单',
                'reason': '命中自定义禁止点击风险词',
            }

    for group in RISK_SEMANTIC_GROUPS:
        for keyword in group['keywords']:
            text = normalize_risk_text(keyword)
            if text and text in joined:
                return {
                    'level': group['level'],
                    'keyword': keyword,
                    'group': group['group'],
                    'reason': f"命中{group['group']}风险语义",
                }
    return None


def contains_forbidden_risk(values: Iterable[object], custom_keywords: Iterable[object] | None = None) -> bool:
    risk = assess_risk_values(values, custom_keywords=custom_keywords)
    return bool(risk and risk.get('level') == 'forbidden')
