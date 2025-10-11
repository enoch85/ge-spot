# Grace Period Mechanism - Complete Technical Documentation

**Date:** October 11, 2025  
**Component:** GE-Spot Integration  
**Feature:** Post-Startup Grace Period  
**Status:** ✅ Implemented and Active

---

## Executive Summary

The **grace period** is a 5-minute window after Home Assistant restarts or the integration reloads where GE-Spot temporarily bypasses rate limiting to allow immediate data fetching. This prevents sensors from showing "unavailable" or stale data during the critical post-restart phase.

**Key Facts:**
- **Duration:** 5 minutes (configurable via `Network.Defaults.GRACE_PERIOD_MINUTES`)
- **Purpose:** Allow immediate fallback attempts without rate limiting after restart/reload
- **Scope:** Only bypasses rate limiting, does NOT bypass data validity checks or health checks
- **Impact:** Improves user experience by showing fresh data faster after HA restart

---

## The Problem It Solves

### Without Grace Period (Old Behavior)

```
Timeline:
00:00 - Home Assistant restarts
00:00 - GE-Spot integration loads
00:00 - All sensors show "unavailable" (no data yet)
00:01 - First sensor update triggered
      - UnifiedPriceManager.fetch_data() called
      - FetchDecisionMaker: "No current interval data - need to fetch"
      - Rate limiter: "Last fetch was 2 minutes ago - BLOCKED" ❌
      - Returns cached data if available
      - If no cache: Sensors remain "unavailable" ❌

00:16 - Second sensor update (15 minutes later)
      - Rate limiting expires
      - API fetch allowed ✅
      - Sensors finally show data (16 minutes after restart!)
```

**Problems:**
1. Sensors unavailable for up to 15 minutes after restart
2. User sees errors/warnings during grace period
3. Automations may trigger incorrectly on "unavailable" state
4. Poor user experience during common operation (HA restart)

### With Grace Period (Current Behavior)

```
Timeline:
00:00 - Home Assistant restarts
00:00 - GE-Spot integration loads
      - _coordinator_created_at = 00:00 (timestamp recorded)
00:00 - All sensors show "unavailable" (no data yet)
00:01 - First sensor update triggered
      - UnifiedPriceManager.fetch_data() called
      - is_in_grace_period() → TRUE ✅
      - FetchDecisionMaker: "No current interval data - need to fetch"
      - Rate limiter: "In grace period - BYPASSING rate limit" ✅
      - API fetch proceeds
      - Sensors show fresh data immediately ✅

00:05 - Grace period expires (5 minutes after creation)
00:06 - Subsequent updates respect normal rate limiting
```

**Benefits:**
1. ✅ Sensors show data within seconds after restart
2. ✅ No error messages during expected post-restart fetch
3. ✅ Automations see valid data immediately
4. ✅ Better user experience
5. ✅ Falls back to normal rate limiting after grace period

---

## Implementation Details

### 1. Grace Period Tracking

**File:** `custom_components/ge_spot/coordinator/unified_price_manager.py`

**Initialization (line ~98):**
```python
def __init__(self, hass, config, area):
    """Initialize the Unified Price Manager."""
    # ... other initialization ...
    
    # Track coordinator creation time for grace period calculation
    self._coordinator_created_at = dt_util.utcnow()
    
    # Grace period allows bypassing rate limiting immediately after
    # coordinator creation (HA restart, config reload)
```

**Grace Period Check (lines 146-163):**
```python
def is_in_grace_period(self) -> bool:
    """Check if we're within the grace period after coordinator creation.

    During the grace period (first 5 minutes after reload/startup), we're more
    lenient with validation failures and rate limiting to avoid clearing sensors
    unnecessarily.

    Returns:
        True if within grace period, False otherwise
    """
    try:
        now = dt_util.utcnow()
        time_since_creation = now - self._coordinator_created_at
        grace_period = timedelta(minutes=Network.Defaults.GRACE_PERIOD_MINUTES)
        return time_since_creation < grace_period
    except (TypeError, AttributeError):
        # If anything fails, assume no grace period
        return False
```

