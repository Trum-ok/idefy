import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skill" / "SKILL.md"
README = ROOT / "README.md"
SOURCES = [ROOT / "src" / "idefy" / "validate.py", ROOT / "src" / "idefy" / "parse.py"]

CODE_IN_SOURCE = re.compile(r'"([EW]\d{3})"')
CODE_IN_TABLE = re.compile(r"^\| (?:`)?([EW]\d{3})(?:`)?\s*\|", re.MULTILINE)


def implemented() -> set[str]:
    return {
        code for source in SOURCES for code in CODE_IN_SOURCE.findall(source.read_text("utf-8"))
    }


def test_skill_lists_every_diagnostic_code():
    assert set(CODE_IN_TABLE.findall(SKILL.read_text("utf-8"))) == implemented()


def test_skill_has_frontmatter_with_a_trigger():
    text = SKILL.read_text("utf-8")
    assert text.startswith("---\n")
    header = text.split("---", 2)[1]
    assert re.search(r"^name: \S+", header, re.MULTILINE)
    assert "IDEF0" in header


def test_skill_demands_looking_at_the_preview():
    text = SKILL.read_text("utf-8")
    assert "Посмотрите картинки" in text
    assert "обязателен" in text


@pytest.mark.parametrize(
    "command", ["init", "validate", "preview", "build", "open", "schema", "doctor"]
)
def test_readme_documents_every_command(command):
    assert f"idefy {command}" in README.read_text("utf-8")


def test_readme_pins_no_versions():
    text = README.read_text("utf-8")
    assert not re.search(r"idefy[=>< ]=\s*\d", text)
