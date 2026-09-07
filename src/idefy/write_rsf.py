from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from importlib import resources
from pathlib import Path

from idefy import ir
from idefy.rsf import tables
from idefy.rsf.tables import Archive

ALIVE = "2147483647"
SYSTEM_ELEMENTS = {"1", "2", "3", "4"}
ROOT = 3
FIRST_ELEMENT = 5

Q_SECTOR = 6
Q_STREAM = 7
Q_FUNCTION = 14

A_HIERARCHICAL = 1
A_VISUAL_DATA = 20
A_BACKGROUND = 22
A_FOREGROUND = 23
A_BOUNDS = 24
A_FONT = 25
A_STATUS = 26
A_TYPE = 27
A_DECOMPOSITION_TYPE = 29
A_CREATE_DATE = 31
A_REV_DATE = 32
A_SYSTEM_REV_DATE = 33
A_FUNCTION_SECTOR = 35
A_SECTOR_STREAM = 36
A_SECTOR_POINTS = 37
A_SECTOR_PROPERTIES = 38
A_STREAM_NAME = 39
A_SECTOR = 40
A_BORDER_START = 41
A_BORDER_END = 42
A_MODEL_PREFERENCES = 45
A_NAME = 55

TYPE_CONTEXT = 3
TYPE_PLAIN = 1

VISUAL_ATTRIBUTES = (
    "8180808080808060BF82808080808080808080808080808080808080808080A4C07F7F7F7F"
    "808186808080C4E9E1ECEFE7888080808080808081808080808080808080808080"
)
VISUAL_DATA = "8280808080808080"

FUNCTION_SIDE = {"output": 0, "mechanism": 1, "input": 2, "control": 3}
ROLE_BY_SIDE = {"right": "output", "bottom": "mechanism", "left": "input", "top": "control"}
FRAME_RIGHT, FRAME_BOTTOM, FRAME_LEFT, FRAME_TOP = 0, 1, 2, 3

POINT_ON_VERTICAL = 0
POINT_ON_HORIZONTAL = 1
POINT_FREE = -1

AREA_LEFT = 7
AREA_TOP = 7
AREA_RIGHT = 793
AREA_BOTTOM = 437

TEXT_LINE_HEIGHT = 9.421875
TEXT_CHAR_WIDTH = 6.0

# Java печатает узкий неразрывный пробел перед AM/PM; обычный ломает разбор даты
NARROW_SPACE = "\u202f"

QUALIFIER_MARKER = b"sr\x00\x1ecom.ramussoft.common.Qualifier"


def template_path() -> Path:
    with resources.as_file(resources.files("idefy.rsf").joinpath("blank.rsf")) as path:
        return path


def java_moment(moment: datetime) -> str:
    hour = moment.hour % 12 or 12
    suffix = "AM" if moment.hour < 12 else "PM"
    return f"{moment.month}/{moment.day}/{moment.year % 100}, {hour}:{moment.minute:02d} {suffix}"


def build(document: ir.IR, path: Path, moment: datetime | None = None) -> Path:
    Writer(document, moment or datetime.now()).write(path)
    return path


