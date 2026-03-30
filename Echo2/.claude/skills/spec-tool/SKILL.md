---
name: spec-tool
description: Structured interview process to spec out a new internal tool or automation. Guides the user through requirements gathering, recommends Power Automate vs Glean Agent vs Claude Code as the build path, and produces an executive summary plus the appropriate build guide. Use when someone says "I want to build...", "can we automate...", "tool idea", "someone asked me to build...", or similar.
argument-hint: [brief description of the tool idea]
---

# Internal Tool Specification Skill

You are helping Miles (or a colleague working with Miles) spec out a new internal tool or automation for Aksia. Your job is to conduct a structured interview that:

1. Clarifies exactly what the requester wants
2. Identifies data sources, users, and constraints
3. Recommends the best build path: **Power Automate** (event-driven workflow automation), **Glean** (AI agent over internal data), or **Claude Code** (custom application)
4. Produces an executive summary (always) plus the appropriate build guide for the chosen path

---

## Step 0: Capture the Initial Idea

Read whatever the user has provided (a Slack message, a verbal description, a forwarded email, etc.) and restate it back in 2-3 sentences. Identify what's clear and what's ambiguous. Then proceed to the interview.

---

## Step 1: Structured Interview

Ask questions using the AskUserQuestion tool in focused rounds. Keep each round to 3-5 questions max. Skip questions that are already answered by what the user provided. Offer smart defaults when possible.

### Round 1: Problem & Users

- **What problem does this solve?** Who does this manually today? How long does it take? What pain does it cause?
- **Who is the end user?** One person? A team? Firmwide? External/client-facing?
- **What triggers the work?** On a schedule (quarterly, daily)? On-demand? In response to an event (new filing, new email, status change)?
- **What does success look like?** What's the output they want? (spreadsheet, email, dashboard, Slack message, document, etc.)

### Round 2: Data Sources & Inputs

- **Where does the input data come from?** Probe specifically:
  - Internal systems Aksia already uses (Glean-indexed): SharePoint, Outlook, Teams, Salesforce, Jira, Confluence, etc.
  - External public sources: SEC EDGAR, company websites, government databases, public APIs
  - External private/authenticated sources: vendor portals, subscription databases (PitchBook, Preqin, Bloomberg, etc.)
  - Manual input: user provides info each time (names, URLs, parameters)
  - Files: uploaded CSVs, PDFs, Excel files
- **Is the data structured or unstructured?** (database/API/spreadsheet vs. PDF/HTML/email body)
- **How much data?** (10 records? 1,000? 100,000?)
- **How often does the source data change?**

### Round 3: Processing & Logic

- **What transformation happens?** Is it simple extraction (pull field X from source Y) or does it require:
  - Parsing unstructured text (PDFs, HTML pages)
  - Calculations or aggregations
  - Comparisons across sources
  - Deduplication or matching
  - Classification or judgment calls
- **Are there business rules?** (e.g., "flag if expense ratio > 2%", "only include funds > $100M AUM")
- **Is a human review step needed before output is final?**
- **Are there error/exception cases?** (source unavailable, data missing, format changed)

### Round 4: Output & Delivery

- **What's the exact output format?** (Excel, CSV, email, Slack message, PDF report, dashboard, web page)
- **What are the specific fields/columns/data points in the output?** Ask for the exhaustive list. If they have an existing spreadsheet or report they fill out manually, ask to see it — that IS the spec.
- **Where does the output go?** (emailed to a DL, posted to Slack, saved to SharePoint, uploaded to a system)
- **Who consumes the output?** (same person, their team, leadership, clients)
- **Frequency?** (one-time, daily, weekly, quarterly, on-demand)

### Round 5: Constraints & Context

- **Timeline?** When do they need this?
- **Sensitivity?** Does it touch PII, NDA-protected data, or client-confidential information?
- **Existing attempts?** Have they tried to solve this before? What worked/didn't?
- **Budget for external services?** (API costs, subscriptions)
- **Maintenance?** Who will own this after it's built? Does it need to be self-service?

**Interviewing principles:**
- If the user says "I'm not sure" on a detail, note it as an open question and move on
- If they reference an existing manual process, ask them to walk through it step by step or share the current output
- Offer concrete examples: "So something like: every quarter, pull NAV and expense ratio from N-PORT filings for these 50 funds, and deliver an Excel file — is that right?"
- Summarize back after each round before moving to the next

