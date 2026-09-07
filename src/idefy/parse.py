from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from idefy.diagnostics import Diagnostic, error
from idefy.dsl import (
    EXTERNAL,
    INCOMING_ROLES,
    ROLE_TITLES,
    ROLES,
    Activity,
    ArrowSpec,
    Model,
    Role,
    Tunnel,
    id_key,
    parent_id,
    split_id,
)


class UsageError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Endpoint:
    kind: Literal["block", "boundary"]
    block: str | None = None

    def key(self) -> str:
        return self.block if self.block is not None else EXTERNAL


BOUNDARY = Endpoint(kind="boundary")


@dataclass(slots=True)
class Arrow:
    name: str
    role: Role
    src: Endpoint
    dst: Endpoint
    tunnel: Tunnel = "none"

    def key(self) -> tuple[str, str, str, str]:
        return (self.name, self.src.key(), self.dst.key(), self.role)

    def touches(self, block_id: str) -> bool:
        return self.src.block == block_id or self.dst.block == block_id


@dataclass(slots=True)
class Diagram:
    id: str
    kind: Literal["context", "decomposition"]
    owner: str | None
    blocks: list[Activity]
    arrows: list[Arrow] = field(default_factory=list)


@dataclass(slots=True)
class Resolution:
    diagrams: list[Diagram]
    index: dict[str, Activity]
    children: dict[str, list[Activity]]
    roots: list[Activity]
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def diagram_of_block(self, block_id: str) -> Diagram | None:
        for diagram in self.diagrams:
            if any(block.id == block_id for block in diagram.blocks):
                return diagram
        return None