**Configuration (file: `const/network.py`, line 25):**
```python
class Network:
    class Defaults:
        GRACE_PERIOD_MINUTES = 5  # Grace period after reload/startup for lenient validation
```

---

### 2. Grace Period Usage Points

The grace period is checked at **three critical locations**:

#### A. Fetch Decision Making (line 518)

**Location:** `UnifiedPriceManager.fetch_data()`

```python
# Before calling FetchDecisionMaker
fetch_reason, need_fetch = self._fetch_decision_maker.should_fetch(
    now=now,
    last_fetch=last_fetch_for_area,
    data_validity=data_validity,
    fetch_interval_minutes=Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES,
    in_grace_period=self.is_in_grace_period()  # ← Passed to decision maker
)
```

**Purpose:** Allow FetchDecisionMaker to bypass rate limiting when checking if fetch is needed.

**Flow:**
```
is_in_grace_period() → TRUE
  ↓
Passed to FetchDecisionMaker.should_fetch()
  ↓
Passed to RateLimiter.should_skip_fetch()
  ↓
RateLimiter returns: "In grace period - bypassing rate limit"
  ↓
Fetch proceeds without rate limiting check
```

#### B. Post-Fetch Cache Fallback (line 539)

**Location:** `UnifiedPriceManager.fetch_data()` - after fetch decision says "skip"

```python
# If we decided NOT to fetch but have no cache
if self.is_in_grace_period() and "rate limited" in fetch_reason.lower():
    # Rate limiting after recent reload - this is expected, log as INFO
    minutes_until_fetch = Network.Defaults.MIN_UPDATE_INTERVAL_MINUTES
    _LOGGER.info(
        f"[{self.area}] Data will update within {minutes_until_fetch} minutes "
        f"(rate limit protection active after configuration reload). "
        f"Reason: {fetch_reason}"
    )
else:
    # Unexpected situation - log as ERROR
    _LOGGER.error(
        f"Fetch skipped for {self.area} but no cached data available. "
        f"Reason: {fetch_reason}"
    )
```

**Purpose:** Log appropriate message (INFO vs ERROR) based on grace period status.

**Why This Matters:**
- During grace period: Rate limiting is **expected** → log as INFO (not alarming)
- After grace period: Rate limiting with no cache is **unexpected** → log as ERROR (needs attention)

#### C. Second Rate Limit Check (line 568)

**Location:** `UnifiedPriceManager.fetch_data()` - inside the fetch lock

```python
# Re-check rate limiting inside the fetch lock (for atomicity)
if not force and not self.is_in_grace_period() and last_fetch_for_rate_limit:
    time_since_last_fetch = now - last_fetch_for_rate_limit
    if time_since_last_fetch < min_interval:
        # Rate limited - return cached data or error
        # ...
```

**Purpose:** Bypass the second (atomic) rate limit check during grace period.

**Why Two Checks?**
1. **First check** (before fetch lock): Fast path decision, can use grace period
2. **Second check** (inside fetch lock): Atomic verification, also respects grace period

**Without grace period bypass here:**
- Even if first check passed, second check could block the fetch
- Would defeat the purpose of grace period

---

### 3. Rate Limiter Integration

**File:** `custom_components/ge_spot/utils/rate_limiter.py`

The grace period is passed to `RateLimiter.should_skip_fetch()` which uses it like this:

```python
@staticmethod
def should_skip_fetch(
    last_fetched: datetime,
    current_time: datetime,
    min_interval: int,
    in_grace_period: bool = False
) -> Tuple[bool, str]:
    """Determine if fetch should be skipped due to rate limiting.
    
    Args:
        in_grace_period: If True, bypass rate limiting (post-restart grace period)
    
    Returns:
        Tuple of (should_skip, reason)
    """
    
    # Grace period bypass
    if in_grace_period:
        return False, "Within grace period after startup - bypassing rate limiting"
    
    # Normal rate limiting logic
    # ...
```

