from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from idefy.dsl import Role, Tunnel

IR_VERSION = 1

Point = tuple[int, int]
Side = Literal["left", "top", "right", "bottom"]


@dataclass(slots=True)
class Canvas:
    w: int
    h: int

    def as_dict(self) -> dict[str, Any]:
        return {"w": self.w, "h": self.h}


@dataclass(slots=True)
class Block:
    id: str
    name: str
    x: int
    y: int
    w: int
    h: int
    number: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "number": self.number,
        }

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h


@dataclass(slots=True)
class Endpoint:
    kind: Literal["boundary", "port"]
    icom: str | None = None
    block: str | None = None
    side: Side | None = None
    offset: int | None = None

    def as_dict(self) -> dict[str, Any]:
        if self.kind == "boundary":
            return {"kind": "boundary", "icom": self.icom}
        return {"kind": "port", "block": self.block, "side": self.side, "offset": self.offset}


@dataclass(slots=True)
class Label:
    x: int
    y: int

    def as_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y}


@dataclass(slots=True)
class Arrow:
    name: str
    role: Role
    src: Endpoint
    dst: Endpoint
    points: list[Point]
    tunnel: Tunnel = "none"
    label: Label | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "from": self.src.as_dict(),
            "to": self.dst.as_dict(),
            "points": [list(point) for point in self.points],
            "tunnel": self.tunnel,
            "label": self.label.as_dict() if self.label else None,
        }


@dataclass(slots=True)
class Diagram:
    id: str
    kind: Literal["context", "decomposition"]
    canvas: Canvas
    blocks: list[Block] = field(default_factory=list)
    arrows: list[Arrow] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "canvas": self.canvas.as_dict(),
            "blocks": [block.as_dict() for block in self.blocks],
            "arrows": [arrow.as_dict() for arrow in self.arrows],
        }


@dataclass(slots=True)
class ModelInfo:
    name: str
    author: str | None = None
    purpose: str | None = None
    viewpoint: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "author": self.author,
            "purpose": self.purpose,
            "viewpoint": self.viewpoint,
        }


@dataclass(slots=True)
class IR:
    model: ModelInfo
    diagrams: list[Diagram] = field(default_factory=list)
    ir_version: int = IR_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "ir_version": self.ir_version,
            "model": self.model.as_dict(),
            "diagrams": [diagram.as_dict() for diagram in self.diagrams],
        }

    def diagram(self, diagram_id: str) -> Diagram | None:
        for diagram in self.diagrams:
            if diagram.id == diagram_id:
                return diagram
        return None
