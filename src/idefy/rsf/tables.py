from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

HEADER = b'<?xml version="1.0" encoding="UTF-8"?>'
NUMERIC = frozenset({"BIGINT", "INTEGER", "DOUBLE", "BOOLEAN"})
TABLE_MARKER = b"<table"


@dataclass(frozen=True, slots=True)
class Column:
    id: str
    name: str
    type: str


@dataclass(slots=True)
class Table:
    attrib: dict[str, str]
    columns: list[Column]
    rows: list[dict[str, str | None]] = field(default_factory=list)

    def column_id(self, name: str) -> str:
        for column in self.columns:
            if column.name == name:
                return column.id
        raise KeyError(name)

    def add(self, **values: Any) -> None:
        row: dict[str, str | None] = {}
        for name, value in values.items():
            row[self.column_id(name)] = None if value is None else str(value)
        self.rows.append(row)

    def keep(self, column: str, allowed: set[str]) -> None:
        key = self.column_id(column)
        self.rows = [row for row in self.rows if row.get(key) in allowed]


@dataclass(slots=True)
class Archive:
    entries: list[zipfile.ZipInfo]
    tables: dict[str, Table]
    blobs: dict[str, bytes]

    def table(self, name: str) -> Table:
        return self.tables[f"data/{name}.xml"]

    def add(self, name: str, **values: Any) -> None:
        self.table(name).add(**values)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for entry in self.entries:
                table = self.tables.get(entry.filename)
                data = render(table) if table is not None else self.blobs[entry.filename]
                archive.writestr(entry, data)


def read(path: Path) -> Archive:
    entries: list[zipfile.ZipInfo] = []
    tables: dict[str, Table] = {}
    blobs: dict[str, bytes] = {}
    with zipfile.ZipFile(path) as archive:
        for entry in archive.infolist():
            entries.append(entry)
            data = archive.read(entry.filename)
            if entry.filename.endswith(".xml") and TABLE_MARKER in data[:200]:
                tables[entry.filename] = parse(data)
            else:
                blobs[entry.filename] = data
    return Archive(entries=entries, tables=tables, blobs=blobs)


def parse(data: bytes) -> Table:
    root = ET.fromstring(data)
    columns = [
        Column(id=node.get("id", ""), name=node.get("name", ""), type=node.get("type", ""))
        for node in root.iter("field")
    ]
    rows = [{cell.get("id", ""): cell.text for cell in row.iter("f")} for row in root.iter("row")]
    return Table(attrib=dict(root.attrib), columns=columns, rows=rows)


def render(table: Table) -> bytes:
    parts = [HEADER.decode("utf-8"), "<table"]
    for name, value in table.attrib.items():
        parts.append(f" {name}={quoteattr(value)}")
    parts.append("><fields>")
    for column in table.columns:
        parts.append(
            f'<field id="{column.id}" name={quoteattr(column.name)} type="{column.type}"/>'
        )
    parts.append("</fields>")
    if not table.rows:
        parts.append("<data/>")
    else:
        parts.append("<data>")
        for row in table.rows:
            parts.append("<row>")
            for column in table.columns:
                if column.id not in row:
                    continue
                value = row[column.id]
                if value is None:
                    parts.append(f'<f id="{column.id}"/>')
                else:
                    parts.append(f'<f id="{column.id}">{escape(value)}</f>')
            parts.append("</row>")
        parts.append("</data>")
    parts.append("</table>")
    return "".join(parts).encode("utf-8")


def check_types(archive: Archive) -> list[str]:
    problems: list[str] = []
    for name, table in archive.tables.items():
        types = {column.id: (column.name, column.type) for column in table.columns}
        for position, row in enumerate(table.rows):
            for column_id, value in row.items():
                column_name, column_type = types[column_id]
                if column_type not in NUMERIC:
                    continue
                if value is None or value == "":
                    problems.append(f"{name}[{position}].{column_name}: пустое числовое значение")
                elif not _is_number(value, column_type):
                    problems.append(f"{name}[{position}].{column_name}: «{value}» не {column_type}")
    return problems


def _is_number(value: str, column_type: str) -> bool:
    try:
        if column_type == "DOUBLE":
            float(value)
        elif column_type == "BOOLEAN":
            return value in ("TRUE", "FALSE", "true", "false", "0", "1")
        else:
            int(value)
    except ValueError:
        return False
    return True
