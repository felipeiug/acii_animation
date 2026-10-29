import random
import os
import tempfile
import time
import unittest
from pathlib import Path

import config
from explorer import Explorer, State
from procedural import COSMIC_KINDS, MOUNTAIN_PARALLAX, cosmic_kind, cosmic_object_layout, create_planet, draw_mountain_layer, find_landing_site, terrain_height
from renderer import Canvas
from persistence import load_explorer, save_explorer
from rocket import _sprite_for, sprite_size
from metrics import SystemMonitor


class ProceduralTests(unittest.TestCase):
    def test_terrain_is_deterministic_and_continuous(self):
        values_a = [terrain_height(42, x / 4, 2, "ROCKY") for x in range(100)]
        values_b = [terrain_height(42, x / 4, 2, "ROCKY") for x in range(100)]
        self.assertEqual(values_a, values_b)
        self.assertLess(max(abs(a - b) for a, b in zip(values_a, values_a[1:])), 0.12)

    def test_landing_site_is_in_search_range(self):
        planet = create_planet(random.Random(7))
        site = find_landing_site(planet, 100.0, 80)
        self.assertGreaterEqual(site, 106.0)
        self.assertLess(site, 180.0)

    def test_cosmic_scenery_is_deterministic_and_varied(self):
        first = [cosmic_kind(42, sector) for sector in range(100)]
        second = [cosmic_kind(42, sector) for sector in range(100)]
        self.assertEqual(first, second)
        self.assertEqual(set(first), set(COSMIC_KINDS))

    def test_cosmic_depth_controls_scale_and_parallax(self):
        first = cosmic_object_layout(42, 100.0, 2400, 50)
        second = cosmic_object_layout(42, 110.0, 2400, 50)
        self.assertEqual(first, cosmic_object_layout(42, 100.0, 2400, 50))
        average_scale = {
            layer: sum(obj.scale for obj in first if obj.layer == layer)
            / sum(1 for obj in first if obj.layer == layer)
            for layer in range(3)
        }
        self.assertLess(average_scale[0], average_scale[1])
        self.assertLess(average_scale[1], average_scale[2])
        by_id = {(obj.sector, obj.layer): obj for obj in second}
        movement = {
            layer: [
                obj.x - by_id[(obj.sector, obj.layer)].x
                for obj in first
                if obj.layer == layer and (obj.sector, obj.layer) in by_id
            ]
            for layer in range(3)
        }
        self.assertLess(abs(movement[0][0]), abs(movement[1][0]))
        self.assertLess(abs(movement[1][0]), abs(movement[2][0]))

    def test_terrain_zoom_keeps_landing_area_in_frame(self):
        planet = create_planet(random.Random(12))
        canvas = Canvas(100, 40)
        ground = draw_mountain_layer(canvas, planet, 50.0, 2, 1.0, 1.85)
        self.assertEqual(ground[int(100 * 0.32)], int(40 * 0.80))

    def test_distant_mountains_are_tallest_and_slowest(self):
        planet = create_planet(random.Random(18))
        extents = []
        for layer in range(3):
            ground = draw_mountain_layer(Canvas(160, 50), planet, 200.0, layer)
            extents.append(49 - min(ground))
        self.assertGreater(extents[0], extents[1])
        self.assertGreater(extents[1], extents[2])
        self.assertGreaterEqual(extents[0], 48)
        self.assertLess(MOUNTAIN_PARALLAX[0], MOUNTAIN_PARALLAX[1])
        self.assertLess(MOUNTAIN_PARALLAX[1], MOUNTAIN_PARALLAX[2])


class RendererTests(unittest.TestCase):
    def test_clipping_and_plain_output(self):
        canvas = Canvas(5, 2)
        canvas.text(-2, 0, "abcdef")
        canvas.sprite(3, 1, ("xyz",))
        output = canvas.compose(False)
        self.assertEqual(output, "cdef \n   xy")
        self.assertNotIn("\x1b", output)

    def test_custom_rocket_assets_are_normalized_ascii_lines(self):
        for mode in ("flight", "flight_compact", "approach", "vertical"):
            sprite = _sprite_for(mode, 1.0)
            self.assertIsInstance(sprite, tuple)
            self.assertTrue(all("\n" not in line and line.isascii() for line in sprite))