---

## Step 2: Build Path Recommendation

After completing the interview, evaluate the requirements against this decision framework:

### Use Power Automate when ALL of these are true:

1. **Trigger is an event in the Microsoft ecosystem**: A new email arrives, a SharePoint file is created/modified, a Forms response is submitted, a Teams message is posted, a calendar event occurs, or a scheduled recurrence
2. **The workflow is deterministic (rule-based, not AI-judgment)**: The logic is "if X then Y" — routing, copying, transforming, approving — not "read this document and decide what it means"
3. **Data flows between Microsoft 365 + supported connectors**: The inputs and outputs live in systems Power Automate connects to natively (Outlook, SharePoint, Excel Online, Teams, OneDrive, Dataverse, SQL Server, HTTP endpoints, and 1,000+ connectors including Salesforce, ServiceNow, etc.)
4. **No AI reasoning or unstructured text parsing needed**: The work is moving data, reformatting fields, sending notifications, creating approvals, or updating records — not summarizing, classifying, or extracting meaning from prose
5. **Output is an action, not a document**: Sending an email, updating a row, posting a message, creating a task, triggering an approval — not generating a report or narrative
6. **Aksia already has Power Automate licenses**: Available through Microsoft 365 E3/E5

**Power Automate flow types to consider:**
- **Automated flow**: Triggered by an event (new email, file created, item modified)
- **Scheduled flow**: Runs on a recurring schedule (daily, weekly, monthly)
- **Instant flow**: Triggered manually (button press in Power Apps, Teams, or SharePoint)
- **Approval flow**: Multi-stage approval routing with built-in approval UI
- **Desktop flow** (Power Automate Desktop): For automating legacy desktop apps or local file operations — use only when cloud flows can't reach the target system

**Power Automate is strongest for:**
- Email routing, filing, and auto-responses
- SharePoint document workflows and metadata management
- Approval chains (expense approvals, document sign-offs, access requests)
- Syncing data between Microsoft 365 apps and external SaaS tools
- Scheduled reminders and notifications
- Form submission processing (Microsoft Forms → SharePoint/Excel/email)
- Simple data transformations between systems (no AI needed)

### Use Glean Agent when ALL of these are true:

1. **The task requires AI reasoning over content**: Summarization, extraction from unstructured documents, Q&A, drafting, classification, or judgment calls that an LLM handles well
2. **Data sources are Glean-indexed or simple web**: The inputs come from systems Glean already connects to (SharePoint, Outlook, Salesforce, Jira, Confluence, Slack, Google Workspace, Snowflake, Zendesk, GitHub) OR simple web pages
3. **Output is text-based**: The deliverable is a message (Slack/email), a document, or a simple structured response — not a complex formatted spreadsheet or custom UI
4. **No external scraping or authenticated external APIs**: Doesn't need to hit SEC EDGAR, PitchBook, Bloomberg, or other external systems that Glean doesn't connect to
5. **No complex data pipeline**: Doesn't require storing state across runs, building a database, or doing multi-step ETL
6. **Volume is small**: Processing dozens of items, not thousands
7. **Non-technical maintainer**: The person who'll own it can work in a no-code builder

**Glean agent types to consider:**
- **Workflow Agent**: Best for structured, repeatable multi-step processes with predictable flow
- **Auto-mode Agent**: Best for flexible tasks where the steps may vary based on what the agent discovers
- **Scheduled Agent**: For recurring tasks (uses Input Form trigger + schedule)

### Use Claude Code when ANY of these are true:

1. **External scraping or APIs**: Needs to pull from public websites (SEC, company sites) or authenticated external services not in Glean or Power Automate connectors
2. **Custom UI needed**: Requires a dashboard, web app, or interactive interface
3. **Complex data processing**: ETL pipelines, large-scale parsing, database storage, calculations across many records
4. **Structured output at scale**: Needs to produce formatted Excel files, CSVs with specific schemas, or populate databases
5. **Custom integrations**: Needs to talk to APIs that neither Glean nor Power Automate support
6. **Persistent state**: Needs to track changes over time, maintain a database, or compare current vs. previous runs
7. **High volume**: Processing hundreds or thousands of records per run
8. **Complex AI + code hybrid**: Needs both LLM reasoning AND custom code, data pipelines, or external scraping that Glean alone can't handle