**Effect:** When `in_grace_period=True`, rate limiter immediately returns "don't skip" (allow fetch).

---

### 4. Fetch Decision Maker Integration

**File:** `custom_components/ge_spot/coordinator/fetch_decision.py`

The `FetchDecisionMaker.should_fetch()` method accepts `in_grace_period` parameter and passes it to all rate limiter calls:

```python
def should_fetch(
    self,
    now: datetime,
    last_fetch: Optional[datetime],
    data_validity: DataValidity,
    fetch_interval_minutes: int = 15,
    in_grace_period: bool = False  # ← Accepted here
) -> Tuple[bool, str]:
    """Determine if we need to fetch from API."""
    
    # Example usage in one of the decision points:
    if not data_validity.has_current_interval:
        # ...
        from ..utils.rate_limiter import RateLimiter
        should_skip, skip_reason = RateLimiter.should_skip_fetch(
            last_fetched=last_fetch,
            current_time=now,
            min_interval=fetch_interval_minutes,
            in_grace_period=in_grace_period  # ← Passed through
        )
```

**Propagation chain:**
```
UnifiedPriceManager.is_in_grace_period()
  ↓
UnifiedPriceManager.fetch_data() (calls decision maker)
  ↓
FetchDecisionMaker.should_fetch(in_grace_period=...)
  ↓
RateLimiter.should_skip_fetch(in_grace_period=...)
  ↓
Returns "bypass" or "enforce" rate limiting
```

---

## Real-World Scenarios

### Scenario 1: Home Assistant Restart (Common Case)

```
00:00:00 - HA restarts
00:00:05 - GE-Spot integration initializes
         - _coordinator_created_at = 00:00:05
         
00:00:10 - First sensor update (5 seconds after init)
         - Time since creation: 5 seconds
         - is_in_grace_period() → TRUE (< 5 minutes)
         - Last fetch: None (never fetched)
         - Decision: FETCH (initial startup)
         - Rate limiter: BYPASSED (grace period)
         - API fetch: SUCCESS ✅
         - Sensors show data immediately
         
00:01:10 - Second sensor update (1 minute after init)
         - Time since creation: 65 seconds
         - is_in_grace_period() → TRUE (still < 5 minutes)
         - Last fetch: 00:00:10 (1 minute ago)
         - Decision: SKIP (have current data)
         - Uses cached data
         
00:06:10 - Seventh sensor update (6 minutes after init)
         - Time since creation: 365 seconds
         - is_in_grace_period() → FALSE (> 5 minutes) ❌
         - Grace period expired - normal rate limiting active
         - Rate limiting enforced from this point forward
```

**Result:** User sees data within 10 seconds of restart.

---

### Scenario 2: Configuration Reload (Common Case)

```
13:45:00 - User changes VAT setting from 25% to 0%
13:45:01 - Config reload triggered
         - Old coordinator destroyed
         - New coordinator created
         - _coordinator_created_at = 13:45:01
         - Cache still contains old data (with 25% VAT)
         
13:45:05 - First sensor update after reload
         - Time since creation: 4 seconds
         - is_in_grace_period() → TRUE
         - Last fetch: None (new coordinator, no fetch history)
         - Cache: Available but stale (wrong VAT)
         - Decision: FETCH (need fresh data with new config)
         - Rate limiter: BYPASSED (grace period)
         - API fetch: SUCCESS ✅
         - Data reprocessed with 0% VAT
         - Sensors show correct prices immediately
         
13:45:15 - Second sensor update
         - Time since creation: 14 seconds
         - is_in_grace_period() → TRUE (still < 5 minutes)
         - Last fetch: 13:45:05 (10 seconds ago)
         - Decision: SKIP (have current data with correct config)
         - Uses cached data (now with 0% VAT)
         
13:50:05 - Update after grace period expires
         - Time since creation: 304 seconds
         - is_in_grace_period() → FALSE ❌
         - Normal rate limiting active
         - Last fetch: 13:45:05 (5 minutes ago)
         - Decision: SKIP (still within 15-minute minimum interval)
         - Rate limiter: ENFORCED (no bypass) ✅
```

