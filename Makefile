.PHONY: test lint check health freeze-dry

test:
	python -m pytest -q
lint:
	python -m ruff check src tests scripts
check: lint test
health:
	python -m goldintel health
freeze-dry:
	python scripts/freeze_sources.py --dry-run
