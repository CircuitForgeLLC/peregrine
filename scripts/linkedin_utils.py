# scripts/linkedin_utils.py
"""
LinkedIn profile HTML parser.

Extracts structured profile data from a raw LinkedIn public profile page.
No Playwright dependency — importable by both linkedin_scraper and linkedin_parser.

Selectors target the 2024-2025 LinkedIn public profile DOM.
When LinkedIn changes their markup, update the selector lists here only.
Each section uses ordered fallbacks — first matching selector wins.
"""
from __future__ import annotations
import re
from bs4 import BeautifulSoup


# ── Selector fallback lists ────────────────────────────────────────────────────

_NAME_SELECTORS = [
    "h1.top-card-layout__title",
    "h1[class*='title']",
    ".pv-top-card--list h1",
    "h1",
]

_SUMMARY_SELECTORS = [
    "section[data-section='about'] .show-more-less-text__text--less",
    "section[data-section='about'] p",
    "#about ~ * p.show-more-less-text__text--less",
    ".pv-about-section p",
]

_EXPERIENCE_ITEM_SELECTORS = [
    "section[data-section='experience'] li.experience-item",
    "section[data-section='experience'] li",
    "#experience-section li",
    "#experience ~ * li",
]

_EXP_TITLE_SELECTORS   = ["span.experience-item__title", "span[class*='title']", "h3"]
_EXP_COMPANY_SELECTORS = ["span.experience-item__subtitle", "span[class*='subtitle']", "p[class*='company']"]
_EXP_DATE_SELECTORS    = ["span.date-range", "[class*='date-range']", "span[class*='duration']"]
_EXP_DESC_SELECTORS    = [".show-more-less-text__text--less", "p[class*='description']", "p"]

_EDUCATION_ITEM_SELECTORS = [
    "section[data-section='education'] li.education__list-item",
    "section[data-section='education'] li",
    "#education ~ * li",
]

_EDU_SCHOOL_SELECTORS = ["h3.education__school-name", "h3[class*='school']", "h3"]
_EDU_DEGREE_SELECTORS = ["span.education__item--degree-name", "span[class*='degree']", "p[class*='degree']"]
_EDU_DATES_SELECTORS  = ["span.education__item--duration", "span[class*='duration']", "time"]

_SKILLS_SELECTORS = [
    "section[data-section='skills'] span.mr1",
    "section[data-section='skills'] li span[class*='bold']",
    "section[data-section='skills'] li span",
    "#skills ~ * li span",
]

_CERT_ITEM_SELECTORS = [
    "section[data-section='certifications'] li",
    "#certifications ~ * li",
    "#licenses_and_certifications ~ * li",
]
_CERT_NAME_SELECTORS = ["h3.certifications__name", "h3[class*='name']", "h3", "span[class*='title']"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _select_first(soup, selectors):
    for sel in selectors:
        try:
            el = soup.select_one(sel)
            if el and el.get_text(strip=True):
                return el.get_text(strip=True)
        except Exception:
            continue
    return ""


def _select_all(soup, selectors):
    for sel in selectors:
        try:
            els = soup.select(sel)
            if els:
                return els
        except Exception:
            continue
    return []


def _split_bullets(text):
    parts = re.split(r"[•·]\s*|(?<=\s)–\s+|\n+", text)
    return [p.strip() for p in parts if p.strip() and len(p.strip()) > 3]


def _date_range_text(item):
    for sel in _EXP_DATE_SELECTORS:
        try:
            el = item.select_one(sel)
            if el:
                times = [t.get_text(strip=True) for t in el.find_all("time")]
                if times:
                    return " – ".join(times)
                text = el.get_text(strip=True)
                if text:
                    return text
        except Exception:
            continue
    return ""


# ── Public API ────────────────────────────────────────────────────────────────

def parse_html(raw_html: str) -> dict:
    """
    Extract structured profile data from a raw LinkedIn public profile HTML page.

    Returns a dict with keys: name, email, phone, linkedin, career_summary,
    experience[], education[], skills[], achievements[]

    Never raises — returns empty values for sections that cannot be parsed.
    """
    soup = BeautifulSoup(raw_html, "lxml")

    name = _select_first(soup, _NAME_SELECTORS)
    career_summary = _select_first(soup, _SUMMARY_SELECTORS)

    experience = []
    for item in _select_all(soup, _EXPERIENCE_ITEM_SELECTORS):
        title   = _select_first(item, _EXP_TITLE_SELECTORS)
        company = _select_first(item, _EXP_COMPANY_SELECTORS)
        dates   = _date_range_text(item)
        desc_el = None
        for sel in _EXP_DESC_SELECTORS:
            try:
                desc_el = item.select_one(sel)
                if desc_el:
                    break
            except Exception:
                continue
        bullets = _split_bullets(desc_el.get_text(" ", strip=True)) if desc_el else []
        if title or company:
            experience.append({
                "company":    company,
                "title":      title,
                "date_range": dates,
                "bullets":    bullets,
            })

    education = []
    for item in _select_all(soup, _EDUCATION_ITEM_SELECTORS):
        school = _select_first(item, _EDU_SCHOOL_SELECTORS)
        degree = _select_first(item, _EDU_DEGREE_SELECTORS)
        dates  = ""
        for sel in _EDU_DATES_SELECTORS:
            try:
                el = item.select_one(sel)
                if el:
                    dates = el.get_text(strip=True)
                    break
            except Exception:
                continue
        if school or degree:
            education.append({
                "school": school,
                "degree": degree,
                "field":  "",
                "dates":  dates,
            })

    skills = [el.get_text(strip=True) for el in _select_all(soup, _SKILLS_SELECTORS)
              if el.get_text(strip=True)]
    skills = list(dict.fromkeys(skills))

    achievements = []
    for item in _select_all(soup, _CERT_ITEM_SELECTORS):
        label = _select_first(item, _CERT_NAME_SELECTORS)
        if label:
            achievements.append(label)

    return {
        "name":           name,
        "email":          "",
        "phone":          "",
        "linkedin":       "",
        "career_summary": career_summary,
        "experience":     experience,
        "education":      education,
        "skills":         skills,
        "achievements":   achievements,
    }
