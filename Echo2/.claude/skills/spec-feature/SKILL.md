---
name: spec-feature
description: Interactively spec out a new CRM feature, module, or enhancement by asking structured questions, analyzing the current codebase, and producing a complete implementation plan. Use when the user says things like "I want to add...", "let's spec out...", "new module for...", "Patrick wants..."
argument-hint: [feature description]
---

# CRM Feature Specification Skill

You are helping spec out a new feature or module for Echo 2.0, a CRM system for Aksia (an investment management firm). Your goal is to conduct a structured interview that produces a complete, implementable specification — similar to what would take weeks with spreadsheets, but done in minutes.

## Step 0: Understand the Request

Read `CLAUDE.md` to understand the full project architecture, tech stack, and coding standards.

Read `DATA_IMPORT_PLAN.md` if it exists — it contains the latest decisions about lead types, field naming conventions, and architectural patterns.

Then briefly summarize what you understand the user wants, and confirm before proceeding.

## Step 1: Codebase Analysis (do this BEFORE asking questions)

Silently analyze the relevant parts of the codebase to understand what already exists. Based on the feature description:

1. **Check existing schema** — Read `echo2/db/schema.sql` for relevant tables
2. **Check existing routers** — Glob for `echo2/routers/*.py` and read any that touch the feature area
3. **Check field definitions** — Read `echo2/scripts/seed_field_definitions.py` for existing field patterns
4. **Check reference data** — Grep `echo2/db/schema.sql` for relevant `reference_data` categories
5. **Check form service** — Read `echo2/services/form_service.py` for visibility rule patterns
6. **Check grid service** — Read `echo2/services/grid_service.py` for entity configuration patterns
7. **Check templates** — Glob for relevant template files

Summarize what you found: what exists, what's reusable, what would need to change.

## Step 2: Structured Interview

Ask questions in focused rounds. Use the AskUserQuestion tool for each round. Tailor questions based on what you learned in Step 1 — don't ask about things that are already decided or obvious from the code.

### Round 1: Scope & Entity Model
Ask about:
- What entity/entities does this feature involve? (New table? Extension of existing? Relationship between existing?)
- Who are the primary users? Which roles need access?
- What's the core workflow? (Create → Edit → ... → Archive?)
- Is there a lifecycle/stages/statuses? If so, what are they?

### Round 2: Fields & Data
Based on Round 1 answers, ask about:
- What are the key fields? For each, probe: name, type (text/number/date/dropdown/multi-select/lookup/boolean/currency), required vs optional, any visibility conditions
- Where do dropdown values come from? (Existing reference_data? New category? Dynamic from another table?)
- Are there relationships to other entities? (FK to organizations? People? Leads?)
- Any computed/derived fields? (Rollups, counts, aggregations?)
- Character limits or validation rules?

### Round 3: Business Rules & Logic
Based on Rounds 1-2:
- Are there stage-gated field requirements? (e.g., "required at Focus+")
- Conditional visibility? (e.g., "only when service_type = X")
- Auto-population rules? (e.g., "default to today when status changes")
- Permission restrictions? (e.g., "only Legal can edit")
- Any automation? (Auto-create tasks? Auto-transition statuses? Auto-add to lists?)
- Integration with existing features? (Dashboard widgets? Grid columns? Activity linking?)

### Round 4: UI & Navigation
Based on all prior rounds:
- Where does this appear in the sidebar navigation?
- List view: what are the default grid columns? Sortable? Filterable?
- Detail view: what sections/cards should the page have?
- Form: any special form behavior? (HTMX autocomplete? Multi-select chips? Conditional sections?)
- Any dashboard integration needed?
- Screener/saved view support?

### Round 5: Edge Cases & Rollout
- What happens to existing data? (Migration needed?)
- Are there any known edge cases the stakeholder has mentioned?
- Phase 1 vs Phase 2? What's MVP vs nice-to-have?
- Any fields or logic that are "TBD" / "ask [person]"?

