# Research Workflow Redesign

**Date:** 2026-02-22
**Status:** Approved

## Problem

The current `company_research.py` produces shallow output:
- Resume context is a hardcoded 2-sentence blurb — talking points aren't grounded in Meghan's actual experience
- Search coverage is limited: CEO, HQ, LinkedIn, one generic news query
- Output has 4 sections; new data categories (tech stack, funding, culture, competitors) have nowhere to go
- No skills/keyword config to drive experience matching against the JD

## Approach: Query Expansion + Parallel JSON Searches + Single LLM Pass

Run all searches (companyScraper sequential + new parallel SearXNG JSON queries), aggregate into a structured context block, pre-select resume experiences by keyword score, single LLM call produces all expanded sections.

---

## Design

### 1. Search Pipeline

**Phase 1 — companyScraper (unchanged, sequential)**
- CEO name, HQ address, LinkedIn URL

**Phase 1b — Parallel SearXNG JSON queries (new/expanded)**

Six queries run concurrently via daemon threads:

| Intent | Query pattern |
|---|---|
| Recent news/press | `"{company}" news 2025 2026` |
| Funding & investors | `"{company}" funding round investors Series valuation` |
| Tech stack | `"{company}" tech stack engineering technology platform` |
| Competitors | `"{company}" competitors alternatives vs market` |
| Culture / Glassdoor | `"{company}" glassdoor culture reviews employees` |
| CEO press (if found) | `"{ceo}" "{company}"` |

Each returns 3–4 deduplicated snippets (title + content + URL), labeled by type.
Results are best-effort — any failed query is silently skipped.

---

### 2. Resume Matching

**`config/resume_keywords.yaml`** — three categories, tag-managed via Settings UI:

```yaml
skills:
  - Customer Success
  - Technical Account Management
  - Revenue Operations
  - Salesforce
  - Gainsight
  - data analysis
  - stakeholder management

domains:
  - B2B SaaS
  - enterprise software
  - security / compliance
  - post-sale lifecycle

keywords:
  - QBR
  - churn reduction
  - NRR / ARR
  - onboarding
  - renewal
  - executive sponsorship
  - VOC
```

**Matching logic:**
1. Case-insensitive substring check of all keywords against JD text → `matched_keywords` list
2. Score each experience entry: count of matched keywords appearing in position title + responsibility bullets
3. Top 2 by score → included in prompt as full detail (position, company, period, all bullets)
4. Remaining entries → condensed one-liners ("Founder @ M3 Consulting, 2023–present")

**UpGuard NDA rule** (explicit in prompt): reference as "enterprise security vendor" in general; only name UpGuard directly if the role has a strong security/compliance focus.

---

### 3. LLM Context Block Structure

```
## Role Context
{title} at {company}

## Job Description
{JD text, up to 2500 chars}

## Meghan's Matched Experience
[Top 2 scored experience entries — full detail]

Also in Meghan's background: [remaining entries as one-liners]

## Matched Skills & Keywords
Skills matching this JD: {matched_keywords joined}

## Live Company Data
- CEO: {name}
- HQ: {location}
- LinkedIn: {url}

## News & Press
[snippets]

## Funding & Investors
[snippets]

## Tech Stack
[snippets]

## Competitors
[snippets]

## Culture & Employee Signals
[snippets]
```

---

### 4. Output Sections (7, up from 4)

| Section header | Purpose |
|---|---|
| `## Company Overview` | What they do, business model, size/stage, market position |
| `## Leadership & Culture` | CEO background, leadership team, philosophy |
| `## Tech Stack & Product` | What they build, relevant technology, product direction |
| `## Funding & Market Position` | Stage, investors, recent rounds, competitor landscape |
| `## Recent Developments` | News, launches, pivots, exec moves |
| `## Red Flags & Watch-outs` | Culture issues, layoffs, exec departures, financial stress |
| `## Talking Points for Meghan` | 5 role-matched, resume-grounded, UpGuard-aware talking points ready to speak aloud |

Talking points prompt instructs LLM to: cite the specific matched experience by name, reference matched skills, apply UpGuard NDA rule, frame each as a ready-to-speak sentence.

---

### 5. DB Schema Changes

Add columns to `company_research` table:

```sql
ALTER TABLE company_research ADD COLUMN tech_brief TEXT;
ALTER TABLE company_research ADD COLUMN funding_brief TEXT;
ALTER TABLE company_research ADD COLUMN competitors_brief TEXT;
ALTER TABLE company_research ADD COLUMN red_flags TEXT;
```

Existing columns (`company_brief`, `ceo_brief`, `talking_points`, `raw_output`) unchanged.

---

### 6. Settings UI — Skills & Keywords Tab

New tab in `app/pages/2_Settings.py`:
- One expander or subheader per category (Skills, Domains, Keywords)
- Tag chips rendered with `st.pills` or columns of `st.badge`-style buttons with ×
- Inline text input + Add button per category
- Each add/remove saves immediately to `config/resume_keywords.yaml`

---

### 7. Interview Prep UI Changes

`app/pages/6_Interview_Prep.py` — render new sections alongside existing ones:
- Tech Stack & Product (new panel)
- Funding & Market Position (new panel)
- Red Flags & Watch-outs (new panel, visually distinct — e.g. orange/amber)
- Talking Points promoted to top (most useful during a live call)

---

## Files Affected

| File | Change |
|---|---|
| `scripts/company_research.py` | Parallel search queries, resume matching, expanded prompt + sections |
| `scripts/db.py` | Add 4 new columns to `company_research`; update `save_research` / `get_research` |
| `config/resume_keywords.yaml` | New file |
| `config/resume_keywords.yaml.example` | New committed template |
| `app/pages/2_Settings.py` | New Skills & Keywords tab |
| `app/pages/6_Interview_Prep.py` | Render new sections |
| `tests/test_db.py` | Tests for new columns |
| `tests/test_company_research.py` | New test file for matching logic + section parsing |
