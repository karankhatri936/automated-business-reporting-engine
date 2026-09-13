"""Tests for the reporting scheduler (manual + interval execution).

These tests exercise the real APScheduler with short sub-minute intervals.
They are fully offline -- no external API or network access is involved.
"""

import threading
import time
import unittest

from automated_business_reporting_engine.scheduler.scheduler import (
    ReportScheduler,
    run_job_once,
)
from automated_business_reporting_engine.utils.exceptions import SchedulerError


class TestReportScheduler(unittest.TestCase):
    """Tests for :class:`ReportScheduler` with real (short) intervals."""

    def tearDown(self):
        for scheduler in getattr(self, "_schedulers", []):
            try:
                scheduler.stop(wait=True)
            except Exception:
                pass

    def test_scheduled_job_runs_after_interval(self):
        """A registered job fires on the interval and the scheduler runs."""
        fired = threading.Event()

        def job():
            fired.set()
            return "ok"

        scheduler = ReportScheduler()
        self._schedulers = [scheduler]

        self.assertTrue(scheduler.start(job, seconds=0.2))
        self.assertTrue(scheduler.is_running)
        self.assertTrue(fired.wait(5.0), "scheduled job never fired")
        self.assertIsNotNone(scheduler.next_run_time)

        scheduler.stop()
        self.assertFalse(scheduler.is_running)

    def test_duplicate_start_is_rejected(self):
        """Starting an already-running scheduler must not add a second job."""
        scheduler = ReportScheduler()
        self._schedulers = [scheduler]

        self.assertTrue(scheduler.start(lambda: None, seconds=0.5))
        self.assertFalse(scheduler.start(lambda: None, seconds=0.5))
        # Exactly one job is registered.
        self.assertIsNotNone(scheduler.next_run_time)

    def test_non_positive_interval_raises(self):
        """Non-positive intervals are rejected with SchedulerError."""
        scheduler = ReportScheduler()

        with self.assertRaises(SchedulerError):
            scheduler.start(lambda: None, minutes=0)
        with self.assertRaises(SchedulerError):
            scheduler.start(lambda: None, seconds=-1)

    def test_overlapping_run_is_skipped(self):
        """While one run is executing, later triggers must not overlap it."""
        runs = []
        started = threading.Event()
        release = threading.Event()

        def slow_job():
            runs.append(threading.get_ident())
            started.set()
            release.wait(timeout=5.0)
            return "done"

        scheduler = ReportScheduler()
        self._schedulers = [scheduler]

        self.assertTrue(scheduler.start(slow_job, seconds=0.2))
        self.assertTrue(started.wait(5.0), "slow job never started")

        # Let several intervals pass while the job is still running.
        time.sleep(1.2)
        self.assertEqual(len(runs), 1, "an overlapping run was not prevented")

        release.set()
        scheduler.stop(wait=True)
        self.assertFalse(scheduler.is_running)

    def test_run_job_once_executes_immediately(self):
        """Manual execution runs the job once and returns its result."""
        self.assertEqual(run_job_once(lambda: 42), 42)

    def test_run_job_once_is_guarded_by_global_lock(self):
        """Manual runs are skipped while another run is in progress."""
        release = threading.Event()

        def blocking_job():
            release.wait(timeout=5.0)
            return "blocking"

        # Occupy the shared execution lock on a background thread.
        results = {}

        def occupy():
            results["manual"] = run_job_once(blocking_job)

        thread = threading.Thread(target=occupy)
        thread.start()
        time.sleep(0.2)

        # While the lock is held, a second manual run is skipped (False).
        self.assertFalse(run_job_once(lambda: "second run"))

        release.set()
        thread.join(timeout=5.0)
        self.assertEqual(results["manual"], "blocking")


if __name__ == "__main__":
    unittest.main()