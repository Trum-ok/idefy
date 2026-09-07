import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skill" / "SKILL.md"
README = ROOT / "README.md"
DOCS = ROOT / "docs"
SOURCES = [ROOT / "src" / "idefy" / "validate.py", ROOT / "src" / "idefy" / "parse.py"]

CODE_IN_SOURCE = re.compile(r'"([EW]\d{3})"')
CODE_IN_TABLE = re.compile(r"^\| (?:`)?([EW]\d{3})(?:`)?\s*\|", re.MULTILINE)


def implemented() -> set[str]:
    return {
        code for source in SOURCES for code in CODE_IN_SOURCE.findall(source.read_text("utf-8"))
    }


@pytest.mark.parametrize("page", [SKILL, DOCS / "dsl.md"])
def test_diagnostic_tables_match_the_implementation(page):
    assert set(CODE_IN_TABLE.findall(page.read_text("utf-8"))) == implemented()


def test_navigation_lists_every_page():
    summary = (DOCS / "SUMMARY.md").read_text("utf-8")
    linked = set(re.findall(r"\]\((\S+\.md)\)", summary))
    present = {path.name for path in DOCS.glob("*.md")} - {"SUMMARY.md"}
    assert linked == present


def test_documented_exit_codes_match_the_cli():
    source = (ROOT / "src" / "idefy" / "cli.py").read_text("utf-8")
    used = set(re.findall(r"^EXIT_\w+ = (\d)", source, re.MULTILINE))
    documented = set(
        re.findall(r"^\| (\d) {3}\|", (DOCS / "cli.md").read_text("utf-8"), re.MULTILINE)
    )
    assert documented == used


def test_every_referenced_image_exists():
    for page in DOCS.glob("*.md"):
        for target in re.findall(r"!\[[^\]]*\]\(([^)]+?)(?:\{[^}]*\})?\)", page.read_text("utf-8")):
            assert (DOCS / target).is_file(), f"{page.name} -> {target}"


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
def test_cli_page_documents_every_command(command):
    assert f"idefy {command}" in (DOCS / "cli.md").read_text("utf-8")


def test_readme_links_to_the_documentation():
    assert "trum-ok.github.io/idefy" in README.read_text("utf-8")


def test_readme_pins_no_versions():
    text = README.read_text("utf-8")
    assert not re.search(r"idefy[=>< ]=\s*\d", text)
