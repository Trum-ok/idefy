import typer

from idefy import __version__

app = typer.Typer(help="Генератор IDEF0-моделей из YAML", no_args_is_help=True)


def _version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_version, is_eager=True, help="Показать версию"
    ),
) -> None:
    pass


@app.command()
def version() -> None:
    typer.echo(__version__)
