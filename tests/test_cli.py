import json

from typer.testing import CliRunner

from conftest import FIXTURES
from idefy import __version__
from idefy.cli import app

runner = CliRunner()


def run(*args):
    return runner.invoke(app, list(args))


def envelope(result):
    return json.loads(result.stdout)


def test_version_command():
    result = run("version")
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_version_option():
    result = run("--version")
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_no_args_shows_help():
    result = run()
    assert result.exit_code != 0
    assert "Usage" in result.stdout


def test_validate_clean_model():
    result = run("validate", str(FIXTURES / "valid.yaml"))
    assert result.exit_code == 0


def test_validate_reports_errors():
    result = run("validate", str(FIXTURES / "e006_unresolved.yaml"))
    assert result.exit_code == 1
    assert "E006" in result.stdout


def test_validate_warnings_do_not_fail():
    result = run("validate", str(FIXTURES / "w003_noun_name.yaml"))
    assert result.exit_code == 0
    assert "W003" in result.stdout


def test_missing_model_is_a_usage_error(tmp_path):
    result = run("validate", str(tmp_path / "нет.yaml"))
    assert result.exit_code == 2


def test_json_envelope_shape():
    result = run("validate", str(FIXTURES / "e006_unresolved.yaml"), "--json")
    payload = envelope(result)
    assert payload["ok"] is False
    assert payload["result"] == {"model": str(FIXTURES / "e006_unresolved.yaml")}
    first = payload["diagnostics"][0]
    assert set(first) >= {"code", "level", "where", "message"}


def test_json_usage_error_carries_message(tmp_path):
    result = run("validate", str(tmp_path / "нет.yaml"), "--json")
    assert result.exit_code == 2
    assert envelope(result)["error"]


def test_init_creates_a_valid_model(tmp_path):
    target = tmp_path / "model.yaml"
    assert run("init", str(target)).exit_code == 0
    assert run("validate", str(target)).exit_code == 0


def test_init_refuses_to_overwrite(tmp_path):
    target = tmp_path / "model.yaml"
    run("init", str(target))
    assert run("init", str(target)).exit_code == 2


def test_init_into_directory(tmp_path):
    assert run("init", str(tmp_path)).exit_code == 0
    assert (tmp_path / "model.yaml").exists()


def test_preview_writes_every_diagram(tmp_path):
    result = run("preview", str(FIXTURES / "valid.yaml"), "-o", str(tmp_path), "--json")
    assert result.exit_code == 0
    pages = envelope(result)["result"]["pages"]
    assert sorted(p.split("/")[-1] for p in pages) == ["A-0.svg", "A0.svg"]


def test_preview_single_page(tmp_path):
    result = run("preview", str(FIXTURES / "valid.yaml"), "-o", str(tmp_path), "--page", "A0")
    assert result.exit_code == 0
    assert (tmp_path / "A0.svg").exists()
    assert not (tmp_path / "A-0.svg").exists()


def test_preview_unknown_page(tmp_path):
    result = run("preview", str(FIXTURES / "valid.yaml"), "-o", str(tmp_path), "--page", "A9")
    assert result.exit_code == 2


def test_preview_draws_despite_errors(tmp_path):
    result = run("preview", str(FIXTURES / "e006_unresolved.yaml"), "-o", str(tmp_path))
    assert result.exit_code == 1
    assert (tmp_path / "A0.svg").exists()


def test_preview_dumps_ir(tmp_path):
    dump = tmp_path / "ir.json"
    result = run(
        "preview", str(FIXTURES / "valid.yaml"), "-o", str(tmp_path), "--dump-ir", str(dump)
    )
    assert result.exit_code == 0
    assert json.loads(dump.read_text(encoding="utf-8"))["ir_version"] == 1


def test_preview_png_without_cairosvg(tmp_path, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "cairosvg":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    result = run(
        "preview", str(FIXTURES / "valid.yaml"), "-o", str(tmp_path), "--format", "png", "--json"
    )
    assert result.exit_code == 2
    assert "cairosvg" in envelope(result)["error"]


def test_schema_to_stdout():
    result = run("schema", "--json")
    payload = envelope(result)
    assert payload["result"]["schema"]["properties"]["activities"]


def test_schema_to_file(tmp_path):
    target = tmp_path / "schema.json"
    assert run("schema", "-o", str(target)).exit_code == 0
    assert json.loads(target.read_text(encoding="utf-8"))["$defs"]["Activity"]


def test_packaged_schema_is_current(tmp_path):
    from idefy import parse

    packaged = json.loads(
        (FIXTURES.parent.parent / "src" / "idefy" / "schema" / "idefy.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert packaged == parse.Model.model_json_schema()


def test_quiet_hides_success_message(tmp_path):
    target = tmp_path / "model.yaml"
    result = run("init", str(target), "-q")
    assert result.exit_code == 0
    assert result.stdout.strip() == ""
