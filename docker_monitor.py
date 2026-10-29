"""Leitura assíncrona do estado local do Docker."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from dataclasses import dataclass

import config


@dataclass(frozen=True)
class DockerContainer:
    name: str
    image: str
    state: str
    status: str


@dataclass(frozen=True)
class DockerImage:
    name: str
    size: str


@dataclass(frozen=True)
class DockerSnapshot:
    available: bool
    containers: tuple[DockerContainer, ...] = ()
    images: tuple[DockerImage, ...] = ()

    @property
    def running(self) -> int:
        return sum(container.state.lower() == "running" for container in self.containers)


class DockerMonitor:
    def __init__(self, refresh_interval: float = config.DOCKER_REFRESH_INTERVAL) -> None:
        self.refresh_interval = refresh_interval
        self._snapshot: DockerSnapshot | None = None
        self._next_refresh = 0.0
        self._refreshing = False
        self._lock = threading.Lock()

    def sample(self) -> DockerSnapshot | None:
        now = time.monotonic()
        with self._lock:
            if now >= self._next_refresh and not self._refreshing:
                self._refreshing = True
                self._next_refresh = now + self.refresh_interval
                threading.Thread(target=self._refresh, daemon=True).start()
            return self._snapshot

    def _refresh(self) -> None:
        try:
            containers = _docker_json("container", "ls", "--all")
            images = _docker_json("image", "ls")
            snapshot = DockerSnapshot(
                True,
                tuple(
                    DockerContainer(
                        str(item.get("Names", "?")),
                        str(item.get("Image", "?")),
                        str(item.get("State", "unknown")),
                        str(item.get("Status", "unknown")),
                    )
                    for item in containers
                ),
                tuple(
                    DockerImage(
                        _image_name(item),
                        str(item.get("Size", "?")),
                    )
                    for item in images
                ),
            )
        except (OSError, subprocess.SubprocessError, ValueError):
            snapshot = DockerSnapshot(False)
        with self._lock:
            self._snapshot = snapshot
            self._refreshing = False


def _docker_json(resource: str, action: str, *arguments: str) -> list[dict[str, object]]:
    result = subprocess.run(
        ["docker", resource, action, *arguments, "--format", "{{json .}}"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=config.DOCKER_COMMAND_TIMEOUT,
    )
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def _image_name(item: dict[str, object]) -> str:
    repository = str(item.get("Repository", "<none>"))
    tag = str(item.get("Tag", "<none>"))
    return f"{repository}:{tag}"
