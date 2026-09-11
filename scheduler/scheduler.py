"""Scheduling for the Automated Business Reporting Engine.

The application supports two execution modes:

* **Manual execution** -- ``run_job_once(job_func)`` runs the reporting job
  immediately (single run).
* **Scheduled execution** -- :class:`ReportScheduler` registers the job with
  APScheduler and runs it repeatedly using an interval trigger. The interval
  is read from ``SCHEDULER_INTERVAL_MINUTES`` (default ``60``).

Overlap protection
------------------
Only ONE reporting job may execute at a time. A process-wide lock guards
both manual and scheduled runs, so a scheduled run never starts while a
manual run is in progress (and vice versa). Triggers that arrive while a
run is busy are logged and skipped, never queued, so the process cannot
accidentally accumulate or overlap reporting jobs.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ..config import config
from ..utils.exceptions import SchedulerError
from ..utils.logger import setup_logger

logger = setup_logger(__name__)

#: Timezone APScheduler uses. Interval triggers compute ``next_run_time`` in
#: this zone; the value itself only matters for display purposes.
SCHEDULER_TIMEZONE = "UTC"

#: Process-wide lock ensuring a single reporting run at any moment.
_EXECUTION_LOCK = threading.Lock()


def run_job_once(job_func: Callable[[], Any]) -> Any:
    """Run *job_func* immediately unless another reporting run is active.

    Args:
        job_func: Callable that runs the complete reporting pipeline.

    Returns:
        The job's return value on success, or ``False`` when the run was
        skipped because another run was already in progress.

    Raises:
        Any exception raised by ``job_func`` (never silently swallowed).
    """
    if not _EXECUTION_LOCK.acquire(blocking=False):
        logger.warning(
            "Reporting job skipped: another reporting run is already in progress"
        )
        return False
    try:
        logger.info("Reporting job started (manual execution)")
        result = job_func()
        logger.info("Reporting job completed (manual execution)")
        return result
    except Exception:
        logger.exception("Reporting job failed (manual execution)")
        raise
    finally:
        _EXECUTION_LOCK.release()


class ReportScheduler:
    """Run a reporting job on a fixed interval using APScheduler.

    A duplicate :meth:`start` call is rejected while the scheduler is
    already running, so a process can never register two jobs by accident.
    The wrapped job shares the process-wide execution lock with manual
    runs, which prevents manual/scheduled overlap.
    """

    JOB_ID = "business_reporting_job"

    def __init__(self, scheduler_config=None, timezone: str = SCHEDULER_TIMEZONE) -> None:
        """
        Args:
            scheduler_config: Optional ``SchedulerConfig``; falls back to the
                application configuration.
            timezone: APScheduler timezone name (default UTC).
        """
        if scheduler_config is None:
            scheduler_config = config.scheduler
        self.scheduler_config = scheduler_config
        self.timezone = timezone
        self._scheduler: Optional[BackgroundScheduler] = None

    # ── State helpers ────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """True while the background scheduler thread is active."""
        return self._scheduler is not None and self._scheduler.running

    @property
    def next_run_time(self) -> Optional[datetime]:
        """Next scheduled run time, or None when nothing is scheduled."""
        if self._scheduler is None:
            return None
        job = self._scheduler.get_job(self.JOB_ID)
        return job.next_run_time if job is not None else None

    # ── Job wiring ───────────────────────────────────────────────────

    def _wrap_job(self, job_func: Callable[[], Any]) -> Callable[[], Any]:
        """Wrap the user job with logging and overlap protection."""

        @wraps(job_func)
        def _scheduled_run() -> Any:
            if not _EXECUTION_LOCK.acquire(blocking=False):
                logger.warning(
                    "Scheduled run skipped: another reporting run is "
                    "already in progress"
                )
                return None
            try:
                logger.info("Scheduled reporting job started")
                return job_func()
            except Exception:
                logger.exception("Scheduled reporting job failed")
                raise
            finally:
                _EXECUTION_LOCK.release()

        return _scheduled_run

    # ── Public API ─────────────────────────────────────────────────

    def start(
        self,
        job_func: Callable[[], Any],
        minutes: Optional[int] = None,
        seconds: Optional[float] = None,
    ) -> bool:
        """Start an interval-based background scheduler.

        Args:
            job_func: Callable that runs the full reporting pipeline.
            minutes: Interval override in minutes.
            seconds: Finer-grained interval override (mainly for tests and
                short cycles). Takes precedence over ``minutes``.

        Returns:
            ``True`` when the scheduler was started; ``False`` when a
            scheduler was already running (no duplicate job is registered).

        Raises:
            SchedulerError: If the derived interval is not positive.
        """
        if self.is_running:
            logger.warning(
                "Scheduler is already running; refusing to register a "
                "duplicate job"
            )
            return False

        if seconds is not None:
            interval_seconds = seconds
        elif minutes is not None:
            interval_seconds = minutes * 60
        else:
            interval_seconds = self.scheduler_config.interval_minutes * 60

        if interval_seconds <= 0:
            raise SchedulerError(
                "Scheduling interval must be positive "
                f"(got {interval_seconds} seconds)"
            )

        job_defaults = {
            # Never queue up missed runs (e.g. after a long report run).
            "coalesce": True,
            # Never overlap the same job with itself.
            "max_instances": 1,
            # Ignore runs that were missed a long time ago.
            "misfire_grace_time": 60,
        }
        trigger = IntervalTrigger(seconds=interval_seconds, timezone=self.timezone)
        self._scheduler = BackgroundScheduler(
            timezone=self.timezone, job_defaults=job_defaults
        )
        self._scheduler.add_job(
            self._wrap_job(job_func),
            trigger=trigger,
            id=self.JOB_ID,
            name=(
                "Business reporting job "
                f"(every {interval_seconds / 60:.6g} minutes)"
            ),
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info(
            "Scheduler started: reporting job runs every %s seconds "
            "(next run at %s)",
            interval_seconds,
            self.next_run_time,
        )
        return True

    def stop(self, wait: bool = False) -> None:
        """Stop the background scheduler.

        Args:
            wait: When True, block until an in-progress run finishes before
                returning (used for graceful shutdown).
        """
        if self._scheduler is not None:
            if self._scheduler.running:
                self._scheduler.shutdown(wait=wait)
            self._scheduler = None
        logger.info("Scheduler stopped")

    def wait(self) -> None:
        """Block the calling thread until the scheduler is stopped.

        Catches ``KeyboardInterrupt`` so Ctrl+C performs a clean shutdown
        (the current run is allowed to finish).
        """
        try:
            while self.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Interrupt received; stopping scheduler gracefully")
            self.stop(wait=True)