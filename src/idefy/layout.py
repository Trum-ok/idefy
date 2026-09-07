from __future__ import annotations

from itertools import pairwise

from idefy import ir
from idefy.dsl import ICOM_LETTERS, Activity, Model, Role, id_key
from idefy.parse import Arrow as ResolvedArrow
from idefy.parse import Diagram as ResolvedDiagram
from idefy.parse import Resolution

CANVAS_W = 800
CANVAS_H = 444

AREA_LEFT = 7
AREA_TOP = 7
AREA_RIGHT = 793
AREA_BOTTOM = 437
AREA_W = AREA_RIGHT - AREA_LEFT
AREA_H = AREA_BOTTOM - AREA_TOP

MAX_STEP_X = 190
MAX_STEP_Y = 90
MIN_BLOCK_GAP = 8
WANT_MARGIN = 24

BLOCK_SIZES: dict[int, tuple[int, int]] = {
    1: (228, 78),
    2: (120, 56),
    3: (120, 56),
    4: (120, 56),
    5: (120, 56),
    6: (120, 56),
    7: (100, 50),
    8: (90, 44),
}
FALLBACK_SIZE = (90, 44)

MIN_PORT_STEP = 12
BYPASS_GAP = 15
DETOUR_GAP = 25
INSET = 4
LABEL_OFFSET = 6
LABEL_SHIFT = 12
LABEL_CHAR_W = 5.0
LABEL_LINE_H = 12

SIDE_BY_ROLE: dict[Role, ir.Side] = {
    "input": "left",
    "control": "top",
    "mechanism": "bottom",
    "output": "right",
}
ROLE_BY_SIDE: dict[ir.Side, Role] = {
    "left": "input",
    "top": "control",
    "bottom": "mechanism",
    "right": "output",
}

Ports = dict[tuple[str, ir.Side], dict[str, int]]


def build(model: Model, resolution: Resolution) -> ir.IR:
    return ir.IR(
        model=ir.ModelInfo(
            name=model.model.name,
            author=model.model.author,
            purpose=model.model.purpose,
            viewpoint=model.model.viewpoint,
        ),
        diagrams=[_layout_diagram(diagram, resolution) for diagram in resolution.diagrams],
    )