class ExplorerTests(unittest.TestCase):
    def test_seed_reproduces_planet_and_timing(self):
        first, second = Explorer(99), Explorer(99)
        first._enter(State.APPROACH)
        second._enter(State.APPROACH)
        self.assertEqual(first.encounter_kind, second.encounter_kind)
        self.assertEqual(first.will_land, second.will_land)
        self.assertEqual(first.planet, second.planet)
        self.assertEqual(first.duration, second.duration)
        if first.planet is None:
            first.planet = create_planet(first.rng)
            second.planet = create_planet(second.rng)
        first._enter(State.FLYOVER)
        second._enter(State.FLYOVER)
        self.assertEqual(first.duration, second.duration)
        self.assertEqual(first.landing_world_x, second.landing_world_x)

    def test_random_durations_stay_in_configured_ranges(self):
        explorer = Explorer(10)
        explorer._enter(State.APPROACH)
        self.assertTrue(config.MIN_APPROACH_DURATION <= explorer.duration <= config.MAX_APPROACH_DURATION)
        if explorer.planet is None:
            explorer.planet = create_planet(explorer.rng)
        explorer._enter(State.FLYOVER)
        self.assertTrue(config.MIN_FLYOVER_DURATION <= explorer.duration <= config.MAX_FLYOVER_DURATION)
        explorer._enter(State.LANDED)
        self.assertTrue(config.MIN_LANDED_DURATION <= explorer.duration <= config.MAX_LANDED_DURATION)
        explorer._enter(State.TAKEOFF)
        self.assertTrue(config.MIN_TAKEOFF_DURATION <= explorer.duration <= config.MAX_TAKEOFF_DURATION)

    def test_approaches_include_flybys_and_landings(self):
        explorer = Explorer(44)
        results = set()
        kinds = set()
        for _ in range(120):
            explorer._enter(State.APPROACH)
            kinds.add(explorer.encounter_kind)
            results.add("landing" if explorer.will_land else "flyby")
        self.assertEqual(results, {"landing", "flyby"})
        self.assertIn("PLANET", kinds)
        self.assertGreater(len(kinds), 3)

    def test_flyby_returns_to_space(self):
        explorer = Explorer(45)
        explorer._enter(State.APPROACH)
        explorer.encounter_kind = "BLACK_HOLE"
        explorer.will_land = False
        explorer.elapsed = explorer.duration
        explorer.update(0.1, 80, 24)
        self.assertIs(explorer.state, State.SPACE)
        self.assertEqual(explorer.stats["flybys"], 1)

    def test_all_states_render_at_multiple_sizes(self):
        explorer = Explorer(123)
        explorer._enter(State.APPROACH)
        for state in State:
            if state is State.SPACE:
                explorer._enter(state)
            elif state is State.APPROACH:
                explorer._enter(state)
            else:
                if explorer.planet is None:
                    explorer._enter(State.APPROACH)
                explorer._enter(state)
            for width, height in ((32, 12), (80, 24), (137, 41)):
                explorer.update(0.1, width, height)
                frame = explorer.render(width, height, False)
                lines = frame.splitlines()
                self.assertEqual(len(lines), height)
                self.assertTrue(all(len(line) == width for line in lines))

    def test_state_sequence(self):
        explorer = Explorer(5)
        expected = [
            State.APPROACH,
            State.ATMOSPHERE,
            State.FLYOVER,
            State.LANDING,
            State.LANDED,
            State.TAKEOFF,
            State.SPACE,
        ]
        for state in expected:
            if explorer.state is State.APPROACH:
                explorer.encounter_kind = "PLANET"
                explorer.will_land = True
                if explorer.planet is None:
                    explorer.planet = create_planet(explorer.rng)
            while explorer.state is not state:
                explorer.update(0.25, 80, 24)
            self.assertIs(explorer.state, state)

    def test_landing_position_never_crosses_ground(self):
        explorer = Explorer(21)
        explorer._enter(State.APPROACH)
        explorer._enter(State.LANDING)
        ground = [18] * 80
        for elapsed in (0.0, explorer.duration * 0.5, explorer.duration):
            explorer.elapsed = elapsed
            _, y, mode, _, zoom = explorer._rocket_position(80, 24, ground)
            self.assertLessEqual(y + sprite_size(mode, zoom)[1], 18)

    def test_rocket_and_terrain_zoom_during_landing(self):
        explorer = Explorer(22)
        explorer._enter(State.APPROACH)
        explorer._enter(State.LANDING)
        explorer.elapsed = 0.0
        start = explorer._scene_zoom(40)
        explorer.elapsed = explorer.duration
        end = explorer._scene_zoom(40)
        self.assertEqual(start, 1.0)
        self.assertGreater(end, start)

    def test_resize_keeps_exploration_state(self):
        explorer = Explorer(12)
        explorer._enter(State.APPROACH)
        planet = explorer.planet
        explorer.update(0.1, 60, 18)
        elapsed = explorer.elapsed
        explorer.render(60, 18, False)
        explorer.update(0.1, 120, 35)
        explorer.render(120, 35, False)
        self.assertEqual(explorer.planet, planet)
        self.assertIs(explorer.state, State.APPROACH)
        self.assertGreater(explorer.elapsed, elapsed)
        self.assertLessEqual(len(explorer.stars), int(120 * 35 * config.STAR_DENSITY))

    def test_cosmic_objects_are_counted_once(self):
        explorer = Explorer(31)
        visible = [(0, "SUN"), (1, "BLACK_HOLE")]
        explorer.register_cosmic_objects(visible)
        explorer.register_cosmic_objects(visible)
        self.assertEqual(explorer.stats["suns_seen"], 1)
        self.assertEqual(explorer.stats["black_holes_seen"], 1)

    def test_status_round_trip(self):
        explorer = Explorer(77)
        explorer._enter(State.APPROACH)
        explorer.distance = 123.5
        explorer.stats["black_holes_seen"] = 4
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            save_explorer(explorer, path)
            restored = load_explorer(path)
        self.assertIsNotNone(restored)
        self.assertEqual(restored.seed, 77)
        self.assertEqual(restored.planet, explorer.planet)
        self.assertEqual(restored.distance, 123.5)
        self.assertEqual(restored.stats["black_holes_seen"], 4)

    def test_invalid_status_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            path.write_text("{invalid", encoding="utf-8")
            self.assertIsNone(load_explorer(path))

    def test_memory_pressure_enables_low_resource_mode_once(self):
        explorer = Explorer(80)
        explorer.set_system_metrics(35.0, config.MEMORY_PRESSURE_THRESHOLD + 1.0)
        explorer.set_system_metrics(40.0, config.MEMORY_PRESSURE_THRESHOLD + 2.0)
        self.assertTrue(explorer.memory_pressure)
        self.assertEqual(explorer.stats["resource_alerts"], 1)
        explorer.update(0.1, 100, 30)
        expected = int(100 * 30 * config.STAR_DENSITY * 0.45)
        self.assertEqual(len(explorer.stars), max(8, expected))

    def test_gravity_proximity_follows_critical_load(self):
        explorer = Explorer(81)
        state_elapsed = explorer.elapsed
        explorer.set_system_metrics(99.0, 99.0)
        explorer.update(0.25, 100, 30)
        self.assertTrue(explorer.gravity_active)
        self.assertTrue(explorer.gravity_critical)
        close_proximity = explorer.gravity_proximity
        self.assertGreater(close_proximity, 0.0)
        self.assertEqual(explorer.elapsed, state_elapsed)
        frame = explorer.render(100, 30, False)
        self.assertIn("EVENT HORIZON", frame)
        self.assertIn("CPU: 99.0%", frame)
        recovered_cpu = max(0.0, config.CRITICAL_CPU_THRESHOLD - 1.0)
        recovered_memory = max(0.0, config.CRITICAL_MEMORY_THRESHOLD - 1.0)
        explorer.set_system_metrics(recovered_cpu, recovered_memory)
        explorer.update(0.25, 100, 30)
        self.assertFalse(explorer.gravity_critical)
        self.assertLess(explorer.gravity_proximity, close_proximity)
        self.assertGreater(explorer.elapsed, state_elapsed)
        for _ in range(12):
            explorer.update(0.25, 100, 30)
        self.assertFalse(explorer.gravity_active)
        self.assertEqual(explorer.stats["gravity_escapes"], 1)

    def test_new_critical_load_pulls_black_hole_close_again(self):
        explorer = Explorer(83)
        explorer.set_system_metrics(99.0, 99.0)
        explorer.update(0.25, 100, 30)
        close_proximity = explorer.gravity_proximity
        recovered_cpu = max(0.0, config.CRITICAL_CPU_THRESHOLD - 1.0)
        recovered_memory = max(0.0, config.CRITICAL_MEMORY_THRESHOLD - 1.0)
        explorer.set_system_metrics(recovered_cpu, recovered_memory)
        explorer.update(0.25, 100, 30)
        distant_proximity = explorer.gravity_proximity
        self.assertLess(distant_proximity, close_proximity)
        explorer.set_system_metrics(99.0, 99.0)
        explorer.update(0.25, 100, 30)
        self.assertTrue(explorer.gravity_critical)
        self.assertGreater(explorer.gravity_proximity, distant_proximity)

    def test_background_black_hole_passes_and_reschedules(self):
        explorer = Explorer(82)
        explorer.background_black_hole_timer = 0.0
        explorer.update(0.1, 100, 30)
        self.assertTrue(explorer.background_black_hole_active)
        self.assertTrue(
            config.MIN_BACKGROUND_BLACK_HOLE_DURATION
            <= explorer.background_black_hole_duration
            <= config.MAX_BACKGROUND_BLACK_HOLE_DURATION
        )
        explorer.background_black_hole_elapsed = explorer.background_black_hole_duration * 0.5
        self.assertIn("@", explorer.render(100, 30, False))
        explorer.background_black_hole_elapsed = explorer.background_black_hole_duration
        explorer.update(0.1, 100, 30)
        self.assertFalse(explorer.background_black_hole_active)
        self.assertTrue(
            config.MIN_BACKGROUND_BLACK_HOLE_INTERVAL
            <= explorer.background_black_hole_timer
            <= config.MAX_BACKGROUND_BLACK_HOLE_INTERVAL
        )

    def test_system_metrics_are_bounded_when_available(self):
        monitor = SystemMonitor()
        monitor.sample()
        if os.name == "nt":
            time.sleep(0.02)
        metrics = monitor.sample()
        for value in (metrics.cpu_percent, metrics.memory_percent):
            if value is not None:
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 100.0)
        if os.name == "nt":
            self.assertIsNotNone(metrics.cpu_percent)
            self.assertIsNotNone(metrics.memory_percent)


if __name__ == "__main__":
    unittest.main()

