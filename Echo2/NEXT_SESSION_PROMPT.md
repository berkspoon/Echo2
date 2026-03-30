# Continuation Prompt for Next Session

Copy and paste this as your first message:

---

We are continuing work on Echo 2.0 data import and Lead V17 implementation. Read these files to get full context:

1. `@CLAUDE.md` — project overview and coding standards
2. `@DATA_IMPORT_PLAN.md` — the comprehensive plan with all decisions, field mappings, and implementation steps
3. `@feedback.md` — testing feedback history

**Where we left off:** All ID→text mappings are complete (source: `Echo Mappings.xlsx`). Implementation has 8 steps (0-7).

**Current blockers:**
- Step 0 (Create Users) needs an active employee list from me — I'll provide it when ready
- Steps 1-3 can start immediately (lead schema, fundraise merger, multi-coverage)
- Steps 4-7 need Step 0 to complete first

**What to start on:** Begin with Step 1 (Lead Schema + V17 Fields). After completing, update SESSION_LOG.md and DATA_IMPORT_PLAN.md, and commit. We will be clearing sessions between steps.

**Custom skill available:** `/spec-feature` — use this to interactively spec out new modules (e.g., clients module) with stakeholders.

---
