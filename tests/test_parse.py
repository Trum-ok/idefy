import pytest

from conftest import load
from idefy import parse
from idefy.parse import UsageError


def resolve(name: str) -> parse.Resolution:
    return parse.resolve(load(name))


def arrows(resolution: parse.Resolution, diagram_id: str) -> list[parse.Arrow]:
    diagram = next(d for d in resolution.diagrams if d.id == diagram_id)
    return diagram.arrows


def test_missing_file(tmp_path):
    with pytest.raises(UsageError, match="не найден"):
        parse.load(tmp_path / "нет.yaml")


def test_broken_yaml(tmp_path):
    path = tmp_path / "битый.yaml"
    path.write_text("model: [\n", encoding="utf-8")
    with pytest.raises(UsageError, match="разобрать YAML"):
        parse.load(path)


def test_scalar_root(tmp_path):
    path = tmp_path / "скаляр.yaml"
    path.write_text("просто строка\n", encoding="utf-8")
    with pytest.raises(UsageError, match="отображением"):
        parse.load(path)


def test_schema_violation(tmp_path):
    path = tmp_path / "чужое.yaml"
    path.write_text("version: 1\nmodel:\n  name: x\nactivities: 5\n", encoding="utf-8")
    with pytest.raises(UsageError, match="не соответствует схеме"):
        parse.load(path)


def test_context_diagram_holds_only_root():
    resolution = resolve("context_only")
    assert [diagram.id for diagram in resolution.diagrams] == ["A-0"]
    diagram = resolution.diagrams[0]
    assert diagram.kind == "context"
    assert [block.id for block in diagram.blocks] == ["A0"]
    assert len(diagram.arrows) == 7


def test_decomposition_resolves_internal_and_boundary():
    resolution = resolve("valid")
    internal = [a for a in arrows(resolution, "A0") if a.src.block and a.dst.block]
    assert {(a.src.block, a.dst.block, a.name) for a in internal} == {
        ("A1", "A2", "Проверенная заявка"),
        ("A2", "A3", "Оценка риска"),
    }
    boundary_in = [a for a in arrows(resolution, "A0") if a.src.kind == "boundary"]
    assert {a.name for a in boundary_in} == {"Заявка", "Регламент", "Аналитик"}


def test_fork_keeps_one_name_for_many_targets():
    resolution = resolve("valid")
    control = [a for a in arrows(resolution, "A0") if a.name == "Регламент"]
    assert {a.dst.block for a in control} == {"A1", "A2", "A3"}


def test_join_keeps_one_name_for_many_sources():
    resolution = resolve("feedback6")
    quality = [a for a in arrows(resolution, "A0") if a.name == "Цех"]
    assert {a.dst.block for a in quality} == {"A1", "A2", "A3", "A4", "A5", "A6"}


def test_feedback_is_resolved_backwards():
    resolution = resolve("feedback6")
    feedback = [a for a in arrows(resolution, "A0") if a.name == "Протокол дефектов"]
    assert [(a.src.block, a.dst.block, a.role) for a in feedback] == [("A5", "A4", "control")]


def test_override_creates_arrow_to_frame():
    resolution = resolve("tunnel")
    draft = [a for a in arrows(resolution, "A0") if a.name == "Черновик"]
    assert len(draft) == 1
    assert draft[0].src.block == "A1"
    assert draft[0].dst.kind == "boundary"
    assert draft[0].tunnel == "dest"


def test_override_marks_parent_icom_as_tunneled():
    resolution = resolve("tunnel")
    manual = [a for a in arrows(resolution, "A-0") if a.name == "Инструкция"]
    assert [a.tunnel for a in manual] == ["dest"]
    assert not [d for d in resolution.diagnostics if d.code == "E007"]


def test_unknown_override_is_reported(tmp_path):
    path = tmp_path / "модель.yaml"
    path.write_text(
        "version: 1\n"
        "model:\n"
        "  name: Тест\n"
        "activities:\n"
        "  - id: A0\n"
        "    name: Сделать\n"
        "    control: [Регламент]\n"
        "    output: [Итог]\n"
        "arrows:\n"
        "  - name: Чужая\n"
        "    from: A0\n"
        "    to: external\n",
        encoding="utf-8",
    )
    resolution = parse.resolve(parse.load(path))
    assert [d.code for d in resolution.diagnostics] == ["E006"]


def test_override_without_block_is_reported(tmp_path):
    path = tmp_path / "модель.yaml"
    path.write_text(
        "version: 1\n"
        "model:\n"
        "  name: Тест\n"
        "activities:\n"
        "  - id: A0\n"
        "    name: Сделать\n"
        "    control: [Регламент]\n"
        "    output: [Итог]\n"
        "arrows:\n"
        "  - name: Итог\n"
        "    from: external\n"
        "    to: external\n",
        encoding="utf-8",
    )
    resolution = parse.resolve(parse.load(path))
    assert [d.code for d in resolution.diagnostics] == ["E006"]


def test_arrow_order_is_stable():
    first = [a.key() for a in arrows(resolve("valid"), "A0")]
    second = [a.key() for a in arrows(resolve("valid"), "A0")]
    assert first == second == sorted(first)
