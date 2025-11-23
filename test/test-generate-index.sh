#!/bin/bash
set -e

# Test script for generate-index.sh
# Tests that files are grouped by month and sorted latest first

# Create test directory in local test folder
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_DIR="$SCRIPT_DIR/test-data"

# Clean up any previous test data and create fresh
rm -rf "$TEST_DIR"
mkdir -p "$TEST_DIR/test-content"

# Create test files with dates spanning multiple months
touch "$TEST_DIR/test-content/report-2025-11-23.html"
touch "$TEST_DIR/test-content/report-2025-11-15.html"
touch "$TEST_DIR/test-content/report-2025-11-20.html"
touch "$TEST_DIR/test-content/report-2025-10-31.html"
touch "$TEST_DIR/test-content/report-2025-10-15.html"
touch "$TEST_DIR/test-content/report-2025-09-25.html"

echo "Test files created in $TEST_DIR/test-content"
ls -1 "$TEST_DIR/test-content"

# Run the generate-index script
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bash "$REPO_ROOT/.github/scripts/generate-index.sh" "$TEST_DIR/test-content"

# Check the generated index.html
INDEX_FILE="$TEST_DIR/test-content/index.html"

echo ""
echo "Generated index.html:"
cat "$INDEX_FILE"
echo ""

# Verify expected structure
echo "Running assertions..."

# Check for month headers
if ! grep -q "<h2>November 2025</h2>" "$INDEX_FILE"; then
  echo "FAIL: Missing <h2>November 2025</h2>"
  exit 1
fi

if ! grep -q "<h2>October 2025</h2>" "$INDEX_FILE"; then
  echo "FAIL: Missing <h2>October 2025</h2>"
  exit 1
fi

if ! grep -q "<h2>September 2025</h2>" "$INDEX_FILE"; then
  echo "FAIL: Missing <h2>September 2025</h2>"
  exit 1
fi

# Extract the order of items (simplified check)
# November should come before October, October before September
NOV_LINE=$(grep -n "November 2025" "$INDEX_FILE" | cut -d: -f1)
OCT_LINE=$(grep -n "October 2025" "$INDEX_FILE" | cut -d: -f1)
SEP_LINE=$(grep -n "September 2025" "$INDEX_FILE" | cut -d: -f1)

if [ "$NOV_LINE" -gt "$OCT_LINE" ] || [ "$OCT_LINE" -gt "$SEP_LINE" ]; then
  echo "FAIL: Months not in correct order (latest first)"
  echo "November line: $NOV_LINE, October line: $OCT_LINE, September line: $SEP_LINE"
  exit 1
fi

# Within November, check that 2025-11-23 comes before 2025-11-15
# Get line numbers
LINE_23=$(grep -n "report-2025-11-23.html" "$INDEX_FILE" | cut -d: -f1)
LINE_15=$(grep -n "report-2025-11-15.html" "$INDEX_FILE" | cut -d: -f1)

if [ "$LINE_23" -gt "$LINE_15" ]; then
  echo "FAIL: Within November, items not sorted latest first"
  echo "2025-11-23 line: $LINE_23, 2025-11-15 line: $LINE_15"
  exit 1
fi

echo "PASS: All assertions passed!"
echo "✓ Files grouped by month with <h2> headers"
echo "✓ Months ordered latest first"
echo "✓ Files within months ordered latest first"
