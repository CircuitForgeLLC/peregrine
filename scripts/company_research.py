# scripts/company_research.py
"""
Pre-interview company research generator.

Three-phase approach:
  1. If SearXNG is available, use companyScraper.py to fetch live
     data: CEO name, HQ address, LinkedIn, contact info.
  1b. Use Phase 1 data (company name + CEO if found) to query SearXNG for
      recent news snippets (funding, launches, leadership changes, etc.).
  2. Feed all real data into an LLM prompt to synthesise a structured brief
     covering company overview, leadership, recent developments, and talking
     points tailored to the candidate.

Falls back to pure LLM knowledge when SearXNG is offline.

Usage (standalone):
    conda run -n job-seeker python scripts/company_research.py --job-id 42
    conda run -n job-seeker python scripts/company_research.py --job-id 42 --no-scrape
"""
import re
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.user_profile import UserProfile
_USER_YAML = Path(__file__).parent.parent / "config" / "user.yaml"
_profile = UserProfile(_USER_YAML) if UserProfile.exists(_USER_YAML) else None

# ── SearXNG scraper integration ───────────────────────────────────────────────
# companyScraper is bundled into the Docker image at /app/scrapers/
_SCRAPER_AVAILABLE = False
for _scraper_candidate in [
    Path("/app/scrapers"),          # Docker container path
    Path(__file__).parent.parent / "scrapers",  # local dev fallback
]:
    if _scraper_candidate.exists():
        sys.path.insert(0, str(_scraper_candidate))
        try:
            from companyScraper import EnhancedCompanyScraper, Config as _ScraperConfig
            _SCRAPER_AVAILABLE = True
        except (ImportError, SystemExit):
            pass
        break


_SEARXNG_URL: str = _profile.searxng_url if _profile else "http://localhost:8888"


