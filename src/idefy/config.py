from __future__ import annotations

import os
import shutil
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ENV_RAMUS = "IDEFY_RAMUS_PATH"
ENV_CONFIG = "IDEFY_CONFIG"

Source = Literal["флаг", "переменная окружения", "конфиг", "автопоиск"]

MACOS_CANDIDATES = (
    "/Applications/Ramus.app",
    "/Applications/Ramus Educational.app",
    "~/Applications/Ramus.app",
    "~/Applications/Ramus Educational.app",
)
LINUX_CANDIDATES = (
    "/opt/ramus/ramus",
    "/usr/lib/ramus/ramus",
    "/usr/share/ramus/ramus",
    "~/.local/share/ramus/ramus",
)


@dataclass(frozen=True, slots=True)
class Ramus:
    path: Path
    source: Source


def config_path() -> Path:
    override = os.environ.get(ENV_CONFIG)
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or "~/.config"
    return Path(base).expanduser() / "idefy" / "config.toml"


def load() -> dict[str, object]:
    path = config_path()
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def find_ramus(override: Path | None = None) -> Ramus | None:
    if override is not None:
        return Ramus(path=override.expanduser(), source="флаг")
    env = os.environ.get(ENV_RAMUS)
    if env:
        return Ramus(path=Path(env).expanduser(), source="переменная окружения")
    configured = load().get("ramus")
    if isinstance(configured, str) and configured:
        return Ramus(path=Path(configured).expanduser(), source="конфиг")
    discovered = discover()
    if discovered is not None:
        return Ramus(path=discovered, source="автопоиск")
    return None


def discover() -> Path | None:
    candidates = MACOS_CANDIDATES if sys.platform == "darwin" else LINUX_CANDIDATES
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.exists():
            return path
    found = shutil.which("ramus")
    return Path(found) if found else None


def launch_command(ramus: Path, model: Path) -> list[str]:
    if ramus.suffix == ".app":
        return ["open", "-a", str(ramus), str(model)]
    return [str(ramus), str(model)]
