from typer.testing import CliRunner

from idefy import __version__
from idefy.cli import app

runner = CliRunner()


def test_version_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_version_option():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_no_args_shows_help():
    result = runner.invoke(app, [])
    assert result.exit_code != 0
    assert "Usage" in result.stdout
