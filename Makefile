# VinylVault Test Makefile
# Provides convenient commands for testing and deployment validation

.PHONY: help test test-unit test-integration test-api test-performance test-deployment test-all clean setup install-test-deps docker-test quick-test coverage lint

# Default target
help:
	@echo "VinylVault Test Commands:"
	@echo ""
	@echo "Setup and Installation:"
	@echo "  setup                 - Setup development environment"
	@echo "  install-test-deps     - Install test dependencies"
	@echo ""
	@echo "Testing:"
	@echo "  test                  - Run all tests"
	@echo "  test-unit            - Run unit tests only"
	@echo "  test-integration     - Run integration tests only"
	@echo "  test-api             - Run API tests only"
	@echo "  test-performance     - Run performance tests only"
	@echo "  test-deployment      - Run deployment tests only"
	@echo "  quick-test           - Run quick tests (skip slow tests)"
	@echo ""
	@echo "Coverage and Quality:"
	@echo "  coverage             - Generate coverage report"
	@echo "  lint                 - Run code linting"
	@echo ""
	@echo "Docker and Deployment:"
	@echo "  docker-test          - Run tests in Docker container"
	@echo "  docker-build         - Build Docker image"
	@echo "  docker-run           - Run application in Docker"
	@echo ""
	@echo "Maintenance:"
	@echo "  clean                - Clean test artifacts"

# Setup development environment
setup:
	@echo "Setting up VinylVault development environment..."
	python3 -m venv venv
	. venv/bin/activate && pip install -r requirements.txt
	. venv/bin/activate && pip install -r test-requirements.txt
	@echo "✓ Development environment ready"

# Install test dependencies
install-test-deps:
	@echo "Installing test dependencies..."
	pip install -r test-requirements.txt
	@echo "✓ Test dependencies installed"

# Run all tests
test:
	@echo "Running complete VinylVault test suite..."
	python3 run_tests.py

# Run unit tests only
test-unit:
	@echo "Running unit tests..."
	python3 -m pytest tests/unit -v --tb=short

# Run integration tests only
test-integration:
	@echo "Running integration tests..."
	python3 -m pytest tests/integration -v --tb=short

# Run API tests only
test-api:
	@echo "Running API tests..."
	python3 -m pytest tests/unit/test_api_endpoints.py -v --tb=short -m api

# Run performance tests only
test-performance:
	@echo "Running performance tests..."
	python3 -m pytest tests/performance -v --tb=short -m performance

# Run deployment tests only
test-deployment:
	@echo "Running deployment tests..."
	python3 -m pytest tests/deployment -v --tb=short -m deployment

# Run quick tests (exclude slow tests)
quick-test:
	@echo "Running quick tests..."
	python3 -m pytest -v --tb=short -m "not slow"

# Generate coverage report
coverage:
	@echo "Generating coverage report..."
	python3 -m pytest --cov=. --cov-report=html --cov-report=term-missing
	@echo "✓ Coverage report generated in htmlcov/"

# Run code linting
lint:
	@echo "Running code linting..."
	python3 -m flake8 --max-line-length=88 --extend-ignore=E203,W503 *.py
	python3 -m pylint --disable=C0114,C0115,C0116 *.py || true
	@echo "✓ Linting complete"

# Docker build
docker-build:
	@echo "Building Docker image..."
	docker build -t vinylvault:test .
	@echo "✓ Docker image built"

# Run tests in Docker
docker-test: docker-build
	@echo "Running tests in Docker container..."
	docker run --rm \
		-v $(PWD)/test-results:/app/test-results \
		-v $(PWD)/htmlcov:/app/htmlcov \
		vinylvault:test \
		python3 run_tests.py --skip-setup
	@echo "✓ Docker tests complete"

# Run application in Docker
docker-run:
	@echo "Running VinylVault in Docker..."
	docker-compose up --build

# Clean test artifacts
clean:
	@echo "Cleaning test artifacts..."
	rm -rf test-results/
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf __pycache__/
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete
	find . -name ".coverage" -delete
	@echo "✓ Cleanup complete"

# Deployment readiness check
deployment-check: test
	@echo ""
	@echo "🚀 DEPLOYMENT READINESS SUMMARY"
	@echo "================================"
	@if [ -f test-results/test-report.json ]; then \
		python3 -c "import json; data=json.load(open('test-results/test-report.json')); print('✓ Tests passed' if data['summary']['deployment_ready'] else '❌ Tests failed'); print(f\"Total: {data['summary']['total_tests']} tests, {data['summary']['total_failed']} failed\")"; \
	else \
		echo "❌ No test results found"; \
	fi

# Continuous integration command
ci: clean install-test-deps test deployment-check
	@echo "✓ CI pipeline complete"

# Development workflow
dev-test: quick-test
	@echo "✓ Development tests complete"