**Result:** User sees updated prices (with new VAT) within 5 seconds of config change.

---

### Scenario 3: API Failure During Grace Period

```
02:30:00 - HA restarts
02:30:05 - GE-Spot initializes
         - _coordinator_created_at = 02:30:05
         
02:30:10 - First sensor update
         - is_in_grace_period() → TRUE
         - Decision: FETCH (no data)
         - Rate limiter: BYPASSED
         - API fetch: FAILURE (Nordpool API down) ❌
         - Fallback to ENTSOE
         - ENTSOE fetch: FAILURE (also down) ❌
         - No cache available (fresh restart)
         - Result: Empty data, sensors show "unavailable"
         
02:30:25 - Second sensor update (15 seconds later)
         - is_in_grace_period() → TRUE (still < 5 minutes)
         - Last fetch: 02:30:10 (15 seconds ago)
         - Decision: FETCH (no current data)
         - Rate limiter: BYPASSED (grace period) ✅
         - API fetch: RETRY IMMEDIATELY (no rate limit wait)
         - Nordpool: SUCCESS ✅
         - Sensors show data
```

**Benefit:** During grace period, failed fetches can be retried immediately without waiting 15 minutes. This gives the system multiple chances to recover during the critical post-startup window.

---

### Scenario 4: Grace Period Expiration

```
10:00:00 - Config reload
         - _coordinator_created_at = 10:00:00
         
10:04:30 - Update during grace period
         - is_in_grace_period() → TRUE (4.5 minutes)
         - Rate limiting: BYPASSED ✅
         
10:05:01 - Update after grace period expires
         - Time since creation: 301 seconds (5 minutes 1 second)
         - is_in_grace_period() → FALSE ❌
         - Rate limiting: ENFORCED
         - Last fetch: 10:00:05 (5 minutes ago)
         - Too soon for next fetch (< 15 minutes)
         - Decision: SKIP, use cached data ✅
         
10:15:05 - Update after rate limit expires
         - is_in_grace_period() → FALSE (still no grace period)
         - Last fetch: 10:00:05 (15 minutes ago)
         - Rate limiting: PASSED (>15 minutes) ✅
         - Decision: FETCH if needed
```

**Behavior:** Grace period ends exactly 5 minutes after coordinator creation, then normal rate limiting takes over immediately.

---

## Why Grace Period Exists

### 1. **Home Assistant Restart Optimization**

Home Assistant restarts are common operations:
- Manual restarts for configuration changes
- Automatic restarts after updates
- System reboots
- Integration reloads

Without grace period:
- Every area would wait 15 minutes before first fetch
- 6 areas × 15 minutes = potential for prolonged "unavailable" state
- User frustration: "Why is my electricity price integration broken after restart?"

With grace period:
- All areas fetch immediately on restart
- Sensors show data within seconds
- Smooth user experience

### 2. **Configuration Reload Support**

When users change integration settings:
- VAT rate changes
- Currency changes
- Display unit changes
- Area selection changes

The integration reloads (new coordinator created). Without grace period, sensors would be unavailable during the rate limit window, even though the old cache exists. Grace period allows immediate fetch with new configuration.

### 3. **Fallback Chain Recovery**

GE-Spot uses multiple API sources (Nordpool, ENTSOE, Energy Charts, etc.) with fallback:

During normal operation:
- Rate limiting applies to entire area (all sources share the limit)
- If primary fails, must wait 15 minutes before trying fallback

During grace period:
- All fallback sources can be tried immediately
- Higher chance of successful data fetch
- Better reliability during critical post-startup phase

### 4. **Better User Experience**

Users expect integrations to work immediately after:
- HA restarts
- Config changes
- Integration reloads

Grace period meets this expectation by prioritizing **immediate data availability** over **strict rate limiting** during the short window when it matters most.