### Quick Decision Guide:

| Signal | Power Automate | Glean Agent | Claude Code |
|--------|---------------|-------------|-------------|
| "When an email arrives, do X" | **Yes** | | |
| "Approval workflow" | **Yes** | | |
| "Sync data between two systems" | **Yes** | | |
| "Read these docs and summarize" | | **Yes** | |
| "Answer questions about our policies" | | **Yes** | |
| "Draft a response based on context" | | **Yes** | |
| "Scrape data from public websites" | | | **Yes** |
| "Build me a dashboard" | | | **Yes** |
| "Process 1,000 records quarterly" | | | **Yes** |
| "Parse PDFs and load into a database" | | | **Yes** |

### Present the recommendation:

Clearly state which path you recommend and why, referencing specific requirements from the interview. If it's a close call, explain the tradeoffs of each path (e.g., "Power Automate could handle the trigger and routing, but Glean would be better for the summarization step — you could combine both"). Use the AskUserQuestion tool to confirm the path before producing the deliverable.

---

## Step 3: Executive Summary (ALWAYS produce this, regardless of build path)

Before producing the path-specific deliverable, ALWAYS write an executive summary to `[tool-name]-executive-summary.md` in the current directory. This is a non-technical document designed to be shared with the team for awareness, feedback, and buy-in.

```markdown
# [Tool Name] — Executive Summary

**Requested by:** [name if known]
**Prepared by:** [Miles or whoever is running the spec]
**Date:** [today]
**Status:** Proposed

## What Is This Tool?
[2-3 sentence plain-English description. No jargon. A managing director who has never seen a line of code should understand this paragraph.]

## The Problem It Solves
[Describe the current manual process — who does it, how long it takes, what pain it causes. Use concrete numbers where possible: "takes ~8 hours per quarter", "covers 50 interval funds", etc.]

## How It Works (User's Perspective)
[Walk through the experience from the end user's point of view. Step 1, Step 2, Step 3. What do they do? What do they see? What do they get?]

## What It Produces
[Describe the output: "A quarterly Excel report with columns X, Y, Z delivered via email to the [team] distribution list." Be specific.]

## Data Sources
[Bullet list of where the tool gets its information. Flag any sources that require access, subscriptions, or approvals.]

## Build Approach
- **Platform:** [Power Automate Flow / Glean AI Agent / Custom Tool (Claude Code)]
- **Why this approach:** [1-2 sentences explaining the choice in plain terms]
- **Estimated complexity:** [Simple / Moderate / Complex]
- **Maintenance:** [Who owns it after launch, what ongoing upkeep looks like]

## Timeline & Next Steps
1. [Next step — e.g., "Resolve open questions below"]
2. [Next step — e.g., "Build and test MVP"]
3. [Next step — e.g., "Pilot with [team] for one quarter"]

## Open Questions & Feedback Requested
[Bulleted list of unresolved items. Frame these as questions the team can weigh in on:]
- [ ] [Question 1 — e.g., "Should we include offshore feeder funds in scope?"]
- [ ] [Question 2]
- [ ] [Question 3]

## Risks & Dependencies
[Anything that could block or delay this — access approvals, data quality concerns, vendor limitations, etc.]
```

**Writing principles for the exec summary:**
- Write for a non-technical audience — no code, no architecture, no acronyms without explanation
- Lead with the "so what" — why should anyone care about this tool?
- Be specific about the output — vague descriptions like "automates the process" don't help people give feedback
- The Open Questions section is the most important part — this is how the team contributes

---

## Step 4A: Glean Agent Build Guide

If the recommendation is Glean, produce a comprehensive build guide. Write it to a file named `[tool-name]-glean-guide.md` in the current directory.

Structure:

```markdown
# [Tool Name] — Glean Agent Build Guide

**Requested by:** [name if known]
**Date:** [today]
**Agent type:** [Workflow Agent / Auto-mode Agent / Scheduled Agent]

## Overview
[1-2 sentence description of what this agent does]

## Prerequisites
- [ ] Confirm Glean agent creation permissions
- [ ] Confirm required data source connections are active in Glean admin
- [ ] [Any other prerequisites]

## Agent Configuration

### Trigger
- **Type:** [Chat Message / Input Form]
- **Input fields:** [list each field with name, type (Text/Document/Multiple Choice), and description]
- **Schedule:** [if applicable — frequency and timing]

### Step-by-Step Build Instructions

#### Step 1: [Step Name]
- **Action:** [Glean action to use — e.g., Read Document, Web Search, Respond, Think, etc.]
- **Instructions for this step:**
  ```
  [Exact instructions to paste into the step's instruction field.
   Be specific, reference input variables with [[ variable_name ]] syntax.
   Include output format requirements.]
  ```
- **Input references:** [which [[ variables ]] this step uses]
- **Model recommendation:** [default / specific model if reasoning-heavy]

#### Step 2: [Step Name]
[... repeat for each step]

### Flow / Branching
[If the agent needs conditional logic, describe each branch:]
- **Condition:** [what to evaluate]
- **Branch A:** [what happens if true]
- **Branch B:** [what happens if false]

### Sub-agents
[If the workflow is complex enough to benefit from sub-agents, describe each:]
- **Sub-agent:** [name and purpose]
- **Steps within sub-agent:** [brief list]

### Memory Configuration
[For each step, note if it should have access to: Full history / Previous step only / None]

### Output / Write Actions
- **Action:** [Slack DM / Email / etc.]
- **Configuration:** [recipient, format, etc.]

## Testing Plan
1. Test case 1: [description, expected output]
2. Test case 2: [description, expected output]
3. Edge case: [description, expected behavior]

## Sharing & Permissions
- **Visibility:** [who should have access]
- **Publish to:** [Agent Library? Specific team?]

## Maintenance Notes
- [What might break and how to fix it]
- [When to update instructions or data sources]

## Open Questions
- [ ] [Anything still TBD]
```

**Best practices to incorporate in the guide:**
- Start with read/think actions before write actions
- Use the "Enhance prompt" feature on each step after writing initial instructions
- Be explicit in step instructions — don't rely on the LLM to guess parameter mappings
- Use sub-agents to isolate complex reasoning and keep memory focused
- For scheduled agents, always include a write action (Slack/email) since Respond alone won't produce output in background mode
- Test with realistic inputs before publishing
- Set conversation starters if using a Chat Message trigger to guide users

---

## Step 4B: Power Automate Build Guide

If the recommendation is Power Automate, produce a comprehensive build guide. Write it to a file named `[tool-name]-power-automate-guide.md` in the current directory.

Structure:

```markdown
# [Tool Name] — Power Automate Build Guide

**Requested by:** [name if known]
**Date:** [today]
**Flow type:** [Automated / Scheduled / Instant / Approval / Desktop]

## Overview
[1-2 sentence description of what this flow does]

## Prerequisites
- [ ] Confirm Power Automate license type (included with M365 E3/E5, or Premium needed?)
- [ ] Confirm access to required connectors (list which are standard vs. premium)
- [ ] Confirm permissions on target systems (SharePoint site access, mailbox access, etc.)
- [ ] [Any other prerequisites — e.g., SharePoint list must exist, Teams channel must exist]

## Connector Inventory
| Connector | Standard/Premium | Purpose in this flow |
|-----------|-----------------|---------------------|
| [e.g., Outlook 365] | Standard | Trigger: when email arrives |
| [e.g., SharePoint] | Standard | Action: create list item |
| [e.g., HTTP] | Premium | Action: call external API |

## Flow Architecture

### Trigger
- **Type:** [Automated / Scheduled / Instant]
- **Connector:** [which connector provides the trigger]
- **Trigger action:** [e.g., "When a new email arrives (V3)" / "Recurrence - every Monday at 8am"]
- **Trigger conditions:** [any filtering at the trigger level — e.g., subject contains "Report", from specific sender]

### Step-by-Step Build Instructions

Open Power Automate (https://make.powerautomate.com) and follow these steps:

#### Step 1: Create the Flow
1. Click **+ Create** → **[Automated cloud flow / Scheduled cloud flow / Instant cloud flow]**
2. Name the flow: `[descriptive flow name]`
3. Select trigger: **[exact trigger name from connector]**
4. Configure trigger:
   - [Setting 1]: [value]
   - [Setting 2]: [value]

#### Step 2: [Action Name]
1. Click **+ New step**
2. Search for: **[exact action name]**
3. Configure:
   - [Field 1]: [value or dynamic content reference]
   - [Field 2]: [value or dynamic content reference]
4. **Dynamic content used:** [list which dynamic content tokens from previous steps are referenced]

#### Step 3: [Action Name]
[... repeat for each step]

### Conditions / Branching
[If the flow needs conditional logic:]

#### Condition: [what is being evaluated]
- **Left side:** [dynamic content or expression]
- **Operator:** [is equal to / contains / is greater than / etc.]
- **Right side:** [value]
- **If yes:** [describe actions in the Yes branch]
- **If no:** [describe actions in the No branch]

### Loops (Apply to Each / Do Until)
[If the flow processes multiple items:]
- **Apply to each:** [which array/collection]
  - **Actions inside loop:** [list actions]
  - **Concurrency control:** [sequential or parallel, and why]

### Error Handling
- **Configure run after:** [which steps should run even if a previous step fails]
- **Scope blocks:** [group related actions for try/catch-style handling]
- **Retry policy:** [for HTTP or connector actions that may intermittently fail]

### Expressions Used
[List any Power Automate expressions needed, with explanation:]
| Expression | Purpose | Example |
|-----------|---------|---------|
| `formatDateTime(utcNow(), 'yyyy-MM-dd')` | Format today's date | Used in file name |
| `if(equals(triggerBody()?['status'], 'Approved'), 'Yes', 'No')` | Conditional value | Used in email body |

## Variables
[If the flow uses variables:]
| Variable Name | Type | Initial Value | Purpose |
|--------------|------|---------------|---------|
| [varName] | [String/Integer/Boolean/Array] | [value] | [what it tracks] |

## Connections Required
[List each connection the flow creator needs to authenticate:]
1. **[Connector name]** — sign in as [which account/service account]
2. **[Connector name]** — sign in as [which account/service account]

*Note: Flows run under the connection owner's identity. If the flow creator leaves the org, connections must be reassigned.*

## Testing Plan
1. **Happy path:** [description, trigger the flow with normal input, expected outcome]
2. **Edge case:** [description — e.g., empty input, missing field, duplicate entry]
3. **Error path:** [description — e.g., target system unavailable, permission denied]
4. **Schedule verification:** [for scheduled flows — confirm next run time after saving]

## Sharing & Ownership
- **Owner:** [who owns the flow]
- **Co-owners:** [who should have edit access — add as co-owners in flow settings]
- **Run-only users:** [who can trigger the flow but not edit it]
- **Environment:** [Default environment or specific environment]

## Monitoring & Maintenance
- **Run history:** Check at Power Automate → My flows → [flow name] → Run history
- **Failure notifications:** Flow owners receive email on failure by default
- **Common failure causes:**
  - [e.g., "SharePoint list column renamed — update the step referencing it"]
  - [e.g., "Connection expired — re-authenticate in flow connections"]
  - [e.g., "API rate limit hit — add a delay action between calls"]
- **Review schedule:** [how often to check the flow is still running correctly]

## Governance Notes
- [Any DLP policy considerations — e.g., does this flow cross business/non-business data boundaries?]
- [Any premium connector cost implications]
- [Service account vs. personal account considerations]

## Open Questions
- [ ] [Anything still TBD]
```

**Best practices to incorporate in the guide:**
- Use descriptive flow and step names — future maintainers need to understand the flow at a glance
- Add "Compose" actions as intermediate steps to inspect and debug dynamic content during development
- Use Scope blocks to group related steps — enables error handling and makes the flow collapsible/readable
- Set concurrency control on "Apply to each" loops to sequential if order matters or if the target system has rate limits
- Always configure "Run after" settings for cleanup actions (e.g., send failure notification even if a step fails)
- Use environment variables or SharePoint config lists instead of hardcoding values that may change
- For scheduled flows, set the time zone explicitly in the trigger
- Test with the "Test" button using real data before turning on the flow
- Document the flow with a comment action at the top explaining what it does and who requested it

---