def _searxng_running(searxng_url: str = "http://localhost:8888") -> bool:
    """Quick check whether SearXNG is reachable."""
    try:
        import requests
        r = requests.get(f"{searxng_url}/", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _scrape_company(company: str) -> dict:
    """
    Use companyScraper in minimal mode to pull live CEO / HQ data.
    Returns a dict with keys: ceo, headquarters, linkedin (may be 'Not found').
    """
    mock_args = SimpleNamespace(
        mode="minimal",
        verbose=False,
        dry_run=False,
        debug=False,
        use_cache=True,
        save_raw=False,
        target_staff=None,
        include_types=None,
        exclude_types=None,
        include_contact=False,
        include_address=False,
        include_social=True,   # grab LinkedIn while we're at it
        timeout=20,
        input_file=None,
        output_file="/dev/null",
        searxng_url=_SEARXNG_URL + "/",
    )
    # Override the singleton Config URL
    _ScraperConfig.SEARXNG_URL = _SEARXNG_URL + "/"

    scraper = EnhancedCompanyScraper(mock_args)
    scraper.companies = [company]

    result: dict = {"ceo": "Not found", "headquarters": "Not found", "linkedin": "Not found"}
    for search_type in ["ceo", "hq", "social"]:
        html = scraper.search_company(company, search_type)
        if search_type == "ceo":
            result["ceo"] = scraper.extract_ceo(html, company)
        elif search_type == "hq":
            result["headquarters"] = scraper.extract_address(html, company)
        elif search_type == "social":
            social = scraper.extract_social(html, company)
            # Pull out just the LinkedIn entry
            for part in (social or "").split(";"):
                if "linkedin" in part.lower():
                    result["linkedin"] = part.strip()
                    break

    return result


_SEARCH_QUERIES = {
    "news":          '"{company}" news 2025 2026',
    "funding":       '"{company}" funding round investors Series valuation',
    "tech":          '"{company}" tech stack engineering technology platform',
    "competitors":   '"{company}" competitors alternatives vs market',
    "culture":       '"{company}" glassdoor culture reviews employees',
    "accessibility": '"{company}" ADA accessibility disability inclusion accommodation ERG',
    "ceo_press":     '"{ceo}" "{company}"',  # only used if ceo is known
}


def _run_search_query(query: str, results: dict, key: str) -> None:
    """Thread target: run one SearXNG JSON query, store up to 4 snippets in results[key]."""
    import requests

    snippets: list[str] = []
    seen: set[str] = set()
    try:
        resp = requests.get(
            f"{_SEARXNG_URL}/search",
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

    keys: list[str] = []
    for key, pattern in _SEARCH_QUERIES.items():
        if key == "ceo_press" and not ceo or (ceo or "").lower() == "not found":
            continue
        # Use replace() not .format() — company names may contain curly braces
        query = pattern.replace("{company}", company).replace("{ceo}", ceo)
        t = threading.Thread(
            target=_run_search_query,
            args=(query, results, key),
            daemon=True,
        )
        threads.append(t)
        keys.append(key)
        t.start()

    for t, key in zip(threads, keys):
        t.join(timeout=15)
        # Thread may still be alive after timeout — pre-populate key so
        # the results dict contract ("missing queries → empty string") holds
        if t.is_alive():
            results.setdefault(key, "")

    return results


def _parse_sections(text: str) -> dict[str, str]:
    """Split LLM markdown output on ## headers into named sections."""
    sections: dict[str, str] = {}
    pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    for i, match in enumerate(matches):
        name = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[name] = text[start:end].strip()
    return sections


_RESUME_YAML = Path(__file__).parent.parent / "aihawk" / "data_folder" / "plain_text_resume.yaml"
_KEYWORDS_YAML = Path(__file__).parent.parent / "config" / "resume_keywords.yaml"


def _company_label(exp: dict) -> str:
    company = exp.get("company", "")
    score = exp.get("score", 0)
    if _profile:
        return _profile.nda_label(company, score)
    return company


def _score_experiences(experiences: list[dict], keywords: list[str], jd: str) -> list[dict]:
    """Score each experience entry by keyword overlap with JD; return sorted descending."""
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
    NDA companies are masked via UserProfile.nda_label() when score < threshold.
    """
    experiences = resume.get("experience_details", [])
    if not experiences:
        return ""

    scored = _score_experiences(experiences, keywords, jd)
    top2 = scored[:2]
    rest = scored[2:]

    candidate = _profile.name if _profile else "the candidate"

    def _exp_header(exp: dict) -> str:
        return f"{exp.get('position', '')} @ {_company_label(exp)} ({exp.get('employment_period', '')})"

    def _exp_bullets(exp: dict) -> str:
        bullets = [v for resp in exp.get("key_responsibilities", []) for v in resp.values()]
        return "\n".join(f"  - {b}" for b in bullets)

    lines = [f"## {candidate}'s Matched Experience"]
    for exp in top2:
        lines.append(f"\n**{_exp_header(exp)}** (match score: {exp['score']})")
        lines.append(_exp_bullets(exp))

    if rest:
        condensed = ", ".join(_exp_header(e) for e in rest)
        lines.append(f"\nAlso in {candidate}'s background: {condensed}")

    return "\n".join(lines)


def _load_resume_and_keywords() -> tuple[dict, list[str]]:
    """Load resume YAML and keywords config. Returns (resume_dict, all_keywords_list)."""
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


def research_company(job: dict, use_scraper: bool = True, on_stage=None) -> dict:
    """
    Generate a pre-interview research brief for a job.

    Parameters
    ----------
    job : dict
        Job row from the DB (needs at least 'company', 'title', 'description').
    use_scraper : bool
        Whether to attempt live data via SearXNG before falling back to LLM.

    Returns
    -------
    dict with keys: raw_output, company_brief, ceo_brief, tech_brief,
    funding_brief, competitors_brief, red_flags, talking_points
    """
    from scripts.llm_router import LLMRouter

    router = LLMRouter()
    research_order = router.config.get("research_fallback_order") or router.config["fallback_order"]
    company = job.get("company") or "the company"
    title = job.get("title") or "this role"
    jd_excerpt = (job.get("description") or "")[:1500]

    resume, keywords = _load_resume_and_keywords()
    matched_keywords = [kw for kw in keywords if kw.lower() in jd_excerpt.lower()]
    resume_context = _build_resume_context(resume, keywords, jd_excerpt)
    keywords_note = (
        f"\n\n## Matched Skills & Keywords\nSkills matching this JD: {', '.join(matched_keywords)}"
        if matched_keywords else ""
    )

    def _stage(msg: str) -> None:
        if on_stage:
            try:
                on_stage(msg)
            except Exception:
                pass  # never let stage callbacks break the task

    # ── Phase 1: live scrape (optional) ──────────────────────────────────────
    live_data: dict = {}
    scrape_note = ""
    _stage("Checking for live company data…")
    if use_scraper and _SCRAPER_AVAILABLE and _searxng_running(_SEARXNG_URL):
        _stage("Scraping CEO & HQ data…")
        try:
            live_data = _scrape_company(company)
            parts = []
            if live_data.get("ceo") not in (None, "Not found"):
                parts.append(f"CEO: {live_data['ceo']}")
            if live_data.get("headquarters") not in (None, "Not found"):
                parts.append(f"HQ: {live_data['headquarters']}")
            if live_data.get("linkedin") not in (None, "Not found"):
                parts.append(f"LinkedIn: {live_data['linkedin']}")
            if parts:
                scrape_note = (
                    "\n\n**Live data retrieved via SearXNG:**\n"
                    + "\n".join(f"- {p}" for p in parts)
                    + "\n\nIncorporate these facts where relevant."
                )
        except BaseException as e:
            scrape_note = f"\n\n_(Live scrape attempted but failed: {e})_"

    # ── Phase 1b: parallel search queries ────────────────────────────────────
    search_data: dict[str, str] = {}
    _stage("Running web searches…")
    if use_scraper and _searxng_running(_SEARXNG_URL):
        _stage("Running web searches (news, funding, tech, culture)…")
        try:
            ceo_name = (live_data.get("ceo") or "") if live_data else ""
            search_data = _fetch_search_data(company, ceo=ceo_name)
        except BaseException:
            pass  # best-effort; never fail the whole task

    # Track whether SearXNG actually contributed usable data to this brief.
    scrape_used = 1 if (live_data or any(v.strip() for v in search_data.values())) else 0

    def _section_note(key: str, label: str) -> str:
        text = search_data.get(key, "").strip()
        return f"\n\n## {label} (live web search)\n\n{text}" if text else ""

    news_note          = _section_note("news",          "News & Press")
    funding_note       = _section_note("funding",       "Funding & Investors")
    tech_note          = _section_note("tech",          "Tech Stack")
    competitors_note   = _section_note("competitors",   "Competitors")
    culture_note       = _section_note("culture",       "Culture & Employee Signals")
    accessibility_note = _section_note("accessibility", "Accessibility & Disability Inclusion")
    ceo_press_note     = _section_note("ceo_press",     "CEO in the News")

    # ── Phase 2: LLM synthesis ────────────────────────────────────────────────
    _stage("Generating brief with LLM… (30–90 seconds)")
    name = _profile.name if _profile else "the candidate"
    career_summary = _profile.career_summary if _profile else ""
    prompt = f"""You are preparing {name} for a job interview.
{f"Candidate background: {career_summary}" if career_summary else ""}

Role: **{title}** at **{company}**

## Job Description
{jd_excerpt}
{resume_context}{keywords_note}

## Live Company Data
{scrape_note.strip() or "_(scrape unavailable)_"}
{news_note}{funding_note}{tech_note}{competitors_note}{culture_note}{accessibility_note}{ceo_press_note}

---

Produce a structured research brief using **exactly** these eight markdown section headers
(include all eight even if a section has limited data — say so honestly):

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

## Inclusion & Accessibility
Assess {company}'s commitment to disability inclusion and accessibility. Cover:
- ADA accommodation language in job postings or company policy
- Disability Employee Resource Group (ERG) or affinity group
- Product or service accessibility (WCAG compliance, adaptive features, AT integrations)
- Any public disability/accessibility advocacy, partnerships, or certifications
- Glassdoor or press signals about how employees with disabilities experience the company
If no specific signals are found, say so clearly — absence of public commitment is itself signal.
This section is for the candidate's personal decision-making only and will not appear in any application.

## Talking Points for {name}
Five specific talking points for the phone screen. Each must:
- Reference a concrete experience from {name}'s matched background by name
  (NDA rule: use the masked label shown in the matched experience section for any NDA-protected employer)
- Connect to a specific signal from the JD or company context above
- Be 1–2 sentences, ready to speak aloud
- Never give generic advice

---
⚠️ This brief combines live web data and LLM training knowledge. Verify key facts before the call.
"""

    raw = router.complete(prompt, fallback_order=research_order)
    # Strip <think>…</think> blocks emitted by reasoning models (e.g. DeepSeek, Qwen-R)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    sections = _parse_sections(raw)

    return {
        "raw_output":        raw,
        "company_brief":     sections.get("Company Overview", ""),
        "ceo_brief":         sections.get("Leadership & Culture", ""),
        "tech_brief":        sections.get("Tech Stack & Product", ""),
        "funding_brief":     sections.get("Funding & Market Position", ""),
        "competitors_brief": sections.get("Funding & Market Position", ""),  # competitor landscape is in the funding section
        "red_flags":         sections.get("Red Flags & Watch-outs", ""),
        "accessibility_brief": sections.get("Inclusion & Accessibility", ""),
        "talking_points":    sections.get(f"Talking Points for {name}", ""),
        "scrape_used":       scrape_used,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate company research brief")
    parser.add_argument("--job-id", type=int, required=True, help="Job ID in staging.db")
    parser.add_argument("--no-scrape", action="store_true", help="Skip SearXNG live scrape")
    args = parser.parse_args()

    from scripts.db import DEFAULT_DB, init_db, save_research
    import sqlite3

    init_db(DEFAULT_DB)
    conn = sqlite3.connect(DEFAULT_DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (args.job_id,)).fetchone()
    conn.close()

    if not row:
        sys.exit(f"Job {args.job_id} not found in {DEFAULT_DB}")

    job = dict(row)
    print(f"Researching: {job['title']} @ {job['company']} …\n")
    if _SCRAPER_AVAILABLE and not args.no_scrape:
        print(f"SearXNG available: {_searxng_running(_SEARXNG_URL)}")

    result = research_company(job, use_scraper=not args.no_scrape)
    save_research(DEFAULT_DB, job_id=args.job_id, **result)
    print(result["raw_output"])
    print(f"\n[Saved to company_research for job {args.job_id}]")