---

## What Grace Period Does NOT Do

### ❌ Does NOT Bypass Data Validity Checks

Grace period only affects **rate limiting**, not data validity:

```python
# These checks still happen during grace period:
if not data_validity.has_current_interval:
    # This check is NOT bypassed
    # Still requires current interval data
    
if intervals_remaining < SAFETY_BUFFER:
    # This check is NOT bypassed
    # Still enforces safety buffer
```

**Result:** Grace period won't fetch if data is still valid, even if rate limit would normally block.

### ❌ Does NOT Affect Health Checks

Health check scheduling is independent of grace period:

```python
# Health check runs on its own schedule
# Grace period doesn't accelerate or delay health checks
_schedule_health_check()  # Runs at 00:00-01:00 and 13:00-15:00
```

### ❌ Does NOT Apply to Manual Force Fetch

`force=True` bypasses rate limiting regardless of grace period:

```python
if force:
    # Grace period check not even consulted
    # Force bypasses everything
```

Grace period is only consulted for **normal automatic fetches**.

### ❌ Does NOT Prevent API Errors

Grace period allows fetches to happen, but doesn't make them succeed:

```python
# During grace period:
rate_limiter → BYPASSED ✅
API fetch → MAY STILL FAIL ❌
```

If all API sources fail during grace period, sensors will still show "unavailable".

### ❌ Does NOT Extend Beyond 5 Minutes

Grace period is strictly time-limited:

```python
if time_since_creation < timedelta(minutes=5):
    return True  # In grace period
else:
    return False  # Grace period expired
```

No exceptions, no extensions. After 5 minutes, normal rate limiting applies.

---

## Edge Cases and Safeguards

### 1. Clock Skew Protection

```python
try:
    now = dt_util.utcnow()
    time_since_creation = now - self._coordinator_created_at
    grace_period = timedelta(minutes=5)
    return time_since_creation < grace_period
except (TypeError, AttributeError):
    # If anything fails, assume no grace period
    return False
```

**Protection:** If time calculation fails (clock skew, invalid timestamps), default to **no grace period** (safer).

### 2. Multiple Coordinator Instances

Each coordinator has its own independent grace period:

```
Coordinator for SE1:
  Created at: 10:00:00
  Grace period: 10:00:00 - 10:05:00

Coordinator for SE2:
  Created at: 10:00:03
  Grace period: 10:00:03 - 10:05:03

Coordinator for SE3:
  Created at: 10:00:05
  Grace period: 10:00:05 - 10:05:05
```

**Benefit:** Each area can fetch independently during its own grace period.

### 3. Rapid Reload Protection

If user repeatedly reloads configuration:

```
10:00:00 - Reload 1 → Grace period 10:00-10:05
10:01:00 - Reload 2 → Grace period 10:01-10:06
10:02:00 - Reload 3 → Grace period 10:02-10:07
```

**What Happens:**
- Each reload creates a new coordinator with new grace period
- Each grace period allows one immediate fetch
- After 5 minutes from creation, normal rate limiting applies

**Why This is OK:**
- Config reloads are rare user-initiated actions
- Brief API burst is acceptable during troubleshooting
- Alternative would be worse (sensors unavailable during config changes)

### 4. Grace Period During Special Windows

Grace period and special windows (00:00-01:00, 13:00-15:00) are independent:

```
13:30:00 - HA restart (inside special window)
         - Grace period: 13:30 - 13:35 ✅
         - Special window: 13:00 - 15:00 ✅
         - Both apply simultaneously
         
13:35:01 - Grace period expires
         - Grace period: EXPIRED ❌
         - Special window: STILL ACTIVE ✅
         - Special window rules now apply
```

**Result:** During overlap, both mechanisms encourage fetching (reinforcing effect).

---

## Logging and Debugging

### Grace Period Active Logs

```
INFO: [SE1] Data will update within 15 minutes (rate limit protection 
      active after configuration reload). Reason: Rate limited: Last 
      fetch 2 minutes ago
```

