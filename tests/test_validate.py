import pytest

from conftest import codes, diagnose, load
from idefy import parse, validate

CASES = [
    ("e001_duplicate_id", "E001"),
    ("e002_orphan", "E002"),
    ("e003_no_output", "E003"),
    ("e004_no_control", "E004"),
    ("e005_too_many_blocks", "E005"),
    ("e006_unresolved", "E006"),
    ("e007_untunneled", "E007"),
    ("e008_self_loop", "E008"),
    ("e009_no_context", "E009"),
    ("e010_two_contexts", "E010"),
    ("w001_block_count", "W001"),
    ("w002_no_purpose", "W002"),
    ("w003_noun_name", "W003"),
    ("w004_undecomposed", "W004"),
    ("w005_long_feedback", "W005"),
    ("w006_role_conflict", "W006"),
]


@pytest.mark.parametrize(("fixture", "code"), CASES)
def test_fixture_reports_its_code(fixture, code):
    assert code in codes(fixture)


@pytest.mark.parametrize("fixture", ["valid", "feedback6", "tunnel", "context_only", "two_levels"])
def test_clean_fixtures_have_no_errors(fixture):
    assert not validate.has_errors(diagnose(fixture))


def test_errors_come_before_warnings():
    diagnostics = diagnose("e007_untunneled")
    levels = [diagnostic.level for diagnostic in diagnostics]
    assert levels == sorted(levels, key=lambda level: 0 if level == "error" else 1)


def test_e006_hint_points_at_similar_name():
    hints = [d.hint for d in diagnose("e006_unresolved") if d.code == "E006"]
    assert any(hint and "Проверенная заявка" in hint for hint in hints)


def test_e007_hint_offers_tunnel():
    hints = [d.hint for d in diagnose("e007_untunneled") if d.code == "E007"]
    assert any(hint and "tunnel" in hint for hint in hints)


def test_diagnostic_serialisation_skips_absent_hint():
    diagnostics = diagnose("w001_block_count")
    payload = [diagnostic.as_dict() for diagnostic in diagnostics]
    assert all({"code", "level", "where", "message"} <= set(item) for item in payload)
    assert any("hint" not in item for item in payload)


def test_check_is_deterministic():
    model = load("w005_long_feedback")
    first = [d.as_dict() for d in validate.check(model, parse.resolve(model))]
    second = [d.as_dict() for d in validate.check(model, parse.resolve(model))]
    assert first == second
