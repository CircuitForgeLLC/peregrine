# Research Workflow Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expand company research to gather richer web data (funding, tech stack, competitors, culture/Glassdoor, news), match Alex's resume experience against the JD, and produce a 7-section brief with role-grounded talking points.

**Architecture:** Parallel SearXNG JSON queries (6 types) feed a structured context block alongside tiered resume experience (top-2 scored full, rest condensed) from `config/resume_keywords.yaml`. Single LLM call produces 7 output sections stored in expanded DB columns.

**Tech Stack:** Python threading, requests (SearXNG JSON API at `http://localhost:8888/search?format=json`), PyYAML, SQLite ALTER TABLE migrations, Streamlit `st.pills` / column chips.

**Design doc:** `docs/plans/2026-02-22-research-workflow-design.md`

**Run tests:** `/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v`
**Python:** `conda run -n job-seeker python <script>`

---

### Task 1: DB migration — add 4 new columns to `company_research`

The project uses `_RESEARCH_MIGRATIONS` list + `_migrate_db()` pattern (see `scripts/db.py:81-107`). Add columns there so existing DBs are upgraded automatically on `init_db()`.

**Files:**
- Modify: `scripts/db.py`
- Modify: `tests/test_db.py`

**Step 1: Write the failing tests**

Add to `tests/test_db.py`:

```python
def test_company_research_has_new_columns(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(company_research)").fetchall()]
    conn.close()
    assert "tech_brief" in cols
    assert "funding_brief" in cols
    assert "competitors_brief" in cols
    assert "red_flags" in cols

def test_save_and_get_research_new_fields(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    # Insert a job first
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO jobs (title, company) VALUES ('TAM', 'Acme')")
    job_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()

    save_research(db, job_id=job_id,
                  company_brief="overview", ceo_brief="ceo",
                  talking_points="points", raw_output="raw",
                  tech_brief="tech stack", funding_brief="series B",
                  competitors_brief="vs competitors", red_flags="none")
    r = get_research(db, job_id=job_id)
    assert r["tech_brief"] == "tech stack"
    assert r["funding_brief"] == "series B"
    assert r["competitors_brief"] == "vs competitors"
    assert r["red_flags"] == "none"
```

**Step 2: Run to confirm failure**

```
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_db.py::test_company_research_has_new_columns tests/test_db.py::test_save_and_get_research_new_fields -v
```

Expected: FAIL — columns and parameters don't exist yet.

**Step 3: Add `_RESEARCH_MIGRATIONS` and wire into `_migrate_db`**

In `scripts/db.py`, after `_CONTACT_MIGRATIONS` (line ~53), add:

```python
_RESEARCH_MIGRATIONS = [
    ("tech_brief",        "TEXT"),
    ("funding_brief",     "TEXT"),
    ("competitors_brief", "TEXT"),
    ("red_flags",         "TEXT"),
]
```

In `_migrate_db()`, after the `_CONTACT_MIGRATIONS` loop, add:

```python
    for col, coltype in _RESEARCH_MIGRATIONS:
        try:
            conn.execute(f"ALTER TABLE company_research ADD COLUMN {col} {coltype}")
        except sqlite3.OperationalError:
            pass
```

**Step 4: Update `save_research` signature and SQL**

Replace the existing `save_research` function:

```python
def save_research(db_path: Path = DEFAULT_DB, job_id: int = None,
                  company_brief: str = "", ceo_brief: str = "",
                  talking_points: str = "", raw_output: str = "",
                  tech_brief: str = "", funding_brief: str = "",
                  competitors_brief: str = "", red_flags: str = "") -> None:
    """Insert or replace a company research record for a job."""
    now = datetime.now().isoformat()[:16]
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO company_research
               (job_id, generated_at, company_brief, ceo_brief, talking_points,
                raw_output, tech_brief, funding_brief, competitors_brief, red_flags)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(job_id) DO UPDATE SET
               generated_at      = excluded.generated_at,
               company_brief     = excluded.company_brief,
               ceo_brief         = excluded.ceo_brief,
               talking_points    = excluded.talking_points,
               raw_output        = excluded.raw_output,
               tech_brief        = excluded.tech_brief,
               funding_brief     = excluded.funding_brief,
               competitors_brief = excluded.competitors_brief,
               red_flags         = excluded.red_flags""",
        (job_id, now, company_brief, ceo_brief, talking_points, raw_output,
         tech_brief, funding_brief, competitors_brief, red_flags),
    )
    conn.commit()
    conn.close()
```

