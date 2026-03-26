# Phase 3: Grid Bulk Operations — Josh Feedback

Read `Echo2/CLAUDE.md` and `Echo2/feedback.md` for full project context. This prompt implements Phase 3 of Josh's feedback: grid bulk operations.

## What Was Done in Phases 1-2
- **Phase 1:** Bug fixes (drill-down column change, DL filter auto-adds everyone)
- **Phase 2:** Dashboard configurability (metric selector, dashboard presets, country group-by, owner filter, hot prospects traction highlighting)

## Phase 3 Tasks

### 3A. Row Selection (Checkboxes + Select All)

**Goal:** Add checkboxes to each grid row and a "Select All" checkbox in the header, enabling users to select multiple records for bulk actions.

**Current code:** `components/_grid.html` renders the data table. Each row has entity-specific cells but no selection mechanism.

**Changes needed:**
1. `templates/components/_grid.html`:
   - Add a checkbox column as the first `<th>` in the header: `<input type="checkbox" id="select-all-{{ grid_container_id }}" onchange="toggleSelectAll(this, '{{ grid_container_id }}')">`.
   - Add a checkbox as the first `<td>` in each row: `<input type="checkbox" class="row-select-{{ grid_container_id }}" value="{{ row.id }}" onchange="updateBulkBar('{{ grid_container_id }}')">`.
   - Do NOT add checkboxes when `is_drilldown` is true (drilldown grids shouldn't have bulk actions).

2. JavaScript functions (inline in `_grid.html` or in a `<script>` block):
   - `toggleSelectAll(checkbox, containerId)` — checks/unchecks all `.row-select-{containerId}` checkboxes.
   - `updateBulkBar(containerId)` — counts selected rows, shows/hides the floating bulk action bar, updates count label.
   - `getSelectedIds(containerId)` — returns array of selected row IDs.

### 3B. Floating Bulk Action Bar

**Goal:** When 1+ rows are selected, show a sticky bar at the bottom of the viewport with "X selected", "Edit Selected", and "Delete Selected" buttons.

**Changes needed:**
1. `templates/components/_grid.html`:
   - Add a hidden floating bar div below the table (inside the grid container):
     ```html
     <div id="bulk-bar-{{ grid_container_id }}" class="hidden fixed bottom-0 left-0 right-0 z-40 bg-white border-t shadow-lg p-3">
       <div class="max-w-7xl mx-auto flex items-center justify-between">
         <span id="bulk-count-{{ grid_container_id }}" class="text-sm font-medium text-gray-700">0 selected</span>
         <div class="flex gap-2">
           <button onclick="bulkEdit('{{ grid_container_id }}', '{{ entity_type }}')" class="px-3 py-1.5 text-sm font-medium rounded-md bg-brand-500 text-white hover:bg-brand-600">Edit Selected</button>
           <button onclick="bulkDelete('{{ grid_container_id }}', '{{ entity_type }}')" class="px-3 py-1.5 text-sm font-medium rounded-md bg-red-500 text-white hover:bg-red-600">Delete Selected</button>
           <button onclick="clearSelection('{{ grid_container_id }}')" class="px-3 py-1.5 text-sm text-gray-600 border border-gray-300 rounded-md hover:bg-gray-50">Clear</button>
         </div>
       </div>
     </div>
     ```
   - `clearSelection(containerId)` — unchecks all, hides bar.

### 3C. Bulk Edit

**Goal:** "Edit Selected" opens a modal where the user picks a field and a new value, then applies that value to all selected records.

**Changes needed:**
1. `routers/views.py`:
   - Add `POST /views/bulk-edit/{entity_type}` endpoint. Accepts: `record_ids` (comma-separated), `field_name`, `field_value`. For each record: loads old record, updates the field, writes audit log. Returns count of updated records.
   - Use `parse_form_data` / `split_core_eav` for proper core vs EAV handling.

2. `templates/components/_grid.html` (or a new `_bulk_edit_modal.html`):
   - Modal with field selector dropdown (populated from visible columns that are editable), value input (type changes based on field type), and Apply button.
   - `bulkEdit(containerId, entityType)` JS function opens the modal, populates the field dropdown from visible columns.
   - On submit, POST to `/views/bulk-edit/{entity_type}` with selected IDs and field/value.
   - On success, trigger `gridRefresh` to reload the grid.

### 3D. Bulk Delete (Soft Delete)

**Goal:** "Delete Selected" confirms and soft-deletes all selected records.

**Changes needed:**
1. `routers/views.py`:
   - Add `POST /views/bulk-delete/{entity_type}` endpoint. Accepts: `record_ids` (comma-separated). For each record: sets `is_deleted = True`, writes audit log entry. Returns count of deleted records. Only admin can bulk delete (reuse `require_role`).

2. `templates/components/_grid.html`:
   - `bulkDelete(containerId, entityType)` JS function shows confirmation dialog ("Are you sure you want to delete X records?"). On confirm, POST to `/views/bulk-delete/{entity_type}`.
   - On success, trigger `gridRefresh`.

## Key Files
- `echo2/templates/components/_grid.html` — grid template (add checkboxes, bulk bar, modals, JS)
- `echo2/routers/views.py` — add bulk-edit and bulk-delete endpoints
- `echo2/services/grid_service.py` — no changes expected (grid query logic unchanged)
- `echo2/db/helpers.py` — `audit_changes()` used for audit logging

## Permissions
- Bulk Edit: same permissions as single-record edit (admin, standard_user, rfp_team — entity-dependent)
- Bulk Delete: admin only (consistent with single-record soft delete)

## After Completing Phase 3
1. Update `Echo2/CLAUDE.md` — add session notes
2. Update `Echo2/feedback.md` — mark items `[x]`
3. Write `Echo2/Phase_4_Josh_Prompt.md` for Data Export to Excel
4. Pause for context clear
