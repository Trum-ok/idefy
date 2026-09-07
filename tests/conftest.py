from __future__ import annotations

from pathlib import Path

import pytest

from idefy import layout, parse, validate
from idefy.diagnostics import Diagnostic
from idefy.ir import IR

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = Path(__file__).parent / "golden"
ACTUAL = Path(__file__).parent / ".actual"


def keep(name: str, data: bytes) -> None:
    ACTUAL.mkdir(exist_ok=True)
    (ACTUAL / name).write_bytes(data)


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def golden() -> Path:
    return GOLDEN


def load(name: str) -> parse.Model:
    return parse.load(FIXTURES / f"{name}.yaml")


def diagnose(name: str) -> list[Diagnostic]:
    model = load(name)
    return validate.check(model, parse.resolve(model))


def codes(name: str) -> set[str]:
    return {diagnostic.code for diagnostic in diagnose(name)}


def represent(name: str) -> IR:
    model = load(name)
    return layout.build(model, parse.resolve(model))
