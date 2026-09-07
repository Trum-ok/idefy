from __future__ import annotations

import math
from xml.sax.saxutils import escape

from idefy import ir

FONT = "Arial, Helvetica, sans-serif"
BLOCK_FONT_SIZE = 11
LABEL_FONT_SIZE = 9
NUMBER_FONT_SIZE = 9
CHAR_RATIO = 0.55
LINE_HEIGHT = 13
ARROW_HEAD = 8
ARROW_HALF_WIDTH = 3.5
TUNNEL_RADIUS = 4


def render(diagram: ir.Diagram, title: str = "") -> str:
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{diagram.canvas.w}" '
        f'height="{diagram.canvas.h}" viewBox="0 0 {diagram.canvas.w} {diagram.canvas.h}">',
        f"<title>{escape(title or diagram.id)}</title>",
        f'<rect x="0" y="0" width="{diagram.canvas.w}" height="{diagram.canvas.h}" fill="#ffffff"/>',
        '<g fill="none" stroke="#000000" stroke-width="1">',
        '<rect x="7.5" y="7.5" width="785" height="429"/>',
        "</g>",
    ]
    for block in diagram.blocks:
        parts.extend(_block(block))
    for arrow in diagram.arrows:
        parts.extend(_arrow(arrow))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _block(block: ir.Block) -> list[str]:
    parts = [
        f'<rect x="{block.x}" y="{block.y}" width="{block.w}" height="{block.h}" '
        'fill="#ffffff" stroke="#000000" stroke-width="1"/>'
    ]
    lines = wrap(block.name, block.w - 10, BLOCK_FONT_SIZE)
    top = block.y + block.h / 2 - (len(lines) - 1) * LINE_HEIGHT / 2 + BLOCK_FONT_SIZE / 3
    for index, line in enumerate(lines):
        parts.append(
            f'<text x="{_num(block.x + block.w / 2)}" y="{_num(top + index * LINE_HEIGHT)}" '
            f'font-family="{FONT}" font-size="{BLOCK_FONT_SIZE}" text-anchor="middle" '
            f'fill="#000000">{escape(line)}</text>'
        )
    parts.append(
        f'<text x="{block.x + block.w - 4}" y="{block.y + block.h - 5}" font-family="{FONT}" '
        f'font-size="{NUMBER_FONT_SIZE}" text-anchor="end" fill="#000000">'
        f"{escape(block.number)}</text>"
    )
    return parts


def _arrow(arrow: ir.Arrow) -> list[str]:
    points = " ".join(f"{x},{y}" for x, y in arrow.points)
    parts = [f'<polyline points="{points}" fill="none" stroke="#000000" stroke-width="1"/>']
    if arrow.dst.kind == "port" and len(arrow.points) >= 2:
        parts.append(_head(arrow.points[-2], arrow.points[-1]))
    if arrow.tunnel in ("source", "both"):
        parts.extend(_tunnel(arrow.points[0], arrow.points[1]))
    if arrow.tunnel in ("dest", "both"):
        parts.extend(_tunnel(arrow.points[-1], arrow.points[-2]))
    if arrow.label is not None:
        parts.append(
            f'<text x="{arrow.label.x}" y="{arrow.label.y}" font-family="{FONT}" '
            f'font-size="{LABEL_FONT_SIZE}" text-anchor="middle" fill="#000000">'
            f"{escape(arrow.name)}</text>"
        )
    parts.extend(_icom(arrow))
    return parts


def _head(previous: ir.Point, tip: ir.Point) -> str:
    dx, dy = tip[0] - previous[0], tip[1] - previous[1]
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    base = (tip[0] - ux * ARROW_HEAD, tip[1] - uy * ARROW_HEAD)
    left = (base[0] - uy * ARROW_HALF_WIDTH, base[1] + ux * ARROW_HALF_WIDTH)
    right = (base[0] + uy * ARROW_HALF_WIDTH, base[1] - ux * ARROW_HALF_WIDTH)
    corners = " ".join(f"{_num(x)},{_num(y)}" for x, y in (tip, left, right))
    return f'<polygon points="{corners}" fill="#000000"/>'


def _tunnel(point: ir.Point, neighbour: ir.Point) -> list[str]:
    dx, dy = neighbour[0] - point[0], neighbour[1] - point[1]
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    parts: list[str] = []
    for sign in (-1, 1):
        cx = point[0] + ux * TUNNEL_RADIUS * sign
        cy = point[1] + uy * TUNNEL_RADIUS * sign
        start = (cx + nx * TUNNEL_RADIUS, cy + ny * TUNNEL_RADIUS)
        end = (cx - nx * TUNNEL_RADIUS, cy - ny * TUNNEL_RADIUS)
        control = (cx + ux * TUNNEL_RADIUS * sign * 1.6, cy + uy * TUNNEL_RADIUS * sign * 1.6)
        parts.append(
            f'<path d="M {_num(start[0])} {_num(start[1])} '
            f'Q {_num(control[0])} {_num(control[1])} {_num(end[0])} {_num(end[1])}" '
            'fill="none" stroke="#000000" stroke-width="1"/>'
        )
    return parts


def _icom(arrow: ir.Arrow) -> list[str]:
    parts: list[str] = []
    if arrow.src.kind == "boundary" and arrow.src.icom:
        parts.append(_icom_text(arrow.points[0], arrow.role, arrow.src.icom))
    if arrow.dst.kind == "boundary" and arrow.dst.icom:
        parts.append(_icom_text(arrow.points[-1], arrow.role, arrow.dst.icom))
    return parts


def _icom_text(point: ir.Point, role: str, code: str) -> str:
    if role == "input":
        x, y, anchor = point[0] + 3, point[1] - 4, "start"
    elif role == "output":
        x, y, anchor = point[0] - 3, point[1] - 4, "end"
    elif role == "control":
        x, y, anchor = point[0] + 3, point[1] + 11, "start"
    else:
        x, y, anchor = point[0] + 3, point[1] - 4, "start"
    return (
        f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{LABEL_FONT_SIZE}" '
        f'text-anchor="{anchor}" fill="#000000">{escape(code)}</text>'
    )


def wrap(text: str, width: float, font_size: int) -> list[str]:
    limit = max(int(width / (font_size * CHAR_RATIO)), 1)
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= limit:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _num(value: float) -> str:
    rounded = round(value, 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:g}"
