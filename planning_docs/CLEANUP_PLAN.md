# Planning Docs Cleanup Plan

This plan captures the keep/merge/remove decision for every document in `planning_docs/` (including subfolders) ahead of the restructuring work.

## Top-Level Files

| File | Decision | Rationale |
|------|----------|-----------|
| `MASTER_MIGRATION_PLAN.md` | Keep | Canonical end-to-end plan that remains the single source of truth for the migration. Will reference it from the cleaned README/master plan. |
| `README.md` | Keep (update) | Needs refreshed navigation and contributor guidance once obsolete docs are removed and reports are consolidated. |
| `IMPLEMENTATION_INSTRUCTIONS.md` | Keep | Still the authoritative checklist for phased implementation; aligns with the master plan and will remain useful to contributors. |
| `CURRENT_STATUS.md` | Keep (revise) | Contains granular phase-by-phase reality checks that match unresolved code (e.g., `price/__init__.py` still uses `hourly_*`). Needs a refresh to reflect current branch status after cleanup. |
| `INTEGRATION_TEST_FIXES.md` | Merge | Roll into the new consolidated integration-test report so there is a single authoritative narrative. |
| `INTEGRATION_TEST_FIXES_COMPLETED.md` | Merge | Same content family as above—fold into the consolidated report. |
| `ALL_INTEGRATION_TEST_FIXES_COMPLETED.md` | Merge | Duplicate/complementary summary; merge into the unified report to avoid repetition. |
| `INTEGRATION_TEST_KEY_FIXES.md` | Merge | Captures partial progress; incorporate into the consolidated report timeline section. |
| `INTEGRATION_TEST_AUDIT_STATUS.md` | Merge | Latest audit snapshot; fold findings into the unified report’s "remaining issues" section. |
| `TEST_REFERENCE_AUDIT.md` | Merge | Details specific broken references that belong in the consolidated integration-test report. |
| `TEST_VALIDATION_REPORT.md` | Merge | Positive validation write-up that should live in the new report’s "final validation" section for a single source of truth. |
| `EV_SMART_CHARGING_COMPATIBILITY.md` | Keep | Targeted integration guidance that is still current and not duplicated elsewhere. |
| `NO_BACKWARD_COMPATIBILITY.md` | Keep | Documents the enforced policy of clean renames; still relevant while migration work is ongoing. |
| `PHASE_6_7_8_AUDIT.md` | Keep (update) | Accurately highlights remaining work—keep as an audit log but refresh cross-links once cleanup completes. |
| `FACT_FINDING_15MIN.md` | Remove | Marked as consolidated in the README; master plan already embeds the essential analysis. |
| `IMPLEMENTATION_PLAN_15MIN.md` | Remove | Superseded by the master plan; referenced in README as obsolete. |
| `GENERIC_NAMING_GUIDE.md` | Remove | Guidance has been merged into the master plan and implementation instructions; flagged as consolidated in README. |

## `completed_phases/` Subfolder

| File | Decision | Rationale |
|------|----------|-----------|
| `completed_phases/` (folder) | Remove (with noted exceptions) | Folder consists of interim status snapshots that are superseded by `CURRENT_STATUS.md` and the master plan. Individual files below cover the lone pieces that might be preserved elsewhere. |
| `completed_phases/ACTUAL_PROGRESS_SUMMARY.md` | Remove | Outdated (claims progress only through Phase 5) and conflicts with newer audits. |
| `completed_phases/API_DATA_RESOLUTION_ANALYSIS.md` | Merge | Contains valuable API research; plan to roll the insights into the "Impact Analysis" section of the master plan before deleting the standalone file. |
| `completed_phases/CRITICAL_PARSER_FIXES_PHASE5.md` | Merge | Detail already referenced in integration documentation; migrate key notes into the consolidated integration-test report timeline. |
| `completed_phases/MIGRATION_SUMMARY.md` | Remove | Redundant with `MASTER_MIGRATION_PLAN.md` executive summary. |
| `completed_phases/PHASE3_COMPLETE_DATA_STRUCTURE.md` | Remove | Snapshot of completed work; master plan now tracks the same deliverables. |
| `completed_phases/PROGRESS_TRACKER.md` | Remove | Duplicates the master plan’s checklist; also contradicts current progress metrics. |

## Remaining Notes

- All integration-test documents marked "Merge" will feed into one new `planning_docs/INTEGRATION_TEST_STATUS_REPORT.md` (name TBD) with the required structure: summary, timeline, remaining issues, final validation.
- Before deleting any "Merge" files, ensure their critical details are captured in either the master plan or the new consolidated report.
- README and `MASTER_MIGRATION_PLAN.md` must be updated after the consolidation to reflect the trimmed document set.
