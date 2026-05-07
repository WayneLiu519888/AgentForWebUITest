.PHONY: install test lint clean build check

install:
	pip install -e ".[dev]"

test:
	cd /root/AgentForWebUITest && python3 -m pytest tests/ -q --tb=line

test-v:
	cd /root/AgentForWebUITest && python3 -m pytest tests/ -v

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf dist/ build/ *.egg-info

build:
	python3 -m build

check:
	python3 -c "from src.cli import cmd_check; cmd_check()"

check-all: lint test
	@echo "✅ All checks passed"
