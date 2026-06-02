PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
SRC := src
TESTS := tests
COVERAGE := $(PYTHON) -m coverage

.PHONY: all install install-dev install-live editable test unit features live lint type format coverage clean help

help:
	@echo "Symphony-py development makefile"
	@echo ""
	@echo "Targets:"
	@echo "  install       Install the package + runtime deps into the active environment"
	@echo "  install-dev   Add dev deps (pytest, mypy, ruff, pytest-bdd, ...)"
	@echo "  install-live  Add live-e2e deps (ghapi)"
	@echo "  editable      Install in editable mode (development install)"
	@echo "  format        Run ruff format"
	@echo "  lint          Run ruff check"
	@echo "  type          Run mypy --strict"
	@echo "  test          Run unit + BDD feature tests"
	@echo "  unit          Run unit tests only"
	@echo "  features      Run BDD feature tests only"
	@echo "  live          Run live e2e tests (requires SYMPHONY_RUN_LIVE_E2E=1)"
	@echo "  coverage      Run tests with coverage report"
	@echo "  all           format + lint + type + test + coverage (the conformance gate)"
	@echo "  clean         Remove build artifacts"

install:
	$(PIP) install .

install-dev: install
	$(PIP) install .[dev]

install-live: install
	$(PIP) install .[live]

editable:
	$(PIP) install -e .[dev]

format:
	$(PYTHON) -m ruff format $(SRC) $(TESTS)

lint:
	$(PYTHON) -m ruff check $(SRC) $(TESTS)

type:
	$(PYTHON) -m mypy --strict $(SRC)

unit:
	$(PYTHON) -m pytest $(TESTS)/unit

features:
	$(PYTHON) -m pytest $(TESTS)/steps $(TESTS)/features

test: unit features

live:
	SYMPHONY_RUN_LIVE_E2E=1 $(PYTHON) -m pytest $(TESTS)/live

coverage:
	$(COVERAGE) run -m pytest $(TESTS)
	$(COVERAGE) report

all: format lint type test coverage

clean:
	rm -rf build dist .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name '*.egg-info' -prune -exec rm -rf {} +