**Important interviewing principles:**
- Skip questions that are already answered by the codebase analysis or prior answers
- If the user says "same as [existing module]", reference that module's pattern instead of re-asking
- Offer smart defaults based on existing patterns (e.g., "Like leads, this should probably have soft deletes and audit logging — confirm?")
- When asking about fields, show what similar entities use as a starting point
- Keep rounds focused — 3-5 questions max per round
- If the user brings a stakeholder into the conversation, adjust your language to be less technical

## Step 3: Generate Specification

After the interview, produce a complete specification document. Write it to `echo2/specs/[feature-name].md` with this structure:

```markdown
# [Feature Name] — Specification

**Specced by:** [stakeholder name if mentioned]
**Date:** [today]
**Status:** Ready for implementation

## Overview
[1-2 sentence summary]

## Entity Model
### Table: [table_name]
| Column | Type | Required | Default | Notes |
|--------|------|----------|---------|-------|
| ... |

### Relationships
- [FK relationships, junction tables]

## Reference Data
| Category | Values |
|----------|--------|
| ... |

## Field Definitions
| Field | Type | Section | Required | Visibility | Suggested | Notes |
|-------|------|---------|----------|-----------|-----------|-------|
| ... |

## Business Rules
1. [Rule with clear trigger → action format]
2. ...

## Permissions
| Role | Can View | Can Create | Can Edit | Can Archive | Special |
|------|----------|-----------|----------|-------------|---------|
| ... |

## UI Specification
### Navigation
- Sidebar position: ...
### List View (Grid)
- Default columns: ...
- Default sort: ...
- Filters: ...
### Detail View
- Sections: ...
### Form
- Sections: ...
- Conditional logic: ...

## Dashboard Integration
[If applicable]

## Migration / Data Considerations
[If applicable]

## Open Questions
- [ ] [Anything still TBD]

## Implementation Checklist
- [ ] Schema (schema.sql + migrate_schema.sql)
- [ ] Reference data seeds
- [ ] Field definitions seed
- [ ] Router (CRUD + business logic)
- [ ] Templates (list, detail, form + partials)
- [ ] Grid service config (default columns, sort, virtual columns)
- [ ] Form service (visibility rules, validation)
- [ ] Sidebar navigation (base.html)
- [ ] Dashboard widgets (if applicable)
- [ ] Seed data updates
- [ ] Admin view configs
```

## Step 4: Review & Iterate

Present the spec summary to the user. Ask if anything needs to change. Iterate until they approve.

When approved, ask: "Ready to implement, or save the spec for later?"

If implementing now, create a plan and proceed step by step, committing after each major piece (schema → router → templates → integration).

## Patterns to Reuse

When designing new features, default to these Echo 2.0 patterns unless the user specifies otherwise:

- **Soft deletes:** `is_archived BOOLEAN DEFAULT FALSE` — never SQL DELETE
- **Audit logging:** Every field change → `audit_log` table via `audit_changes()`
- **Auth:** `require_role()` on every route, `get_current_user` dependency injection
- **Dropdowns:** Always from `reference_data` table, never hardcoded
- **Forms:** Dynamic via `field_definitions` + `form_service.py` (`build_form_context`, `parse_form_data`, `validate_form_data`, `save_record`)
- **Grids:** Via `grid_service.py` + `build_grid_context()` with screeners, column filters, export
- **HTMX:** Return partials when `HX-Request` header present, full pages otherwise
- **Route ordering:** Static paths (`/new`, `/my-items`) BEFORE `/{id}` catch-all
- **DB access:** Always through `db/client.py` via `get_supabase()`
- **UUID PKs:** All tables use `id UUID PRIMARY KEY DEFAULT uuid_generate_v4()`
- **Timestamps:** `created_at TIMESTAMPTZ DEFAULT now()`, `updated_at TIMESTAMPTZ DEFAULT now()`
- **Multi-owner:** Junction table pattern (like `lead_owners`)
- **Stage gating:** Visibility rules with `min_stage` in field_definitions
- **Conditional fields:** Visibility rules with `when`/`equals`/`in`/`not_in`
- **Suggested fields:** `suggestion_rules` JSONB for amber-highlighted non-blocking suggestions
