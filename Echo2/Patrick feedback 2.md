## Key takeaways

- Miles demonstrated significant progress on the Cloud Code CRM system after 5 days of development, including filterable views, custom fields, role management, and pipeline dashboards
- The system now supports dynamic screeners, saved views, custom field creation, and user role assignments with granular permissions
- Patrick provided strategic direction to consolidate functionality, reuse the dynamic table component across modules, and prepare for multi-tenant architecture
- Discussion focused on making the system more flexible through field type expansion, calculated fields, and dynamic distribution lists
- Long-term vision includes potentially offering the CRM as a product to RIAs and other clients, with embedded research and data capabilities

## Brainstorm topics

### Filterable Views and Screeners

**Miles**: Demonstrated new filtering capabilities for organizations and leads with saveable screeners
- **Details**
    - Miles: Users can filter by multiple criteria, add/remove columns, and save custom views as screeners
    - Miles: System automatically returns to default view after saving, but saved screeners preserve column configurations
    - Miles: Added summary functionality to show filtered results count
    - Miles: Implemented filtering for leads by owner and date ranges
- **Conclusion**
    - Filterable views are functional across organizations and leads modules
    - Saved screeners preserve user preferences for future use

### Custom Fields and Admin Portal

**Miles**: Showcased custom field creation with various field types and admin role management
- **Details**
    - Miles: Users can add custom fields to any entity type with multiple field types including text, number, currency, date, boolean, dropdown, multi-select, email, URL, phone, and lookup
    - Miles: Fields can be assigned to sections within entity layouts
    - Miles: Admin portal allows role creation and permission assignment
    - Miles: Discovered issue where custom fields appear in tables but not in edit forms
- **Conclusion**
    - Custom field infrastructure is in place but needs refinement
    - Action item identified to ensure custom fields appear in edit forms

### Field Configuration Architecture

**Patrick**: Proposed removing sections from field definitions and making them layout-specific
- **Details**
    - Patrick: Sections should only exist at the layout level, not hardcoded into field definitions
    - Patrick: This allows multiple layouts for the same entity type without field duplication
    - Miles: Agreed this approach provides more flexibility
    - Patrick: Field-level dependencies should control visibility based on other field values
- **Conclusion**
    - Fields should be agnostic to sections
    - Layouts should organize fields into sections
    - Field visibility and suggestions should be conditional based on other field values

### Conditional Field Visibility

**Patrick**: Suggested implementing field visibility and requirement logic based on other field values
- **Details**
    - Patrick: Fields should be visible or hidden based on criteria from other fields
    - Patrick: Suggested fields should appear when certain conditions are met rather than being required
    - Patrick: Required fields should remain static to avoid complications with editable screeners
    - Miles: Understood the need to store dependency information at the field level
- **Conclusion**
    - Implement visibility conditions: fields appear/disappear based on other field values
    - Implement suggestion conditions: fields become suggested based on criteria
    - Keep required fields static to maintain screener functionality

### Column Resizing and Editable Grids

**Patrick**: Requested ability to resize columns and discussed editable grid functionality
- **Details**
    - Patrick: Users should be able to resize columns in table views
    - Patrick: Discussed two approaches for editing: converting entire grid to editable Excel-style format or pop-up editors for individual rows
    - Miles: Expressed concern about click targets and user experience with inline editing
    - Patrick: Emphasized importance of bulk editing without switching between screens
- **Conclusion**
    - Add column resizing capability
    - Explore feasibility of either bulk editable grid or individual row pop-up editors
    - Priority is enabling quick edits across multiple records without page navigation

### Activities and Task Management

**Miles**: Demonstrated activity tracking with follow-up assignments
- **Details**
    - Miles: Activities can be created with follow-up requirements and assigned to other users
    - Miles: System supports filtering activities by follow-up status and assignee
    - Miles: Tasks appear in assigned user's task list
    - Patrick: Confirmed functionality works as expected
- **Conclusion**
    - Activity and task assignment functionality is operational
    - Follow-up tracking integrates with user task lists

### Pipeline Dashboards and Analysis

**Miles**: Showcased dynamic pipeline visualization with grouping and filtering
- **Details**
    - Miles: Pipeline can be grouped by stage, service type, owner, asset class, or fund
    - Miles: Clicking on pipeline segments shows detailed lead information
    - Miles: Filters at top allow drilling down into specific segments
    - Miles: Discovered discrepancy between active and inactive leads in counts
