"""Métricas leves de CPU e memória sem dependências externas."""

from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from pathlib import Path


class _FileTime(ctypes.Structure):
    _fields_ = (("low", ctypes.c_ulong), ("high", ctypes.c_ulong))


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = (
        ("length", ctypes.c_ulong),
        ("memory_load", ctypes.c_ulong),
        ("total_physical", ctypes.c_ulonglong),
        ("available_physical", ctypes.c_ulonglong),
        ("total_page_file", ctypes.c_ulonglong),
        ("available_page_file", ctypes.c_ulonglong),
        ("total_virtual", ctypes.c_ulonglong),
        ("available_virtual", ctypes.c_ulonglong),
        ("available_extended_virtual", ctypes.c_ulonglong),
    )


@dataclass(frozen=True)
class SystemMetrics:
    cpu_percent: float | None
    memory_percent: float | None


class SystemMonitor:
    def __init__(self) -> None:
        self._previous_cpu: tuple[int, int] | None = None

    def sample(self) -> SystemMetrics:
        if os.name == "posix" and Path("/proc/stat").exists():
            return SystemMetrics(self._linux_cpu(), self._linux_memory())
        if os.name == "nt":
            return SystemMetrics(self._windows_cpu(), self._windows_memory())
        return SystemMetrics(self._load_average_cpu(), None)

    def _windows_cpu(self) -> float | None:
        try:
            idle, kernel, user = _FileTime(), _FileTime(), _FileTime()
            get_times = ctypes.windll.kernel32.GetSystemTimes
            if not get_times(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
                return None
            idle_value = _filetime_value(idle)
            total = _filetime_value(kernel) + _filetime_value(user)
            current = (total, idle_value)
            previous, self._previous_cpu = self._previous_cpu, current
            if previous is None or total <= previous[0]:
                return None
            total_delta = total - previous[0]
            idle_delta = idle_value - previous[1]
            return _clamp_percent((1.0 - idle_delta / total_delta) * 100.0)
        except (AttributeError, OSError, ZeroDivisionError):
            return None

    @staticmethod
    def _windows_memory() -> float | None:
        try:
            status = _MemoryStatusEx()
            status.length = ctypes.sizeof(_MemoryStatusEx)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
            if status.total_physical <= 0:
                return None
            used = status.total_physical - status.available_physical
            return _clamp_percent(used / status.total_physical * 100.0)
        except (AttributeError, OSError, ZeroDivisionError):
            return None

    def _linux_cpu(self) -> float | None:
        try:
            first = Path("/proc/stat").read_text(encoding="ascii").splitlines()[0]
            values = [int(value) for value in first.split()[1:]]
            total = sum(values)
            idle = values[3] + (values[4] if len(values) > 4 else 0)
            current = (total, idle)
            previous, self._previous_cpu = self._previous_cpu, current
            if previous is None or total <= previous[0]:
                return self._load_average_cpu()
            total_delta = total - previous[0]
            idle_delta = idle - previous[1]
            return _clamp_percent((1.0 - idle_delta / total_delta) * 100.0)
        except (OSError, ValueError, IndexError, ZeroDivisionError):
            return None

    @staticmethod
    def _linux_memory() -> float | None:
        try:
            values: dict[str, int] = {}
            for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
                name, _, value = line.partition(":")
                if name in {"MemTotal", "MemAvailable"}:
                    values[name] = int(value.split()[0])
            total = values["MemTotal"]
            return _clamp_percent((1.0 - values["MemAvailable"] / total) * 100.0)
        except (OSError, ValueError, KeyError, ZeroDivisionError):
            return None

    @staticmethod
    def _load_average_cpu() -> float | None:
        try:
            cores = max(1, os.cpu_count() or 1)
            return _clamp_percent(os.getloadavg()[0] / cores * 100.0)
        except (AttributeError, OSError):
            return None


def _clamp_percent(value: float) -> float:
    return max(0.0, min(100.0, value))


def _filetime_value(value: _FileTime) -> int:
    return (value.high << 32) | value.low