@dataclass(slots=True)
class Writer:
    document: ir.IR
    moment: datetime
    archive: Archive = field(init=False)
    date: str = field(init=False)
    next_element: int = FIRST_ELEMENT
    next_ordinate: int = 1
    next_crosspoint: int = 1
    functions: dict[str, int] = field(default_factory=dict)
    streams: dict[str, int] = field(default_factory=dict)
    last_stream: int = -1
    links: dict[tuple[str, str, str], int] = field(default_factory=dict)
    linked_outer: set[tuple[str, str, str]] = field(default_factory=set)
    linked_inner: set[tuple[str, str, str]] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.archive = tables.read(template_path())
        self.date = java_moment(self.moment)
        self._strip()

    def write(self, path: Path) -> None:
        self._root()
        self._functions()
        self._sectors()
        self._preferences()
        self._sequences()
        self._session()
        self.archive.write(path)

    def _strip(self) -> None:
        for table in self.archive.tables.values():
            try:
                table.keep("ELEMENT_ID", SYSTEM_ELEMENTS)
            except KeyError:
                continue

    def _element(self, qualifier: int) -> int:
        element = self.next_element
        self.next_element += 1
        self.archive.add(
            "elements",
            ELEMENT_ID=element,
            ELEMENT_NAME=None,
            QUALIFIER_ID=qualifier,
            CREATED_BRANCH_ID=0,
            REMOVED_BRANCH_ID=ALIVE,
        )
        return element

    def _ordinate(self) -> int:
        value = self.next_ordinate
        self.next_ordinate += 1
        return value

    def _crosspoint(self) -> int:
        value = self.next_crosspoint
        self.next_crosspoint += 1
        return value

    def _root(self) -> None:
        self.archive.add(
            "IDEF0/attribute_visual_datas",
            ATTRIBUTE_ID=A_VISUAL_DATA,
            DATA=VISUAL_DATA,
            ELEMENT_ID=ROOT,
            VALUE_BRANCH_ID=0,
        )
        for attribute in (A_REV_DATE, A_SYSTEM_REV_DATE):
            self.archive.add(
                "Core/attribute_dates",
                ATTRIBUTE_ID=attribute,
                ELEMENT_ID=ROOT,
                VALUE=self.date,
                VALUE_BRANCH_ID=0,
            )

    def _functions(self) -> None:
        for diagram in self.document.diagrams:
            owner = ROOT if diagram.kind == "context" else self.functions[diagram.id]
            previous = -1
            for block in diagram.blocks:
                element = self._function(block, owner, previous, diagram.kind == "context")
                self.functions[block.id] = element
                previous = element

    def _function(self, block: ir.Block, owner: int, previous: int, context: bool) -> int:
        element = self._element(Q_FUNCTION)
        decomposed = self.document.diagram(block.id) is not None
        self.archive.add(
            "Core/attribute_texts",
            ATTRIBUTE_ID=A_NAME,
            ELEMENT_ID=element,
            VALUE=block.name,
            VALUE_BRANCH_ID=0,
        )
        self.archive.add(
            "Core/attribute_hierarchicals",
            ATTRIBUTE_ID=A_HIERARCHICAL,
            ELEMENT_ID=element,
            ICON_ID=-1,
            PARENT_ELEMENT_ID=owner,
            PREVIOUS_ELEMENT_ID=previous,
            VALUE_BRANCH_ID=0,
        )
        self.archive.add(
            "IDEF0/attribute_rectangles",
            ATTRIBUTE_ID=A_BOUNDS,
            ELEMENT_ID=element,
            HEIGHT=float(block.h),
            WIDTH=float(block.w),
            X=float(block.x),
            Y=float(block.y),
            VALUE_BRANCH_ID=0,
        )
        self.archive.add(
            "IDEF0/attribute_function_types",
            ATTRIBUTE_ID=A_TYPE,
            ELEMENT_ID=element,
            TYPE=TYPE_CONTEXT if context else TYPE_PLAIN,
            VALUE_BRANCH_ID=0,
        )
        self.archive.add(
            "IDEF0/attribute_colors",
            ATTRIBUTE_ID=A_BACKGROUND,
            COLOR=-1,
            ELEMENT_ID=element,
            VALUE_BRANCH_ID=0,
        )
        self.archive.add(
            "IDEF0/attribute_colors",
            ATTRIBUTE_ID=A_FOREGROUND,
            COLOR=-16777216,
            ELEMENT_ID=element,
            VALUE_BRANCH_ID=0,
        )
        self.archive.add(
            "IDEF0/attribute_fonts",
            ATTRIBUTE_ID=A_FONT,
            ELEMENT_ID=element,
            NAME="Dialog",
            SIZE=10,
            STYLE=0,
            VALUE_BRANCH_ID=0,
        )
        self.archive.add(
            "IDEF0/attribute_statuses",
            ATTRIBUTE_ID=A_STATUS,
            ELEMENT_ID=element,
            OTHER_NAME="",
            TYPE=0,
            VALUE_BRANCH_ID=0,
        )
        self.archive.add(
            "IDEF0/attribute_visual_datas",
            ATTRIBUTE_ID=A_VISUAL_DATA,
            DATA=VISUAL_DATA if decomposed else None,
            ELEMENT_ID=element,
            VALUE_BRANCH_ID=0,
        )
        if context:
            for attribute in (A_CREATE_DATE, A_REV_DATE, A_SYSTEM_REV_DATE):
                self.archive.add(
                    "Core/attribute_dates",
                    ATTRIBUTE_ID=attribute,
                    ELEMENT_ID=element,
                    VALUE=self.date,
                    VALUE_BRANCH_ID=0,
                )
        else:
            self.archive.add(
                "IDEF0/attribute_decomposition_types",
                ATTRIBUTE_ID=A_DECOMPOSITION_TYPE,
                ELEMENT_ID=element,
                TYPE=-1,
                VALUE_BRANCH_ID=0,
            )
        return element

    def _stream(self, name: str) -> int:
        known = self.streams.get(name)
        if known is not None:
            return known
        element = self._element(Q_STREAM)
        self.archive.add(
            "Core/attribute_texts",
            ATTRIBUTE_ID=A_STREAM_NAME,
            ELEMENT_ID=element,
            VALUE=name,
            VALUE_BRANCH_ID=0,
        )
        self.archive.add(
            "Core/attribute_hierarchicals",
            ATTRIBUTE_ID=A_HIERARCHICAL,
            ELEMENT_ID=element,
            ICON_ID=-1,
            PARENT_ELEMENT_ID=-1,
            PREVIOUS_ELEMENT_ID=self.last_stream,
            VALUE_BRANCH_ID=0,
        )
        self.last_stream = element
        self.streams[name] = element
        return element

    def _sectors(self) -> None:
        for diagram in self.document.diagrams:
            owner = ROOT if diagram.kind == "context" else self.functions[diagram.id]
            for arrow in diagram.arrows:
                self._sector(diagram, owner, arrow)

    def _sector(self, diagram: ir.Diagram, owner: int, arrow: ir.Arrow) -> None:
        element = self._element(Q_SECTOR)
        self.archive.add(
            "Core/attribute_other_elements",
            ATTRIBUTE_ID=A_FUNCTION_SECTOR,
            ELEMENT_ID=element,
            OTHER_ELEMENT=owner,
            VALUE_BRANCH_ID=0,
        )
        self.archive.add(
            "Core/attribute_other_elements",
            ATTRIBUTE_ID=A_SECTOR_STREAM,
            ELEMENT_ID=element,
            OTHER_ELEMENT=self._stream(arrow.name),
            VALUE_BRANCH_ID=0,
        )
        self.archive.add(
            "IDEF0/attribute_sectors",
            ALTERNATIVE_TEXT="",
            ATTRIBUTE_ID=A_SECTOR,
            CREATE_POS=0.0,
            CREATE_STATE=-1,
            ELEMENT_ID=element,
            SHOW_TEXT=1 if arrow.label else 0,
            TEXT_ALIGMENT=0,
            VISUAL_ATTRIBUTES=VISUAL_ATTRIBUTES,
            VALUE_BRANCH_ID=0,
        )
        self._border(element, A_BORDER_START, diagram, arrow, arrow.src, arrow.points[0])
        self._border(element, A_BORDER_END, diagram, arrow, arrow.dst, arrow.points[-1])
        self._points(element, arrow.points)
        self._properties(element, arrow)

    def _border(
        self,
        element: int,
        attribute: int,
        diagram: ir.Diagram,
        arrow: ir.Arrow,
        endpoint: ir.Endpoint,
        point: ir.Point,
    ) -> None:
        start = attribute == A_BORDER_START
        tunnelled = arrow.tunnel in (("source", "both") if start else ("dest", "both"))
        if endpoint.kind == "port":
            role = ROLE_BY_SIDE[endpoint.side or "right"]
            crosspoint = self._link(endpoint.block or "", role, arrow.name, outer=True)
            self.archive.add(
                "IDEF0/attribute_sector_borders",
                ATTRIBUTE_ID=attribute,
                BORDER_TYPE=-1,
                CROSSPOINT=crosspoint,
                ELEMENT_ID=element,
                FUNCTION=self.functions[endpoint.block or ""],
                FUNCTION_TYPE=FUNCTION_SIDE[role],
                TUNNEL_SOFT=1 if tunnelled else 0,
                VALUE_BRANCH_ID=0,
            )
            return
        if diagram.kind == "context":
            crosspoint = self._crosspoint()
        else:
            crosspoint = self._link(diagram.id, arrow.role, arrow.name, outer=False)
        self.archive.add(
            "IDEF0/attribute_sector_borders",
            ATTRIBUTE_ID=attribute,
            BORDER_TYPE=_frame_side(point),
            CROSSPOINT=crosspoint,
            ELEMENT_ID=element,
            FUNCTION=-1,
            FUNCTION_TYPE=-1,
            TUNNEL_SOFT=1 if tunnelled else 0,
            VALUE_BRANCH_ID=0,
        )

    def _link(self, block_id: str, role: str, name: str, outer: bool) -> int:
        key = (block_id, role, name)
        used = self.linked_outer if outer else self.linked_inner
        if key in used:
            return self._crosspoint()
        used.add(key)
        known = self.links.get(key)
        if known is None:
            known = self._crosspoint()
            self.links[key] = known
        return known

    def _points(self, element: int, points: list[ir.Point]) -> None:
        horizontals: dict[int, int] = {}
        verticals: dict[int, int] = {}
        for position, (x, y) in enumerate(points):
            if x not in horizontals:
                horizontals[x] = self._ordinate()
            if y not in verticals:
                verticals[y] = self._ordinate()
            self.archive.add(
                "IDEF0/attribute_sector_points",
                ATTRIBUTE_ID=A_SECTOR_POINTS,
                ELEMENT_ID=element,
                POINT_TYPE=_point_type(x, y),
                POSITION=position,
                X_ORDINATE_ID=horizontals[x],
                X_POSITION=float(x),
                Y_ORDINATE_ID=verticals[y],
                Y_POSITION=float(y),
                VALUE_BRANCH_ID=0,
            )

    def _properties(self, element: int, arrow: ir.Arrow) -> None:
        if arrow.label is None:
            self.archive.add(
                "IDEF0/attribute_sector_properties",
                ATTRIBUTE_ID=A_SECTOR_PROPERTIES,
                ELEMENT_ID=element,
                SHOW_TEXT=0,
                SHOW_TILDA=0,
                TEXT_HIEGHT=0.0,
                TEXT_WIDTH=0.0,
                TEXT_X=0.0,
                TEXT_Y=0.0,
                TILDA_POS=0.0,
                TRANSPARENT=0,
                VALUE_BRANCH_ID=0,
            )
            return
        width = len(arrow.name) * TEXT_CHAR_WIDTH
        self.archive.add(
            "IDEF0/attribute_sector_properties",
            ATTRIBUTE_ID=A_SECTOR_PROPERTIES,
            ELEMENT_ID=element,
            SHOW_TEXT=1,
            SHOW_TILDA=1,
            TEXT_HIEGHT=TEXT_LINE_HEIGHT,
            TEXT_WIDTH=width,
            TEXT_X=arrow.label.x - width / 2,
            TEXT_Y=arrow.label.y - TEXT_LINE_HEIGHT,
            TILDA_POS=0.5,
            TRANSPARENT=1,
            VALUE_BRANCH_ID=0,
        )

    def _preferences(self) -> None:
        table = self.archive.table("IDEF0/attribute_model_preferences")
        if not table.rows:
            table.add(
                ATTRIBUTE_ID=A_MODEL_PREFERENCES,
                ELEMENT_ID=ROOT,
                DIAGRAM_SIZE="A4",
                VALUE_BRANCH_ID=0,
            )
        row = table.rows[0]
        row[table.column_id("CHANGE_DATE")] = self.date
        row[table.column_id("CREATE_DATE")] = self.date
        row[table.column_id("PROJECT_NAME")] = self.document.model.name
        row[table.column_id("PROJECT_AUTOR")] = self.document.model.author or ""
        row[table.column_id("DEFINITION")] = self.document.model.purpose or None
        row[table.column_id("USED_AT")] = self.document.model.viewpoint or None

    def _sequences(self) -> None:
        name = "data/sequences.xml"
        text = self.archive.blobs[name].decode("utf-8")
        text = re.sub(r'(?<="ordinates__sequence">)\d+', str(self.next_ordinate), text)
        text = re.sub(r'(?<="crosspoint_sequence">)\d+', str(self.next_crosspoint), text)
        self.archive.blobs[name] = text.encode("utf-8")

    def _session(self) -> None:
        name = "user/gui/session.binary"
        blob = self.archive.blobs.get(name)
        context = next(
            (
                self.functions[block.id]
                for diagram in self.document.diagrams
                if diagram.kind == "context"
                for block in diagram.blocks
            ),
            None,
        )
        if blob is None or context is None:
            return
        at = blob.find(QUALIFIER_MARKER)
        if at < 8:
            return
        self.archive.blobs[name] = blob[: at - 8] + context.to_bytes(8, "big") + blob[at:]


def _frame_side(point: ir.Point) -> int:
    x, y = point
    if x <= AREA_LEFT:
        return FRAME_LEFT
    if x >= AREA_RIGHT:
        return FRAME_RIGHT
    if y <= AREA_TOP:
        return FRAME_TOP
    return FRAME_BOTTOM


def _point_type(x: int, y: int) -> int:
    if x in (AREA_LEFT, AREA_RIGHT):
        return POINT_ON_VERTICAL
    if y in (AREA_TOP, AREA_BOTTOM):
        return POINT_ON_HORIZONTAL
    return POINT_FREE
