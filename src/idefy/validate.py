from __future__ import annotations

from collections import Counter

from idefy.diagnostics import Diagnostic, error, sort_key, warning
from idefy.dsl import (
    INCOMING_ROLES,
    ROLE_TITLES,
    Model,
    Role,
    id_key,
    parent_id,
    starts_with_infinitive,
)
from idefy.parse import Resolution

MAX_BLOCKS = 8
RECOMMENDED_BLOCKS = range(3, 7)
MAX_ICOM_WITHOUT_DECOMPOSITION = 5
MAX_FEEDBACK_SPAN = 2


def check(model: Model, resolution: Resolution) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = list(resolution.diagnostics)
    diagnostics.extend(_check_ids(model, resolution))
    diagnostics.extend(_check_activities(resolution))
    diagnostics.extend(_check_diagrams(resolution))
    diagnostics.extend(_check_model_meta(model))
    diagnostics.sort(key=sort_key)
    return diagnostics


def has_errors(diagnostics: list[Diagnostic]) -> bool:
    return any(diagnostic.level == "error" for diagnostic in diagnostics)


def _check_ids(model: Model, resolution: Resolution) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    counts = Counter(activity.id for activity in model.activities)
    for activity_id in sorted((i for i, n in counts.items() if n > 1), key=id_key):
        diagnostics.append(
            error("E001", activity_id, f"Идентификатор {activity_id} встречается несколько раз")
        )

    for activity in sorted(model.activities, key=lambda a: id_key(a.id)):
        parent = parent_id(activity.id)
        if parent is not None and parent not in resolution.index:
            diagnostics.append(
                error(
                    "E002",
                    activity.id,
                    f"Нет родительской функции {parent} для {activity.id}",
                    f"добавьте функцию {parent} или переименуйте {activity.id}",
                )
            )

    roots = resolution.roots
    if not any(activity.id == "A0" for activity in roots):
        diagnostics.append(
            error(
                "E009",
                "<модель>",
                "Отсутствует контекстная функция A0",
                "у модели должна быть ровно одна функция верхнего уровня с id A0",
            )
        )
    if len(roots) > 1:
        listed = ", ".join(activity.id for activity in roots)
        diagnostics.append(
            error(
                "E010",
                "<модель>",
                f"В модели больше одной контекстной диаграммы: {listed}",
                "оставьте одну функцию верхнего уровня",
            )
        )
    return diagnostics


def _check_activities(resolution: Resolution) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for activity in sorted(resolution.index.values(), key=lambda a: id_key(a.id)):
        if not activity.output:
            diagnostics.append(
                error(
                    "E003",
                    activity.id,
                    f"У функции {activity.id} нет ни одного выхода",
                    "функция без выхода не производит результата",
                )
            )
        if not activity.control:
            diagnostics.append(
                error(
                    "E004",
                    activity.id,
                    f"У функции {activity.id} нет ни одного управления",
                    "укажите правило, регламент или условие, задающее выполнение функции",
                )
            )
        for role in INCOMING_ROLES:
            for position, name in enumerate(activity.names(role)):
                if name in activity.output:
                    diagnostics.append(
                        error(
                            "E008",
                            f"{activity.id}.{role}[{position}]",
                            f"«{name}» стоит и в выходе, и в {ROLE_TITLES[role]} функции {activity.id}",
                            "петля на себя в IDEF0 не рисуется: разведите имена "
                            "или вынесите итерацию в декомпозицию",
                        )
                    )
        if not starts_with_infinitive(activity.name):
            diagnostics.append(
                warning(
                    "W003",
                    activity.id,
                    f"Имя «{activity.name}» не начинается с глагола в неопределённой форме",
                    "IDEF0 требует имени-действия: «Обработать заявку», а не «Обработка заявки»",
                )
            )
        undecomposed = activity.id not in resolution.children
        if undecomposed and activity.icom_count() > MAX_ICOM_WITHOUT_DECOMPOSITION:
            diagnostics.append(
                warning(
                    "W004",
                    activity.id,
                    f"У функции {activity.id} {activity.icom_count()} стрелок, "
                    "но она не декомпозирована",
                    "такой блок обычно скрывает несколько функций",
                )
            )
    diagnostics.extend(_check_role_conflicts(resolution))
    return diagnostics


def _check_role_conflicts(resolution: Resolution) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for owner_id in sorted(resolution.children, key=id_key):
        roles: dict[str, set[Role]] = {}
        for block in resolution.children[owner_id]:
            for role in INCOMING_ROLES:
                for name in block.names(role):
                    roles.setdefault(name, set()).add(role)
        for name in sorted(name for name, used in roles.items() if len(used) > 1):
            listed = ", ".join(ROLE_TITLES[role] for role in sorted(roles[name]))
            diagnostics.append(
                warning(
                    "W006",
                    f"{owner_id}/{name}",
                    f"«{name}» потребляется в разных ролях: {listed}",
                    "одна сущность обычно играет одну роль; проверьте, не разные ли это потоки",
                )
            )
    return diagnostics


def _check_diagrams(resolution: Resolution) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for owner_id in sorted(resolution.children, key=id_key):
        blocks = resolution.children[owner_id]
        count = len(blocks)
        if count > MAX_BLOCKS:
            diagnostics.append(
                error(
                    "E005",
                    owner_id,
                    f"В декомпозиции {owner_id} {count} блоков, максимум {MAX_BLOCKS}",
                    "разбейте уровень на два",
                )
            )
        elif count not in RECOMMENDED_BLOCKS:
            diagnostics.append(
                warning(
                    "W001",
                    owner_id,
                    f"В декомпозиции {owner_id} {count} блоков, рекомендуется 3–6",
                )
            )

    order = {}
    for diagram in resolution.diagrams:
        for position, block in enumerate(diagram.blocks):
            order[block.id] = position
    for diagram in resolution.diagrams:
        for arrow in diagram.arrows:
            if arrow.src.block is None or arrow.dst.block is None:
                continue
            source = order[arrow.src.block]
            target = order[arrow.dst.block]
            if source - target > MAX_FEEDBACK_SPAN:
                diagnostics.append(
                    warning(
                        "W005",
                        f"{diagram.id}/{arrow.name}",
                        f"Обратная связь «{arrow.name}» из {arrow.src.block} в {arrow.dst.block} "
                        f"пересекает {source - target - 1} блока",
                        "такая стрелка загромождает диаграмму: подумайте о промежуточном блоке",
                    )
                )
    return diagnostics


def _check_model_meta(model: Model) -> list[Diagnostic]:
    missing = [
        title
        for field_name, title in (("purpose", "purpose"), ("viewpoint", "viewpoint"))
        if not (getattr(model.model, field_name) or "").strip()
    ]
    if not missing:
        return []
    return [
        warning(
            "W002",
            "model",
            f"Не заполнено: {', '.join(missing)}",
            "цель и точка зрения задают границы модели, без них декомпозиция расползается",
        )
    ]
