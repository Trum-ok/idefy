import sys
from pathlib import Path

import pytest

from idefy import config


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch, tmp_path):
    monkeypatch.delenv(config.ENV_RAMUS, raising=False)
    monkeypatch.setenv(config.ENV_CONFIG, str(tmp_path / "config.toml"))
    monkeypatch.setattr(config, "discover", lambda: None)


def write_config(tmp_path: Path, text: str) -> None:
    (tmp_path / "config.toml").write_text(text, encoding="utf-8")


def test_no_source_gives_nothing():
    assert config.find_ramus() is None


def test_flag_wins(monkeypatch, tmp_path):
    monkeypatch.setenv(config.ENV_RAMUS, "/env/ramus")
    write_config(tmp_path, 'ramus = "/config/ramus"\n')
    found = config.find_ramus(Path("/flag/ramus"))
    assert found is not None
    assert (found.path, found.source) == (Path("/flag/ramus"), "флаг")


def test_environment_beats_config(monkeypatch, tmp_path):
    monkeypatch.setenv(config.ENV_RAMUS, "/env/ramus")
    write_config(tmp_path, 'ramus = "/config/ramus"\n')
    found = config.find_ramus()
    assert found is not None
    assert (found.path, found.source) == (Path("/env/ramus"), "переменная окружения")


def test_config_beats_discovery(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "discover", lambda: Path("/discovered/ramus"))
    write_config(tmp_path, 'ramus = "/config/ramus"\n')
    found = config.find_ramus()
    assert found is not None
    assert found.source == "конфиг"


def test_discovery_is_the_last_resort(monkeypatch):
    monkeypatch.setattr(config, "discover", lambda: Path("/discovered/ramus"))
    found = config.find_ramus()
    assert found is not None
    assert found.source == "автопоиск"


def test_broken_config_is_ignored(tmp_path):
    write_config(tmp_path, "ramus = [\n")
    assert config.load() == {}


def test_config_path_follows_xdg(monkeypatch):
    monkeypatch.delenv(config.ENV_CONFIG, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/выбор")
    assert config.config_path() == Path("/tmp/выбор/idefy/config.toml")


def test_tilde_is_expanded(monkeypatch, tmp_path):
    write_config(tmp_path, 'ramus = "~/Ramus.app"\n')
    found = config.find_ramus()
    assert found is not None
    assert "~" not in str(found.path)


@pytest.mark.parametrize(
    ("ramus", "expected"),
    [
        (Path("/Applications/Ramus.app"), ["open", "-a", "/Applications/Ramus.app", "модель.rsf"]),
        (Path("/opt/ramus/ramus"), ["/opt/ramus/ramus", "модель.rsf"]),
    ],
)
def test_launch_command(ramus, expected):
    assert config.launch_command(ramus, Path("модель.rsf")) == expected


@pytest.mark.skipif(sys.platform != "darwin", reason="список кандидатов зависит от системы")
def test_discovery_looks_at_applications():
    assert any("Ramus.app" in candidate for candidate in config.MACOS_CANDIDATES)
