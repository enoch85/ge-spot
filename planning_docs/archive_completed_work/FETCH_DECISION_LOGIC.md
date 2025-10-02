# Fetch Decision Logic - Content-Based Cache Validation

**Date:** October 2, 2025  
**Branch:** 15min  
**Status:** ✅ Active Implementation

---

## 🎯 High-Level Flow

```
┌─────────────────────────────────────────────────────────┐
│  User requests electricity price data                   │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│  Step 1: Check Cache (Content-Based)                    │
│  ✅ NO max_age_minutes filtering!                       │
│                                                          │
│  cache.get_data(area, target_date)                      │
│                                                          │
│  Returns data if exists, regardless of age              │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│  Step 2: Evaluate Cache Content                         │
│                                                          │
│  ✅ has_current_hour_price?                             │
│     Check: cached_data.get("current_price") is not None │
│                                                          │
│  ✅ has_complete_data?                                  │
│     Check: cached_data["statistics"]["complete_data"]   │
│            (True if 20+ hours of data)                  │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│  Step 3: Ask FetchDecisionMaker                         │
│  "Do we NEED to fetch?"                                 │
│                                                          │
│  decision_maker.should_fetch(                           │
│      has_current_hour_price=...,  ← Content check!      │
│      has_complete_data_for_today=... ← Content check!   │
│  )                                                       │
└─────────────────┬───────────────────────────────────────┘
                  │
         ┌────────┴────────┐
         │                 │
         ▼                 ▼
    ┌─────────┐       ┌─────────┐
    │  FALSE  │       │  TRUE   │
    │ (Skip)  │       │ (Fetch) │
    └────┬────┘       └────┬────┘
         │                 │
         │                 ▼
         │     ┌─────────────────────────────┐
         │     │  Step 4: Ask RateLimiter    │
         │     │  "CAN we fetch NOW?"        │
         │     │                             │
         │     │  RateLimiter.should_skip(   │
         │     │      last_fetched=...,      │
         │     │      current_time=...,      │
         │     │      consecutive_failures=..│
         │     │  )                          │
         │     └────┬────────────────────────┘
         │          │
         │     ┌────┴─────┐
         │     │          │
         │     ▼          ▼
         │  ┌──────┐  ┌──────┐
         │  │ SKIP │  │ALLOW │
         │  └───┬──┘  └───┬──┘
         │      │          │
         ▼      ▼          ▼
    ┌────────────────────────────┐
    │  Return Cached Data        │
    │  (if available)            │
    │                            │
    │  OR                        │
    │                            │
    │  Return Error/Wait         │
    │  (if no cache)             │
    └────────────────────────────┘
                            
                            ▼
                    ┌────────────────┐
                    │  Fetch from    │
                    │  API           │
                    │                │
                    │  Store in      │
                    │  Cache         │
                    └────────────────┘
```

---

## 📋 Detailed Logic Breakdown

### Step 1: Cache Lookup (Content-Based) ✅

**File:** `unified_price_manager.py` lines 196-199

```python
# Get current cache status to inform fetch decision
cached_data_for_decision = self._cache_manager.get_data(
    area=self.area,
    target_date=today_date
    # ✅ NO max_age_minutes parameter!
    # Returns data if it exists, regardless of age
)
```

**What this does:**
- ✅ Looks up cache by `area` and `target_date` only
- ✅ NO time-based filtering
- ✅ Returns data if it exists, `None` if not
- ✅ Age is irrelevant at this stage

---

### Step 2: Content Evaluation ✅

**File:** `unified_price_manager.py` lines 201-217

