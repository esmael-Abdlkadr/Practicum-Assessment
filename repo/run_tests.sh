#!/bin/bash
set -e
echo "=============================="
echo " Practicum System - Test Suite"
echo "=============================="

if [ ! -x ".venv/bin/python" ]; then
    echo "Creating local virtual environment..."
    python3 -m venv .venv
fi

PYTHON_BIN=".venv/bin/python"

# Provide safe defaults when validator does not inject .env values.
export SECRET_KEY="${SECRET_KEY:-practicum-dev-secret-key-change-in-production}"
export DATABASE_URL="${DATABASE_URL:-sqlite:///data/practicum.db}"

echo "Installing test dependencies..."
"$PYTHON_BIN" -m pip install -q -r requirements-test.txt

echo "Installing Playwright Chromium browser..."
if ! "$PYTHON_BIN" -m playwright install chromium --with-deps; then
    echo "WARNING: Playwright browser install failed. E2E tests may not run."
    echo "         Run manually: $PYTHON_BIN -m playwright install chromium --with-deps"
fi
echo ""
echo "[1/3] Running unit tests..."
set +e
PYTHONPATH=. "$PYTHON_BIN" -m pytest tests/unit/ -v --tb=short 2>&1
UNIT_EXIT=$?
echo ""
echo "[2/3] Running API/integration tests..."
PYTHONPATH=. "$PYTHON_BIN" -m pytest tests/api/ -v --tb=short 2>&1
API_EXIT=$?
echo ""
echo "[3/3] Running E2E tests..."
PYTHONPATH=. "$PYTHON_BIN" -m pytest tests/e2e/ -v --tb=short 2>&1
E2E_STATUS=$?
set -e
echo ""
echo "=============================="
if [ $UNIT_EXIT -eq 0 ] && [ $API_EXIT -eq 0 ] && [ $E2E_STATUS -eq 0 ]; then
    echo " ALL TESTS PASSED"
else
    echo " SOME TESTS FAILED"
    echo " Unit exit: $UNIT_EXIT | API exit: $API_EXIT | E2E exit: $E2E_STATUS"
fi
echo "=============================="
exit $(( UNIT_EXIT + API_EXIT + E2E_STATUS ))
