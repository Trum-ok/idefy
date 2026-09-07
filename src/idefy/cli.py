from __future__ import annotations

import json
import subprocess
from enum import StrEnum
from importlib import resources
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
from rich.console import Console

from idefy import __version__, config, ir, layout, parse, render_svg, validate, write_rsf
from idefy.diagnostics import Diagnostic
from idefy.rsf import tables

EXIT_OK = 0
EXIT_DIAGNOSTICS = 1
EXIT_USAGE = 2
EXIT_ENVIRONMENT = 3

app = typer.Typer(help="Генератор IDEF0-моделей из YAML", no_args_is_help=True)

console = Console()
errors = Console(stderr=True)

JsonOption = Annotated[bool, typer.Option("--json", help="Машинный вывод")]
QuietOption = Annotated[bool, typer.Option("-q", "--quiet", help="Не печатать прогресс")]


class Format(StrEnum):
    svg = "svg"
    png = "png"


def _version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version, is_eager=True, help="Показать версию"),
    ] = False,
) -> None:
    pass


@app.command(help="Показать версию")
def version() -> None:
    typer.echo(__version__)


@app.command(help="Создать model.yaml из шаблона")
def init(
    path: Annotated[Path, typer.Argument(help="Куда положить модель")] = Path("model.yaml"),
    json_output: JsonOption = False,
    quiet: QuietOption = False,
) -> None:
    if path.is_dir():
        path = path / "model.yaml"
    if path.exists():
        _fail(f"Файл уже существует: {path}", json_output)
    template = resources.files("idefy.templates").joinpath("model.yaml").read_text(encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(template, encoding="utf-8")
    _emit([], {"path": str(path)}, json_output, quiet, f"Создан {path}")


@app.command(help="Выгрузить JSON Schema языка")
def schema(
    output: Annotated[Path | None, typer.Option("-o", "--output", help="Файл для схемы")] = None,
    json_output: JsonOption = False,
    quiet: QuietOption = False,
) -> None:
    document = parse.Model.model_json_schema()
    if output is None:
        if json_output:
            _emit([], {"schema": document}, True, quiet, "")
        else:
            console.print_json(json.dumps(document, ensure_ascii=False))
        raise typer.Exit(EXIT_OK)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _emit([], {"path": str(output)}, json_output, quiet, f"Схема записана в {output}")


@app.command("validate", help="Проверить нотацию")
def validate_command(
    model: Annotated[Path, typer.Argument(help="Файл модели")],
    json_output: JsonOption = False,
    quiet: QuietOption = False,
) -> None:
    diagnostics, _, _ = _analyse(model, json_output)
    _emit(diagnostics, {"model": str(model)}, json_output, quiet, "Ошибок нет")
    raise typer.Exit(EXIT_DIAGNOSTICS if validate.has_errors(diagnostics) else EXIT_OK)


@app.command(help="Нарисовать диаграммы в SVG или PNG")
def preview(
    model: Annotated[Path, typer.Argument(help="Файл модели")],
    output: Annotated[Path, typer.Option("-o", "--output", help="Каталог для картинок")] = Path(
        "preview"
    ),
    image_format: Annotated[Format, typer.Option("--format", help="Формат картинок")] = Format.svg,
    page: Annotated[str | None, typer.Option("--page", help="Одна диаграмма по её id")] = None,
    dump_ir: Annotated[
        Path | None, typer.Option("--dump-ir", help="Выгрузить промежуточное представление")
    ] = None,
    json_output: JsonOption = False,
    quiet: QuietOption = False,
) -> None:
    diagnostics, document, representation = _analyse(model, json_output)
    diagrams = representation.diagrams
    if page is not None:
        selected = representation.diagram(page)
        if selected is None:
            known = ", ".join(diagram.id for diagram in diagrams) or "нет диаграмм"
            _fail(f"Диаграмма {page} не найдена. Есть: {known}", json_output)
        diagrams = [selected]

    if dump_ir is not None:
        dump_ir.parent.mkdir(parents=True, exist_ok=True)
        dump_ir.write_text(
            json.dumps(representation.as_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    output.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for diagram in diagrams:
        svg = render_svg.render(diagram, title=f"{document.model.name} — {diagram.id}")
        if image_format is Format.svg:
            target = output / f"{diagram.id}.svg"
            target.write_text(svg, encoding="utf-8")
        else:
            target = output / f"{diagram.id}.png"
            _write_png(svg, target, json_output)
        written.append(str(target))

    result: dict[str, Any] = {"pages": written}
    if dump_ir is not None:
        result["ir"] = str(dump_ir)
    _emit(diagnostics, result, json_output, quiet, "\n".join(written))
    raise typer.Exit(EXIT_DIAGNOSTICS if validate.has_errors(diagnostics) else EXIT_OK)


@app.command(help="Собрать файл Ramus")
def build(
    model: Annotated[Path, typer.Argument(help="Файл модели")],
    output: Annotated[
        Path | None, typer.Option("-o", "--output", help="Куда положить .rsf")
    ] = None,
    json_output: JsonOption = False,
    quiet: QuietOption = False,
) -> None:
    diagnostics, _, representation = _analyse(model, json_output)
    if validate.has_errors(diagnostics):
        _emit(diagnostics, None, json_output, quiet, "")
        raise typer.Exit(EXIT_DIAGNOSTICS)
    target = output or model.with_suffix(".rsf")
    write_rsf.build(representation, target)
    _emit(diagnostics, {"path": str(target)}, json_output, quiet, str(target))
    raise typer.Exit(EXIT_OK)


@app.command("open", help="Открыть .rsf в Ramus")
def open_command(
    file: Annotated[Path, typer.Argument(help="Файл .rsf")],
    ramus: Annotated[
        Path | None, typer.Option("--ramus", help="Путь к Ramus, приоритетнее конфига")
    ] = None,
    json_output: JsonOption = False,
    quiet: QuietOption = False,
) -> None:
    if not file.is_file():
        _fail(f"Файл не найден: {file}", json_output)
    found = config.find_ramus(ramus)
    if found is None or not found.path.exists():
        _environment(
            f"Ramus не найден{'' if found is None else f': {found.path}'}",
            f"укажите путь: --ramus PATH, переменная {config.ENV_RAMUS} "
            f'или ramus = "..." в {config.config_path()}',
            json_output,
        )
    command = config.launch_command(found.path, file)
    try:
        subprocess.Popen(command, start_new_session=True)
    except OSError as exc:
        _environment(f"Не удалось запустить Ramus: {exc}", None, json_output)
    _emit(
        [],
        {"ramus": str(found.path), "source": found.source, "file": str(file)},
        json_output,
        quiet,
        f"Запущен {found.path}",
    )


@app.command(help="Проверить шаблон .rsf и путь к Ramus")
def doctor(
    json_output: JsonOption = False,
    quiet: QuietOption = False,
) -> None:
    checks = [_check_template(), _check_config(), _check_ramus(), _check_png()]
    broken = [check for check in checks if check["level"] == "fail"]
    if json_output:
        typer.echo(
            json.dumps(
                {"ok": not broken, "diagnostics": [], "result": {"checks": checks}},
                ensure_ascii=False,
                indent=2,
            )
        )
    elif not quiet:
        marks = {"ok": "[green]ок[/]", "warn": "[yellow]нет[/]", "fail": "[red]сломано[/]"}
        for check in checks:
            console.print(f"{marks[check['level']]} {check['name']}: {check['detail']}")
    raise typer.Exit(EXIT_ENVIRONMENT if broken else EXIT_OK)


def _check_template() -> dict[str, str]:
    try:
        path = write_rsf.template_path()
        archive = tables.read(path)
        problems = tables.check_types(archive)
    except Exception as exc:
        return _check("шаблон .rsf", "fail", f"{type(exc).__name__}: {exc}")
    if problems:
        return _check("шаблон .rsf", "fail", f"{len(problems)} значений не по типу колонки")
    return _check("шаблон .rsf", "ok", f"таблиц: {len(archive.tables)}, {path}")


def _check_config() -> dict[str, str]:
    path = config.config_path()
    if not path.is_file():
        return _check("конфиг", "warn", f"нет файла {path}")
    return _check("конфиг", "ok", str(path))


def _check_ramus() -> dict[str, str]:
    found = config.find_ramus()
    if found is None:
        return _check("Ramus", "warn", "не найден, нужен только для idefy open")
    if not found.path.exists():
        return _check("Ramus", "warn", f"{found.path} ({found.source}) не существует")
    return _check("Ramus", "ok", f"{found.path} ({found.source})")


def _check_png() -> dict[str, str]:
    try:
        import cairosvg  # ty: ignore[unresolved-import]  # noqa: F401
    except ImportError:
        return _check("PNG", "warn", "нет cairosvg, доступен только --format svg")
    return _check("PNG", "ok", "cairosvg на месте")


def _check(name: str, level: str, detail: str) -> dict[str, str]:
    return {"name": name, "level": level, "detail": detail}


def _environment(message: str, hint: str | None, json_output: bool) -> NoReturn:
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "diagnostics": [],
                    "result": None,
                    "error": message if hint is None else f"{message}: {hint}",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        errors.print(f"[bold red]Ошибка[/]: {message}")
        if hint:
            errors.print(f"    [dim]подсказка:[/] {hint}")
    raise typer.Exit(EXIT_ENVIRONMENT)


def _write_png(svg: str, target: Path, json_output: bool) -> None:
    try:
        import cairosvg  # ty: ignore[unresolved-import]
    except ImportError:
        _fail(
            "PNG требует cairosvg: установите `idefy[png]` или используйте --format svg",
            json_output,
        )
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(target))


def _analyse(model_path: Path, json_output: bool) -> tuple[list[Diagnostic], parse.Model, ir.IR]:
    try:
        document = parse.load(model_path)
    except parse.UsageError as exc:
        _fail(str(exc), json_output)
    resolution = parse.resolve(document)
    diagnostics = validate.check(document, resolution)
    return diagnostics, document, layout.build(document, resolution)


def _fail(message: str, json_output: bool) -> NoReturn:
    if json_output:
        typer.echo(
            json.dumps(
                {"ok": False, "diagnostics": [], "result": None, "error": message},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        errors.print(f"[bold red]Ошибка[/]: {message}")
    raise typer.Exit(EXIT_USAGE)


def _emit(
    diagnostics: list[Diagnostic],
    result: Any,
    json_output: bool,
    quiet: bool,
    success_message: str,
) -> None:
    ok = not validate.has_errors(diagnostics)
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "ok": ok,
                    "diagnostics": [diagnostic.as_dict() for diagnostic in diagnostics],
                    "result": result,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    for diagnostic in diagnostics:
        colour = "red" if diagnostic.level == "error" else "yellow"
        console.print(
            f"[bold {colour}]{diagnostic.code}[/] [dim]{diagnostic.where}[/] {diagnostic.message}"
        )
        if diagnostic.hint:
            console.print(f"    [dim]подсказка:[/] {diagnostic.hint}")
    if quiet:
        return
    if ok and success_message:
        console.print(success_message)