## Step 4C: Claude Code Deliverable

If the recommendation is Claude Code, produce TWO deliverables:

### Deliverable 1: PRD

Write a PRD to `[tool-name]-PRD.md` in the current directory:

```markdown
# [Tool Name] — Product Requirements Document

**Requested by:** [name if known]
**Date:** [today]
**Status:** Draft

## 1. Problem Statement
[What problem this solves, who has it, current pain]

## 2. Proposed Solution
[High-level description of the tool]

## 3. Users & Personas
| Persona | Description | Key Needs |
|---------|-------------|-----------|
| ... |

## 4. Data Sources
| Source | Type | Access Method | Auth Required | Notes |
|--------|------|---------------|---------------|-------|
| ... |

## 5. Functional Requirements
### 5.1 Data Collection
- FR-1: [requirement]
- FR-2: [requirement]

### 5.2 Data Processing
- FR-X: [requirement]

### 5.3 Output & Delivery
- FR-X: [requirement]

### 5.4 Scheduling & Automation
- FR-X: [requirement]

## 6. Non-Functional Requirements
- **Performance:** [expected volume, speed]
- **Reliability:** [error handling, retry logic]
- **Security:** [data sensitivity, access control]
- **Maintainability:** [who maintains, how often sources change]

## 7. Technical Architecture (Recommended)
- **Language/Framework:** [recommendation based on requirements]
- **Storage:** [if needed]
- **Hosting:** [where it runs]
- **Key libraries/APIs:** [specific packages]

## 8. Data Model
[Tables, fields, relationships if applicable]

## 9. UI/UX (if applicable)
[Wireframe descriptions or skip if no UI]

## 10. MVP Scope
[What's in v1 vs. what's deferred]

## 11. Open Questions
- [ ] [Anything still TBD]

## 12. Success Metrics
[How to know if this tool is working]
```

### Deliverable 2: Claude Code Build Prompts

Write a prompt guide to `[tool-name]-prompts.md` in the current directory. This is a sequence of prompts the user (or Miles) can paste into Claude Code sessions to build the tool incrementally:

```markdown
# [Tool Name] — Claude Code Build Prompts

Use these prompts in sequence across one or more Claude Code sessions.
Each prompt builds on the previous step. Review and test after each step before proceeding.

## Prerequisites
- [ ] [Environment setup: Python version, API keys, etc.]
- [ ] [Access confirmed: data sources, credentials]

## Prompt 1: Project Setup & Data Source Spike
```
[A complete, self-contained prompt that tells Claude Code to:
- Set up the project structure
- Install dependencies
- Write a proof-of-concept script that connects to the primary data source
- Extract a small sample of the target data
- Print/save the results so the user can verify the approach works]
```

**What to check before moving on:**
- [ ] [Verification steps]

## Prompt 2: Core Data Pipeline
```
[Prompt to build the main extraction/processing logic]
```

**What to check before moving on:**
- [ ] [Verification steps]

## Prompt 3: Output Generation
```
[Prompt to build the output formatting and delivery]
```

**What to check before moving on:**
- [ ] [Verification steps]

## Prompt 4: Error Handling & Edge Cases
```
[Prompt to add robustness]
```

## Prompt 5: Scheduling / Automation
```
[Prompt to set up recurring execution if applicable]
```

## Prompt 6: Documentation & Handoff
```
[Prompt to generate README, usage instructions, and maintenance notes]
```
```

**Prompt-writing principles:**
- Each prompt should be self-contained — assume Claude Code has the project context but not the prior conversation
- Include specific filenames, function names, and architectural decisions from the PRD
- Include "verify by running X" steps so the user can confirm each stage works
- Keep prompts focused on one concern at a time (don't combine data extraction + UI + deployment)
- Reference the PRD by name so Claude Code can read it for context
- Start with the riskiest/most uncertain piece first (usually the data source connection) so the user discovers blockers early

---

## Step 5: Review & Handoff

Present a summary of the deliverable(s) you produced. Ask:

1. Does this accurately capture what [requester] wants?
2. Are there any open questions we should resolve before building?
3. For Power Automate: Would you like to walk through the build steps together?
4. For Glean: Would you like to walk through the build steps together?
5. For Claude Code: Would you like to start with Prompt 1 now?
