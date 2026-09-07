from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Level = Literal["error", "warning"]


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    level: Level
    where: str
    message: str
    hint: str | None = None

    def as_dict(self) -> dict[str, str]:
        data = {
            "code": self.code,
            "level": self.level,
            "where": self.where,
            "message": self.message,
        }
        if self.hint is not None:
            data["hint"] = self.hint
        return data


def error(code: str, where: str, message: str, hint: str | None = None) -> Diagnostic:
    return Diagnostic(code=code, level="error", where=where, message=message, hint=hint)


def warning(code: str, where: str, message: str, hint: str | None = None) -> Diagnostic:
    return Diagnostic(code=code, level="warning", where=where, message=message, hint=hint)


def sort_key(diagnostic: Diagnostic) -> tuple[int, str, str]:
    return (0 if diagnostic.level == "error" else 1, diagnostic.code, diagnostic.where)
