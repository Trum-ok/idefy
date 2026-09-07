import pytest

from conftest import GOLDEN, keep, represent
from idefy import render_svg

GOLDEN_CASES = [
    ("context_only", "A-0"),
    ("valid", "A0"),
    ("feedback6", "A0"),
    ("tunnel", "A-0"),
]


def render(fixture: str, diagram_id: str) -> str:
    diagram = represent(fixture).diagram(diagram_id)
    assert diagram is not None
    return render_svg.render(diagram, title=f"{fixture} {diagram_id}")


@pytest.mark.parametrize(("fixture", "diagram_id"), GOLDEN_CASES)
def test_matches_golden(fixture, diagram_id):
    produced = render(fixture, diagram_id)
    keep(f"{fixture}.{diagram_id}.svg", produced.encode("utf-8"))
    assert produced == (GOLDEN / f"{fixture}.{diagram_id}.svg").read_text(encoding="utf-8")


@pytest.mark.parametrize(("fixture", "diagram_id"), GOLDEN_CASES)
def test_render_is_deterministic(fixture, diagram_id):
    assert render(fixture, diagram_id) == render(fixture, diagram_id)


def test_tunnel_draws_brackets():
    assert "<path" in render("tunnel", "A-0")


def test_names_are_escaped(tmp_path):
    from idefy import ir

    diagram = ir.Diagram(
        id="A-0",
        kind="context",
        canvas=ir.Canvas(w=800, h=444),
        blocks=[ir.Block(id="A0", name="A & B <тест>", x=10, y=10, w=100, h=50, number="A0")],
    )
    assert "A &amp; B &lt;тест&gt;" in render_svg.render(diagram)


@pytest.mark.parametrize(
    ("text", "width", "expected"),
    [
        ("Проверить полноту документов", 110, ["Проверить полноту", "документов"]),
        ("Принять", 110, ["Принять"]),
        ("", 110, [""]),
    ],
)
def test_wrap(text, width, expected):
    assert render_svg.wrap(text, width, 11) == expected
