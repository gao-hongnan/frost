.DEFAULT_GOAL := help

PACKAGE_NAME := frost
TEST_DIR := tests
SOURCES := $(PACKAGE_NAME) $(TEST_DIR)

.PHONY: .uv
.uv:
	@uv -V || echo 'Please install uv: https://docs.astral.sh/uv/getting-started/installation/'

.PHONY: install
install: .uv
	uv sync --frozen --group all --all-extras

.PHONY: format
format: .uv
	uv run ruff check --fix --exit-zero $(SOURCES)
	uv run ruff format $(SOURCES)

.PHONY: lint
lint: .uv
	uv run ruff check $(SOURCES)
	uv run ruff format --check $(SOURCES)

.PHONY: typecheck
typecheck: .uv
	uv run mypy $(SOURCES)
	uv run pyright $(SOURCES)
	# @echo "Running ty (experimental)..."
	# uv run ty check $(SOURCES) || echo "ty check failed (expected for pre-release)"

.PHONY: test
test: .uv
	uv run pytest $(TEST_DIR)

.PHONY: coverage
coverage: .uv
	uv run coverage run -m pytest $(TEST_DIR)
	uv run coverage report
	uv run coverage html
	uv run coverage xml

.PHONY: docs
docs:
	cd docs && make html

.PHONY: ci
ci: format lint typecheck test coverage

.PHONY: lock
lock: .uv
	uv lock --upgrade

.PHONY: clean
clean:
	@echo "🧹 Cleaning Python cache files and directories..."
	# Remove __pycache__ directories (including nested ones)
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	# Remove compiled Python files
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	# Remove cache directories (including nested ones)
	find . -type d -name ".cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	# Remove coverage files and directories
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "coverage.xml" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	find . -type f -name ".coverage.*" -delete 2>/dev/null || true
	find . -type f -name ".dmypy.json" -delete 2>/dev/null || true
	# Remove additional Python-related cache files
	find . -type f -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".tox" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".nox" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "build" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "dist" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Cleanup complete!"

.PHONY: build
build: .uv clean
	@echo "🏗️  Building package..."
	uv build --no-sources
	@echo "✅ Build complete! Artifacts in dist/"

.PHONY: publish-test
publish-test: ci build
	@echo "🚀 Publishing to TestPyPI..."
	@if [ -z "$(TESTPYPI_TOKEN)" ]; then \
		echo "❌ Error: TESTPYPI_TOKEN environment variable not set"; \
		echo "Get your token from: https://test.pypi.org/account/api-tokens/"; \
		exit 1; \
	fi
	uv publish --publish-url https://test.pypi.org/legacy/ --token $(TESTPYPI_TOKEN)
	@echo "✅ Published to TestPyPI successfully!"

.PHONY: publish-prod
publish-prod: ci build
	@echo "🚀 Publishing to PyPI..."
	@if [ -z "$(PYPI_TOKEN)" ]; then \
		echo "❌ Error: PYPI_TOKEN environment variable not set"; \
		echo "Get your token from: https://pypi.org/account/api-tokens/"; \
		exit 1; \
	fi
	uv publish --token $(PYPI_TOKEN)
	@echo "✅ Published to PyPI successfully!"

.PHONY: verify-install
verify-install: .uv
	@echo "🔍 Verifying package installation..."
	uv run --with $(PACKAGE_NAME) --no-project -- python -c "import $(PACKAGE_NAME); print('✅ Package $(PACKAGE_NAME) installed and importable!')"

.PHONY: help
help:
	@echo "Development Commands:"
	@echo "  install             Install dependencies"
	@echo "  format              Format code with ruff"
	@echo "  lint                Lint code with ruff"
	@echo "  typecheck           Run type checking with mypy, pyright, and ty"
	@echo "  test                Run tests with pytest"
	@echo "  coverage            Run tests with coverage reporting"
	@echo "  docs                Build documentation"
	@echo "  ci                  Run full CI pipeline (lint, typecheck, test, coverage)"
	@echo ""
	@echo "Publishing Commands:"
	@echo "  build               Build package for distribution"
	@echo "  publish-test        Publish to TestPyPI (requires TESTPYPI_TOKEN)"
	@echo "  publish-prod        Publish to PyPI (requires PYPI_TOKEN)"
	@echo "  verify-install      Verify package can be installed and imported"
	@echo ""
	@echo "Utility Commands:"
	@echo "  lock                Update lock files"
	@echo "  clean               Clean build artifacts and cache files"
	@echo "  help                Show this help message"