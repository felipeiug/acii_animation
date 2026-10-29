"""Máquina de estados e composição das cenas."""

from __future__ import annotations

import math
import random
from enum import Enum, auto

import config
from procedural import (
    Planet,
    Star,
    create_planet,
    draw_close_encounter,
    draw_cosmic_scenery,
    draw_gravity_hazard,
    draw_mountain_layer,
    draw_planet_disc,
    draw_planet_sky,
    draw_passing_black_hole,
    draw_stars,
    draw_surface_details,
    find_landing_site,
    generate_stars,
    resize_stars,
    terrain_height,
    update_stars,
)
from renderer import Canvas
from rocket import draw_rocket, sprite_size


class State(Enum):
    SPACE = auto()
    APPROACH = auto()
    ATMOSPHERE = auto()
    FLYOVER = auto()
    LANDING = auto()
    LANDED = auto()
    TAKEOFF = auto()


class Explorer:
    def __init__(self, seed: int | None = None) -> None:
        self.seed = seed if seed is not None else random.SystemRandom().randrange(2**31)
        self.rng = random.Random(self.seed)
        self.state = State.SPACE
        self.elapsed = 0.0
        self.duration = self.rng.uniform(config.MIN_SPACE_DURATION, config.MAX_SPACE_DURATION)
        self.planet: Planet | None = None
        self.stars: list[Star] = generate_stars(self.rng, 80)
        self.world_x = 0.0
        self.distance = 0.0
        self.visited = 0
        self.stats = {
            "planets_discovered": 0,
            "landings": 0,
            "takeoffs": 0,
            "suns_seen": 0,
            "galaxies_seen": 0,
            "black_holes_seen": 0,
            "nebulae_seen": 0,
            "ringed_worlds_seen": 0,
            "flybys": 0,
            "resource_alerts": 0,
            "gravity_escapes": 0,
            "runtime_seconds": 0.0,
        }
        self.max_cosmic_sector: int | None = None
        self.encounter_kind = ""
        self.will_land = False
        self.landing_world_x = 0.0
        self.flyover_start_world_x = 0.0
        self.thrust_frame = 0
        self.last_size = (0, 0)
        self.cpu_percent: float | None = None
        self.memory_percent: float | None = None
        self.memory_pressure = False
        self.gravity_active = False
        self.gravity_critical = False
        self.gravity_proximity = 0.0
        self.gravity_elapsed = 0.0
        self.background_black_hole_active = False
        self.background_black_hole_elapsed = 0.0
        self.background_black_hole_duration = 0.0
        self.background_black_hole_timer = self.rng.uniform(
            config.MIN_BACKGROUND_BLACK_HOLE_INTERVAL,
            config.MAX_BACKGROUND_BLACK_HOLE_INTERVAL,
        )

    @property
    def progress(self) -> float:
        return min(1.0, self.elapsed / max(0.001, self.duration))

    def _enter(self, state: State) -> None:
        self.state = state
        self.elapsed = 0.0
        if state is State.SPACE:
            self.duration = self.rng.uniform(config.MIN_SPACE_DURATION, config.MAX_SPACE_DURATION)
            self.planet = None
            self.encounter_kind = ""
            self.will_land = False
        elif state is State.APPROACH:
            if self.rng.random() < config.PLANET_ENCOUNTER_CHANCE:
                self.encounter_kind = "PLANET"
                self.planet = create_planet(self.rng)
                self.will_land = self.rng.random() < config.PLANET_LANDING_CHANCE
                self.stats["planets_discovered"] += 1
            else:
                self.encounter_kind = self.rng.choice(("SUN", "GALAXY", "BLACK_HOLE", "NEBULA", "RINGED_WORLD"))
                self.planet = None
                self.will_land = False
                self._record_cosmic_kind(self.encounter_kind)
            self.duration = self.rng.uniform(config.MIN_APPROACH_DURATION, config.MAX_APPROACH_DURATION)
        elif state is State.ATMOSPHERE:
            if self.planet is None:
                self.planet = create_planet(self.rng)
            self.duration = config.ATMOSPHERE_DURATION
        elif state is State.FLYOVER:
            self.duration = self.rng.uniform(config.MIN_FLYOVER_DURATION, config.MAX_FLYOVER_DURATION)
            assert self.planet is not None
            self.flyover_start_world_x = self.world_x
            start = self.world_x + self.duration * 7.0
            self.landing_world_x = find_landing_site(self.planet, start, 100)
        elif state is State.LANDING:
            self.duration = config.LANDING_DURATION
        elif state is State.LANDED:
            self.duration = self.rng.uniform(config.MIN_LANDED_DURATION, config.MAX_LANDED_DURATION)
            self.visited += 1
            self.stats["landings"] += 1
        elif state is State.TAKEOFF:
            self.duration = self.rng.uniform(config.MIN_TAKEOFF_DURATION, config.MAX_TAKEOFF_DURATION)
            self.stats["takeoffs"] += 1

    def update(self, dt: float, width: int, height: int) -> None:
        dt = max(0.0, min(dt, 0.25))
        self.stats["runtime_seconds"] += dt
        self.thrust_frame += 1
        self.last_size = (width, height)
        density_factor = 0.45 if self.memory_pressure else 1.0
        target_stars = int(width * height * config.STAR_DENSITY * density_factor)
        resize_stars(self.stars, self.rng, target_stars)
        update_stars(self.stars, dt)
        critical = (
            self.cpu_percent is not None
            and self.memory_percent is not None
            and self.cpu_percent >= config.CRITICAL_CPU_THRESHOLD
            and self.memory_percent >= config.CRITICAL_MEMORY_THRESHOLD
        )
        was_critical = self.gravity_critical
        self.gravity_critical = critical
        target_proximity = 1.0 if critical else 0.0
        response = min(1.0, dt * config.GRAVITY_RESPONSE_SPEED)
        self.gravity_proximity += (target_proximity - self.gravity_proximity) * response
        if critical and not was_critical:
            self.stats["black_holes_seen"] += 1
        elif was_critical and not critical:
            self.stats["gravity_escapes"] += 1
        if not critical and self.gravity_proximity < 0.015:
            self.gravity_proximity = 0.0
        self.gravity_active = critical or self.gravity_proximity > 0.0
        if self.gravity_active:
            self.gravity_elapsed += dt
        if critical:
            return

        if self.background_black_hole_active:
            self.background_black_hole_elapsed += dt
            if self.background_black_hole_elapsed >= self.background_black_hole_duration:
                self.background_black_hole_active = False
                self.background_black_hole_elapsed = 0.0
                self.background_black_hole_timer = self.rng.uniform(
                    config.MIN_BACKGROUND_BLACK_HOLE_INTERVAL,
                    config.MAX_BACKGROUND_BLACK_HOLE_INTERVAL,
                )
        elif self.state is State.SPACE:
            self.background_black_hole_timer -= dt
            if self.background_black_hole_timer <= 0.0:
                self.background_black_hole_active = True
                self.background_black_hole_elapsed = 0.0
                self.background_black_hole_duration = self.rng.uniform(
                    config.MIN_BACKGROUND_BLACK_HOLE_DURATION,
                    config.MAX_BACKGROUND_BLACK_HOLE_DURATION,
                )
                self.stats["black_holes_seen"] += 1

        self.elapsed += dt

        speeds = {
            State.SPACE: 8.0,
            State.APPROACH: 6.0,
            State.ATMOSPHERE: 5.0,
            State.FLYOVER: 4.5,
            State.LANDING: 1.2,
            State.LANDED: 0.0,
            State.TAKEOFF: 3.0,
        }
        previous_world_x = self.world_x
        if self.state is State.FLYOVER:
            rocket_center = width * 0.32
            target_camera = self.landing_world_x - rocket_center
            eased = self.progress * self.progress * (3.0 - 2.0 * self.progress)
            self.world_x = self.flyover_start_world_x * (1.0 - eased) + target_camera * eased
        else:
            movement = speeds[self.state] * dt
            self.world_x += movement
        movement = self.world_x - previous_world_x
        self.distance += movement * 0.08

        if self.elapsed >= self.duration:
            next_state = {
                State.SPACE: State.APPROACH,
                State.APPROACH: State.ATMOSPHERE if self.encounter_kind == "PLANET" and self.will_land else State.SPACE,
                State.ATMOSPHERE: State.FLYOVER,
                State.FLYOVER: State.LANDING,
                State.LANDING: State.LANDED,
                State.LANDED: State.TAKEOFF,
                State.TAKEOFF: State.SPACE,
            }[self.state]
            if self.state is State.APPROACH and next_state is State.SPACE:
                self.stats["flybys"] += 1
            self._enter(next_state)

    def set_system_metrics(self, cpu_percent: float | None, memory_percent: float | None) -> None:
        previous_pressure = self.memory_pressure
        self.cpu_percent = cpu_percent
        self.memory_percent = memory_percent
        self.memory_pressure = (
            memory_percent is not None and memory_percent >= config.MEMORY_PRESSURE_THRESHOLD
        )
        if self.memory_pressure and not previous_pressure:
            self.stats["resource_alerts"] += 1

    def register_cosmic_objects(self, visible: list[tuple[int, str]]) -> None:
        unseen = [item for item in visible if self.max_cosmic_sector is None or item[0] > self.max_cosmic_sector]
        for _, kind in unseen:
            self._record_cosmic_kind(kind)
        if visible:
            highest = max(sector for sector, _ in visible)
            self.max_cosmic_sector = highest if self.max_cosmic_sector is None else max(self.max_cosmic_sector, highest)

    def _record_cosmic_kind(self, kind: str) -> None:
        counters = {
            "SUN": "suns_seen",
            "GALAXY": "galaxies_seen",
            "BLACK_HOLE": "black_holes_seen",
            "NEBULA": "nebulae_seen",
            "RINGED_WORLD": "ringed_worlds_seen",
        }
        self.stats[counters[kind]] += 1

    def snapshot(self) -> dict[str, object]:
        planet = None
        if self.planet:
            planet = {
                "name": self.planet.name,
                "kind": self.planet.kind,
                "seed": self.planet.seed,
                "colors": list(self.planet.colors),
            }
        return {
            "version": 1,
            "seed": self.seed,
            "state": self.state.name,
            "state_elapsed_seconds": self.elapsed,
            "state_duration_seconds": self.duration,
            "distance_au": self.distance,
            "world_x": self.world_x,
            "planets_visited": self.visited,
            "current_planet": planet,
            "landing_world_x": self.landing_world_x,
            "flyover_start_world_x": self.flyover_start_world_x,
            "max_cosmic_sector": self.max_cosmic_sector,
            "encounter_kind": self.encounter_kind,
            "will_land": self.will_land,
            "background_black_hole_active": self.background_black_hole_active,
            "background_black_hole_elapsed": self.background_black_hole_elapsed,
            "background_black_hole_duration": self.background_black_hole_duration,
            "background_black_hole_timer": self.background_black_hole_timer,
            "statistics": dict(self.stats),
            "random_state": self.rng.getstate(),
        }

    @classmethod
    def from_snapshot(cls, data: dict[str, object]) -> "Explorer":
        explorer = cls(int(data["seed"]))
        explorer.state = State[str(data.get("state", "SPACE"))]
        explorer.elapsed = float(data.get("state_elapsed_seconds", 0.0))
        explorer.duration = max(0.001, float(data.get("state_duration_seconds", explorer.duration)))
        explorer.distance = float(data.get("distance_au", 0.0))
        explorer.world_x = float(data.get("world_x", 0.0))
        explorer.visited = int(data.get("planets_visited", 0))
        explorer.landing_world_x = float(data.get("landing_world_x", 0.0))
        explorer.flyover_start_world_x = float(data.get("flyover_start_world_x", explorer.world_x))
        maximum = data.get("max_cosmic_sector")
        explorer.max_cosmic_sector = int(maximum) if maximum is not None else None
        explorer.encounter_kind = str(data.get("encounter_kind", "PLANET" if data.get("current_planet") else ""))
        explorer.will_land = bool(data.get("will_land", data.get("current_planet") is not None))
        explorer.background_black_hole_active = bool(data.get("background_black_hole_active", False))
        explorer.background_black_hole_elapsed = float(data.get("background_black_hole_elapsed", 0.0))
        explorer.background_black_hole_duration = float(data.get("background_black_hole_duration", 0.0))
        explorer.background_black_hole_timer = float(
            data.get("background_black_hole_timer", explorer.background_black_hole_timer)
        )
        saved_stats = data.get("statistics", {})
        if isinstance(saved_stats, dict):
            for key in explorer.stats:
                if key in saved_stats:
                    explorer.stats[key] = float(saved_stats[key]) if key == "runtime_seconds" else int(saved_stats[key])
        saved_planet = data.get("current_planet")
        if isinstance(saved_planet, dict):
            colors = saved_planet.get("colors", ["dim", "white"])
            explorer.planet = Planet(
                str(saved_planet["name"]),
                str(saved_planet["kind"]),
                int(saved_planet["seed"]),
                (str(colors[0]), str(colors[1])),
            )
        random_state = data.get("random_state")
        if random_state is not None:
            explorer.rng.setstate(_as_tuple(random_state))
        return explorer

    def _terrain_reveal(self) -> float:
        if self.state is State.ATMOSPHERE:
            return self.progress
        if self.state is State.TAKEOFF:
            return max(0.0, 1.0 - max(0.0, self.progress - 0.55) / 0.45)
        return 1.0

    def _scene_zoom(self, height: int) -> float:
        maximum = 1.85 if height >= 32 else 1.40 if height >= 24 else 1.0
        if self.state is State.LANDING:
            return 1.0 + (maximum - 1.0) * self.progress
        if self.state is State.LANDED:
            return maximum
        if self.state is State.TAKEOFF:
            return maximum + (1.0 - maximum) * self.progress
        return 1.0

    def _rocket_position(self, width: int, height: int, ground: list[int] | None) -> tuple[float, float, str, bool, float]:
        p = self.progress
        flight_y = height * 0.32 + math.sin((self.distance + self.elapsed) * 0.35) * 0.7
        thrust = True
        zoom = self._scene_zoom(height)
        mode = "vertical" if self.state in {State.LANDING, State.LANDED, State.TAKEOFF} else "approach" if self.state in {State.APPROACH, State.ATMOSPHERE} else "flight_compact" if width < 64 else "flight"
        rocket_center = width * 0.32
        if self.state is State.SPACE:
            rocket_center = width * (0.34 + 0.015 * math.sin(self.elapsed * 0.5))
        elif self.state is State.APPROACH:
            rocket_center = width * (0.34 - 0.02 * p)
        rocket_width, rocket_height = sprite_size(mode, zoom)
        x = rocket_center - rocket_width / 2
        ground_y = (ground[int(min(width - 1, max(0, rocket_center)))] if ground else int(height * 0.78))
        landed_y = ground_y - rocket_height

        if self.state is State.SPACE:
            flight_y = height * 0.40 + math.sin(self.elapsed * 0.7) * 0.8
        elif self.state is State.APPROACH:
            flight_y = height * (0.40 - 0.08 * p)
        elif self.state is State.LANDING:
            eased = p * p * (3.0 - 2.0 * p)
            flight_y = flight_y * (1.0 - eased) + landed_y * eased
        elif self.state is State.LANDED:
            flight_y, thrust = landed_y, False
        elif self.state is State.TAKEOFF:
            eased = p * p * (3.0 - 2.0 * p)
            target = height * 0.32
            flight_y = landed_y * (1.0 - eased) + target * eased
        return x, min(flight_y, landed_y if self.state is State.LANDING else flight_y), mode, thrust, zoom

    def _draw_decorations(self, canvas: Canvas) -> None:
        if self.state is not State.SPACE:
            return
        marker = int(self.distance) % 137
        if config.ENABLE_ASTEROIDS and marker < 12:
            x = canvas.width - marker * 3
            canvas.text(x, int(canvas.height * 0.7), "<o>", "dim")
        if config.ENABLE_COMETS and 66 <= marker < 78:
            x = canvas.width - (marker - 66) * 4
            canvas.text(x, int(canvas.height * 0.2), "---*", "white")

    def render(self, width: int, height: int, use_colors: bool = True) -> str:
        canvas = Canvas(width, height)
        terrain_states = {State.ATMOSPHERE, State.FLYOVER, State.LANDING, State.LANDED, State.TAKEOFF}
        visibility = 1.0
        if self.state is State.ATMOSPHERE:
            visibility = 1.0 - self.progress
        elif self.state in terrain_states and self.state is not State.TAKEOFF:
            visibility = 0.12
        elif self.state is State.TAKEOFF:
            visibility = self.progress
        draw_stars(canvas, self.stars, visibility)
        if self.gravity_active:
            pulse = (self.gravity_elapsed % 8.0) / 8.0
            draw_gravity_hazard(
                canvas,
                pulse,
                self.seed + self.stats["gravity_escapes"],
                self.gravity_proximity,
            )
            pull = self.gravity_proximity * (
                0.90 + math.sin(self.gravity_elapsed * 2.4) * 0.06
            )
            mode = "flight_compact" if width < 64 else "flight"
            rocket_width, _ = sprite_size(mode)
            center_x = width * (0.34 + 0.28 * pull)
            x = center_x - rocket_width / 2
            y = height * (0.42 + math.sin(self.gravity_elapsed * 3.1) * 0.025 * pull)
            draw_rocket(canvas, x, y, mode, self.thrust_frame, True)
            self._draw_hud(canvas)
            return canvas.compose(use_colors)

        if self.background_black_hole_active and not self.memory_pressure:
            progress = min(
                1.0,
                self.background_black_hole_elapsed / max(0.001, self.background_black_hole_duration),
            )
            draw_passing_black_hole(canvas, progress, self.seed + self.stats["black_holes_seen"])

        if config.ENABLE_COSMIC_LANDMARKS and not self.memory_pressure and self.state is State.SPACE:
            visible = draw_cosmic_scenery(canvas, self.seed, self.world_x)
            self.register_cosmic_objects(visible)
        if not self.memory_pressure:
            self._draw_decorations(canvas)

        if self.state is State.APPROACH:
            if self.encounter_kind == "PLANET" and self.planet:
                encounter_progress = self.progress if self.will_land else math.sin(self.progress * math.pi)
                draw_planet_disc(canvas, self.planet, encounter_progress)
            elif self.encounter_kind:
                draw_close_encounter(canvas, self.encounter_kind, self.progress, self.seed + int(self.distance))

        ground = None
        if self.state in terrain_states and self.planet:
            reveal = self._terrain_reveal()
            zoom = self._scene_zoom(height)
            if config.ENABLE_PLANET_SCENERY and not self.memory_pressure:
                draw_planet_sky(canvas, self.planet, self.world_x, reveal, zoom)
            for layer in range(3):
                heights = draw_mountain_layer(canvas, self.planet, self.world_x, layer, reveal, zoom)
                if layer == 2:
                    ground = heights
            if config.ENABLE_PLANET_SCENERY and not self.memory_pressure and ground:
                draw_surface_details(canvas, self.planet, self.world_x, ground, reveal, zoom)

        x, y, mode, thrust, zoom = self._rocket_position(width, height, ground)
        draw_rocket(canvas, x, y, mode, self.thrust_frame, thrust, zoom)
        self._draw_hud(canvas)
        return canvas.compose(use_colors)

    def _draw_hud(self, canvas: Canvas) -> None:
        canvas.text(1, 0, "ASCII SPACE EXPLORER", "dim")
        if canvas.height < 16 or canvas.width < 48:
            status = "GRAVITY STRUGGLE" if self.gravity_critical else "LEAVING GRAVITY WELL" if self.gravity_active else "LOW MEMORY" if self.memory_pressure else self.state.name
            canvas.text(1, 1, status, "red" if self.gravity_critical else "white")
            canvas.text(1, 2, self._metrics_text(), "yellow" if self.memory_pressure else "dim")
            return
        target = self.planet.name if self.planet else self.encounter_kind.replace("_", " ") if self.encounter_kind else "DEEP SPACE"
        canvas.text(1, 1, f"TARGET: {target}", "dim")
        if self.gravity_active:
            status = "GRAVITY STRUGGLE" if self.gravity_critical else "LEAVING GRAVITY WELL"
        elif self.memory_pressure:
            status = "LOW RESOURCE MODE"
        elif self.state is State.APPROACH and not self.will_land:
            status = "PLANETARY FLYBY" if self.encounter_kind == "PLANET" else "CLOSE FLYBY"
        else:
            status = self.state.name
        canvas.text(1, 2, f"STATUS: {status}", "dim")
        if canvas.width >= 64:
            canvas.text(1, 3, f"DISTANCE: {int(self.distance):06d} AU  VISITED: {self.visited}", "dim")
            metric_color = "red" if self.gravity_critical else "yellow" if self.memory_pressure else "dim"
            canvas.text(1, 4, self._metrics_text(), metric_color)

    def _metrics_text(self) -> str:
        cpu = "--" if self.cpu_percent is None else f"{self.cpu_percent:4.1f}%"
        memory = "--" if self.memory_percent is None else f"{self.memory_percent:4.1f}%"
        return f"CPU: {cpu}  RAM: {memory}"


def _as_tuple(value: object) -> object:
    if isinstance(value, list):
        return tuple(_as_tuple(item) for item in value)
    return value