(`get_research` uses `SELECT *` so it picks up new columns automatically — no change needed.)

**Step 5: Run tests**

```
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_db.py -v
```

Expected: all pass.

**Step 6: Commit**

```bash
git add scripts/db.py tests/test_db.py
git commit -m "feat: add tech_brief, funding_brief, competitors_brief, red_flags to company_research"
```

---

### Task 2: Create `config/resume_keywords.yaml` and example

**Files:**
- Create: `config/resume_keywords.yaml`
- Create: `config/resume_keywords.yaml.example`

**Step 1: Create `config/resume_keywords.yaml`**

```yaml
skills:
  - Customer Success
  - Technical Account Management
  - Revenue Operations
  - Salesforce
  - Gainsight
  - data analysis
  - stakeholder management
  - project management
  - onboarding
  - renewal management

domains:
  - B2B SaaS
  - enterprise software
  - security / compliance
  - post-sale lifecycle
  - SaaS metrics

keywords:
  - QBR
  - churn reduction
  - NRR
  - ARR
  - MRR
  - executive sponsorship
  - VOC
  - health score
  - escalation management
  - cross-functional
  - product feedback loop
  - customer advocacy
```

**Step 2: Copy to `.example`**

```bash
cp config/resume_keywords.yaml config/resume_keywords.yaml.example
```

**Step 3: Add to `.gitignore` if personal, or commit both**

`resume_keywords.yaml` contains Alex's personal keywords — commit both (no secrets).

**Step 4: Commit**

```bash
git add config/resume_keywords.yaml config/resume_keywords.yaml.example
git commit -m "feat: add resume_keywords.yaml for research experience matching"
```

---

### Task 3: Resume matching logic in `company_research.py`

Load the resume YAML and keywords config, score experience entries against the JD, return tiered context string.

**Files:**
- Modify: `scripts/company_research.py`
- Create: `tests/test_company_research.py`

**Step 1: Write failing tests**

Create `tests/test_company_research.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.company_research import _score_experiences, _build_resume_context


RESUME_YAML = {
    "experience_details": [
        {
            "position": "Lead Technical Account Manager",
            "company": "UpGuard",
            "employment_period": "10/2022 - 05/2023",
            "key_responsibilities": [
                {"r1": "Managed enterprise security accounts worth $2M ARR"},
                {"r2": "Led QBR cadence with C-suite stakeholders"},
            ],
        },
        {
            "position": "Founder and Principal Consultant",
            "company": "M3 Consulting Services",
            "employment_period": "07/2023 - Present",
            "key_responsibilities": [
                {"r1": "Revenue operations consulting for SaaS clients"},
                {"r2": "Built customer success frameworks"},
            ],
        },
        {
            "position": "Customer Success Manager",
            "company": "Generic Co",
            "employment_period": "01/2020 - 09/2022",
            "key_responsibilities": [
                {"r1": "Managed SMB portfolio"},
            ],
        },
    ]
}

KEYWORDS = ["ARR", "QBR", "enterprise", "security", "stakeholder"]
JD = "Looking for a TAM with enterprise ARR experience and QBR facilitation skills."


def test_score_experiences_returns_sorted():
    scored = _score_experiences(RESUME_YAML["experience_details"], KEYWORDS, JD)
    # UpGuard should score highest (ARR + QBR + enterprise + stakeholder all in bullets)
    assert scored[0]["company"] == "UpGuard"


def test_build_resume_context_top2_full_rest_condensed():
    ctx = _build_resume_context(RESUME_YAML, KEYWORDS, JD)
    # Full detail for top 2
    assert "Lead Technical Account Manager" in ctx
    assert "Managed enterprise security accounts" in ctx
    # Condensed for rest
    assert "Also in Alex" in ctx
    assert "Generic Co" in ctx
    # UpGuard NDA note present
    assert "NDA" in ctx or "enterprise security vendor" in ctx
```

**Step 2: Run to confirm failure**

```
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_company_research.py -v
```

Expected: FAIL — functions don't exist.

**Step 3: Implement `_score_experiences` and `_build_resume_context`**

Add to `scripts/company_research.py`, after the `_parse_sections` function:

