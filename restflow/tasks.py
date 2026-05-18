"""
For celery, celery uses app level tasks.py to discover tasks
"""
from restflow.caching.tasks import task_run_cache_rules

__all__ = ["task_run_cache_rules"]
