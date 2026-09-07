# idefy

Генератор IDEF0-моделей из декларативного YAML: валидация нотации, автораскладка,
превью в SVG/PNG и сборка нативного файла Ramus (`.rsf`).

Модель — это файл в вашем репозитории. Картинки и `.rsf` — производные артефакты.
Java и сам Ramus для сборки не нужны: `.rsf` пишется напрямую.

Документация: <https://trum-ok.github.io/idefy/>

## Установка

```bash
uv tool install git+https://github.com/Trum-ok/idefy
```

PNG-превью требует дополнительной зависимости:

```bash
uv tool install "idefy[png] @ git+https://github.com/Trum-ok/idefy"
```

Нужен Python 3.12 или новее.

## Быстрый старт

```bash
idefy init model.yaml
idefy validate model.yaml
idefy preview model.yaml
idefy build model.yaml
```

Модель выглядит так:

```yaml
version: 1

model:
  name: "Обработка заявки на кредит"
  author: "Аркадий Артамонов"
  purpose: "Описать порядок обработки заявки для последующей автоматизации"
  viewpoint: "Кредитный аналитик"

activities:
  - id: A0
    name: "Обработать заявку"
    input: [ "Заявка клиента" ]
    control: [ "Кредитная политика" ]
    output: [ "Решение по заявке" ]
    mechanism: [ "Кредитный аналитик" ]

  - id: A1
    name: "Проверить полноту документов"
    input: [ "Заявка клиента" ]
    control: [ "Кредитная политика" ]
    output: [ "Проверенная заявка" ]
    mechanism: [ "Кредитный аналитик" ]

  - id: A2
    name: "Принять решение"
    input: [ "Проверенная заявка" ]
    control: [ "Кредитная политика" ]
    output: [ "Решение по заявке" ]
    mechanism: [ "Кредитный аналитик" ]
```

Стрелки не объявляются: они выводятся сопоставлением имён в ICOM-списках соседей
и родителя. Идентификаторы иерархические — родитель `A11` выводится из имени.

Полный [справочник по языку](https://trum-ok.github.io/idefy/dsl/),
[команды и коды возврата](https://trum-ok.github.io/idefy/cli/),
[памятка по нотации](https://trum-ok.github.io/idefy/idef0/).

## Работа с Claude Code

`skill/SKILL.md` — готовый скилл: положите его в `.claude/skills/idef0/SKILL.md`
своего проекта, и агент будет писать модели, смотреть превью и чинить замечания
сам.

## Разработка

```bash
uv sync
make check
make docs
```

`make check` — это `ruff`, `ty` и `pytest`. Сеть в тестах не используется.

## Лицензия

MIT, см. [LICENSE](LICENSE). Ramus не используется как библиотека: `idefy` читает
и пишет файл данных, а не линкуется с программой.