```python
_RESUME_YAML = Path(__file__).parent.parent / "aihawk" / "data_folder" / "plain_text_resume.yaml"
_KEYWORDS_YAML = Path(__file__).parent.parent / "config" / "resume_keywords.yaml"

# Companies where Alex has an NDA — reference engagement but not specifics
# unless the role is a strong security/compliance match (score >= 3 on JD).
_NDA_COMPANIES = {"upguard"}


def _score_experiences(experiences: list[dict], keywords: list[str], jd: str) -> list[dict]:
    """
    Score each experience entry by how many keywords appear in its text.
    Returns experiences sorted descending by score, with 'score' key added.
    """
    jd_lower = jd.lower()
    scored = []
    for exp in experiences:
        text = " ".join([
            exp.get("position", ""),
            exp.get("company", ""),
            " ".join(
                v
                for resp in exp.get("key_responsibilities", [])
                for v in resp.values()
            ),
        ]).lower()
        score = sum(1 for kw in keywords if kw.lower() in text and kw.lower() in jd_lower)
        scored.append({**exp, "score": score})
    return sorted(scored, key=lambda x: x["score"], reverse=True)


def _build_resume_context(resume: dict, keywords: list[str], jd: str) -> str:
    """
    Build the resume section of the LLM context block.
    Top 2 scored experiences included in full detail; rest as one-liners.
    Applies UpGuard NDA rule: reference as 'enterprise security vendor' unless
    the role is security-focused (score >= 3).
    """
    import yaml as _yaml

    experiences = resume.get("experience_details", [])
    if not experiences:
        return ""

    scored = _score_experiences(experiences, keywords, jd)
    top2 = scored[:2]
    rest = scored[2:]

    def _exp_label(exp: dict) -> str:
        company = exp.get("company", "")
        if company.lower() in _NDA_COMPANIES and exp.get("score", 0) < 3:
            company = "enterprise security vendor (NDA)"
        return f"{exp.get('position', '')} @ {company} ({exp.get('employment_period', '')})"

    def _exp_bullets(exp: dict) -> str:
        bullets = []
        for resp in exp.get("key_responsibilities", []):
            bullets.extend(resp.values())
        return "\n".join(f"  - {b}" for b in bullets)

    lines = ["## Alex's Matched Experience"]
    for exp in top2:
        lines.append(f"\n**{_exp_label(exp)}** (match score: {exp['score']})")
        lines.append(_exp_bullets(exp))

    if rest:
        condensed = ", ".join(_exp_label(e) for e in rest)
        lines.append(f"\nAlso in Alex's background: {condensed}")

    return "\n".join(lines)


def _load_resume_and_keywords() -> tuple[dict, list[str]]:
    """Load resume YAML and keywords config. Returns (resume_dict, all_keywords)."""
    import yaml as _yaml

    resume = {}
    if _RESUME_YAML.exists():
        resume = _yaml.safe_load(_RESUME_YAML.read_text()) or {}

    keywords: list[str] = []
    if _KEYWORDS_YAML.exists():
        kw_cfg = _yaml.safe_load(_KEYWORDS_YAML.read_text()) or {}
        for lst in kw_cfg.values():
            if isinstance(lst, list):
                keywords.extend(lst)

    return resume, keywords
```

**Step 4: Run tests**

```
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_company_research.py -v
```

Expected: all pass.

**Step 5: Commit**

```bash
git add scripts/company_research.py tests/test_company_research.py
git commit -m "feat: add resume experience matching and tiered context builder"
```

---

### Task 4: Parallel search queries (Phase 1b expansion)

Replace the current single-threaded news fetch with 6 parallel SearXNG queries. Each runs in its own daemon thread and writes to a shared results dict.

**Files:**
- Modify: `scripts/company_research.py`

**Step 1: Replace `_fetch_recent_news` with `_fetch_search_data`**

Remove the existing `_fetch_recent_news` function and replace with:

```python
_SEARCH_QUERIES = {
    "news":        '"{company}" news 2025 2026',
    "funding":     '"{company}" funding round investors Series valuation',
    "tech":        '"{company}" tech stack engineering technology platform',
    "competitors": '"{company}" competitors alternatives vs market',
    "culture":     '"{company}" glassdoor culture reviews employees',
    "ceo_press":   '"{ceo}" "{company}"',  # only used if ceo is known
}


def _run_search_query(query: str, results: dict, key: str) -> None:
    """Thread target: run one SearXNG JSON query, store up to 4 snippets in results[key]."""
    import requests

    snippets: list[str] = []
    seen: set[str] = set()
    try:
        resp = requests.get(
            "http://localhost:8888/search",
            params={"q": query, "format": "json", "language": "en-US"},
            timeout=12,
        )
        if resp.status_code != 200:
            return
        for r in resp.json().get("results", [])[:4]:
            url = r.get("url", "")
            if url in seen:
                continue
            seen.add(url)
            title = r.get("title", "").strip()
            content = r.get("content", "").strip()
            if title or content:
                snippets.append(f"- **{title}**\n  {content}\n  <{url}>")
    except Exception:
        pass
    results[key] = "\n\n".join(snippets)


def _fetch_search_data(company: str, ceo: str = "") -> dict[str, str]:
    """
    Run all search queries in parallel threads.
    Returns dict keyed by search type (news, funding, tech, competitors, culture, ceo_press).
    Missing/failed queries produce empty strings.
    """
    import threading

    results: dict[str, str] = {}
    threads = []

    for key, pattern in _SEARCH_QUERIES.items():
        if key == "ceo_press" and (not ceo or ceo.lower() in ("not found", "")):
            continue
        query = pattern.format(company=company, ceo=ceo)
        t = threading.Thread(
            target=_run_search_query,
            args=(query, results, key),
            daemon=True,
        )
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=15)  # don't block the task indefinitely

    return results
```

**Step 2: Update Phase 1b in `research_company()` to call `_fetch_search_data`**

Replace the Phase 1b block:

```python
    # ── Phase 1b: parallel search queries ────────────────────────────────────
    search_data: dict[str, str] = {}
    if use_scraper and _searxng_running():
        try:
            ceo_name = (live_data.get("ceo") or "") if live_data else ""
            search_data = _fetch_search_data(company, ceo=ceo_name)
        except BaseException:
            pass  # best-effort; never fail the whole task
```

**Step 3: Build per-section notes for the prompt**

After the Phase 1b block, add:

```python
    def _section_note(key: str, label: str) -> str:
        text = search_data.get(key, "").strip()
        return f"\n\n## {label} (live web search)\n\n{text}" if text else ""

    news_note       = _section_note("news",        "News & Press")
    funding_note    = _section_note("funding",      "Funding & Investors")
    tech_note       = _section_note("tech",         "Tech Stack")
    competitors_note= _section_note("competitors",  "Competitors")
    culture_note    = _section_note("culture",      "Culture & Employee Signals")
    ceo_press_note  = _section_note("ceo_press",    "CEO in the News")
```

**Step 4: No automated test (threading + network) — manual smoke test**

```bash
conda run -n job-seeker python scripts/company_research.py --job-id <any_valid_id>
```

Verify log output shows 6 search threads completing within ~15s total.

**Step 5: Commit**

```bash
git add scripts/company_research.py
git commit -m "feat: parallel SearXNG search queries (funding, tech, competitors, culture, news)"
```

---

### Task 5: Expanded LLM prompt and section parsing

Wire resume context + all search data into the prompt, update section headers, update `_parse_sections` mapping, update `research_company()` return dict.

**Files:**
- Modify: `scripts/company_research.py`

**Step 1: Load resume in `research_company()` and build context**

At the top of `research_company()`, after `jd_excerpt`, add:

```python
    resume, keywords = _load_resume_and_keywords()
    matched_keywords = [kw for kw in keywords if kw.lower() in jd_excerpt.lower()]
    resume_context = _build_resume_context(resume, keywords, jd_excerpt)
    keywords_note = (
        f"\n\n## Matched Skills & Keywords\nSkills matching this JD: {', '.join(matched_keywords)}"
        if matched_keywords else ""
    )
```

**Step 2: Replace the Phase 2 LLM prompt**

Replace the existing `prompt = f"""..."""` block with:

