# Echo 2.0 — IT Requests for Data Migration

**Date:** March 30, 2026
**From:** Miles Greenspoon
**Priority:** High — blocks production data import

---

## 1. Power Apps Option Set Mappings (CRITICAL)

We need the numeric ID → display label mapping for these Power Apps option sets. These are used in our CRM data export (EchoData.xlsx) and we cannot import data without them.

### Already Resolved (no IT help needed)
- Organization Entity Type (20 values) — mapped
- Organization Relationship Type (3 values) — mapped
- Coverage Office (4 values) — mapped
- Engagement Status (6 values) — mapped
- Service Type — 3 of 6 confirmed (IM, Advisory, Research)

### Still Needed

**Please provide the ID → label mapping for each of these option sets:**

#### a) Lead Status (Rating)
Could not find this option set in the system. Need to verify by checking specific leads:
| Lead Name | Org | What stage is this lead in? |
|-----------|-----|----------------------------|
| PC Co-Invest | Nest Corporation | ? |
| PC/RA Fund of One | Future Growth Capital | ? |
| EOS - PC - APC | EOS Investimentos | ? |
| NYC - Advisory - PE | NYC Police Pension Fund | ? |
| 1650 Wealth Mgmt - IM - PC - CAPIX | 1650 Wealth Management | ? |
| product | Ninety One | ? |

#### b) Service Type — confirm remaining 3
| ID | Our best guess | Please confirm |
|----|---------------|----------------|
| 4 | Reporting | Lead: "Zurich Insurance Company Ltd - Reporting - PC" |
| 5 | Product | Lead: "Skandia Fonder - Distribution Partnership" |
| 6 | Project | Lead: "RWJ Foundation - Project - PC" |

#### c) Relationship
| ID | Lead (for context) | Org | Label? |
|----|-------------------|-----|--------|
| 1 | PC Co-Invest | Nest Corporation | ? |
| 3 | NYC - Advisory - PE | NYC Police Pension Fund | ? |
| 5 | Test | Bundespensionskasse AG | ? |
| 6 | ESSSuper - IM | ESSSuper | ? |

#### d) RFP Status
| ID | Lead | Org | Label? |
|----|------|-----|--------|
| 1 | State of CT - PE/PC Advisory | State of Connecticut | ? |
| 2 | Global Fund Search - PC - APC | Global Fund Search | ? |
| 3 | PC SMA | Sarawak Sovereign Wealth | ? |
| 4 | PC Co-Invest | Nest Corporation | ? |

#### e) Pricing Proposal Type
| ID | Lead | Org | Label? |
|----|------|-----|--------|
| 1 | NYC - Advisory - PE | NYC Police Pension Fund | ? |
| 2 | OIA - Advisory - HF | Oman Investment Authority | ? |
| 3 | PC Co-Invest | Nest Corporation | ? |

#### f) Risk Weight
| ID | Lead | Org | Label? |
|----|------|-----|--------|
| 1 | State of CT - PE/PC Advisory | State of Connecticut | ? |
| 2 | IM - Co-Invest PE | Afore Profuturo | ? |
| 3 | EOS - PC - APC | EOS Investimentos | ? |

#### g) Waystone Approved
| ID | Lead | Org | Label? |
|----|------|-----|--------|
| 1 | Acclivis - PE - APEC | Acclivis Investment | ? |
| 2 | Products for FO Adviser | PatriCon Principal | ? |
| 3 | PC Co-Invest | Nest Corporation | ? |

#### h) Commitment Status (Internal Client Status / Initial Review)
| ID | Lead | Org | Label? |
|----|------|-----|--------|
| 1 | EOS - PC - APC | EOS Investimentos | ? |
| 2 | EOS - HF - HEDGX Offshore | EOS Investimentos | ? |
| 3 | Evolve - PE - CAPVX Offshore | Evolve | ? |
| 4 | Tesonet - PC - APC | Tesonet Family Office | ? |
| 5 | Harbor Ithaka - Product - PC - APC | Harbor Ithaka Wealth Mgmt | ? |

#### i) Activity Type (cr932_type)
| ID | Count | Example Title | Example Org | Label? |
|----|-------|---------------|-------------|--------|
| 1 | 12,992 | "Ampera (HF) \| Call on Pentwater" | Ampera Invest | ? |
| 2 | 7,152 | "Morgan Stanley CRE Dinner" | Future Growth Capital | ? |
| 3 | 7,226 | "Cold outreach" | Ninety One | ? |
| 4 | 3 | "Email Outreach" | Capital Investment LLC | ? |

---

## 2. Publication Subscription Levels (MEDIUM)

In the People data export, publication columns use values 0, 1, 2. We've confirmed:
- 0 / blank = not in system
- 1 = none (not subscribed)
- 2 = L2

**Question:** Is there an L1 subscription level in the system? We found no value=3 or other indicator for L1 membership. If L1 exists, how is it represented?

---

## 3. Country Value Normalization (LOW)

The CRM uses free-text country names (e.g., "United States of America", "United States", "United Kingdom"). We need a complete list of distinct country values used in the system so we can build a mapping table.

**Can IT export:** `SELECT DISTINCT country FROM organizations WHERE country IS NOT NULL ORDER BY country`

---

## Summary

| Request | Priority | Blocks |
|---------|----------|--------|
| Option set mappings (9 sets, items a-i above) | Critical | All data import |
| L1 publication level clarification | Medium | Distribution list import |
| Country value list | Low | Can work around |