```python
has_current_hour_price_in_cache = False
has_complete_data_for_today_in_cache = False

if cached_data_for_decision:
    # ✅ Content Check 1: Do we have current interval price?
    if cached_data_for_decision.get("current_price") is not None:
        has_current_hour_price_in_cache = True
    
    # ✅ Content Check 2: Do we have complete data (20+ hours)?
    if cached_data_for_decision.get("statistics", {}).get("complete_data", False):
        has_complete_data_for_today_in_cache = True
    
    _LOGGER.debug(
        f"[{self.area}] Decision making: cached_data_for_decision found. "
        f"Current price available in cache: {has_current_hour_price_in_cache}. "
        f"Complete data in cache (20+ hrs): {has_complete_data_for_today_in_cache}."
    )
else:
    _LOGGER.debug(f"[{self.area}] Decision making: no cached_data_for_decision found.")
```

**What this evaluates:**

1. **`has_current_hour_price`**: Do we have a price for RIGHT NOW?
   - Checks: `cached_data.get("current_price") is not None`
   - This is the MOST CRITICAL check
   - If FALSE → We MUST fetch (can't show current price)

2. **`has_complete_data`**: Do we have 20+ hours of price data?
   - Checks: `cached_data["statistics"]["complete_data"] == True`
   - Indicates comprehensive coverage for today/tomorrow
   - If TRUE → Less urgency to fetch

---

### Step 3: Fetch Decision Logic ✅

**File:** `fetch_decision.py` - `should_fetch()` method

```python
def should_fetch(
    self,
    now: datetime,
    last_fetch: Optional[datetime],
    fetch_interval: int,
    has_current_hour_price: bool,      # ← Content check!
    has_complete_data_for_today: bool  # ← Content check!
) -> Tuple[bool, str]:
```

#### Decision Priority (Highest to Lowest):

##### 1️⃣ **CRITICAL: No Current Price** (Highest Priority)
```python
if not has_current_hour_price:
    current_interval_key = self._tz_service.get_current_interval_key()
    reason = f"No cached data for current interval {current_interval_key}, fetching from API"
    _LOGGER.info(reason)
    return True, reason  # ✅ MUST FETCH!
```

**Logic:**
- If we don't have the price for RIGHT NOW → **FETCH IMMEDIATELY**
- This overrides all other checks
- User needs current price to function

---

##### 2️⃣ **Special Time Windows** (13:00-15:00, 00:00-01:00)
```python
hour = now.hour
for start_hour, end_hour in Network.Defaults.SPECIAL_HOUR_WINDOWS:
    if start_hour <= hour < end_hour:
        if not has_current_hour_price:
            reason = f"Special time window ({start_hour}-{end_hour}), no current hour data"
            return True, reason  # ✅ Fetch during special window
        else:
            reason = f"Special window but we have current hour data, skipping"
            return False, reason  # ✅ Skip, already have data
```

**Logic:**
- Special windows = times when new prices are published
- 13:00-15:00 → Tomorrow's prices released
- 00:00-01:00 → Today's new prices released
- If we have current price → Skip (no need to hammer API)
- If we lack current price → Fetch (might be available now)

---

##### 3️⃣ **Rate Limiter Check**
```python
from ..utils.rate_limiter import RateLimiter
should_skip, skip_reason = RateLimiter.should_skip_fetch(
    last_fetched=last_fetch,
    current_time=now,
    min_interval=fetch_interval
)

if should_skip and has_current_hour_price:
    reason = f"Rate limiter suggests skipping: {skip_reason}"
    return False, reason  # ✅ Skip, rate limited + have data
```

**Logic:**
- Rate limiter says "Can we fetch NOW?" (timing control)
- If rate limiter says SKIP **AND** we have current price → **SKIP**
- If rate limiter says SKIP but we DON'T have current price → **FETCH** (critical need overrides)

---

##### 4️⃣ **Complete Data Check**
```python
if has_complete_data_for_today:
    reason = "Valid data for 20+ hours exists. Fetch not needed."
    _LOGGER.debug(reason)
    # Don't set need_api_fetch = True yet
else:
    reason = "Complete_data quota (20+ hours) not met. Fetching new data."
    _LOGGER.info(reason)
    need_api_fetch = True  # ✅ Need more data
```

**Logic:**
- If we have 20+ hours of data → Less urgency to fetch
- If we have < 20 hours → Should fetch to fill gaps
- BUT this is overridden by critical checks (no current price)

---

##### 5️⃣ **Fetch Interval Check**
```python
if not need_api_fetch and last_fetch:
    time_since_fetch = (now - last_fetch).total_seconds() / 60
    if time_since_fetch >= fetch_interval:
        if not has_current_hour_price:
            reason = f"Interval ({fetch_interval} min) passed and no current price"
            need_api_fetch = True  # ✅ Fetch
        elif has_current_hour_price:
            reason = f"Interval passed but current price available. Not fetching."
            _LOGGER.debug(reason)
```

**Logic:**
- If enough time has passed (e.g., 15 minutes)
- **AND** we don't have current price → **FETCH**
- **BUT** if we have current price → **SKIP** (no need yet)

---

##### 6️⃣ **First Fetch (Never Fetched)**
```python
if not need_api_fetch and not last_fetch:
    reason = "Initial startup or forced refresh, fetching from API"
    _LOGGER.info(reason)
    need_api_fetch = True  # ✅ Always fetch on first run
```

**Logic:**
- First time ever running → Must fetch
- No cache exists → Must populate

---

### Step 4: Rate Limiter (Can We Fetch NOW?) ✅

**File:** `rate_limiter.py` - `should_skip_fetch()` method

**Priority Order:**

1. **Never fetched?** → Allow (first fetch)
2. **Failure backoff?** → Skip (prevent hammering during issues)
3. **AEMO market hours?** → Allow (frequent updates needed)
4. **Special time windows?** → Allow (price release times)
5. **Below min interval?** → Skip (too soon)
6. **Interval boundary crossed?** → Allow (new interval, fetch)

**Result:**
- `should_skip = False` → Can fetch now ✅
- `should_skip = True` → Must wait ⏳

---

## 🎯 Decision Tree

```
START: User requests data
│
├─ Step 1: Check cache (no age filtering)
│   ├─ Cache exists? → Go to Step 2
│   └─ No cache? → has_current_hour_price = False
│
├─ Step 2: Evaluate content
│   ├─ has_current_hour_price? (Check: current_price exists)
│   └─ has_complete_data? (Check: 20+ hours coverage)
│
├─ Step 3: FetchDecisionMaker - Do we NEED data?
│   │
│   ├─ ❌ No current_hour_price?
│   │   └─> YES, FETCH IMMEDIATELY (critical!)
│   │
│   ├─ ⏰ In special time window?
│   │   ├─ Has current_hour_price? → NO, skip fetch
│   │   └─ No current_hour_price? → YES, fetch
│   │
│   ├─ 📊 Has complete data (20+ hours)?
│   │   └─> If YES, lean toward skip (less urgency)
│   │
│   ├─ ⏱️ Fetch interval passed?
│   │   ├─ Has current_hour_price? → NO, skip fetch
│   │   └─ No current_hour_price? → YES, fetch
│   │
│   └─ 🆕 Never fetched before?
│       └─> YES, FETCH (initial data)
│
├─ Decision Result: Should Fetch?
│   │
│   ├─ NO → Return cached data
│   │   └─ END
│   │
│   └─ YES → Go to Step 4
│
├─ Step 4: RateLimiter - CAN we fetch NOW?
│   │
│   ├─ 🔴 In failure backoff?
│   │   └─> SKIP (wait for backoff to expire)
│   │
│   ├─ ⏰ AEMO market hours (7-19)?
│   │   └─> ALLOW (frequent updates)
│   │
│   ├─ 🕐 Special time window (0-1, 13-15)?
│   │   └─> ALLOW (price release time)
│   │
│   ├─ ⏱️ Below minimum interval (15 min)?
│   │   └─> SKIP (too soon)
│   │
│   ├─ 🔄 Crossed interval boundary?
│   │   └─> ALLOW (new interval)
│   │
│   └─> ALLOW (default)
│
└─ Fetch Result:
    ├─ ALLOWED → Fetch from API, update cache
    └─ SKIPPED → Use cached data or return error
```

---

## 📊 Example Scenarios

### Scenario 1: Normal Operation with Good Cache ✅

```
Time: 10:30:00
Last Fetch: 10:15:00 (15 minutes ago)

Step 1: Check Cache
  ✅ Cache exists for today_date

Step 2: Evaluate Content
  ✅ has_current_hour_price = True (10:30 price exists)
  ✅ has_complete_data = True (20+ hours)

Step 3: FetchDecisionMaker
  ✅ Has current price → Not critical
  ✅ Has complete data → Not urgent
  ✅ In special window? → No (10:30)
  ✅ Interval passed? → No (only 15 min)
  
  Decision: SKIP fetch

Result: Return cached data ✅
API Call: NO 🚫
```

---

### Scenario 2: Missing Current Price (CRITICAL) 🚨

```
Time: 14:32:00
Last Fetch: 14:15:00 (17 minutes ago)

Step 1: Check Cache
  ✅ Cache exists for today_date

Step 2: Evaluate Content
  ❌ has_current_hour_price = False (14:30 price missing!)
  ✅ has_complete_data = True (20+ hours but not for current)

Step 3: FetchDecisionMaker
  ❌ NO CURRENT PRICE → CRITICAL!
  
  Decision: FETCH IMMEDIATELY (override all other checks)

Step 4: RateLimiter
  ✅ Check if can fetch now
  ✅ 17 min passed > 15 min min_interval → ALLOW
  
Result: Fetch from API ✅
API Call: YES ✅
```

---

### Scenario 3: Special Window + Already Have Data ✅

```
Time: 13:45:00 (In special window 13:00-15:00)
Last Fetch: 13:30:00 (15 minutes ago)

Step 1: Check Cache
  ✅ Cache exists for today_date

Step 2: Evaluate Content
  ✅ has_current_hour_price = True (13:45 price exists)
  ✅ has_complete_data = True

Step 3: FetchDecisionMaker
  ✅ In special window (13-15)
  ✅ But has current_hour_price → Skip
  
  Decision: SKIP fetch (already have what we need)

Result: Return cached data ✅
API Call: NO 🚫
```

---

### Scenario 4: Interval Boundary Crossed 🔄

```
Time: 10:15:00
Last Fetch: 10:00:00 (15 minutes ago)

Step 1: Check Cache
  ✅ Cache exists for today_date

Step 2: Evaluate Content
  ✅ has_current_hour_price = True (10:15 exists from previous fetch)
  ✅ has_complete_data = True

Step 3: FetchDecisionMaker
  ✅ Has current price → Not critical
  ✅ Fetch interval passed → But has price, not urgent
  
  Decision: Evaluate further (not urgent but could refresh)

Step 4: RateLimiter
  ✅ Crossed interval boundary (10:00 → 10:15)
  
  Decision: ALLOW fetch (refresh at boundary)

Result: Fetch from API ✅
API Call: YES ✅
Purpose: Refresh data at natural interval boundary
```

---

### Scenario 5: Rate Limited with Cache 🚫

```
Time: 10:05:00
Last Fetch: 10:00:00 (5 minutes ago)

Step 1: Check Cache
  ✅ Cache exists for today_date

Step 2: Evaluate Content
  ✅ has_current_hour_price = True (10:00 interval price)
  ✅ has_complete_data = True

Step 3: FetchDecisionMaker
  ✅ Has current price → Not critical
  
  Decision: Check rate limiter

Step 4: RateLimiter
  ❌ Only 5 min since last fetch (min: 15 min)
  ❌ SKIP fetch (rate limited)

Result: Return cached data ✅
API Call: NO 🚫
Message: "Rate limited, using cache"
```

---

### Scenario 6: Incomplete Data + Time to Refresh 📈

```
Time: 16:00:00
Last Fetch: 10:00:00 (6 hours ago)

Step 1: Check Cache
  ✅ Cache exists for today_date

Step 2: Evaluate Content
  ✅ has_current_hour_price = True (16:00 exists)
  ❌ has_complete_data = False (only 14 hours, need 20+)

Step 3: FetchDecisionMaker
  ✅ Has current price → Not critical
  ❌ Doesn't have complete data → Should fetch
  ✅ Fetch interval passed → 6 hours >> 15 min
  
  Decision: FETCH (to get more complete data)

Step 4: RateLimiter
  ✅ Well past min interval → ALLOW

Result: Fetch from API ✅
API Call: YES ✅
Purpose: Fill in more price data (get to 20+ hours)
```

---

## 💡 Key Insights

### Content-Based vs Time-Based

**OLD (Time-Based):**
```python
# ❌ Age-based decision
if cache_age > 60 minutes:
    fetch()  # Even if data is valid!
```

**NEW (Content-Based):**
```python
# ✅ Content-based decision
if not has_current_hour_price:
    fetch()  # Only if we need it!
elif not has_complete_data:
    fetch()  # Fill gaps
else:
    use_cache()  # We have what we need
```

### Separation of Concerns

1. **Cache Manager**: "Here's the data (if it exists)"
   - No age filtering
   - Just returns what's there

2. **Fetch Decision Maker**: "Do we NEED more data?"
   - Evaluates content
   - Checks completeness
   - Makes strategic decision

3. **Rate Limiter**: "CAN we fetch NOW?"
   - Enforces timing rules
   - Prevents API hammering
   - Handles failures gracefully

### Priority Rules

**CRITICAL** (always fetch):
- No current_hour_price

**HIGH** (fetch if allowed):
- Never fetched before
- Incomplete data (< 20 hours)

**MEDIUM** (fetch at boundaries):
- Interval boundary crossed
- Special time window

**LOW** (use cache):
- Has current_hour_price
- Has complete data
- Within rate limit window

---

## 🔐 API Protection

Even with content-based validation, we still protect APIs through:

1. ✅ **Cache First** - Always check cache before considering fetch
2. ✅ **Content Evaluation** - Only fetch if data is missing/incomplete
3. ✅ **Fetch Decision** - Strategic evaluation of necessity
4. ✅ **Rate Limiter** - Timing and frequency control
5. ✅ **Global Lock** - One fetch per area at a time
6. ✅ **Backoff** - Exponential delays on failures

**Result:** Intelligent fetching based on need, not arbitrary time limits!

---

## 📝 Summary

### The Flow in Plain English:

1. **Check cache** (no age check, just get the data)
2. **Evaluate content**:
   - "Do I have the price for RIGHT NOW?"
   - "Do I have comprehensive data (20+ hours)?"
3. **Make decision**:
   - If NO current price → **FETCH IMMEDIATELY** (critical)
   - If YES current price + complete data → **USE CACHE** (we're good)
   - If YES current price but incomplete → **CONSIDER FETCHING** (fill gaps)
4. **Check rate limiter**:
   - "Can we fetch RIGHT NOW or too soon?"
   - Apply backoff, special windows, interval boundaries
5. **Execute**:
   - Fetch → Store in cache → Return
   - Skip → Return cached data

### Key Principle:

> **Cache validity is determined by WHAT we have (content),**  
> **not WHEN we got it (time).**

### Why This Works:

- ✅ Electricity prices are self-validating (valid until their timestamp)
- ✅ Current price check ensures we always show relevant data
- ✅ Complete data check ensures comprehensive coverage
- ✅ Rate limiter prevents API abuse
- ✅ All protection mechanisms remain intact
- ✅ Significantly fewer unnecessary API calls

---

**Implementation Status:** ✅ **COMPLETE AND ACTIVE**  
**Documentation:** ✅ **COMPREHENSIVE**  
**Testing:** ✅ **VERIFIED**