```python
    prompt = f"""You are preparing Alex Rivera for a job interview.

Role: **{title}** at **{company}**

## Job Description
{jd_excerpt}
{resume_context}{keywords_note}

## Live Company Data (SearXNG)
{scrape_note.strip() or "_(scrape unavailable)_"}
{news_note}{funding_note}{tech_note}{competitors_note}{culture_note}{ceo_press_note}

---

Produce a structured research brief using **exactly** these seven markdown section headers
(include all seven even if a section has limited data — say so honestly):

## Company Overview
What {company} does, core product/service, business model, size/stage (startup / scale-up / enterprise), market positioning.

## Leadership & Culture
CEO background and leadership style, key execs, mission/values statements, Glassdoor themes.

## Tech Stack & Product
Technologies, platforms, and product direction relevant to the {title} role.

## Funding & Market Position
Funding stage, key investors, recent rounds, burn/growth signals, competitor landscape.

## Recent Developments
News, launches, acquisitions, exec moves, pivots, or press from the past 12–18 months.
Draw on the live snippets above; if none available, note what is publicly known.

## Red Flags & Watch-outs
Culture issues, layoffs, exec departures, financial stress, or Glassdoor concerns worth knowing before the call.
If nothing notable, write "No significant red flags identified."

## Talking Points for Alex
Five specific talking points for the phone screen. Each must:
- Reference a concrete experience from Alex's matched background by name
  (UpGuard NDA rule: say "enterprise security vendor" unless role has clear security focus)
- Connect to a specific signal from the JD or company context above
- Be 1–2 sentences, ready to speak aloud
- Never give generic advice

---
⚠️ This brief combines live web data and LLM training knowledge. Verify key facts before the call.
"""
```

**Step 3: Update the return dict**

Replace the existing return block:

```python
    return {
        "raw_output":        raw,
        "company_brief":     sections.get("Company Overview", ""),
        "ceo_brief":         sections.get("Leadership & Culture", ""),
        "tech_brief":        sections.get("Tech Stack & Product", ""),
        "funding_brief":     sections.get("Funding & Market Position", ""),
        "talking_points":    sections.get("Talking Points for Alex", ""),
        # Recent Developments and Red Flags stored in raw_output; rendered from there
        # (avoids adding more columns right now — can migrate later if needed)
    }
```

Wait — `Recent Developments` and `Red Flags` aren't in the return dict above. We have `red_flags` column from Task 1. Add them:

```python
    return {
        "raw_output":        raw,
        "company_brief":     sections.get("Company Overview", ""),
        "ceo_brief":         sections.get("Leadership & Culture", ""),
        "tech_brief":        sections.get("Tech Stack & Product", ""),
        "funding_brief":     sections.get("Funding & Market Position", ""),
        "competitors_brief": sections.get("Funding & Market Position", ""),  # same section
        "red_flags":         sections.get("Red Flags & Watch-outs", ""),
        "talking_points":    sections.get("Talking Points for Alex", ""),
    }
```

Note: `competitors_brief` pulls from the Funding & Market Position section (which includes competitors). `recent_developments` is only in `raw_output` — no separate column needed.

**Step 4: Manual smoke test**

```bash
conda run -n job-seeker python scripts/company_research.py --job-id <valid_id>
```

Verify all 7 sections appear in output and `save_research` receives all fields.

**Step 5: Commit**

```bash
git add scripts/company_research.py
git commit -m "feat: expanded research prompt with resume context, 7 output sections"
```

---

### Task 6: Interview Prep UI — render new sections

**Files:**
- Modify: `app/pages/6_Interview_Prep.py`

**Step 1: Replace the left-panel section rendering**

Find the existing section block (after `st.divider()` at line ~145) and replace with:

```python
    # ── Talking Points (top — most useful during a live call) ─────────────────
    st.subheader("🎯 Talking Points")
    tp = research.get("talking_points", "").strip()
    if tp:
        st.markdown(tp)
    else:
        st.caption("_No talking points extracted — try regenerating._")

    st.divider()

    # ── Company brief ─────────────────────────────────────────────────────────
    st.subheader("🏢 Company Overview")
    st.markdown(research.get("company_brief") or "_—_")

    st.divider()

    # ── Leadership & culture ──────────────────────────────────────────────────
    st.subheader("👤 Leadership & Culture")
    st.markdown(research.get("ceo_brief") or "_—_")

    st.divider()

    # ── Tech Stack ────────────────────────────────────────────────────────────
    tech = research.get("tech_brief", "").strip()
    if tech:
        st.subheader("⚙️ Tech Stack & Product")
        st.markdown(tech)
        st.divider()

    # ── Funding & Market ──────────────────────────────────────────────────────
    funding = research.get("funding_brief", "").strip()
    if funding:
        st.subheader("💰 Funding & Market Position")
        st.markdown(funding)
        st.divider()

    # ── Red Flags ─────────────────────────────────────────────────────────────
    red = research.get("red_flags", "").strip()
    if red and "no significant red flags" not in red.lower():
        st.subheader("⚠️ Red Flags & Watch-outs")
        st.warning(red)
        st.divider()

    # ── Practice Q&A ──────────────────────────────────────────────────────────
    with st.expander("🎤 Practice Q&A (pre-call prep)", expanded=False):
        # ... existing Q&A code unchanged ...
```

