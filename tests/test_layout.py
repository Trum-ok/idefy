from itertools import pairwise

import pytest

from conftest import represent
from idefy import layout
from idefy.dsl import Activity


def blocks(count: int):
    activities = [
        Activity(
            id=f"A{index}", name=f"Шаг {index}", control=["Регламент"], output=[f"Итог {index}"]
        )
        for index in range(1, count + 1)
    ]
    return layout.place_blocks(activities)


@pytest.mark.parametrize("count", range(1, 9))
def test_blocks_stay_inside_working_area(count):
    for block in blocks(count):
        assert block.x >= layout.AREA_LEFT
        assert block.y >= layout.AREA_TOP
        assert block.right <= layout.AREA_RIGHT
        assert block.bottom <= layout.AREA_BOTTOM


@pytest.mark.parametrize("count", range(2, 9))
def test_neighbours_keep_the_minimal_gap(count):
    placed = blocks(count)
    for first, second in pairwise(placed):
        assert second.x - first.right >= layout.MIN_BLOCK_GAP
        assert second.y - first.bottom >= layout.MIN_BLOCK_GAP


def test_single_block_is_centred():
    block = blocks(1)[0]
    assert block.x + block.w // 2 == layout.AREA_LEFT + layout.AREA_W // 2
    assert block.y + block.h // 2 == layout.AREA_TOP + layout.AREA_H // 2


def test_block_order_follows_id_not_file_order():
    ids = [block.id for block in represent("valid").diagrams[1].blocks]
    assert ids == ["A1", "A2", "A3"]


def test_points_are_orthogonal():
    for diagram in represent("feedback6").diagrams:
        for arrow in diagram.arrows:
            for first, second in pairwise(arrow.points):
                assert first[0] == second[0] or first[1] == second[1]


def test_fork_branches_share_the_trunk():
    diagram = represent("valid").diagram("A0")
    assert diagram is not None
    branches = [a.points for a in diagram.arrows if a.name == "Регламент"]
    assert len(branches) == 3
    assert len({points[0] for points in branches}) == 1


def test_fork_gets_one_icom_code():
    diagram = represent("valid").diagram("A0")
    assert diagram is not None
    control = [a.src.icom for a in diagram.arrows if a.name == "Регламент"]
    assert set(control) == {"C1"}


def test_boundary_codes_are_numbered_along_the_frame():
    diagram = represent("context_only").diagram("A-0")
    assert diagram is not None
    outputs = sorted(
        ((a.points[-1][1], a.dst.icom) for a in diagram.arrows if a.role == "output"),
    )
    assert [code for _, code in outputs] == ["O1", "O2"]


def test_one_label_per_arrow_name():
    diagram = represent("valid").diagram("A0")
    assert diagram is not None
    labelled = [a.name for a in diagram.arrows if a.label is not None]
    assert len(labelled) == len(set(labelled))


def test_layout_is_deterministic():
    assert represent("feedback6").as_dict() == represent("feedback6").as_dict()
