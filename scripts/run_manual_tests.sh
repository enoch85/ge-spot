#!/bin/bash
# run_manual_tests.sh
# Script to run all manual (non-pytest) tests in the tests/manual directory

set -e

# Change to the project root directory
cd "$(dirname "$0")/.."

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Running GE Spot manual tests...${NC}"
echo "================================================"
echo ""

# Find all Python files in the tests/manual directory with "test" in the name
TEST_FILES=$(find tests/manual -name "*.py" | grep -v "__init__" | grep -v "__pycache__" | sort)

if [ -z "$TEST_FILES" ]; then
    echo -e "${YELLOW}No manual test files found in tests/manual${NC}"
    echo "To add manual tests, create Python files in the tests/manual directory"
    exit 0
fi

TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Run each test file
for test_file in $TEST_FILES; do
    echo -e "${YELLOW}Running test: ${test_file}${NC}"
    echo "------------------------------------------------"
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    # Run the test and capture the exit code
    python3 "$test_file" "$@"
    RESULT=$?
    
    if [ $RESULT -eq 0 ]; then
        echo -e "${GREEN}✓ Test passed: ${test_file}${NC}"
        PASSED_TESTS=$((PASSED_TESTS + 1))
    else
        echo -e "${RED}✗ Test failed: ${test_file}${NC}"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        FAILED_TEST_FILES="${FAILED_TEST_FILES} ${test_file}"
    fi
    
    echo ""
done

# Print summary
echo "================================================"
echo -e "${YELLOW}Test Summary:${NC}"
echo "Total tests: $TOTAL_TESTS"
echo -e "${GREEN}Passed: $PASSED_TESTS${NC}"
if [ $FAILED_TESTS -gt 0 ]; then
    echo -e "${RED}Failed: $FAILED_TESTS${NC}"
    echo ""
    echo -e "${RED}Failed tests:${NC}"
    for failed_file in $FAILED_TEST_FILES; do
        echo " - $failed_file"
    done
    exit 1
else
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
fi