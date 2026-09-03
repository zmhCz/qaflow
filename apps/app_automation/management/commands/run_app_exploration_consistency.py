# -*- coding: utf-8 -*-
"""Run APP exploration consistency batches in a dedicated local process."""

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone


class Command(BaseCommand):
    help = 'Run a target-inspection exploration task repeatedly for consistency checks.'

    def add_arguments(self, parser):
        parser.add_argument('task_id', type=int)
        parser.add_argument('run_ids', type=str, help='Comma separated AppExplorationRun ids')
        parser.add_argument('--task-identifier', default='', help='Local task identifier for diagnostics')

    def handle(self, *args, **options):
        from apps.app_automation.models import AppExplorationRun, AppExplorationTask
        from apps.app_automation.tasks import execute_app_exploration_task

        task_id = options['task_id']
        run_ids = [
            int(item)
            for item in str(options['run_ids']).split(',')
            if str(item).strip()
        ]
        total = len(run_ids)
        close_old_connections()

        try:
            for index, run_id in enumerate(run_ids, 1):
                task = AppExplorationTask.objects.filter(id=task_id).first()
                if not task:
                    raise RuntimeError(f'探索任务不存在：{task_id}')
                if task.status == 'stopped':
                    self.stdout.write(f'Task {task_id} stopped before run {run_id}.')
                    break

                summary = dict(task.summary or {})
                summary.update({
                    'current_stage': f'三次一致性验证 {index}/{total}：正在执行',
                    'consistency_batch_total': total,
                    'consistency_batch_index': index,
                    'consistency_batch_run_ids': run_ids,
                    'consistency_batch_worker': options.get('task_identifier') or '',
                })
                task.summary = summary
                task.save(update_fields=['summary', 'updated_at'])

                run = AppExplorationRun.objects.filter(id=run_id, task_id=task_id).first()
                if run:
                    run_summary = dict(run.summary or {})
                    run_summary.update({
                        'current_stage': f'三次一致性验证 {index}/{total}：正在执行',
                        'consistency_batch_total': total,
                        'consistency_batch_index': index,
                        'consistency_batch_worker': options.get('task_identifier') or '',
                    })
                    run.summary = run_summary
                    run.save(update_fields=['summary', 'updated_at'])

                self.stdout.write(f'Starting consistency run {index}/{total}: task={task_id}, run={run_id}')
                result = execute_app_exploration_task.run(task_id, run_id)
                if isinstance(result, dict) and result.get('success') is False:
                    raise RuntimeError(result.get('error') or f'一致性第 {index}/{total} 轮执行失败')

            self.stdout.write(f'Consistency batch finished: task={task_id}, runs={run_ids}')
        except Exception as exc:
            self.stderr.write(f'Consistency batch failed: task={task_id}, error={exc}')
            finished_at = timezone.now()
            task = AppExplorationTask.objects.filter(id=task_id).first()
            if task:
                summary = dict(task.summary or {})
                summary.update({
                    'current_stage': '三次一致性验证执行失败',
                    'consistency_batch_run_ids': run_ids,
                    'consistency_batch_error': str(exc),
                })
                task.status = 'error'
                task.result = 'failed'
                task.error_message = str(exc)
                task.finished_at = finished_at
                if task.started_at:
                    task.duration = (finished_at - task.started_at).total_seconds()
                task.summary = summary
                task.save(update_fields=['status', 'result', 'error_message', 'finished_at', 'duration', 'summary', 'updated_at'])

            for run in AppExplorationRun.objects.filter(id__in=run_ids, status__in=['pending', 'running']):
                summary = dict(run.summary or {})
                summary.update({
                    'current_stage': '三次一致性验证执行失败',
                    'consistency_batch_error': str(exc),
                })
                run.status = 'error'
                run.result = 'failed'
                run.error_message = str(exc)
                run.finished_at = finished_at
                if run.started_at:
                    run.duration = (finished_at - run.started_at).total_seconds()
                run.summary = summary
                run.save(update_fields=['status', 'result', 'error_message', 'finished_at', 'duration', 'summary', 'updated_at'])
            raise
        finally:
            close_old_connections()
