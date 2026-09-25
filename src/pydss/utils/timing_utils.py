"""Utility functions for timing measurements."""

import functools
import time

from loguru import logger


def timed_info(func):
    """Decorator to measure and logger.info a function's execution time."""

    @functools.wraps(func)
    def timed_(*args, **kwargs):
        return _timed(func, logger.info, *args, **kwargs)

    return timed_


def timed_debug(func):
    """Decorator to measure and logger.debug a function's execution time."""

    @functools.wraps(func)
    def timed_(*args, **kwargs):
        return _timed(func, logger.debug, *args, **kwargs)

    return timed_


def _timed(func, log_func, *args, **kwargs):
    start = time.time()
    result = func(*args, **kwargs)
    total = time.time() - start
    log_func("execution-time=%s func=%s", get_time_duration_string(total), func.__name__)
    return result


def get_time_duration_string(seconds):
    """Returns a string with the time converted to reasonable units."""
    if seconds >= 1:
        val = "{:.3f} s".format(seconds)
    elif seconds >= 0.001:
        val = "{:.3f} ms".format(seconds * 1000)
    elif seconds >= 0.000001:
        val = "{:.3f} us".format(seconds * 1000000)
    elif seconds == 0:
        val = "0 s"
    else:
        val = "{:.3f} ns".format(seconds * 1000000000)

    return val


class TimerStats:
    """Tracks timing stats for one code block."""

    def __init__(self, name):
        self._name = name
        self._count = 0
        self._max = 0.0
        self._min = None
        self._avg = 0.0
        self._total = 0.0

    def get_stats(self):
        """Get the current stats summary.

        Returns
        -------
        dict

        """
        avg = 0 if self._count == 0 else self._total / self._count
        return {
            "min": self._min,
            "max": self._max,
            "total": self._total,
            "avg": avg,
            "count": self._count,
        }

    def log_stats(self):
        """Log a summary of the stats."""
        if self._count == 0:
            logger.info("No stats have been recorded for %s.", self._name)
            return

        x = self.get_stats()
        text = "total={:.3f}s avg={:.3f}ms max={:.3f}ms min={:.3f}ms count={}".format(
            x["total"], x["avg"] * 1000, x["max"] * 1000, x["min"] * 1000, x["count"]
        )
        logger.info(f"TimerStats summary: {self._name}: {text}")

    def update(self, duration):
        """Update the stats with a new timing."""
        self._count += 1
        self._total += duration
        if duration > self._max:
            self._max = duration
        if self._min is None or duration < self._min:
            self._min = duration


class Timer:
    """Times a code block."""

    def __init__(self, timer_stats, name):
        self._start = None
        self._timer_stat = timer_stats.get_stat(name)

    def __enter__(self):
        self._start = time.perf_counter()

    def __exit__(self, exc, value, tb):
        self._timer_stat.update(time.perf_counter() - self._start)


class TimerStatsCollector:
    """Collects statistics for timed code segments."""

    def __init__(self):
        self._stats = {}

    def clear(self):
        """Clear all stats."""
        self._stats.clear()

    def get_stat(self, name):
        """Return a TimerStats.

        Parameters
        ----------
        name : str

        Returns
        -------
        TimerStats

        """
        if name not in self._stats:
            self.register_stat(name)
        return self._stats[name]

    def log_stats(self, clear=False):
        """Log statistics for all tracked stats.

        Parameters
        ----------
        clear : bool
            If True, clear all stats.

        """
        for stat in self._stats.values():
            stat.log_stats()
        if clear:
            self._stats.clear()

    def register_stat(self, name):
        """Register tracking of a new stat.

        Parameters
        ----------
        name : str

        Returns
        -------
        TimerStats

        """
        if name in self._stats:
            raise Exception(f"{name} is already stored")
        stat = TimerStats(name)
        self._stats[name] = stat
        return stat


def track_timing(timer_stats):
    """Decorator to track statistics on a function's execution time.

    Parameters
    ----------
    timer_stats : TimerStatsCollector

    """

    def wrap(func):
        def timed_(*args, **kwargs):
            return _timed_func(timer_stats, func, *args, **kwargs)

        return timed_

    return wrap


def _timed_func(timer_stats, func, *args, **kwargs):
    with Timer(timer_stats, func.__qualname__):
        return func(*args, **kwargs)


timer_stats_collector = TimerStatsCollector()
