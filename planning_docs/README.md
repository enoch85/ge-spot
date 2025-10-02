# Planning Documents for 15-Minute Interval Migration

**Status:** Planning Complete  
**Date:** October 1, 2025

---

## 📋 Primary References

1. **`MASTER_MIGRATION_PLAN.md`** – Single source of truth for scope, architecture, and phased work.
2. **`CURRENT_STATUS.md`** – Realistic progress snapshot aligned with the 15min branch.
3. **`INTEGRATION_TEST_STATUS_REPORT.md`** – Consolidated history, outstanding work, and validation guidance for integration testing.
4. **`PHASE_6_7_8_AUDIT.md`** – Deep dive into remaining coordinator/utility TODOs (kept as an audit trail).
5. **`NO_BACKWARD_COMPATIBILITY.md`** – Policy reminder: rename everything cleanly, no aliases.

Additional targeted references:
- `EV_SMART_CHARGING_COMPATIBILITY.md` – Attribute contract for EV Smart Charging integration.
- `CLEANUP_PLAN.md` – Record of the 2025 documentation consolidation (for maintainers).

---

## 🎯 Quick Start

1. Read `MASTER_MIGRATION_PLAN.md` end-to-end.
2. Skim `CURRENT_STATUS.md` to confirm what’s still outstanding.
3. Review the latest findings in `INTEGRATION_TEST_STATUS_REPORT.md` before touching tests.
4. Coordinate with the maintainer, then start at Phase 1 of the master plan.
5. Test after each phase using the guidance in the status report.

---

## 🗑️ After Migration

**Delete this entire folder when done!**

```bash
rm -rf /workspaces/ge-spot/planning_docs/
```

The planning docs are only needed during migration.

---

## 📊 What's in the Master Plan?

- Executive summary
- Complete impact analysis (40+ files)
- Architecture design (configuration-driven)
- 13 implementation phases
- 27 detailed TODOs
- Code examples (good vs bad)
- Testing strategy
- Progress tracking
- FAQ

**Everything you need, all in one place!**

---

## 🗃️ Retired Artifacts

These historical docs were consolidated into the resources above and removed on October 2, 2025: `IMPLEMENTATION_PLAN_15MIN.md`, `FACT_FINDING_15MIN.md`, `GENERIC_NAMING_GUIDE.md`, `MIGRATION_SUMMARY.md`, `PROGRESS_TRACKER.md`, `INTEGRATION_TEST_FIXES*.md`, `TEST_REFERENCE_AUDIT.md`, and `TEST_VALIDATION_REPORT.md`.
