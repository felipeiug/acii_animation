"""Buffer ASCII com clipping e composição ANSI."""

from __future__ import annotations

RESET = "\x1b[0m"
COLORS = {
    "white": "\x1b[97m",
    "dim": "\x1b[90m",
    "cyan": "\x1b[96m",
    "yellow": "\x1b[93m",
    "blue": "\x1b[34m",
    "green": "\x1b[32m",
    "ice": "\x1b[94m",
    "red": "\x1b[31m",
    "magenta": "\x1b[35m",
}


class Canvas:
    def __init__(self, width: int, height: int) -> None:
        self.width = max(1, width)
        self.height = max(1, height)
        self.chars = [[" "] * self.width for _ in range(self.height)]
        self.colors = [[""] * self.width for _ in range(self.height)]

    def put(self, x: int, y: int, char: str, color: str = "") -> None:
        if char and 0 <= x < self.width and 0 <= y < self.height:
            self.chars[y][x] = char[0]
            self.colors[y][x] = color

    def text(self, x: int, y: int, value: str, color: str = "") -> None:
        if not 0 <= y < self.height:
            return
        for offset, char in enumerate(value):
            self.put(x + offset, y, char, color)

    def sprite(
        self, x: int, y: int, lines: tuple[str, ...], color: str = "white"
    ) -> None:
        for row, line in enumerate(lines):
            self.text(x, y + row, line, color)

    def compose(self, use_colors: bool = True) -> str:
        if not use_colors:
            return "\n".join("".join(row) for row in self.chars)

        output: list[str] = []
        active = ""
        for y in range(self.height):
            for x in range(self.width):
                color = self.colors[y][x]
                if color != active:
                    output.append(COLORS.get(color, RESET if active else ""))
                    active = color
                output.append(self.chars[y][x])
            if y != self.height - 1:
                output.append("\n")
        if active:
            output.append(RESET)
        return "".join(output)

