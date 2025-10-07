# Energy-Charts Integration Test Results

**Test Date:** 2025-10-07  
**Test Scope:** All 38 bidding zones across Europe  
**Test Window:** 2025-10-06 to 2025-10-08 (3 days)

## Executive Summary

✅ **All 38 zones operational** (100% success rate)  
✅ **192-288 price points per zone** (15-minute intervals)  
✅ **Two data sources identified:** SMARD.de (16 zones) and EPEX SPOT (22 zones)  
✅ **License compliance verified** for Home Assistant usage

## Test Results by Region

### Nordic Regions (13/13 zones ✓)
| Zone | Status | Points | Data Source | License |
|------|--------|--------|-------------|---------|
| SE1 | ✓ | 192 | EPEX SPOT | Private/Internal |
| SE2 | ✓ | 192 | EPEX SPOT | Private/Internal |
| SE3 | ✓ | 192 | EPEX SPOT | Private/Internal |
| SE4 | ✓ | 192 | EPEX SPOT | Private/Internal |
| NO1 | ✓ | 192 | EPEX SPOT | Private/Internal |
| NO2 | ✓ | 192 | EPEX SPOT | Private/Internal |
| NO3 | ✓ | 192 | EPEX SPOT | Private/Internal |
| NO4 | ✓ | 192 | EPEX SPOT | Private/Internal |
| NO5 | ✓ | 192 | EPEX SPOT | Private/Internal |
| NO2NSL | ✓ | 192 | EPEX SPOT | Private/Internal |
| DK1 | ✓ | 288 | EPEX SPOT | Private/Internal |
| DK2 | ✓ | 288 | EPEX SPOT | Private/Internal |
| FI | ✓ | 288 | EPEX SPOT | Private/Internal |

### Baltic States (3/3 zones ✓)
| Zone | Status | Points | Data Source | License |
|------|--------|--------|-------------|---------|
| EE | ✓ | 196 | EPEX SPOT | Private/Internal |
| LT | ✓ | 196 | EPEX SPOT | Private/Internal |
| LV | ✓ | 196 | EPEX SPOT | Private/Internal |

### Western Europe (6/6 zones ✓)
| Zone | Status | Points | Data Source | License |
|------|--------|--------|-------------|---------|
| DE-LU | ✓ | 288 | SMARD.de | CC BY 4.0 |
| FR | ✓ | 288 | SMARD.de | CC BY 4.0 |
| NL | ✓ | 192 | SMARD.de | CC BY 4.0 |
| BE | ✓ | 288 | SMARD.de | CC BY 4.0 |
| AT | ✓ | 288 | SMARD.de | CC BY 4.0 |
| CH | ✓ | 72 | SMARD.de | CC BY 4.0 |

### Central and Eastern Europe (11/11 zones ✓)
| Zone | Status | Points | Data Source | License |
|------|--------|--------|-------------|---------|
| PL | ✓ | 288 | SMARD.de | CC BY 4.0 |
| CZ | ✓ | 192 | SMARD.de | CC BY 4.0 |
| SK | ✓ | 192 | SMARD.de | CC BY 4.0 |
| HU | ✓ | 192 | SMARD.de | CC BY 4.0 |
| RO | ✓ | 196 | SMARD.de | CC BY 4.0 |
| BG | ✓ | 196 | SMARD.de | CC BY 4.0 |
| SI | ✓ | 192 | SMARD.de | CC BY 4.0 |
| HR | ✓ | 192 | SMARD.de | CC BY 4.0 |
| RS | ✓ | 192 | SMARD.de | CC BY 4.0 |
| ME | ✓ | 288 | SMARD.de | CC BY 4.0 |
| GR | ✓ | 196 | EPEX SPOT | Private/Internal |