- **Conclusion**
    - Pipeline dashboards provide flexible analysis views
    - Need to filter for active leads by default and make status filter explicit

### Reusable Dynamic Table Component

**Patrick**: Proposed reusing the leads table component across all modules
- **Details**
    - Patrick: The dynamic table with sorting, filtering, and column selection should be the gold standard
    - Patrick: Same table should be used for activities, people, organizations, and within dashboard drill-downs
    - Patrick: Distribution list creation should also leverage this table component
    - Miles: Confirmed all current tables use the same underlying structure
- **Conclusion**
    - Standardize on the dynamic table component across all modules
    - Replace static tables in pipeline analysis with the dynamic table
    - Use same component for distribution list member selection

### Dynamic Pipeline Grouping

**Patrick**: Suggested making pipeline grouping fully dynamic based on field types
- **Details**
    - Patrick: Any dropdown or multi-select field should automatically appear as grouping option
    - Miles: Confirmed current implementation uses multi-select fields
    - Patrick: Recommended including both dropdown and multi-select field types
    - Miles: Believed this was already implemented but would verify
- **Conclusion**
    - Pipeline grouping should automatically include all dropdown and multi-select fields
    - Custom fields with these types should automatically appear as grouping options
    - Consider adding field-level exclusion flag if needed in future

### Duplicate Detection

**Miles**: Demonstrated duplicate detection functionality for organizations
- **Details**
    - Miles: System identifies potential duplicates with similarity scoring
    - Miles: Actions should include merge, delete record A, or delete record B options
    - Miles: Similarity scoring needs refinement
    - Patrick: Acknowledged this needs further work before being production-ready
- **Conclusion**
    - Duplicate detection framework exists but needs improvement
    - Similarity algorithm requires tuning
    - Merge functionality needs to be implemented

### Reference Data and Field Management Consolidation

**Patrick**: Proposed merging reference data management into the fields interface
- **Details**
    - Patrick: Lead stages and other reference data should be managed within field definitions
    - Patrick: When field type is dropdown, the dropdown values should be configurable in the same interface
    - Patrick: This eliminates need for separate reference data section
    - Miles: Understood the consolidation approach
- **Conclusion**
    - Merge reference data management into fields section
    - Dropdown field type should expose value management options
    - Simplifies admin interface by reducing separate configuration areas

### Calculated Field Types

**Patrick**: Proposed adding calculated fields that pull data from related entities
- **Details**
    - Patrick: Calculated fields could show organization city for people records
    - Patrick: Could display counts like number of owners for a lead
    - Patrick: Concern about performance impact from joining tables
    - Miles: Suggested this might be implemented through field-level joins
- **Conclusion**
    - Add calculated field type to field options
    - Calculated fields join data from related entities
    - Need to test performance impact before broad implementation

### Multiple Text Strings Field Type

**Patrick**: Proposed new field type for storing multiple text variations
- **Details**
    - Patrick: Use case is storing organization nicknames and abbreviations
    - Patrick: Example: Orange County, OCERS, OC ERS all referring to same entity
    - Patrick: All variations should be searchable and return the same entity
    - Patrick: Field should allow adding unlimited text strings
    - Miles: Understood as text multiple select with add more functionality
- **Conclusion**
    - Create new field type for multiple text strings or aliases
    - All stored strings should be searchable
    - Display all variations when viewing entity
    - Serves as test case for field type flexibility

### Shared Views and Team Screeners

**Patrick**: Discussed sharing saved views across teams
- **Details**
    - Miles: System already supports sharing screeners with team when saving
    - Miles: Suggested adding team views section separate from private views
    - Patrick: Confirmed this approach makes sense
    - Miles: Similar pattern exists for distribution lists with private vs official lists
- **Conclusion**
    - View sharing functionality exists
    - Need to implement team views section for discoverability
    - Pattern mirrors distribution list private vs official structure

### Distribution List Architecture

**Patrick**: Proposed making distribution lists dynamic with snapshot capability
- **Details**
    - Patrick: Distribution lists should work like saved screeners
    - Patrick: Users should choose between dynamic lists that update automatically or static snapshots
    - Patrick: Static snapshots should allow manual additions
    - Patrick: Use case: create filtered list of 53 conference invitees, then manually add 12 more
    - Miles: Understood distinction between dynamic filters and static snapshots
- **Conclusion**
    - Distribution lists should support both dynamic and static modes
    - Dynamic lists update automatically based on filters
    - Static lists are snapshots that allow manual additions
    - Reuse same filtering technology as leads module

