"""Sprites e desenho do pequeno foguete."""

from __future__ import annotations

from functools import lru_cache

from renderer import Canvas

FLIGHT = r"""
  _
 / \________________________________
|                                   ‾‾‾‾___    
|    |  IA      o    o    o    o    o      >
|                                   ____‾‾‾
 \_/‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾"""

APPROACH =r"""
       ^
      / \
     /   \
    /     \
   |       |
   |   o   |
   |       |
   |   o   |
   |       |
   |   o   |
   |       |
   |   o   |
   |       |
   |   o   |
   |       |
   |   A   |
   |       |
 __|       |__
/             \
\_____________/
   |       |
   |_______|"""

FLIGHT_COMPACT = (
    "====   /\\",
    "======| IA \\>",
    "====   \\___/",
)


def _place(grid: list[list[str]], y: int, x: int, text: str) -> None:
    if not 0 <= y < len(grid):
        return
    for offset, char in enumerate(text):
        if char != " " and 0 <= x + offset < len(grid[0]):
            grid[y][x + offset] = char


def _asset_lines(asset: str | tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(asset, str):
        return asset
    safe = asset.translate(str.maketrans({"o": "O", "🔥": "*", "‾": "-"}))
    return tuple(line.rstrip() for line in safe.strip("\n").splitlines())


def _approach_body() -> tuple[str, ...]:
    lines = _asset_lines(APPROACH)
    for index, line in enumerate(lines):
        if "*" in line:
            return lines[:index]
    return lines


@lru_cache(maxsize=24)
def _vertical_sprite(width: int, height: int) -> tuple[str, ...]:
    """Constrói um foguete detalhado que cresce sem trocar de desenho."""
    width = max(7, width | 1)
    height = max(7, height)
    center = width // 2
    grid = [[" "] * width for _ in range(height)]
    body_left = max(2, width // 4)
    body_right = width - body_left - 1
    nose_end = max(3, height // 3)
    body_end = height - 3

    for y in range(nose_end):
        if y == 0:
            grid[y][center - 1] = "/"
            grid[y][center] = "\\"
            continue
        half = max(1, round(1 + (center - body_left - 1) * y / max(1, nose_end - 1)))
        grid[y][center - half] = "/"
        grid[y][center + half] = "\\"
    for y in range(nose_end, body_end):
        grid[y][body_left] = "|"
        grid[y][body_right] = "|"

    window_y = min(body_end - 2, nose_end + 1)
    window = " IA " if width >= 11 else "IA"
    _place(grid, window_y, center - len(window) // 2, window)
    if body_end - window_y >= 3:
        _place(grid, window_y + 2, center - 2, "[::]")

    for x in range(body_left + 1, body_right):
        grid[body_end - 1][x] = "_"
    grid[body_end - 1][body_left] = "|"
    grid[body_end - 1][body_right] = "|"

    grid[body_end][max(0, body_left - 2)] = "/"
    grid[body_end][body_left] = "|"
    grid[body_end][body_right] = "|"
    grid[body_end][min(width - 1, body_right + 2)] = "\\"
    for x in range(max(0, body_left - 1), min(width, body_right + 2)):
        if grid[body_end][x] == " ":
            grid[body_end][x] = "_"

    _place(grid, height - 2, center - 2, "/||\\")
    _place(grid, height - 1, center - 2, " || ")
    return tuple("".join(row).rstrip() for row in grid)


def _sprite_for(mode: str, zoom: float) -> tuple[str, ...]:
    if mode == "flight_compact":
        return FLIGHT_COMPACT
    if mode.startswith("flight"):
        return _asset_lines(FLIGHT)
    if mode == "approach":
        return _approach_body()
    if zoom < 1.18:
        return _approach_body()
    width = 7 + round(max(0.0, zoom - 1.0) * 10)
    height = 7 + round(max(0.0, zoom - 1.0) * 9)
    return _vertical_sprite(width, height)


def sprite_size(mode: str, zoom: float = 1.0) -> tuple[int, int]:
    sprite = _sprite_for(mode, zoom)
    return max(map(len, sprite)), len(sprite)


def draw_rocket(
    canvas: Canvas,
    x: float,
    y: float,
    mode: str,
    thrust_frame: int,
    thrust: bool = True,
    zoom: float = 1.0,
) -> None:
    sprite = _sprite_for(mode, zoom)
    left, top = int(round(x)), int(round(y))
    for row, line in enumerate(sprite):
        visible = [column for column, char in enumerate(line) if char != " "]
        if visible:
            for column in range(min(visible), max(visible) + 1):
                canvas.put(left + column, top + row, " ")
        for column, char in enumerate(line):
            if char != " ":
                color = "white" if char in "[]()O:" else "cyan"
                canvas.put(left + column, top + row, char, color)
    if not thrust:
        return
    flames = ("*", "+", ":", ".")
    flame = flames[thrust_frame % len(flames)]
    if mode == "flight":
        exhaust_y = top + len(sprite) // 2
        canvas.put(left - 1, exhaust_y, flame, "yellow")
        if thrust_frame & 1:
            canvas.put(left - 2, exhaust_y, ".", "yellow")
    else:
        center = left + max(map(len, sprite)) // 2
        exhaust_y = top + len(sprite)
        canvas.text(center - 1, exhaust_y, "\\/", "yellow")
        canvas.text(center - 1, exhaust_y + 1, flame * 2, "yellow")
        if thrust_frame & 1:
            canvas.text(center - 2, exhaust_y + 2, ".  .", "yellow")