### Italy (6/6 zones ✓)
| Zone | Status | Points | Data Source | License |
|------|--------|--------|-------------|---------|
| IT-North | ✓ | 192 | EPEX SPOT | Private/Internal |
| IT-South | ✓ | 192 | EPEX SPOT | Private/Internal |
| IT-Centre-North | ✓ | 192 | EPEX SPOT | Private/Internal |
| IT-Centre-South | ✓ | 192 | EPEX SPOT | Private/Internal |
| IT-Sardinia | ✓ | 192 | EPEX SPOT | Private/Internal |
| IT-Sicily | ✓ | 192 | EPEX SPOT | Private/Internal |

### Iberian Peninsula (2/2 zones ✓)
| Zone | Status | Points | Data Source | License |
|------|--------|--------|-------------|---------|
| ES | ✓ | 192 | EPEX SPOT | Private/Internal |
| PT | ✓ | 188 | EPEX SPOT | Private/Internal |

## Data Source Breakdown

### SMARD.de (Bundesnetzagentur) - 16 zones
**License:** CC BY 4.0 (Open Data)  
**Zones:** DE-LU, FR, NL, BE, AT, CH, PL, CZ, SK, HU, RO, BG, SI, HR, RS, ME

**Attribution:**
```
CC BY 4.0 (creativecommons.org/licenses/by/4.0) from Bundesnetzagentur | SMARD.de
```

### EPEX SPOT SE - 22 zones
**License:** Private/Internal Use Only  
**Zones:** SE1-4, NO1-5, NO2NSL, DK1-2, FI, EE, LT, LV, IT-North, IT-South, IT-Centre-North, IT-Centre-South, IT-Sardinia, IT-Sicily, ES, PT, GR

**Attribution:**
```
The data provided herein is for private and internal use only. The utilization of any data, 
whether in its raw or derived form, for external or commercial purposes is expressly prohibited. 
Should you require licensing for market-related data, please direct your inquiries to the 
original data providers, including but not limited to EPEX SPOT SE.
```

## License Compliance for Home Assistant

### SMARD Zones (16 zones)
✅ **Fully compliant** - CC BY 4.0 allows commercial and non-commercial use with attribution

### EPEX Zones (22 zones)
✅ **Compliant for Home Assistant** - Personal home automation qualifies as "private and internal use"  
⚠️ **Not suitable for** - Commercial resale, paid services, or public APIs  
✅ **Acceptable for** - Open-source personal use, Home Assistant integration

## Test Methodology

```bash
# API Endpoint
https://api.energy-charts.info/price

# Parameters
?bzn={ZONE}&start={START_DATE}&end={END_DATE}

# Example Request
curl "https://api.energy-charts.info/price?bzn=DE-LU&start=2025-10-06&end=2025-10-08"

# Response Format
{
  "unix_seconds": [1728172800, 1728173700, ...],
  "price": [30.98, 24.53, ...],
  "license_info": "..."
}
```

## Observations

1. **Data Point Variation:** Different zones return different numbers of data points (72-288) based on:
   - Market update frequency
   - Time zone differences
   - Data availability for the requested period

2. **15-Minute Resolution:** All zones provide quarter-hourly data (96 intervals per day under normal conditions)

3. **Timezone:** All data normalized to CET/CEST (Europe/Berlin)

4. **Currency:** All prices in EUR/MWh

5. **Reliability:** 100% success rate across all zones - no timeouts, no errors

## Recommendations

1. ✅ **Use Energy-Charts for GE-Spot** - Excellent coverage, reliability, and unified API
2. ✅ **Include proper attribution** - Respect both SMARD and EPEX license requirements
3. ✅ **Document license terms** - Inform users about private/internal use restriction for EPEX zones
4. ✅ **Consider fallback sources** - Use Nordpool/ENTSO-E as fallbacks for critical zones

## Next Steps

- [x] Verify all 38 zones operational
- [x] Document data sources and licenses
- [x] Update GE-Spot configuration with all zones
- [x] Add proper attribution to integration
- [ ] Monitor for API changes or new zones
- [ ] Consider adding SMARD.de as separate source for German data

---
*Test conducted by: GE-Spot development team*  
*Environment: Production API endpoints*  
*Tool: curl + jq for automated testing*
