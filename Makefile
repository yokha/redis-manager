SHELL := /bin/bash

# Development on latest supported python version
VENV_DIR := venv3.11
PYTHON := python3.11
ACTIVATE := source "$(VENV_DIR)/bin/activate"

# Packaging on oldest supported python version
PKG_VENV_DIR := venv3.8
PKG_PYTHON := python3.8
PKG_ACTIVATE := source "$(PKG_VENV_DIR)/bin/activate"

# Supported Python versions
PYTHON_VERSIONS := 3.8 3.9 3.10 3.11 3.12

.PHONY: lint format test cov integration docker-up docker-down testbench testbench-clean testbench-rebuild testbench-logs testbench-docker-up testbench-docker-down

all: lint format format-check test cov integration package

# Target to set up a fresh virtual environment
setup-venv:
	@if [ ! -d "$(VENV_DIR)" ]; then \
		if command -v $(PYTHON) > /dev/null 2>&1; then \
			echo "Creating virtual environment with $(PYTHON)..."; \
			$(PYTHON) -m venv $(VENV_DIR); \
		elif command -v python > /dev/null 2>&1; then \
			echo "Creating virtual environment with default python..."; \
			python -m venv $(VENV_DIR); \
		else \
			echo "Error: Python executable not found!"; \
			exit 1; \
		fi; \
		$(ACTIVATE) && pip install --upgrade pip && pip install -r requirements.txt -r dev-requirements.txt; \
	else \
		echo "Virtual environment already exists."; \
	fi

# Clean up build artifacts and the packaging virtual environment
clean-venv:
	@echo "Cleaning up build artifacts and the virtual environment..."
	rm -rf $(VENV_DIR)
	@echo "Cleanup complete!"


lint: setup-venv
	@$(ACTIVATE) && PYTHONPATH=src pylint --jobs=0 src tests

format: setup-venv
	@$(ACTIVATE) && PYTHONPATH=src  black src/ tests/

format-check: setup-venv
	@$(ACTIVATE) && PYTHONPATH=src black --check src tests

test: setup-venv
	@$(ACTIVATE) && PYTHONPATH=src pytest -n auto --dist=loadscope -v tests/unit

cov: setup-venv
	@$(ACTIVATE) && PYTHONPATH=src pytest -n auto --dist=loadscope --cov=src --cov-report=term-missing --cov-report=html:htmlcov tests/unit

integration: integration-docker-reset 
	@$(MAKE) --no-print-directory integration-docker-test-runner
	@$(MAKE) --no-print-directory integration-docker-down
	@$(MAKE) --no-print-directory integration-docker-clean
	
# Call make targets from tests/integration/Makefile
integration-%:
	@$(MAKE) --no-print-directory -C tests/integration $(MAKECMDGOALS)

integration-docker-up:
	@$(MAKE) --no-print-directory -C tests/integration docker-up

integration-docker-down:
	@$(MAKE) --no-print-directory -C tests/integration docker-down

integration-docker-clean:
	@$(MAKE) --no-print-directory -C tests/integration docker-clean

integration-docker-reset:
	@$(MAKE) --no-print-directory -C tests/integration docker-reset

integration-docker-logs:
	@$(MAKE) --no-print-directory -C tests/integration docker-logs

integration-docker-logs-%:
	@$(MAKE) --no-print-directory -C tests/integration docker-logs-$*

integration-docker-test-runner:
	@$(MAKE) --no-print-directory -C tests/integration docker-test-runner

# Testbench (RedisManager Simulation with metric is grafana)
testbench: testbench-docker-down ## Run the testbench (simulate RedisManager)
	docker-compose up --force-recreate

# Testbench Helper
testbench-helper: ## Display helper information about the testbench
	@echo "==============================================="
	@echo "🚀 Testbench Instructions:"
	@echo "1. Run: make testbench"
	@echo "2. Wait for services to start."
	@echo "3. Access the following endpoints:"
	@echo "   👉 Prometheus metrics: http://localhost:8000/metrics"
	@echo "   👉 Grafana dashboard:  http://localhost:3000"
	@echo "4. Customize the testbench application by editing:"
	@echo "   👉 testbench/app/app.py"
	@echo "==============================================="

testbench-docker-up: ## Bring up the Docker Compose services
	docker-compose up -d

testbench-docker-down: ## Bring down the Docker Compose services
	docker-compose down --volumes --remove-orphans

testbench-clean: docker-down ## Clean up Docker containers, volumes, and networks
	docker-compose down --volumes --remove-orphans

testbench-rebuild: clean ## Rebuild and recreate all containers
	docker-compose up --build --force-recreate

testbench-logs: ## Show logs from the Docker Compose services
	docker-compose logs -f

## All packaging/release targets below are not part of the pipeline for now.
# Target to set up a fresh virtual environment
setup-pkg-venv:
	@if [ ! -d "$(PKG_VENV_DIR)" ]; then \
		if command -v $(PKG_PYTHON) > /dev/null 2>&1; then \
			echo "Creating virtual environment with $(PKG_PYTHON)..."; \
			$(PKG_PYTHON) -m venv $(PKG_VENV_DIR); \
		elif command -v python > /dev/null 2>&1; then \
			echo "Creating virtual environment with default python..."; \
			python -m venv $(PKG_VENV_DIR); \
		else \
			echo "Error: Python executable not found!"; \
			exit 1; \
		fi; \
		$(PKG_ACTIVATE) && pip install --upgrade pip twine setuptools wheel; \
	else \
		echo "Virtual environment already exists."; \
	fi

