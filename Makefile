.PHONY: lint format test coverage check docs docs-serve

package ?= src tests

lint:
	uv run ruff check $(package)
	uv run ruff format --check $(package)
	uv run ty check $(package)

format:
	uv run ruff check --fix $(package)
	uv run ruff format $(package)

test:
	uv run pytest

coverage:
	uv run pytest --cov --cov-report=term-missing --cov-report=html

check: lint test

docs:
	uv run --group docs properdocs build --strict -f mkdocs.yml

docs-serve:
	uv run --group docs properdocs serve -f mkdocs.yml