### Multi-Tenant Architecture

**Patrick**: Proposed implementing global admin level for multiple clients
- **Details**
    - Patrick: Create master admin level to provision multiple clients
    - Patrick: Each client gets their own admin who provisions their users
    - Patrick: Acknowledges this may face internal resistance as company is not a software firm
    - Patrick: Believes now is the right time to implement this architecture
    - Miles: Questioned whether offering CRM or data to other clients
- **Conclusion**
    - Implement multi-tenant architecture in phase one
    - Start by thinking of it as CRM offering to other organizations
    - Can later layer in data offerings including proprietary and third-party data
    - Patrick will handle internal stakeholder management

### RIA Market Opportunity

**Patrick**: Explored offering CRM to RIAs as value-add and marketing tool
- **Details**
    - Patrick: Previous Max Light concept for RIAs was not valuable enough
    - Patrick: Full CRM could be much bigger value proposition
    - Patrick: Could offer free to small RIAs allocating to interval funds
    - Patrick: Could embed research and alts information over time
    - Patrick: Serves as both value-add and marketing tool to get on their desktop
    - Miles: Saw potential for tracking allocations and commitments
- **Conclusion**
    - CRM offering to RIAs could be significant opportunity
    - Provides more value than previous limited data offerings
    - Can evolve to include research and alternative investment information
    - Positions company on RIA desktops as trusted tool

### Document Management

**Miles**: Mentioned document module for organizations and people
- **Details**
    - Miles: Document module now exists for organizations and people
    - Miles: Could track fee arrangements and fund assignments
    - Miles: Potential for allocation tracking against total allocation targets
- **Conclusion**
    - Document management capability is in place
    - Can be extended for various tracking use cases

### Navigation and UI Consolidation

**Patrick**: Suggested consolidating navigation and reducing toolbar items
- **Details**
    - Patrick: Core functions are view individual record, edit individual record, view/edit all records of a type, and flexible dashboards
    - Patrick: Left toolbar should shrink as functionality consolidates
    - Patrick: Admin functions could move to dedicated admin section
    - Miles: Agreed simplification would improve navigation
- **Conclusion**
    - Focus on consolidating core viewing and editing patterns
    - Reduce number of top-level navigation items
    - Move admin functions to separate area
    - Prioritize simplicity as features expand

## Action items

- **Miles**
    - [x] Ensure custom fields appear as editable in basic information edit forms, not just in tables
    - [x] Add ability to resize columns in table views
    - [x] Investigate feasibility of bulk editor on screener or individual mini pop-up editor for quick edits — implemented pop-up row editor
    - [x] Add linked organization fields to people screener columns
    - [x] Remove sections from field definitions and make them layout-specific only
    - [x] Develop default layouts based on existing sections
    - [x] Implement field visibility and suggestion conditions based on other field values
    - [x] Investigate performance impact of filtering people by organization attributes through table joins — implemented as virtual columns with batch resolution
    - [x] Replace static pipeline analysis table with dynamic customizable table component
    - [x] Make pipeline grouping automatically include all dropdown and multi-select fields, including custom ones
    - [x] Add stage filter to top filter bar in pipeline view
    - [x] Change pipeline view to show only active leads by default with explicit active/inactive filter
    - [x] Merge reference data management into fields section, making dropdown values configurable within field type
    - [x] Add calculated field type for pulling data from related entities — implemented as specific virtual columns (org fields on people/leads, aggregates on orgs)
    - [x] Create multiple text strings field type for storing aliases and nicknames
    - [x] Implement team views section for shared screeners separate from private views
    - [x] Add option for distribution lists to be either dynamic or static
    - [x] Integrate distribution list creation with people module filtering
    - [x] Allow manual additions to static snapshot distribution lists
    - [x] Automatically show current members when adding people to distribution lists
    - [ ] Test and refine duplicate detection similarity scoring algorithm — deferred per Patrick
    - [ ] Implement merge functionality for duplicate records — deferred per Patrick
    - [ ] Review Patrick's message about multi-tenant architecture and phase one priorities — deferred (Patrick said "Not Phase 1")
    - [x] Review meeting transcript to ensure full understanding of all discussed items
    - [ ] Focus remaining work day on non-CRM job responsibilities
- **Patrick**
    - [ ] Send updated leads format with final tweaks and copy Miles
    - [ ] Schedule call with Miles when ready to discuss field architecture in detail
