"""Unit tests for scheduler reschedule behavior."""
from unittest.mock import patch
import unittest

from scraping import scheduler as scheduler_module
from scraping.scheduler import SmartScheduler
from storage.config import Config


class FakeTimer:
    def __init__(self, interval, callback):
        self.interval = interval
        self.callback = callback
        self.cancelled = False
        self.started = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True


class FakeThread:
    def __init__(self, target, *args, **kwargs):
        self.target = target

    def start(self):
        self.target()


class TestSchedulerReschedule(unittest.TestCase):
    def test_reschedule_sentinel_uses_delay_timer(self):
        sched = SmartScheduler()
        sched._running = True
        previous = FakeTimer(10, None)
        sched._sentinel_timer = previous
        timers = []

        def fake_timer(interval, callback):
            t = FakeTimer(interval, callback)
            timers.append(t)
            return t

        with patch.object(scheduler_module.threading, "Timer", side_effect=fake_timer):
            with patch.object(sched, "_seconds_until_tier_allowed", return_value=120):
                sched.reschedule_sentinel()

        self.assertTrue(previous.cancelled)
        self.assertIsNotNone(sched._sentinel_timer)
        self.assertEqual(len(timers), 1)
        self.assertEqual(timers[0].interval, 120)

    def test_reschedule_sentinel_runs_cycle_when_allowed(self):
        sched = SmartScheduler()
        sched._running = True
        calls = {"cycle": 0}

        with patch.object(scheduler_module.threading, "Thread", FakeThread):
            with patch.object(sched, "_seconds_until_tier_allowed", return_value=0):
                with patch.object(sched, "_sentinel_cycle", side_effect=lambda: calls.__setitem__("cycle", calls["cycle"] + 1)):
                    sched.reschedule_sentinel()

        self.assertEqual(calls["cycle"], 1)
        self.assertIsNone(sched._sentinel_timer)

    def test_reschedule_briefing_respects_enabled_flag(self):
        sched = SmartScheduler()
        sched._running = True
        current = FakeTimer(12, None)
        sched._briefing_timer = current

        with patch.object(Config, "scheduled_briefing", return_value={"enabled": False}):
            with patch.object(sched, "_schedule_briefing") as schedule:
                sched.reschedule_briefing()
        self.assertTrue(current.cancelled)
        schedule.assert_not_called()

        with patch.object(Config, "scheduled_briefing", return_value={"enabled": True}):
            with patch.object(sched, "_schedule_briefing") as schedule2:
                sched.reschedule_briefing()
        schedule2.assert_called_once()


if __name__ == "__main__":
    unittest.main()
