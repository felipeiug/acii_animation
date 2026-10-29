"""Entrada do ASCII Space Explorer."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time

import config
from explorer import Explorer
from metrics import SystemMonitor
from persistence import load_explorer, save_explorer

HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"
RESET = "\x1b[0m"
HOME = "\x1b[H"
CLEAR = "\x1b[2J"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Protetor de tela espacial ASCII procedural")
    parser.add_argument("--seed", type=int, help="semente para uma viagem reproduzível")
    parser.add_argument("--no-color", action="store_true", help="desativa cores ANSI")
    parser.add_argument("--fps", type=float, default=config.FPS, help="quadros por segundo")
    parser.add_argument("--reset-status", action="store_true", help="inicia uma nova exploração")
    return parser.parse_args()


def enable_windows_ansi() -> None:
    if os.name == "nt":
        os.system("")


def terminal_area() -> tuple[int, int]:
    size = shutil.get_terminal_size((80, 24))
    return max(1, size.columns - 1), max(1, size.lines)


def run(explorer: Explorer, use_colors: bool, fps: float) -> None:
    if fps <= 0:
        raise ValueError("FPS deve ser maior que zero")
    frame_time = 1.0 / fps
    previous = time.perf_counter()
    last_save = previous
    last_metrics = previous - config.METRICS_REFRESH_INTERVAL
    monitor = SystemMonitor()
    sys.stdout.write(CLEAR + HOME + HIDE_CURSOR)
    sys.stdout.flush()
    try:
        while True:
            started = time.perf_counter()
            dt = started - previous
            previous = started
            if started - last_metrics >= config.METRICS_REFRESH_INTERVAL:
                metrics = monitor.sample()
                explorer.set_system_metrics(metrics.cpu_percent, metrics.memory_percent)
                last_metrics = started
            width, height = terminal_area()
            if width < config.MIN_WIDTH or height < config.MIN_HEIGHT:
                message = f"Terminal pequeno: mínimo {config.MIN_WIDTH + 1}x{config.MIN_HEIGHT}"
                frame = message[:width].ljust(width)
            else:
                explorer.update(dt, width, height)
                frame = explorer.render(width, height, use_colors)
            sys.stdout.write(HOME + frame)
            sys.stdout.flush()
            if started - last_save >= config.STATUS_SAVE_INTERVAL:
                save_explorer(explorer)
                last_save = started
            remaining = frame_time - (time.perf_counter() - started)
            if remaining > 0:
                time.sleep(remaining)
    finally:
        try:
            save_explorer(explorer)
        finally:
            sys.stdout.write(RESET + SHOW_CURSOR + "\n")
            sys.stdout.flush()


def main() -> int:
    args = parse_args()
    enable_windows_ansi()
    explorer = None if args.seed is not None or args.reset_status else load_explorer()
    explorer = explorer or Explorer(args.seed)
    try:
        run(explorer, config.USE_COLORS and not args.no_color, args.fps)
    except KeyboardInterrupt:
        return 0
    except (BrokenPipeError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

