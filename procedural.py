"""Geração procedural determinística de espaço, planetas e terreno."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import config
from renderer import Canvas

PLANET_TYPES = ("ROCKY", "DESERT", "ICE", "ALIEN", "VOLCANIC")
TYPE_COLORS = {
    "ROCKY": ("dim", "white"),
    "DESERT": ("yellow", "white"),
    "ICE": ("blue", "ice"),
    "ALIEN": ("magenta", "green"),
    "VOLCANIC": ("red", "yellow"),
}
PREFIXES = ("KEPLER", "NOVA", "XENON", "ORION", "LYRA", "VEGA", "ATLAS")
COSMIC_KINDS = ("SUN", "GALAXY", "BLACK_HOLE", "NEBULA", "RINGED_WORLD")
MOUNTAIN_PARALLAX = (0.14, 0.42, 1.0)
MOUNTAIN_HEIGHT_RANGES = ((0.26, 1.05), (0.14, 0.62), (0.05, 0.28))


@dataclass(frozen=True)
class Planet:
    name: str
    kind: str
    seed: int
    colors: tuple[str, str]


@dataclass
class Star:
    x: float
    y: float
    layer: int
    phase: float


@dataclass(frozen=True)
class CosmicObject:
    sector: int
    kind: str
    layer: int
    x: float
    y: float
    scale: float


def create_planet(rng: random.Random) -> Planet:
    kind = rng.choice(PLANET_TYPES)
    return Planet(
        f"{rng.choice(PREFIXES)}-{rng.randint(10, 999)}",
        kind,
        rng.randrange(1, 2_147_483_647),
        TYPE_COLORS[kind],
    )


def _hash(seed: int, value: int) -> float:
    number = (value * 374761393 + seed * 668265263) & 0xFFFFFFFF
    number = ((number ^ (number >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((number ^ (number >> 16)) & 0xFFFFFFFF) / 0xFFFFFFFF


def _smooth_noise(seed: int, x: float, spacing: float) -> float:
    point = x / spacing
    left = math.floor(point)
    blend = point - left
    blend = blend * blend * (3.0 - 2.0 * blend)
    return (_hash(seed, left) * (1.0 - blend) + _hash(seed, left + 1) * blend) * 2.0 - 1.0


def terrain_height(seed: int, world_x: float, layer: int, planet_type: str) -> float:
    """Retorna altura normalizada, de 0 (plano) a aproximadamente 1."""
    profiles = {
        "ROCKY": (0.34, 0.25, 17.0),
        "DESERT": (0.24, 0.13, 29.0),
        "ICE": (0.37, 0.31, 13.0),
        "ALIEN": (0.30, 0.22, 21.0),
        "VOLCANIC": (0.40, 0.33, 18.0),
    }
    base, amplitude, spacing = profiles.get(planet_type, profiles["ROCKY"])
    depth = (0.58, 0.78, 1.0)[max(0, min(2, layer))]
    x = world_x * (0.72 + layer * 0.16)
    broad = _smooth_noise(seed + layer * 97, x, spacing)
    detail = _smooth_noise(seed + layer * 193, x, max(5.0, spacing * 0.38))
    wave = math.sin((x + seed % 101) * 0.055) * 0.22
    height = (base + amplitude * (broad * 0.68 + detail * 0.20 + wave)) * depth
    if planet_type == "ICE":
        height += max(0.0, detail) * 0.07 * depth
    elif planet_type == "VOLCANIC":
        height += max(0.0, broad) ** 4 * 0.10 * depth
    return max(0.08, min(0.82, height))


def find_landing_site(planet: Planet, start_x: float, search_distance: int) -> float:
    best_x = start_x
    best_slope = float("inf")
    end = max(8, search_distance)
    for offset in range(6, end):
        x = start_x + offset
        samples = [terrain_height(planet.seed, x + delta, 2, planet.kind) for delta in range(-3, 4)]
        slope = max(samples) - min(samples)
        if slope < best_slope:
            best_x, best_slope = x, slope
    return best_x


def generate_stars(rng: random.Random, count: int) -> list[Star]:
    return [Star(rng.random(), rng.random(), rng.randrange(3), rng.random() * math.tau) for _ in range(count)]


def resize_stars(stars: list[Star], rng: random.Random, target: int) -> None:
    target = max(8, target)
    if len(stars) < target:
        stars.extend(generate_stars(rng, target - len(stars)))
    elif len(stars) > target:
        del stars[target:]


def update_stars(stars: list[Star], dt: float) -> None:
    speeds = (0.012, 0.027, 0.050)
    for star in stars:
        star.x = (star.x - speeds[star.layer] * dt) % 1.0
        star.phase += dt * (0.7 + star.layer * 0.35)


def draw_stars(canvas: Canvas, stars: list[Star], visibility: float = 1.0) -> None:
    glyphs = ((".", "'"), ("+", "."), ("*", "+"))
    colors = ("dim", "white", "white")
    cutoff = max(0.0, min(1.0, visibility))
    for star in stars:
        if _hash(int(star.phase * 10), int(star.x * 10000)) > cutoff:
            continue
        x = int(star.x * canvas.width)
        y = int(star.y * max(1, canvas.height - 2))
        glyph = glyphs[star.layer][int(star.phase) & 1]
        canvas.put(x, y, glyph, colors[star.layer])


def cosmic_kind(seed: int, sector: int) -> str:
    return COSMIC_KINDS[min(len(COSMIC_KINDS) - 1, int(_hash(seed + 811, sector) * len(COSMIC_KINDS)))]


def cosmic_object_layout(
    seed: int, world_x: float, width: int, height: int
) -> list[CosmicObject]:
    """Posiciona astros em tres profundidades de paralaxe deterministicas."""
    if width < 44 or height < 14:
        return []
    objects: list[CosmicObject] = []
    for layer, (speed, spacing, scale_range) in enumerate(
        zip(config.COSMIC_PARALLAX, config.COSMIC_LAYER_SPACING, config.COSMIC_SCALE_RANGES)
    ):
        camera_x = world_x * speed
        first = math.floor(camera_x / spacing) - 1
        last = math.floor((camera_x + width) / spacing) + 1
        for sector in range(first, last + 1):
            identity = sector * 3 + layer
            scale_noise = _hash(seed + 1201 + layer * 101, sector)
            scale = scale_range[0] + (scale_range[1] - scale_range[0]) * scale_noise
            offset = spacing * (0.18 + _hash(seed + 1301 + layer * 103, sector) * 0.64)
            x = sector * spacing + offset - camera_x
            top = max(5.0, height * 0.12)
            bottom = max(top, height * (0.56 if layer < 2 else 0.68))
            y = top + (bottom - top) * _hash(seed + 1409 + layer * 107, sector)
            kind = cosmic_kind(seed + layer * 977, sector)
            margin = 34 * scale
            if -margin <= x < width + margin:
                objects.append(CosmicObject(identity, kind, layer, x, y, scale))
    return objects


def _scaled_sprite(
    canvas: Canvas, center_x: int, center_y: int, lines: tuple[str, ...], scale: float, color: str
) -> None:
    source_width = max(map(len, lines))
    target_width = max(1, int(round(source_width * scale)))
    target_height = max(1, int(round(len(lines) * scale)))
    left = center_x - target_width // 2
    top = center_y - target_height // 2
    for ty in range(target_height):
        sy = min(len(lines) - 1, int(ty / scale))
        line = lines[sy].ljust(source_width)
        for tx in range(target_width):
            sx = min(source_width - 1, int(tx / scale))
            char = line[sx]
            if char != " ":
                canvas.put(left + tx, top + ty, char, color)


def _draw_nebula(canvas: Canvas, x: int, y: int, seed: int, scale: float, color: str) -> None:
    glyphs = (".", "'", ":", "~")
    radius_x = max(5, int(15 * scale))
    radius_y = max(2, int(4 * scale))
    for dy in range(-radius_y, radius_y + 1):
        for dx in range(-radius_x, radius_x + 1):
            radius = (dx / radius_x) ** 2 + (dy / radius_y) ** 2
            mist = _hash(seed + dy * 17, dx)
            if radius < 1.15 and mist > 0.42 + radius * 0.30:
                canvas.put(x + dx, y + dy, glyphs[int(mist * 10) % len(glyphs)], color)


def _draw_cosmic_object(
    canvas: Canvas, kind: str, x: int, y: int, seed: int, scale: float = 1.0, layer: int = 1
) -> None:
    color = "dim" if layer == 0 else None
    if kind == "SUN":
        sprite = (
            "     \\ | /", "   `.  *  .'", "---  (###)  ---", "   .'  *  `.", "     / | \\",
        )
        _scaled_sprite(canvas, x, y, sprite, scale, color or "yellow")
    elif kind == "GALAXY":
        sprite = (
            "       .  *", "   .-'  .   `-.", " .'   .(@).    `.", "<  .  (###)  .  >", " `.    `@'   .'", "   `-.  . .-'", "      *  .",
        )
        _scaled_sprite(canvas, x, y, sprite, scale, color or "magenta")
    elif kind == "BLACK_HOLE":
        sprite = (
            "       .-~~~~~~~~-.", "   .-'   .::::.   `-.", "==<====(      )====>==", "   `-.   `::::'  .-'", "       `-......-'",
        )
        _scaled_sprite(canvas, x, y, sprite, scale, color or "blue")
    elif kind == "RINGED_WORLD":
        sprite = (
            "        .---.", "     .-'::::::`-.", "---==(::::::::::)==---", "     `-.::::::.-'", "        `---'",
        )
        _scaled_sprite(canvas, x, y, sprite, scale, color or "cyan")
    else:
        _draw_nebula(canvas, x, y, seed, scale, color or "magenta")


def draw_cosmic_scenery(canvas: Canvas, seed: int, world_x: float) -> list[tuple[int, str]]:
    """Desenha marcos persistentes do fundo ao primeiro plano."""
    visible: list[tuple[int, str]] = []
    for obj in cosmic_object_layout(seed, world_x, canvas.width, canvas.height):
        _draw_cosmic_object(
            canvas, obj.kind, int(obj.x), int(obj.y), seed + obj.sector, obj.scale, obj.layer
        )
        visible.append((obj.sector, obj.kind))
    return visible


def draw_close_encounter(canvas: Canvas, kind: str, progress: float, seed: int) -> None:
    """Faz um astro atravessar a tela durante uma aproximação tranquila."""
    progress = max(0.0, min(1.0, progress))
    x = int(canvas.width * (1.18 - progress * 1.38))
    y = int(canvas.height * (0.34 + math.sin(progress * math.pi) * 0.08))
    scale = 0.75 + math.sin(progress * math.pi) * 1.35
    _draw_cosmic_object(canvas, kind, x, y, seed, scale, 2)
    if canvas.width >= 60:
        labels = {
            "SUN": "STELLAR FLYBY",
            "GALAXY": "DISTANT GALAXY",
            "BLACK_HOLE": "GRAVITY WELL",
            "NEBULA": "NEBULA CROSSING",
            "RINGED_WORLD": "RINGED WORLD",
        }
        label = labels[kind]
        canvas.text(max(1, x - len(label) // 2), min(canvas.height - 1, y + 6), label, "dim")


def _draw_black_hole(
    canvas: Canvas,
    center_x: int,
    center_y: int,
    radius_x: int,
    radius_y: int,
    seed: int,
    label: bool,
) -> None:
    for y in range(max(0, center_y - radius_y), min(canvas.height, center_y + radius_y + 1)):
        for x in range(max(0, center_x - radius_x), min(canvas.width, center_x + radius_x + 1)):
            dx = (x - center_x) / radius_x
            dy = (y - center_y) / radius_y
            distance = math.sqrt(dx * dx + dy * dy)
            if distance < 0.38:
                canvas.put(x, y, " ")
            elif 0.38 <= distance < 0.58:
                canvas.put(x, y, "@" if (x + y) % 3 else "#", "dim")
            elif 0.58 <= distance < 1.05:
                noise = _hash(seed + y, x)
                glyph = "=" if abs(dy) < 0.12 else "~" if noise > 0.55 else "."
                color = "yellow" if abs(dy) < 0.16 else "magenta"
                canvas.put(x, y, glyph, color)
    if label and canvas.width >= 60:
        label_text = "EVENT HORIZON"
        label_x = min(canvas.width - len(label_text) - 1, max(1, center_x - 8))
        canvas.text(label_x, min(canvas.height - 1, center_y + radius_y), label_text, "red")


def draw_gravity_hazard(
    canvas: Canvas, progress: float, seed: int, proximity: float = 1.0
) -> None:
    """Buraco negro próximo usado no evento de carga crítica do servidor."""
    proximity = max(0.0, min(1.0, proximity))
    center_x = int(canvas.width * (1.16 - 0.34 * proximity))
    center_y = int(canvas.height * 0.48)
    radius_x = max(
        4,
        int(canvas.width * (0.04 + 0.16 * proximity + 0.025 * proximity * math.sin(progress * math.pi))),
    )
    radius_y = max(3, int(canvas.height * (0.08 + 0.22 * proximity)))
    _draw_black_hole(canvas, center_x, center_y, radius_x, radius_y, seed, True)


def draw_passing_black_hole(canvas: Canvas, progress: float, seed: int) -> None:
    """Versão distante que cruza lentamente o fundo da exploração."""
    progress = max(0.0, min(1.0, progress))
    center_x = int(canvas.width * (1.25 - progress * 1.50))
    center_y = int(canvas.height * (0.30 + math.sin(progress * math.pi) * 0.10))
    radius_x = max(10, int(canvas.width * 0.14))
    radius_y = max(5, int(canvas.height * 0.21))
    _draw_black_hole(canvas, center_x, center_y, radius_x, radius_y, seed, False)


def draw_planet_disc(canvas: Canvas, planet: Planet, progress: float) -> None:
    radius_y = max(2, int(canvas.height * (0.05 + 0.20 * progress)))
    radius_x = radius_y * 2
    center_x = canvas.width - radius_x - max(1, int(canvas.width * 0.04))
    center_y = int(canvas.height * 0.45)
    for dy in range(-radius_y, radius_y + 1):
        span = int(radius_x * math.sqrt(max(0.0, 1.0 - (dy / radius_y) ** 2)))
        for dx in range(-span, span + 1):
            edge = abs(dx) >= span - 1
            texture = _hash(planet.seed + dy, dx + center_x)
            char = "#" if edge else (":" if texture > 0.78 else "." if texture > 0.56 else " ")
            if char != " ":
                canvas.put(center_x + dx, center_y + dy, char, planet.colors[1 if edge else 0])


def _bottom_sprite(canvas: Canvas, x: int, ground_y: int, sprite: tuple[str, ...], color: str) -> None:
    width = max(map(len, sprite))
    canvas.sprite(x - width // 2, ground_y - len(sprite), sprite, color)


def _zoomed_x(world_position: float, camera_x: float, focus_x: float, zoom: float) -> int:
    return int(round(focus_x + (world_position - camera_x - focus_x) * zoom))


def draw_planet_sky(
    canvas: Canvas, planet: Planet, world_x: float, reveal: float, zoom: float = 1.0
) -> None:
    """Lua, nuvens e grandes formações distantes do bioma atual."""
    if reveal < 0.15 or canvas.width < 40:
        return
    color = planet.colors[0]
    focus_x = canvas.width * 0.32
    sky_zoom = 1.0 + (zoom - 1.0) * 0.35
    sky_drift = world_x * 0.16
    moon_sector = math.floor(sky_drift / 150)
    moon_x = _zoomed_x(moon_sector * 150 + 95, sky_drift, focus_x, sky_zoom)
    moon_y = max(5, int(canvas.height * 0.22))
    sky_objects = {
        "ROCKY": ("   .--.", " .' .. `.", "(  .  .  )", " `.____.'"),
        "DESERT": ("   \\ | /", " -- (O) --", "   / | \\"),
        "ICE": ("    .", " .- * -.", "    '"),
        "ALIEN": ("  .-=-.", "( o O o )", " `-===-'"),
        "VOLCANIC": ("  .::.", " (####)", "  `::'"),
    }
    moon = sky_objects[planet.kind]
    _bottom_sprite(canvas, moon_x, moon_y + len(moon), moon, color)

    formation_drift = world_x * 0.42
    formation_zoom = 1.0 + (zoom - 1.0) * 0.62
    spacing = 58
    first = math.floor(formation_drift / spacing) - 1
    last = math.floor((formation_drift + canvas.width) / spacing) + 1
    formations = {
        "ROCKY": ("      /\\", "  /\\ /  \\ /\\", "_/  V    V  \\_"),
        "DESERT": ("    ______", " __/      \\__", "/            \\"),
        "ICE": ("      /\\", "  /\\ /  /\\", "_/  V  /  \\_"),
        "ALIEN": ("   .-^-.", " _( o o )_", "   /| |\\", "  / | | \\"),
        "VOLCANIC": ("      (  )", "   (  )( )", "    /\\ /\\", "___/  V  \\__"),
    }
    sprite = formations[planet.kind]
    base = int(canvas.height * 0.66)
    for sector in range(first, last + 1):
        if _hash(planet.seed + 307, sector) < 0.28:
            continue
        x = _zoomed_x(sector * spacing + spacing * 0.5, formation_drift, focus_x, formation_zoom)
        _bottom_sprite(canvas, x, base, sprite, color)


def draw_surface_details(
    canvas: Canvas,
    planet: Planet,
    world_x: float,
    ground: list[int],
    reveal: float,
    zoom: float = 1.0,
) -> None:
    """Adiciona vegetação, cristais, ruínas e rochas presas ao terreno."""
    if reveal < 0.55 or canvas.width < 32 or not ground:
        return
    sprites = {
        "ROCKY": (("  __", "_/  \\_"), (" /\\", "/__\\"), ("  |", "[=]", "_|_")),
        "DESERT": ((" _|_", "  | ", " _| ", "  | "), (" .--.", "/____\\"), ("  /\\", "_/  \\_")),
        "ICE": (("  /\\", " /  \\", "/_/\\_\\"), (" /|", "/_|"), ("  *", " /\\", "/__\\")),
        "ALIEN": ((" .-.", "(o o)", " \\|/", "  | "), ("  @", " /|\\", "(_|_)"), (" \\|/", "--O--", " /|\\")),
        "VOLCANIC": ((" ( )", "  )", " /\\", "/__\\"), ("  ^", " /#\\", "/###\\"), (" .-.", "(___)")),
    }
    large_sprites = {
        "ROCKY": (("    ____", " __/    \\__", "/          \\"), ("   /\\", "  /  \\", " / /\\ \\", "/_/  \\_\\"), ("  .---.", "  |[] |", "  |   |", "__|___|__")),
        "DESERT": (("  _|_", "   |  _", "  _|_|_", "   | |", "   | |"), ("   _______", " _/       \\_", "/____________\\"), ("   _  _", " _/ \\/ \\_", "/        \\")),
        "ICE": (("    /\\", "   /  \\", " /\\ /\\ \\", "/__V__\\_\\"), ("  /|", " / | /|", "/__|/_|"), ("    *", "   /\\", "  /  \\", " /_/\\_\\")),
        "ALIEN": (("  .---.", " ( o o )", "  `-+-'", "  \\ | /", "   \\|/", "    |"), ("   .-@-.", "  /     \\", " (_______)", "    | |", "   _| |_"), ("   \\ | /", " -- (O) --", "   / | \\", "     |")),
        "VOLCANIC": (("   (  )", "  ( )( )", "   )  (", "   /\\", "  /##\\", "_/####\\_"), ("    ^", "   /#\\", "  /###\\", "_/#####\\_"), ("  .---.", " / . . \\", "/_______\\")),
    }
    choices = large_sprites[planet.kind] if zoom >= 1.45 else sprites[planet.kind]
    focus_x = canvas.width * 0.32
    spacing = 19
    first = math.floor(world_x / spacing) - 1
    last = math.floor((world_x + canvas.width) / spacing) + 1
    for sector in range(first, last + 1):
        chance = _hash(planet.seed + 509, sector)
        if chance < 0.42:
            continue
        x = _zoomed_x(sector * spacing + spacing * 0.5, world_x, focus_x, zoom)
        if not 0 <= x < canvas.width:
            continue
        sprite = choices[int(chance * 10) % len(choices)]
        _bottom_sprite(canvas, x, ground[x], sprite, planet.colors[1])


def draw_mountain_layer(
    canvas: Canvas,
    planet: Planet,
    world_x: float,
    layer: int,
    reveal: float = 1.0,
    zoom: float = 1.0,
) -> list[int]:
    reveal = max(0.0, min(1.0, reveal))
    bottom = canvas.height - 1
    speed = MOUNTAIN_PARALLAX[layer]
    minimum, maximum = MOUNTAIN_HEIGHT_RANGES[layer]
    normalization = (0.34, 0.54, 0.70)[layer]
    layer_zoom = 1.0 + (max(1.0, zoom) - 1.0) * (0.35, 0.65, 1.0)[layer]
    focus_x = canvas.width * 0.32
    heights: list[int] = []
    color = "dim" if layer == 0 else planet.colors[0 if layer == 1 else 1]
    for x in range(canvas.width):
        sample_x = world_x * speed + focus_x + (x - focus_x) / max(1.0, zoom)
        raw_height = terrain_height(planet.seed, sample_x, layer, planet.kind)
        shape = max(0.0, min(1.0, (raw_height - 0.08) / normalization))
        if layer == 0:
            massif = (math.sin((sample_x + planet.seed % 503) * math.tau / 170.0) + 1.0) * 0.5
            shape = max(shape, massif**4)
        ratio = minimum + (maximum - minimum) * shape
        height = int(canvas.height * ratio * reveal * layer_zoom)
        top = max(0, min(bottom, bottom - height))
        heights.append(top)
    if layer == 2 and zoom > 1.0 and heights:
        focus_index = min(canvas.width - 1, max(0, int(focus_x)))
        landing_line = int(canvas.height * 0.80)
        vertical_shift = landing_line - heights[focus_index]
        heights = [min(bottom, top + vertical_shift) for top in heights]
    for x, top in enumerate(heights):
        if reveal <= 0.0:
            continue
        before = heights[max(0, x - 1)]
        after = heights[min(canvas.width - 1, x + 1)]
        edge = "/" if after < top else "\\" if before < top else "_"
        canvas.put(x, top, edge, color)
        fills = {
            "ROCKY": (".", ":", "#"),
            "DESERT": (".", "~", ":"),
            "ICE": (".", "/", "*"),
            "ALIEN": ("'", ":", "%"),
            "VOLCANIC": (".", "^", "#"),
        }
        fill = fills[planet.kind][layer]
        for y in range(top + 1, bottom + 1):
            texture = _hash(planet.seed + layer * 701 + y, int(world_x * speed) + x)
            if layer == 2:
                glyph = fill if texture > 0.16 else (":" if texture > 0.08 else " ")
                canvas.put(x, y, glyph, color)
            elif texture > 0.58 + layer * 0.08:
                canvas.put(x, y, fill, color)
    return heights

