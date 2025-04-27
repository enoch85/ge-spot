#!/bin/bash
# Script to run unit tests with pytest for GE Spot

set -e

# Change to the project root directory
cd "$(dirname "$0")/.."

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Running GE Spot pytest tests...${NC}"
echo "================================================"
echo ""

# Run unit tests
echo -e "${YELLOW}Running unit tests...${NC}"
python -m pytest tests/pytest/unit/ -v

# Run integration tests if requested
if [ "$1" == "--with-integration" ]; then
  echo ""
  echo -e "${YELLOW}Running integration tests...${NC}"
  python -m pytest tests/pytest/integration/ -v
fi

echo ""
echo -e "${GREEN}All pytest tests completed!${NC}"
exit 0