def load(path: Path) -> Model:
    if not path.exists():
        raise UsageError(f"Файл не найден: {path}")
    yaml = YAML(typ="safe")
    try:
        data = yaml.load(path.read_text(encoding="utf-8"))
    except YAMLError as exc:
        raise UsageError(f"Не удалось разобрать YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise UsageError("Корень модели должен быть отображением (mapping)")
    try:
        return Model.model_validate(data)
    except ValidationError as exc:
        raise UsageError(_format_validation_error(exc)) from exc


def _format_validation_error(exc: ValidationError) -> str:
    lines = ["Модель не соответствует схеме:"]
    for item in exc.errors():
        location = ".".join(str(part) for part in item["loc"]) or "<корень>"
        lines.append(f"  {location}: {item['msg']}")
    return "\n".join(lines)


def resolve(model: Model) -> Resolution:
    index: dict[str, Activity] = {}
    for activity in model.activities:
        index.setdefault(activity.id, activity)

    children: dict[str, list[Activity]] = {}
    roots: list[Activity] = []
    for activity in sorted(index.values(), key=lambda a: id_key(a.id)):
        parent = parent_id(activity.id)
        if parent is None:
            roots.append(activity)
        elif parent in index:
            children.setdefault(parent, []).append(activity)

    diagnostics: list[Diagnostic] = []
    diagrams: list[Diagram] = []

    for root in roots:
        prefix, _ = split_id(root.id)
        diagrams.append(
            Diagram(
                id=f"{prefix}-0",
                kind="context",
                owner=None,
                blocks=[root],
                arrows=_context_arrows(root),
            )
        )

    for owner_id in sorted(children, key=id_key):
        owner = index[owner_id]
        blocks = children[owner_id]
        diagrams.append(
            Diagram(
                id=owner_id,
                kind="decomposition",
                owner=owner_id,
                blocks=blocks,
                arrows=_decomposition_arrows(owner, blocks),
            )
        )

    resolution = Resolution(
        diagrams=diagrams, index=index, children=children, roots=roots, diagnostics=diagnostics
    )
    diagnostics.extend(_apply_overrides(model, resolution))
    diagnostics.extend(_check_coverage(resolution))
    diagnostics.extend(_check_tunnels(resolution))
    for diagram in diagrams:
        diagram.arrows.sort(key=lambda a: a.key())
    return resolution


def _context_arrows(root: Activity) -> list[Arrow]:
    block = Endpoint(kind="block", block=root.id)
    arrows: list[Arrow] = []
    for role in INCOMING_ROLES:
        for name in root.names(role):
            arrows.append(Arrow(name=name, role=role, src=BOUNDARY, dst=block))
    for name in root.output:
        arrows.append(Arrow(name=name, role="output", src=block, dst=BOUNDARY))
    return arrows


def _decomposition_arrows(owner: Activity, blocks: list[Activity]) -> list[Arrow]:
    arrows: list[Arrow] = []

    producers: dict[str, list[str]] = {}
    for block in blocks:
        for name in block.output:
            producers.setdefault(name, []).append(block.id)

    for block in blocks:
        endpoint = Endpoint(kind="block", block=block.id)
        for role in INCOMING_ROLES:
            for name in block.names(role):
                sources = [pid for pid in producers.get(name, []) if pid != block.id]
                for source_id in sources:
                    arrows.append(
                        Arrow(
                            name=name,
                            role=role,
                            src=Endpoint(kind="block", block=source_id),
                            dst=endpoint,
                        )
                    )
                if not sources and name in owner.names(role):
                    arrows.append(Arrow(name=name, role=role, src=BOUNDARY, dst=endpoint))

    for block in blocks:
        endpoint = Endpoint(kind="block", block=block.id)
        for name in block.output:
            if name in owner.output:
                arrows.append(Arrow(name=name, role="output", src=endpoint, dst=BOUNDARY))

    return arrows


def _check_coverage(resolution: Resolution) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for diagram in resolution.diagrams:
        if diagram.owner is None:
            continue
        owner = resolution.index[diagram.owner]
        for block in diagram.blocks:
            for role in INCOMING_ROLES:
                for position, name in enumerate(block.names(role)):
                    covered = any(
                        arrow.name == name and arrow.role == role and arrow.dst.block == block.id
                        for arrow in diagram.arrows
                    )
                    if not covered:
                        diagnostics.append(
                            _unresolved(owner, diagram.blocks, block, role, position, name, True)
                        )
            for position, name in enumerate(block.output):
                covered = any(
                    arrow.name == name and arrow.src.block == block.id for arrow in diagram.arrows
                )
                if not covered:
                    diagnostics.append(
                        _unresolved(owner, diagram.blocks, block, "output", position, name, False)
                    )
    return diagnostics


def _unresolved(
    owner: Activity,
    blocks: list[Activity],
    block: Activity,
    role: Role,
    position: int,
    name: str,
    incoming: bool,
) -> Diagnostic:
    where = f"{block.id}.{role}[{position}]"
    message = f"Стрелка «{name}» не разрешена на диаграмме {owner.id}"
    if incoming:
        hint = _similar_hint(name, owner, blocks, role, want_output=True)
        hint = hint or (
            f"добавьте «{name}» в {ROLE_TITLES[role]} функции {owner.id} "
            f"или в выход одного из соседей"
        )
    else:
        hint = _similar_hint(name, owner, blocks, role, want_output=False)
        hint = hint or (
            f"выход никем не потребляется: добавьте «{name}» в выход функции {owner.id} "
            f"или объявите arrows: [{{name: «{name}», from: {block.id}, to: external}}]"
        )
    return error("E006", where, message, hint)


def _similar_hint(
    name: str, owner: Activity, blocks: list[Activity], role: Role, want_output: bool
) -> str | None:
    target = _fold(name)
    for candidate in blocks:
        source = candidate.output if want_output else _incoming_names(candidate)
        for other in source:
            if other != name and _fold(other) == target:
                place = f"{candidate.id}.output" if want_output else candidate.id
                return f"похожее имя есть у {place}: «{other}»"
    for other in owner.names(role):
        if other != name and _fold(other) == target:
            return f"похожее имя есть у {owner.id}.{role}: «{other}»"
    return None


def _incoming_names(activity: Activity) -> list[str]:
    names: list[str] = []
    for role in INCOMING_ROLES:
        names.extend(activity.names(role))
    return names


def _fold(name: str) -> str:
    return "".join(name.split()).casefold().replace("ё", "е")


def _apply_overrides(model: Model, resolution: Resolution) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for position, spec in enumerate(model.arrows):
        where = f"arrows[{position}]"
        diagram = _override_diagram(spec, resolution)
        if diagram is None:
            diagnostics.append(
                error(
                    "E006",
                    where,
                    f"Стрелка «{spec.name}» не привязана к диаграмме",
                    "хотя бы один из концов должен быть идентификатором функции, "
                    "и оба конца должны лежать на одной диаграмме",
                )
            )
            continue
        matched = [
            arrow
            for arrow in diagram.arrows
            if arrow.name == spec.name
            and arrow.src.key() == spec.src
            and arrow.dst.key() == spec.dst
            and (spec.role is None or arrow.role == spec.role)
        ]
        if matched:
            for arrow in matched:
                arrow.tunnel = spec.tunnel
                if spec.role is not None:
                    arrow.role = spec.role
            continue
        created = _create_override(spec, diagram, resolution)
        if created is None:
            diagnostics.append(
                error(
                    "E006",
                    where,
                    f"Стрелка «{spec.name}» {spec.src} → {spec.dst} не найдена и не может быть создана",
                    "имя должно стоять в выходе источника и во входном списке приёмника",
                )
            )
        else:
            diagram.arrows.append(created)
    return diagnostics


def _override_diagram(spec: ArrowSpec, resolution: Resolution) -> Diagram | None:
    diagrams = []
    for endpoint in (spec.src, spec.dst):
        if endpoint == EXTERNAL:
            continue
        diagram = resolution.diagram_of_block(endpoint)
        if diagram is None:
            return None
        diagrams.append(diagram)
    if not diagrams:
        return None
    if len({diagram.id for diagram in diagrams}) != 1:
        return None
    return diagrams[0]


def _create_override(spec: ArrowSpec, diagram: Diagram, resolution: Resolution) -> Arrow | None:
    if spec.src != EXTERNAL:
        source = resolution.index.get(spec.src)
        if source is None or spec.name not in source.output:
            return None
        src = Endpoint(kind="block", block=spec.src)
    else:
        src = BOUNDARY

    if spec.dst == EXTERNAL:
        if src.kind != "block":
            return None
        return Arrow(name=spec.name, role="output", src=src, dst=BOUNDARY, tunnel=spec.tunnel)

    target = resolution.index.get(spec.dst)
    if target is None:
        return None
    roles = [role for role in INCOMING_ROLES if spec.name in target.names(role)]
    if spec.role is not None:
        if spec.role not in roles:
            return None
        role = spec.role
    elif len(roles) == 1:
        role = roles[0]
    else:
        return None
    return Arrow(
        name=spec.name,
        role=role,
        src=src,
        dst=Endpoint(kind="block", block=spec.dst),
        tunnel=spec.tunnel,
    )


def _check_tunnels(resolution: Resolution) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for owner_id in sorted(resolution.children, key=id_key):
        owner = resolution.index[owner_id]
        blocks = resolution.children[owner_id]
        outer = resolution.diagram_of_block(owner_id)
        for role in ROLES:
            for position, name in enumerate(owner.names(role)):
                if any(name in block.names(role) for block in blocks):
                    continue
                if outer is not None and _is_tunneled(outer, owner_id, name, role):
                    continue
                diagnostics.append(
                    error(
                        "E007",
                        f"{owner_id}.{role}[{position}]",
                        f"{ROLE_TITLES[role].capitalize()} «{name}» функции {owner_id} "
                        f"не подхвачен ни одним блоком её декомпозиции",
                        f"добавьте «{name}» в {ROLE_TITLES[role]} нужного блока или пометьте "
                        f"стрелку туннелем: arrows: [{{name: «{name}», "
                        f"from: {'external' if role != 'output' else owner_id}, "
                        f"to: {owner_id if role != 'output' else 'external'}, "
                        f"tunnel: {'dest' if role != 'output' else 'source'}}}]",
                    )
                )
    return diagnostics


def _is_tunneled(diagram: Diagram, block_id: str, name: str, role: Role) -> bool:
    wanted = "source" if role == "output" else "dest"
    for arrow in diagram.arrows:
        if arrow.name != name or not arrow.touches(block_id):
            continue
        if role == "output" and arrow.src.block != block_id:
            continue
        if role != "output" and (arrow.dst.block != block_id or arrow.role != role):
            continue
        if arrow.tunnel in (wanted, "both"):
            return True
    return False
