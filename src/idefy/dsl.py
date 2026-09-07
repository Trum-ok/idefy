from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Role = Literal["input", "control", "output", "mechanism"]
Tunnel = Literal["none", "source", "dest", "both"]

EXTERNAL = "external"

ROLES: tuple[Role, ...] = ("input", "control", "output", "mechanism")
INCOMING_ROLES: tuple[Role, ...] = ("input", "control", "mechanism")

ROLE_TITLES: dict[Role, str] = {
    "input": "вход",
    "control": "управление",
    "output": "выход",
    "mechanism": "механизм",
}

ICOM_LETTERS: dict[Role, str] = {
    "input": "I",
    "control": "C",
    "output": "O",
    "mechanism": "M",
}

_ID_RE = re.compile(r"^[A-Z]+(?:0|[1-9]+)$")
_ID_SPLIT_RE = re.compile(r"^([A-Z]+)([0-9]+)$")

_INFINITIVE_ENDINGS = ("ться", "ть", "чься", "чь", "тись", "ти")


class Activity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    input: list[str] = Field(default_factory=list)
    control: list[str] = Field(default_factory=list)
    output: list[str] = Field(default_factory=list)
    mechanism: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        value = value.strip()
        if not _ID_RE.match(value):
            raise ValueError(
                f"«{value}» не похож на идентификатор функции: "
                "ожидается буквенный префикс и номер, например A0, A1, A12"
            )
        return value

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("имя функции не может быть пустым")
        return value

    @field_validator("input", "control", "output", "mechanism")
    @classmethod
    def _clean_names(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            name = item.strip()
            if not name:
                raise ValueError("имя стрелки не может быть пустым")
            if name not in cleaned:
                cleaned.append(name)
        return cleaned

    def names(self, role: Role) -> list[str]:
        return getattr(self, role)  # type: ignore[no-any-return]

    def icom_count(self) -> int:
        return sum(len(self.names(role)) for role in ROLES)


class ArrowSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str
    src: str = Field(alias="from")
    dst: str = Field(alias="to")
    role: Role | None = None
    tunnel: Tunnel = "none"

    @field_validator("name", "src", "dst")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("значение не может быть пустым")
        return value


class ModelMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    author: str | None = None
    purpose: str | None = None
    viewpoint: str | None = None


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    model: ModelMeta
    activities: list[Activity] = Field(default_factory=list)
    arrows: list[ArrowSpec] = Field(default_factory=list)


def split_id(activity_id: str) -> tuple[str, str]:
    match = _ID_SPLIT_RE.match(activity_id)
    if match is None:
        return activity_id, ""
    return match.group(1), match.group(2)


def parent_id(activity_id: str) -> str | None:
    prefix, digits = split_id(activity_id)
    if not digits or digits == "0":
        return None
    if len(digits) == 1:
        return f"{prefix}0"
    return f"{prefix}{digits[:-1]}"


def is_root(activity_id: str) -> bool:
    return parent_id(activity_id) is None


def id_key(activity_id: str) -> tuple[str, int, str]:
    prefix, digits = split_id(activity_id)
    return (prefix, len(digits), digits)


def starts_with_infinitive(name: str) -> bool:
    first = name.split()[0].lower() if name.split() else ""
    return first.endswith(_INFINITIVE_ENDINGS)
