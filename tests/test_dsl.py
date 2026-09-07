import pytest

from idefy.dsl import Activity, id_key, parent_id, starts_with_infinitive


@pytest.mark.parametrize(
    ("activity_id", "expected"),
    [("A0", None), ("A1", "A0"), ("A12", "A1"), ("A123", "A12"), ("B0", None), ("B3", "B0")],
)
def test_parent_id(activity_id, expected):
    assert parent_id(activity_id) == expected


def test_id_key_orders_by_depth_then_number():
    ids = ["A2", "A11", "A1", "A0", "A12"]
    assert sorted(ids, key=id_key) == ["A0", "A1", "A2", "A11", "A12"]


@pytest.mark.parametrize("name", ["Обработать заявку", "Принять решение", "Испечь хлеб"])
def test_infinitive_accepted(name):
    assert starts_with_infinitive(name)


@pytest.mark.parametrize("name", ["Обработка заявки", "Решение по заявке"])
def test_noun_rejected(name):
    assert not starts_with_infinitive(name)


@pytest.mark.parametrize("bad", ["0A", "A", "a1", "A-1", "A 1"])
def test_bad_id_rejected(bad):
    with pytest.raises(ValueError, match="идентификатор"):
        Activity(id=bad, name="Сделать")


def test_names_are_stripped_and_deduplicated():
    activity = Activity(id="A0", name=" Сделать ", output=[" Итог ", "Итог"])
    assert activity.name == "Сделать"
    assert activity.output == ["Итог"]


def test_empty_arrow_name_rejected():
    with pytest.raises(ValueError, match="не может быть пустым"):
        Activity(id="A0", name="Сделать", output=["  "])