def place_blocks(activities: list[Activity]) -> list[ir.Block]:
    count = len(activities)
    if count == 0:
        return []
    width, height = BLOCK_SIZES.get(count, FALLBACK_SIZE)
    if count == 1:
        origins = [(AREA_LEFT + (AREA_W - width) // 2, AREA_TOP + (AREA_H - height) // 2)]
    else:
        step_x = _step(AREA_W, width, count, MAX_STEP_X)
        step_y = _step(AREA_H, height, count, MAX_STEP_Y)
        left = AREA_LEFT + (AREA_W - width - step_x * (count - 1)) / 2
        top = AREA_TOP + (AREA_H - height - step_y * (count - 1)) / 2
        origins = [
            (round(left + position * step_x), round(top + position * step_y))
            for position in range(count)
        ]
    return [
        ir.Block(
            id=activity.id,
            name=activity.name,
            x=origin[0],
            y=origin[1],
            w=width,
            h=height,
            number=activity.id,
        )
        for activity, origin in zip(activities, origins, strict=True)
    ]


def _step(area: int, size: int, count: int, cap: int) -> float:
    needed = (size + MIN_BLOCK_GAP) * (count - 1) + size
    margin = max(0, min(WANT_MARGIN, (area - needed) // 2))
    return min((area - 2 * margin - size) / (count - 1), cap)


def _layout_diagram(diagram: ResolvedDiagram, resolution: Resolution) -> ir.Diagram:
    activities = sorted(diagram.blocks, key=lambda a: id_key(a.id))
    blocks = place_blocks(activities)
    by_id = {block.id: block for block in blocks}
    order = {block.id: position for position, block in enumerate(blocks)}
    ports = _assign_ports(diagram, resolution, by_id)

    built: list[tuple[ResolvedArrow, ir.Arrow]] = []
    boundaries: list[tuple[Role, int, str, list[ir.Endpoint]]] = []

    incoming: dict[tuple[Role, str], list[ResolvedArrow]] = {}
    outgoing: dict[str, list[ResolvedArrow]] = {}
    internal: list[ResolvedArrow] = []
    for arrow in diagram.arrows:
        if arrow.src.block is None and arrow.dst.block is not None:
            incoming.setdefault((arrow.role, arrow.name), []).append(arrow)
        elif arrow.dst.block is None and arrow.src.block is not None:
            outgoing.setdefault(arrow.name, []).append(arrow)
        else:
            internal.append(arrow)

    for (role, name), group in incoming.items():
        routes = _route_incoming(group, role, name, by_id, order, ports)
        endpoints: list[ir.Endpoint] = []
        for arrow, points in routes:
            source = ir.Endpoint(kind="boundary")
            endpoints.append(source)
            built.append((arrow, _arrow(arrow, points, source, _port_end(arrow, ports))))
        anchor = routes[0][1][0]
        boundaries.append((role, anchor[1] if role == "input" else anchor[0], name, endpoints))

    for name, group in outgoing.items():
        routes = _route_outgoing(group, name, by_id, order, ports)
        endpoints = []
        for arrow, points in routes:
            target = ir.Endpoint(kind="boundary")
            endpoints.append(target)
            built.append((arrow, _arrow(arrow, points, _port_start(arrow, ports), target)))
        anchor = routes[0][1][-1]
        boundaries.append(("output", anchor[1], name, endpoints))

    for arrow in internal:
        points = _route_internal(arrow, by_id, order, ports)
        built.append(
            (arrow, _arrow(arrow, points, _port_start(arrow, ports), _port_end(arrow, ports)))
        )

    _number_boundaries(boundaries)
    built.sort(key=lambda item: item[0].key())
    arrows = [item[1] for item in built]
    _place_labels(arrows, blocks)
    return ir.Diagram(
        id=diagram.id,
        kind=diagram.kind,
        canvas=ir.Canvas(w=CANVAS_W, h=CANVAS_H),
        blocks=blocks,
        arrows=arrows,
    )


def _arrow(
    arrow: ResolvedArrow, points: list[ir.Point], src: ir.Endpoint, dst: ir.Endpoint
) -> ir.Arrow:
    return ir.Arrow(
        name=arrow.name, role=arrow.role, src=src, dst=dst, points=points, tunnel=arrow.tunnel
    )


def _port_start(arrow: ResolvedArrow, ports: Ports) -> ir.Endpoint:
    assert arrow.src.block is not None
    return ir.Endpoint(
        kind="port",
        block=arrow.src.block,
        side="right",
        offset=ports[(arrow.src.block, "right")][arrow.name],
    )


def _port_end(arrow: ResolvedArrow, ports: Ports) -> ir.Endpoint:
    assert arrow.dst.block is not None
    side = SIDE_BY_ROLE[arrow.role]
    return ir.Endpoint(
        kind="port",
        block=arrow.dst.block,
        side=side,
        offset=ports[(arrow.dst.block, side)][arrow.name],
    )


def _assign_ports(
    diagram: ResolvedDiagram, resolution: Resolution, by_id: dict[str, ir.Block]
) -> Ports:
    used: dict[tuple[str, ir.Side], list[str]] = {}
    for arrow in diagram.arrows:
        if arrow.src.block is not None:
            used.setdefault((arrow.src.block, "right"), []).append(arrow.name)
        if arrow.dst.block is not None:
            used.setdefault((arrow.dst.block, SIDE_BY_ROLE[arrow.role]), []).append(arrow.name)

    ports: Ports = {}
    for (block_id, side), names in used.items():
        activity = resolution.index.get(block_id)
        declared = activity.names(ROLE_BY_SIDE[side]) if activity else []
        ordered = sorted(
            dict.fromkeys(names),
            key=lambda name: (declared.index(name) if name in declared else len(declared), name),
        )
        block = by_id[block_id]
        length = block.h if side in ("left", "right") else block.w
        ports[(block_id, side)] = dict(zip(ordered, _distribute(length, len(ordered)), strict=True))
    return ports


def _distribute(length: int, count: int) -> list[int]:
    if count == 0:
        return []
    step = length / (count + 1)
    if step >= MIN_PORT_STEP:
        return [round(length * (position + 1) / (count + 1)) for position in range(count)]
    start = length / 2 - (count - 1) * MIN_PORT_STEP / 2
    return [round(start + position * MIN_PORT_STEP) for position in range(count)]


def _port_point(block: ir.Block, side: ir.Side, ports: Ports, name: str) -> ir.Point:
    offset = ports[(block.id, side)][name]
    if side == "left":
        return (block.x, block.y + offset)
    if side == "right":
        return (block.right, block.y + offset)
    if side == "top":
        return (block.x + offset, block.y)
    return (block.x + offset, block.bottom)


def _column_after(blocks: list[ir.Block], index: int) -> int:
    current = blocks[index]
    if index + 1 < len(blocks):
        return (current.right + blocks[index + 1].x) // 2
    return min(current.right + BYPASS_GAP, AREA_RIGHT - INSET)


def _column_before(blocks: list[ir.Block], index: int) -> int:
    current = blocks[index]
    if index > 0:
        return (blocks[index - 1].right + current.x) // 2
    return max(current.x - BYPASS_GAP, AREA_LEFT + INSET)


def _above(blocks: list[ir.Block], span: range, gap: int = BYPASS_GAP) -> int:
    top = min(blocks[position].y for position in span)
    return max(top - gap, AREA_TOP + INSET)


def _under(blocks: list[ir.Block], span: range, gap: int = BYPASS_GAP) -> int:
    bottom = max(blocks[position].bottom for position in span)
    return min(bottom + gap, AREA_BOTTOM - INSET)


def _route_incoming(
    group: list[ResolvedArrow],
    role: Role,
    name: str,
    by_id: dict[str, ir.Block],
    order: dict[str, int],
    ports: Ports,
) -> list[tuple[ResolvedArrow, list[ir.Point]]]:
    blocks = sorted(by_id.values(), key=lambda block: order[block.id])
    targets = sorted(group, key=lambda arrow: order[arrow.dst.block or ""])
    side = SIDE_BY_ROLE[role]
    points = [_port_point(by_id[arrow.dst.block or ""], side, ports, name) for arrow in targets]
    span = range(
        min(order[a.dst.block or ""] for a in targets),
        max(order[a.dst.block or ""] for a in targets) + 1,
    )

    routes: list[tuple[ResolvedArrow, list[ir.Point]]] = []
    if role == "input":
        entry = (AREA_LEFT, points[0][1])
        trunk = max(
            min(by_id[arrow.dst.block or ""].x for arrow in targets) - BYPASS_GAP,
            AREA_LEFT + INSET,
        )
        for arrow, point in zip(targets, points, strict=True):
            routes.append((arrow, _clean([entry, (trunk, entry[1]), (trunk, point[1]), point])))
    elif role == "control":
        entry = (points[0][0], AREA_TOP)
        trunk = _above(blocks, span)
        for arrow, point in zip(targets, points, strict=True):
            routes.append((arrow, _clean([entry, (entry[0], trunk), (point[0], trunk), point])))
    else:
        entry = (points[0][0], AREA_BOTTOM)
        trunk = _under(blocks, span)
        for arrow, point in zip(targets, points, strict=True):
            routes.append((arrow, _clean([entry, (entry[0], trunk), (point[0], trunk), point])))
    return routes


def _route_outgoing(
    group: list[ResolvedArrow],
    name: str,
    by_id: dict[str, ir.Block],
    order: dict[str, int],
    ports: Ports,
) -> list[tuple[ResolvedArrow, list[ir.Point]]]:
    sources = sorted(group, key=lambda arrow: order[arrow.src.block or ""])
    points = [_port_point(by_id[arrow.src.block or ""], "right", ports, name) for arrow in sources]
    exit_point = (AREA_RIGHT, points[0][1])
    trunk = min(
        max(by_id[arrow.src.block or ""].right for arrow in sources) + BYPASS_GAP,
        AREA_RIGHT - INSET,
    )
    return [
        (arrow, _clean([point, (trunk, point[1]), (trunk, exit_point[1]), exit_point]))
        for arrow, point in zip(sources, points, strict=True)
    ]


def _route_internal(
    arrow: ResolvedArrow, by_id: dict[str, ir.Block], order: dict[str, int], ports: Ports
) -> list[ir.Point]:
    blocks = sorted(by_id.values(), key=lambda block: order[block.id])
    source = by_id[arrow.src.block or ""]
    target = by_id[arrow.dst.block or ""]
    start = _port_point(source, "right", ports, arrow.name)
    side = SIDE_BY_ROLE[arrow.role]
    end = _port_point(target, side, ports, arrow.name)
    first, last = order[source.id], order[target.id]
    span = range(min(first, last), max(first, last) + 1)
    column = _column_after(blocks, first)

    if side == "top":
        trunk = _above(blocks, span, DETOUR_GAP)
        return _clean([start, (column, start[1]), (column, trunk), (end[0], trunk), end])
    if side == "bottom":
        trunk = _under(blocks, span, DETOUR_GAP)
        return _clean([start, (column, start[1]), (column, trunk), (end[0], trunk), end])
    if last > first:
        return _clean([start, (column, start[1]), (column, end[1]), end])

    trunk = _under(blocks, span, DETOUR_GAP)
    back = _column_before(blocks, last)
    return _clean([start, (column, start[1]), (column, trunk), (back, trunk), (back, end[1]), end])


def _clean(points: list[ir.Point]) -> list[ir.Point]:
    result: list[ir.Point] = []
    for point in points:
        if result and result[-1] == point:
            continue
        result.append(point)
    trimmed: list[ir.Point] = []
    for point in result:
        if len(trimmed) >= 2:
            first, second = trimmed[-2], trimmed[-1]
            if first[0] == second[0] == point[0] or first[1] == second[1] == point[1]:
                trimmed[-1] = point
                continue
        trimmed.append(point)
    return trimmed


def _number_boundaries(groups: list[tuple[Role, int, str, list[ir.Endpoint]]]) -> None:
    by_role: dict[Role, list[tuple[int, str, list[ir.Endpoint]]]] = {}
    for role, anchor, name, endpoints in groups:
        by_role.setdefault(role, []).append((anchor, name, endpoints))
    for role, items in by_role.items():
        items.sort(key=lambda item: (item[0], item[1]))
        for position, (_, _, endpoints) in enumerate(items, start=1):
            code = f"{ICOM_LETTERS[role]}{position}"
            for endpoint in endpoints:
                endpoint.icom = code


def _place_labels(arrows: list[ir.Arrow], blocks: list[ir.Block]) -> None:
    taken: list[tuple[float, float, float, float]] = [
        (block.x, block.y, block.right, block.bottom) for block in blocks
    ]
    carriers: dict[str, ir.Arrow] = {}
    for arrow in arrows:
        current = carriers.get(arrow.name)
        if current is None or _horizontal_run(arrow.points) > _horizontal_run(current.points):
            carriers[arrow.name] = arrow

    for arrow in arrows:
        if carriers.get(arrow.name) is not arrow:
            continue
        width = max(len(arrow.name) * LABEL_CHAR_W, 20.0)
        anchor = _label_anchor(arrow.points, width)
        if anchor is None:
            continue
        half = width / 2
        x = min(max(anchor[0], half + 2), CANVAS_W - half - 2)
        y = anchor[1]
        for _ in range(8):
            box = (x - half, y - LABEL_LINE_H, x + half, y)
            if not any(_overlaps(box, other) for other in taken):
                break
            y += LABEL_SHIFT
        else:
            box = (x - half, y - LABEL_LINE_H, x + half, y)
        taken.append(box)
        arrow.label = ir.Label(x=int(x), y=int(y))


def _horizontal_run(points: list[ir.Point]) -> int:
    runs = [
        abs(second[0] - first[0]) for first, second in pairwise(points) if first[1] == second[1]
    ]
    return max(runs, default=0)


def _label_anchor(points: list[ir.Point], width: float) -> ir.Point | None:
    horizontals = [(first, second) for first, second in pairwise(points) if first[1] == second[1]]
    if horizontals:
        first, second = max(horizontals, key=lambda pair: abs(pair[1][0] - pair[0][0]))
        above = first[1] - LABEL_OFFSET
        if above - LABEL_LINE_H < AREA_TOP:
            above = first[1] + LABEL_OFFSET + LABEL_LINE_H
        return ((first[0] + second[0]) // 2, above)
    if len(points) >= 2:
        first, second = points[0], points[1]
        return (int(first[0] + LABEL_OFFSET + width / 2), (first[1] + second[1]) // 2)
    return None


def _overlaps(
    first: tuple[float, float, float, float], second: tuple[float, float, float, float]
) -> bool:
    return not (
        first[2] <= second[0]
        or second[2] <= first[0]
        or first[3] <= second[1]
        or second[3] <= first[1]
    )
