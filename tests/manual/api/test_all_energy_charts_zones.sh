#!/bin/bash
# Test all 38 Energy-Charts bidding zones

BASE_URL="https://api.energy-charts.info"
ENDPOINT="price"
START_DATE="2025-10-06"
END_DATE="2025-10-08"

# ANSI color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "Testing all 38 Energy-Charts bidding zones..."
echo "=============================================="

SUCCESS_COUNT=0
FAIL_COUNT=0

# Function to test a zone
test_zone() {
    local zone=$1
    local region=$2
    
    response=$(curl -s "${BASE_URL}/${ENDPOINT}?bzn=${zone}&start=${START_DATE}&end=${END_DATE}" 2>&1)
    
    # Check if response contains valid data
    if echo "$response" | jq -e '.unix_seconds[] and .price[]' >/dev/null 2>&1; then
        count=$(echo "$response" | jq '.unix_seconds | length')
        echo -e "${GREEN}✓${NC} ${zone} (${region}): ${count} price points"
        ((SUCCESS_COUNT++))
        return 0
    else
        echo -e "${RED}✗${NC} ${zone} (${region}): FAILED"
        ((FAIL_COUNT++))
        return 1
    fi
}

echo -e "\n${BLUE}Nordic Regions (13 zones)${NC}"
echo "-------------------------"
test_zone "SE1" "Sweden Zone 1"
test_zone "SE2" "Sweden Zone 2"
test_zone "SE3" "Sweden Zone 3"
test_zone "SE4" "Sweden Zone 4"
test_zone "NO1" "Norway Zone 1"
test_zone "NO2" "Norway Zone 2"
test_zone "NO3" "Norway Zone 3"
test_zone "NO4" "Norway Zone 4"
test_zone "NO5" "Norway Zone 5"
test_zone "NO2NSL" "Norway Zone 2 NSL"
test_zone "DK1" "Denmark West"
test_zone "DK2" "Denmark East"
test_zone "FI" "Finland"

echo -e "\n${BLUE}Baltic States (3 zones)${NC}"
echo "-----------------------"
test_zone "EE" "Estonia"
test_zone "LT" "Lithuania"
test_zone "LV" "Latvia"

echo -e "\n${BLUE}Western Europe (6 zones)${NC}"
echo "------------------------"
test_zone "DE-LU" "Germany-Luxembourg"
test_zone "FR" "France"
test_zone "NL" "Netherlands"
test_zone "BE" "Belgium"
test_zone "AT" "Austria"
test_zone "CH" "Switzerland"

echo -e "\n${BLUE}Central and Eastern Europe (11 zones)${NC}"
echo "--------------------------------------"
test_zone "PL" "Poland"
test_zone "CZ" "Czech Republic"
test_zone "SK" "Slovakia"
test_zone "HU" "Hungary"
test_zone "RO" "Romania"
test_zone "BG" "Bulgaria"
test_zone "SI" "Slovenia"
test_zone "HR" "Croatia"
test_zone "RS" "Serbia"
test_zone "ME" "Montenegro"
test_zone "GR" "Greece"

echo -e "\n${BLUE}Italy (6 zones)${NC}"
echo "---------------"
test_zone "IT-North" "Italy North"
test_zone "IT-South" "Italy South"
test_zone "IT-Centre-North" "Italy Centre-North"
test_zone "IT-Centre-South" "Italy Centre-South"
test_zone "IT-Sardinia" "Italy Sardinia"
test_zone "IT-Sicily" "Italy Sicily"

echo -e "\n${BLUE}Iberian Peninsula (2 zones)${NC}"
echo "---------------------------"
test_zone "ES" "Spain"
test_zone "PT" "Portugal"

echo -e "\n=============================================="
echo -e "${GREEN}Successful: ${SUCCESS_COUNT}/38${NC}"
echo -e "${RED}Failed: ${FAIL_COUNT}/38${NC}"

if [ $FAIL_COUNT -eq 0 ]; then
    echo -e "\n${GREEN}✓ All zones working!${NC}"
    exit 0
else
    echo -e "\n${RED}✗ Some zones failed${NC}"
    exit 1
fi