# Clean up build artifacts and the packaging virtual environment
# Releases require .pypirc update with personal tokens.
clean-pkg-venv:
	@echo "Cleaning up build artifacts and the virtual environment..."
	rm -rf $(PKG_VENV_DIR) dist build *.egg-info
	@echo "Cleanup complete!"


# Target to package the project using the virtual environment
package: clean-pkg-venv setup-pkg-venv
	@echo "Building the package inside the fresh virtual environment..."
	@if command -v $(PKG_PYTHON) > /dev/null 2>&1; then \
		$(PKG_ACTIVATE) && $(PKG_PYTHON) setup.py sdist bdist_wheel; \
	elif command -v python > /dev/null 2>&1; then \
		$(PKG_ACTIVATE) && python setup.py sdist bdist_wheel; \
	fi
	@echo "Package built successfully!"

# Release to test PyPI. it requires env vars
# export TWINE_USERNAME="__token__"
# export TWINE_PASSWORD="your-pypi-api-token"
release-pypi-test: package
	@echo "Uploading to test PyPI..."
	@if [ -z "$$TWINE_USERNAME" ] || [ -z "$$TWINE_PASSWORD" ]; then \
		echo "Error: TWINE_USERNAME or TWINE_PASSWORD is not set"; \
		exit 1; \
	fi
	@$(PKG_ACTIVATE) && TWINE_USERNAME=$$TWINE_USERNAME TWINE_PASSWORD=$$TWINE_PASSWORD $(PKG_PYTHON) -m twine upload --repository testpypi dist/*
	@echo "Test Release completed!"


# General verification target
verify-release:
	@echo "Determining VERSION dynamically from pyproject.toml..."
	@VERSION=$$(grep -m1 '^version = ' pyproject.toml | sed -E 's/version = "(.*)"/\1/'); \
	if [ -z "$$VERSION" ]; then \
		echo "ERROR: VERSION could not be determined."; \
		exit 1; \
	fi; \
	echo "Detected version: $$VERSION"; \
	for python in $(PYTHON_VERSIONS); do \
		echo "-------------------------------------------"; \
		echo "Processing for Python $$python..."; \
		if ! command -v python$$python > /dev/null 2>&1; then \
			echo "WARNING: Python $$python is not installed. Skipping..."; \
			continue; \
		fi; \
		rm -rf test_env_$$python; \
		echo "Setting up virtual environment for Python $$python..."; \
		if ! python$$python -m venv test_env_$$python > /dev/null 2>&1; then \
			echo "ERROR: Failed to set up virtual environment for Python $$python."; \
			continue; \
		fi; \
		source test_env_$$python/bin/activate && pip install --upgrade pip > /dev/null 2>&1; \
		echo "Installing package from $(REPO_NAME) for Python $$python..."; \
		source test_env_$$python/bin/activate && pip install --index-url $(REPO_URL) \
			$$(test "$(REPO_NAME)" = "Test PyPI" && echo "--extra-index-url https://pypi.org/simple/") \
			redis-manager==$$VERSION > /dev/null 2>&1; \
		if [ $$? -ne 0 ]; then \
			echo "ERROR: Package installation failed for Python $$python."; \
			rm -rf test_env_$$python; \
			continue; \
		fi; \
		echo "Verifying installation for Python $$python..."; \
		if ! source test_env_$$python/bin/activate && pip list | grep -q 'redis-manager'; then \
			echo "ERROR: Package 'redis-manager' is NOT installed for Python $$python."; \
			rm -rf test_env_$$python; \
			continue; \
		fi; \
		echo "Package 'redis-manager' is installed for Python $$python."; \
		echo "Testing package import for Python $$python..."; \
		if ! source test_env_$$python/bin/activate && python -c "import redis_manager; print(redis_manager.__name__)" | grep -q 'redis_manager'; then \
			echo "ERROR: Failed to import 'redis_manager' for Python $$python."; \
			rm -rf test_env_$$python; \
			continue; \
		fi; \
		echo "Package 'redis_manager' imported successfully for Python $$python."; \
		echo "Verification for Python $$python completed successfully!"; \
		rm -rf test_env_$$python; \
	done; \
	echo "-------------------------------------------"; \
	echo "Verification process completed for all Python versions."; \
	echo "Ensure skipped versions are installed if required."

# Target for verifying against Test PyPI
verify-test-release:
	@$(MAKE) verify-release REPO_NAME="Test PyPI" REPO_URL="https://test.pypi.org/simple/"


# Release to PyPI. it requires env vars
# export TWINE_USERNAME="__token__"
# export TWINE_PASSWORD="your-pypi-api-token"
release-pypi: package
	@echo "Uploading to PyPI..."
	@if [ -z "$$TWINE_USERNAME" ] || [ -z "$$TWINE_PASSWORD" ]; then \
		echo "Error: TWINE_USERNAME or TWINE_PASSWORD is not set"; \
		exit 1; \
	fi
	@$(PKG_ACTIVATE) && TWINE_USERNAME=$$TWINE_USERNAME TWINE_PASSWORD=$$TWINE_PASSWORD $(PKG_PYTHON) -m twine upload --repository pypi dist/*
	@echo "Release completed!"

# Verify the package from PyPI for all Python versions
verify-prod-release:
	@$(MAKE) verify-release REPO_NAME="PyPI" REPO_URL="https://pypi.org/simple/"

# Tag Release version: Ensure you pass the correct version from src/redis_manager/__init__.py
tag-release:
	@read -p "Enter version: " VERSION; \
	git tag -a v$$VERSION -m "Release version $$VERSION"; \
	git push origin v$$VERSION
