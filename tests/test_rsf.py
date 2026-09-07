import collections
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from conftest import GOLDEN, keep, represent
from idefy import write_rsf
from idefy.rsf import tables

MOMENT = datetime(2026, 9, 7, 19, 51)
GOLDEN_CASES = ["context_only", "valid", "feedback6", "two_levels"]
TEMPLATE = write_rsf.template_path()


def built(fixture: str, tmp_path: Path) -> Path:
    return write_rsf.build(represent(fixture), tmp_path / f"{fixture}.rsf", MOMENT)


def contents(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_repacking_the_template_is_byte_identical():
    archive = tables.read(TEMPLATE)
    with zipfile.ZipFile(TEMPLATE) as original:
        for name, table in archive.tables.items():
            assert tables.render(table) == original.read(name), name


def test_template_has_no_type_violations():
    assert tables.check_types(tables.read(TEMPLATE)) == []


def test_null_is_an_absent_tag_not_an_empty_one():
    table = tables.Table(
        attrib={"prefix": "ramus_"},
        columns=[tables.Column("0", "A", "BIGINT"), tables.Column("1", "B", "CLOB")],
    )
    table.add(A=1, B=None)
    rendered = tables.render(table).decode("utf-8")
    assert '<f id="0">1</f><f id="1"/>' in rendered


def test_empty_table_renders_self_closing_data():
    table = tables.Table(attrib={}, columns=[tables.Column("0", "A", "BIGINT")])
    assert b"<data/>" in tables.render(table)


def test_check_types_catches_empty_numeric():
    archive = tables.read(TEMPLATE)
    table = archive.table("Core/attribute_longs")
    table.rows[0][table.column_id("VALUE")] = ""
    assert any("пустое числовое" in problem for problem in tables.check_types(archive))


@pytest.mark.parametrize("fixture", GOLDEN_CASES)
def test_built_file_has_no_type_violations(fixture, tmp_path):
    assert tables.check_types(tables.read(built(fixture, tmp_path))) == []


@pytest.mark.parametrize("fixture", GOLDEN_CASES)
def test_matches_golden(fixture, tmp_path):
    produced = built(fixture, tmp_path)
    keep(f"{fixture}.rsf", produced.read_bytes())
    assert contents(produced) == contents(GOLDEN / f"{fixture}.rsf")


def test_build_is_deterministic(tmp_path):
    first = write_rsf.build(represent("valid"), tmp_path / "a.rsf", MOMENT)
    second = write_rsf.build(represent("valid"), tmp_path / "b.rsf", MOMENT)
    assert first.read_bytes() == second.read_bytes()


def test_every_reference_points_at_a_live_element(tmp_path):
    archive = tables.read(built("feedback6", tmp_path))
    elements = archive.table("elements")
    known = {row[elements.column_id("ELEMENT_ID")] for row in elements.rows}
    known |= {"0", "-1", str(write_rsf.ROOT)}
    for name, table in archive.tables.items():
        for column in table.columns:
            if column.name not in ("PARENT_ELEMENT_ID", "OTHER_ELEMENT", "FUNCTION"):
                continue
            for row in table.rows:
                value = row.get(column.id)
                assert value is None or value in known, f"{name}.{column.name}={value}"


def test_functions_form_a_chain(tmp_path):
    archive = tables.read(built("valid", tmp_path))
    hierarchy = archive.table("Core/attribute_hierarchicals")
    parent = hierarchy.column_id("PARENT_ELEMENT_ID")
    previous = hierarchy.column_id("PREVIOUS_ELEMENT_ID")
    children = [row for row in hierarchy.rows if row.get(parent) == "5"]
    assert [row[previous] for row in children] == ["-1", "6", "7"]


def test_context_function_is_typed_as_context(tmp_path):
    archive = tables.read(built("valid", tmp_path))
    types = archive.table("IDEF0/attribute_function_types")
    element = types.column_id("ELEMENT_ID")
    kind = types.column_id("TYPE")
    by_element = {row[element]: row[kind] for row in types.rows}
    assert by_element["5"] == str(write_rsf.TYPE_CONTEXT)
    assert set(by_element.values()) - {str(write_rsf.TYPE_CONTEXT)} == {str(write_rsf.TYPE_PLAIN)}


def test_boundary_arrow_shares_the_crosspoint_with_the_parent(tmp_path):
    archive = tables.read(built("valid", tmp_path))
    borders = archive.table("IDEF0/attribute_sector_borders")
    crosspoint = borders.column_id("CROSSPOINT")
    function = borders.column_id("FUNCTION")
    at_context = {row[crosspoint] for row in borders.rows if row.get(function) == "5"}
    at_frame = {row[crosspoint] for row in borders.rows if row.get(function) == "-1"}
    assert at_context & at_frame


def test_tunnel_is_written_on_the_marked_end(tmp_path):
    archive = tables.read(built("tunnel", tmp_path))
    borders = archive.table("IDEF0/attribute_sector_borders")
    tunnel = borders.column_id("TUNNEL_SOFT")
    assert sum(row[tunnel] == "1" for row in borders.rows) == 2


def test_icom_is_linked_on_every_level(tmp_path):
    archive = tables.read(built("two_levels", tmp_path))
    borders = archive.table("IDEF0/attribute_sector_borders")
    crosspoint = borders.column_id("CROSSPOINT")
    function = borders.column_id("FUNCTION")
    at_block = collections.defaultdict(set)
    at_frame = set()
    for row in borders.rows:
        if row[function] == "-1":
            at_frame.add(row[crosspoint])
        else:
            at_block[row[function]].add(row[crosspoint])
    assert len(at_block["5"] & at_frame) == 4
    assert len(at_block["6"] & at_frame) == 4


def test_session_points_at_the_context_function(tmp_path):
    archive = tables.read(built("valid", tmp_path))
    blob = archive.blobs["user/gui/session.binary"]
    at = blob.find(write_rsf.QUALIFIER_MARKER)
    assert int.from_bytes(blob[at - 8 : at], "big") == 5


def test_sequences_are_advanced(tmp_path):
    archive = tables.read(built("valid", tmp_path))
    text = archive.blobs["data/sequences.xml"].decode("utf-8")
    assert '<entry key="ordinates__sequence">1</entry>' not in text
    assert '<entry key="crosspoint_sequence">1</entry>' not in text


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (datetime(2026, 9, 7, 19, 51), "9/7/26, 7:51 PM"),
        (datetime(2025, 9, 20, 5, 38), "9/20/25, 5:38 AM"),
        (datetime(2025, 1, 2, 0, 5), "1/2/25, 12:05 AM"),
        (datetime(2025, 1, 2, 12, 0), "1/2/25, 12:00 PM"),
    ],
)
def test_java_moment(moment, expected):
    assert write_rsf.java_moment(moment) == expected


def test_dates_use_the_narrow_space(tmp_path):
    archive = tables.read(built("valid", tmp_path))
    dates = archive.table("Core/attribute_dates")
    value = dates.column_id("VALUE")
    assert dates.rows
    assert all("\u202f" in (row[value] or "") for row in dates.rows)
