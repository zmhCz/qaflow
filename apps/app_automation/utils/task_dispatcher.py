# -*- coding: utf-8 -*-
"""Task dispatch helpers for local APP automation runs."""
from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Iterable

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass
class DispatchResult:
    """Small result object compatible with the AsyncResult fields views need."""

    id: str
    mode: str
    fallback_used: bool = False


def _local_task_id(task_name: str) -> str:
    normalized = (task_name or 'task').replace('.', '_')
    return f"local-{normalized}-{uuid.uuid4().hex[:12]}"


def _run_task_in_thread(task, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
    close_old_connections()
    try:
        task.run(*args, **kwargs)
    except Exception:
        logger.exception("本地后台任务执行失败: %s", getattr(task, 'name', task))
    finally:
        close_old_connections()


def _mark_executions_dispatch_error(execution_ids: Iterable[int], message: str) -> None:
    execution_ids = [eid for eid in execution_ids if eid]
    if not execution_ids:
        return
    try:
        from apps.app_automation.models import AppTestExecution

        AppTestExecution.objects.filter(id__in=execution_ids, status='pending').update(
            status='error',
            result=None,
            error_message=message,
            finished_at=timezone.now(),
        )
    except Exception:
        logger.exception("更新派发失败执行记录失败: %s", execution_ids)


def _is_redis_broker_available() -> bool:
    broker_url = getattr(settings, 'CELERY_BROKER_URL', '') or ''
    if not broker_url.startswith('redis://') and not broker_url.startswith('rediss://'):
        return True
    try:
        import redis

        client = redis.Redis.from_url(
            broker_url,
            socket_connect_timeout=0.35,
            socket_timeout=0.35,
        )
        client.ping()
        return True
    except Exception as exc:
        logger.warning("Celery Redis broker 不可用，跳过队列派发: %s", exc)
        return False


def dispatch_app_task(task, *args, mark_execution_ids: Iterable[int] | None = None, **kwargs) -> DispatchResult:
    """Dispatch an APP automation task, with a local fallback for single-machine dev.

    APP UI automation in this project is often run from a Windows laptop with one
    connected phone. Requiring Redis/Celery every time creates confusing
    "pending forever" records after reboot, so DEBUG defaults to a local thread
    fallback unless APP_AUTOMATION_LOCAL_TASK_FALLBACK=false is configured.
    """

    fallback_enabled = getattr(settings, 'APP_AUTOMATION_LOCAL_TASK_FALLBACK', False)
    broker_available = _is_redis_broker_available() if fallback_enabled else True

    try:
        if broker_available:
            celery_task = task.delay(*args, **kwargs)
            return DispatchResult(id=celery_task.id, mode='celery', fallback_used=False)
        raise RuntimeError('Redis/Celery 队列不可用')
    except Exception as exc:
        task_name = getattr(task, 'name', str(task))
        message = f"任务队列不可用，未能提交到 Celery: {exc}"
        logger.error("%s", message, exc_info=True)

        if not fallback_enabled:
            _mark_executions_dispatch_error(mark_execution_ids or [], message)
            raise RuntimeError(message) from exc

        local_id = _local_task_id(task_name)
        thread = threading.Thread(
            target=_run_task_in_thread,
            args=(task, tuple(args), dict(kwargs)),
            name=local_id,
            daemon=True,
        )
        thread.start()
        logger.warning("Celery 不可用，已切换本地后台线程执行: task=%s, local_id=%s", task_name, local_id)
        return DispatchResult(id=local_id, mode='local_thread', fallback_used=True)