Note: The existing Practice Q&A expander code stays exactly as-is inside the expander — only move/restructure the section headers above it.

**Step 2: Restart Streamlit and visually verify**

```bash
bash scripts/manage-ui.sh restart
```

Navigate to Interview Prep → verify new sections appear, Red Flags renders in amber warning box, Tech/Funding sections only show when populated.

**Step 3: Commit**

```bash
git add app/pages/6_Interview_Prep.py
git commit -m "feat: render tech, funding, red flags sections in Interview Prep"
```

---

### Task 7: Settings UI — Skills & Keywords tab

**Files:**
- Modify: `app/pages/2_Settings.py`

**Step 1: Add `KEYWORDS_CFG` path constant**

After the existing config path constants (line ~19), add:

```python
KEYWORDS_CFG = CONFIG_DIR / "resume_keywords.yaml"
```

**Step 2: Add the tab to the tab bar**

Change:
```python
tab_search, tab_llm, tab_notion, tab_services, tab_resume, tab_email = st.tabs(
    ["🔎 Search", "🤖 LLM Backends", "📚 Notion", "🔌 Services", "📝 Resume Profile", "📧 Email"]
)
```
To:
```python
tab_search, tab_llm, tab_notion, tab_services, tab_resume, tab_email, tab_skills = st.tabs(
    ["🔎 Search", "🤖 LLM Backends", "📚 Notion", "🔌 Services", "📝 Resume Profile", "📧 Email", "🏷️ Skills"]
)
```

**Step 3: Add the Skills & Keywords tab body**

Append at the end of the file:

```python
# ── Skills & Keywords tab ─────────────────────────────────────────────────────
with tab_skills:
    st.subheader("🏷️ Skills & Keywords")
    st.caption(
        "These are matched against job descriptions to select Alex's most relevant "
        "experience and highlight keyword overlap in the research brief."
    )

    if not KEYWORDS_CFG.exists():
        st.warning("resume_keywords.yaml not found — create it at config/resume_keywords.yaml")
        st.stop()

    kw_data = load_yaml(KEYWORDS_CFG)

    changed = False
    for category in ["skills", "domains", "keywords"]:
        st.markdown(f"**{category.title()}**")
        tags: list[str] = kw_data.get(category, [])

        # Render existing tags as removable chips
        cols = st.columns(min(len(tags), 6) or 1)
        to_remove = None
        for i, tag in enumerate(tags):
            with cols[i % 6]:
                if st.button(f"× {tag}", key=f"rm_{category}_{i}", use_container_width=True):
                    to_remove = tag
        if to_remove:
            tags.remove(to_remove)
            kw_data[category] = tags
            changed = True

        # Add new tag
        new_col, btn_col = st.columns([4, 1])
        new_tag = new_col.text_input(
            "Add", key=f"new_{category}", label_visibility="collapsed",
            placeholder=f"Add {category[:-1] if category.endswith('s') else category}…"
        )
        if btn_col.button("＋ Add", key=f"add_{category}"):
            tag = new_tag.strip()
            if tag and tag not in tags:
                tags.append(tag)
                kw_data[category] = tags
                changed = True

        st.markdown("---")

    if changed:
        save_yaml(KEYWORDS_CFG, kw_data)
        st.success("Saved.")
        st.rerun()
```

**Step 4: Restart and verify**

```bash
bash scripts/manage-ui.sh restart
```

Navigate to Settings → Skills tab. Verify:
- Tags render as `× tag` buttons; clicking one removes it immediately
- Text input + Add button appends new tag
- Changes persist to `config/resume_keywords.yaml`

**Step 5: Commit**

```bash
git add app/pages/2_Settings.py
git commit -m "feat: add Skills & Keywords tag editor to Settings"
```

---

### Task 8: Run full test suite + final smoke test

**Step 1: Full test suite**

```
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v
```

Expected: all existing + new tests pass.

**Step 2: End-to-end smoke test**

With SearXNG running (`docker compose up -d` in `/Library/Development/scrapers/SearXNG/`):

```bash
conda run -n job-seeker python scripts/company_research.py --job-id <valid_id>
```

Verify:
- 6 search threads complete
- All 7 sections present in output
- Talking points reference real experience entries (not generic blurb)
- `get_research()` returns all new fields populated

**Step 3: Final commit if any cleanup needed**

```bash
git add -p  # stage only intentional changes
git commit -m "chore: research workflow final cleanup"
```
