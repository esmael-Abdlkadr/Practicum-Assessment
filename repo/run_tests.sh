#!/usr/bin/env bash
set -e

if [ "${IN_DOCKER_TEST:-0}" != "1" ]; then
    echo "Running tests in Docker test service..."
    docker compose --profile test run --rm test
    exit $?
fi

echo "=============================="
echo " Practicum System - Test Suite"
echo "=============================="

PYTHON_BIN="python"

# Keep deterministic test behavior from TestingConfig.
unset SECRET_KEY
export DATABASE_URL="${DATABASE_URL:-sqlite:///data/practicum.db}"

echo ""
echo "[1/4] Running unit tests..."
set +e
PYTHONPATH=. "$PYTHON_BIN" -m pytest tests/unit/ -v --tb=short 2>&1
UNIT_EXIT=$?
echo ""
echo "[2/4] Running API tests..."
PYTHONPATH=. "$PYTHON_BIN" -m pytest tests/api/ -v --tb=short 2>&1
API_EXIT=$?
echo ""
echo "[3/4] Running HTTP integration tests..."
PYTHONPATH=. "$PYTHON_BIN" -m pytest tests/integration/ -v --tb=short 2>&1
HTTP_EXIT=$?
echo ""
echo "[4/4] Running E2E tests..."
PYTHONPATH=. "$PYTHON_BIN" -m pytest tests/e2e/ -v --tb=short 2>&1
E2E_EXIT=$?
set -e

echo ""
echo "=============================="
if [ $UNIT_EXIT -eq 0 ] && [ $API_EXIT -eq 0 ] && [ $HTTP_EXIT -eq 0 ] && [ $E2E_EXIT -eq 0 ]; then
    echo " ALL TESTS PASSED"
else
    echo " SOME TESTS FAILED"
    echo " Unit exit: $UNIT_EXIT | API exit: $API_EXIT | HTTP exit: $HTTP_EXIT | E2E exit: $E2E_EXIT"
fi
echo "=============================="
exit $(( UNIT_EXIT + API_EXIT + HTTP_EXIT + E2E_EXIT ))
