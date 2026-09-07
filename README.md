# idefy

Генератор IDEF0-моделей из декларативного YAML: валидация нотации, автораскладка,
превью в SVG/PNG и сборка нативного файла Ramus (`.rsf`).

Модель — это файл в вашем репозитории. Картинки и `.rsf` — производные артефакты.

## Установка

```bash
uv tool install git+https://github.com/Trum-ok/idefy
```

Или в проект:

```bash
uv add git+https://github.com/Trum-ok/idefy
```

PNG-превью требует дополнительной зависимости:

```bash
uv tool install "idefy[png] @ git+https://github.com/Trum-ok/idefy"
```

Нужен Python 3.12+. Java и сам Ramus для сборки `.rsf` не нужны — файл пишется
напрямую. Ramus нужен только чтобы открыть результат.

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

## Команды

| Команда                            | Что делает                              |
|------------------------------------|-----------------------------------------|
| `idefy init [PATH]`                | создать `model.yaml` из шаблона         |
| `idefy validate MODEL`             | проверить нотацию                       |
| `idefy preview MODEL [-o DIR]`     | нарисовать диаграммы в SVG или PNG      |
| `idefy build MODEL [-o FILE.rsf]`  | собрать файл Ramus                      |
| `idefy open FILE.rsf`              | открыть файл в Ramus                    |
| `idefy schema [-o FILE]`           | выгрузить JSON Schema языка             |
| `idefy doctor`                     | проверить шаблон `.rsf` и путь к Ramus  |

Все команды понимают `--json` для машинного вывода и `-q` для тишины.

Коды возврата: `0` успех, `1` ошибки валидации, `2` ошибка использования,
`3` проблема окружения.

## Конфигурация

Путь к Ramus нужен только команде `idefy open`. Приоритет источников:
флаг `--ramus`, переменная `IDEFY_RAMUS_PATH`, файл конфигурации, автопоиск.

```toml
# ~/.config/idefy/config.toml
ramus = "/Applications/Ramus.app"
```

`idefy doctor` покажет, что откуда взялось.

## Работа с Claude Code

`skill/SKILL.md` — готовый скилл: положите его в `.claude/skills/idef0/SKILL.md`
своего проекта, и агент будет писать модели, смотреть превью и чинить замечания
сам.

## Разработка

```bash
uv sync
make check
```

`make check` — это `ruff`, `ty` и `pytest`. Сеть в тестах не используется.

## Лицензия

MIT, см. [LICENSE](LICENSE). Ramus не используется как библиотека: `idefy` читает
и пишет файл данных, а не линкуется с программой.