**Indicates:** Grace period is active, rate limiting noted but bypassed.

### Grace Period Expired Logs

```
ERROR: Fetch skipped for SE1 but no cached data available. 
       Reason: Rate limited: Last fetch 5 minutes ago
```

**Indicates:** Grace period has expired, rate limiting is enforced, and no cache fallback available.

### Grace Period Bypass Logs

```
DEBUG: Rate limiting [SE1]: ALLOWING fetch - Within grace period after 
       startup - bypassing rate limiting for fallback attempts
```

**Indicates:** Rate limiter explicitly bypassed due to grace period.

---

## Performance Impact

### API Request Rate During Grace Period

**Normal Operation (no grace period):**
```
Fetches per area: 2-3 per day
  - 00:00-01:00 window: 1 fetch (today's data)
  - 13:00-15:00 window: 1 fetch (tomorrow's data)
  - Occasional safety buffer fetch: 0-1 per day
```

**During Grace Period (5 minutes after restart):**
```
Fetches per area: 1 immediate fetch
  - Tries all sources in fallback chain if needed
  - May retry if first attempt fails (still within grace period)
  
Maximum burst: 6 areas × 3 sources = 18 API calls in first minute
Typical burst: 6 areas × 1 source = 6 API calls in first minute
```

**Impact:** Brief spike in API usage during HA restart, then returns to normal.

### Memory Impact

**Grace Period Tracking:**
```python
# Per coordinator:
self._coordinator_created_at = datetime  # 24 bytes
```

**Total:** Negligible (24 bytes × number of areas)

### CPU Impact

**Grace Period Check:**
```python
def is_in_grace_period(self) -> bool:
    now = dt_util.utcnow()  # Fast
    time_since_creation = now - self._coordinator_created_at  # Fast
    return time_since_creation < grace_period  # Fast comparison
```

**Cost:** <0.001ms per check, called 1-2 times per sensor update.

---

## Configuration

### Current Configuration

**File:** `custom_components/ge_spot/const/network.py`

```python
class Network:
    class Defaults:
        GRACE_PERIOD_MINUTES = 5
```

### Recommended Values

| Scenario | Recommended Value | Reasoning |
|----------|------------------|-----------|
| **Default** | 5 minutes | Covers typical HA restart + sensor initialization |
| **Slow system** | 10 minutes | More time for slow startup on RPi, etc. |
| **Fast system** | 3 minutes | Faster transition to normal operation |
| **Testing** | 1 minute | Quick testing of grace period expiration |
| **Disable** | 0 minutes | Disable grace period entirely |

### To Modify

1. Edit `custom_components/ge_spot/const/network.py`
2. Change `GRACE_PERIOD_MINUTES` value
3. Restart Home Assistant
4. New coordinators will use new value

---

## Summary

**Grace Period is a simple but effective mechanism:**

1. **What:** 5-minute window after coordinator creation
2. **When:** Triggered by HA restart, config reload, or integration reload
3. **Why:** Allows immediate data fetching without rate limiting
4. **How:** Bypasses rate limiter when `is_in_grace_period() == True`
5. **Scope:** Only affects rate limiting, not data validity or health checks
6. **Impact:** Better UX during common operations (restart/reload)
7. **Trade-off:** Brief API usage spike vs. prolonged sensor unavailability

**Bottom Line:** Grace period ensures users see fresh electricity prices within seconds of HA restart, not 15 minutes later. This is a reasonable trade-off for a critical user-facing integration.

---

## Related Documentation

- [Daily Health Check Feature](DAILY_HEALTH_CHECK_FEATURE.md) - Source validation mechanism
- [Implicit Validation Implementation](IMPLICIT_VALIDATION_IMPLEMENTATION.md) - Source filtering logic
- [Timezone Data Validity Fix](TIMEZONE_DATA_VALIDITY_FIX.md) - Data validity tracking

---

**Document Status:** ✅ Complete and accurate as of codebase trace on October 11, 2025
