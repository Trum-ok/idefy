from __future__ import annotations

import json
from enum import StrEnum
from importlib import resources
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
from rich.console import Console

from idefy import __version__, ir, layout, parse, render_svg, validate
from idefy.diagnostics import Diagnostic

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


@app.command()
def version() -> None:
    typer.echo(__version__)


@app.command()
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


@app.command()
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


@app.command("validate")
def validate_command(
    model: Annotated[Path, typer.Argument(help="Файл модели")],
    json_output: JsonOption = False,
    quiet: QuietOption = False,
) -> None:
    diagnostics, _, _ = _analyse(model, json_output)
    _emit(diagnostics, {"model": str(model)}, json_output, quiet, "Ошибок нет")
    raise typer.Exit(EXIT_DIAGNOSTICS if validate.has_errors(diagnostics) else EXIT_OK)


@app.command()
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
