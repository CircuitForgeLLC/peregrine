# scripts/linkedin_scraper.py
"""
LinkedIn profile scraper.

Two entry points:
  scrape_profile(url, stage_path)         — Playwright headless fetch
  parse_export_zip(zip_bytes, stage_path) — LinkedIn data archive CSV parse

Both write a staging file at stage_path and return the extracted dict.
"""
from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from scripts.linkedin_utils import parse_html

_LINKEDIN_PROFILE_RE = re.compile(r"https?://(www\.)?linkedin\.com/in/", re.I)

_CHROME_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _write_stage(stage_path: Path, payload: dict) -> None:
    """Atomic write: write to .tmp then rename to avoid partial reads."""
    tmp = stage_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    tmp.rename(stage_path)


def scrape_profile(url: str, stage_path: Path) -> dict:
    """
    Fetch a public LinkedIn profile via Playwright headless Chrome.

    Raises ValueError if url is not a linkedin.com/in/ URL.
    Raises RuntimeError on scrape failure (timeout, blocked, etc.).
    Returns the extracted dict and writes the staging file.
    """
    if not _LINKEDIN_PROFILE_RE.match(url):
        raise ValueError(
            f"Expected a LinkedIn profile URL (linkedin.com/in/…), got: {url}"
        )

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(user_agent=_CHROME_UA)
            page.goto(url, timeout=30_000)
            page.wait_for_selector(
                "h1, section[data-section], #experience, #about",
                timeout=20_000,
            )
            raw_html = page.content()
            browser.close()
    except PWTimeout:
        raise RuntimeError(
            "LinkedIn did not load in time — the request may have been blocked. "
            "Try the data export option instead."
        )
    except Exception as e:
        raise RuntimeError(f"LinkedIn scrape failed: {e}") from e

    extracted = parse_html(raw_html)
    extracted["linkedin"] = url

    _write_stage(stage_path, {
        "url":        url,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source":     "url_scrape",
        "raw_html":   raw_html,
        "extracted":  extracted,
    })
    return extracted


def parse_export_zip(zip_bytes: bytes, stage_path: Path) -> dict:
    """
    Parse a LinkedIn data export archive.

    zip_bytes: raw zip bytes — callers do: zip_bytes = uploaded_file.read()
    Returns the extracted dict and writes the staging file.
    Missing CSV files are skipped silently.
    """
    extracted: dict = {
        "name": "", "email": "", "phone": "", "linkedin": "",
        "career_summary": "",
        "experience": [], "education": [], "skills": [], "achievements": [],
    }

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names_in_zip = {n.lower(): n for n in zf.namelist()}

            def _read_csv(filename: str) -> list[dict]:
                key = filename.lower()
                if key not in names_in_zip:
                    return []
                text = zf.read(names_in_zip[key]).decode("utf-8-sig", errors="replace")
                return list(csv.DictReader(io.StringIO(text)))

            for row in _read_csv("Profile.csv"):
                first = row.get("First Name", "").strip()
                last  = row.get("Last Name", "").strip()
                extracted["name"]           = f"{first} {last}".strip()
                extracted["email"]          = row.get("Email Address", "").strip()
                extracted["career_summary"] = row.get("Summary", "").strip()
                break

            for row in _read_csv("Position.csv"):
                company    = row.get("Company Name", "").strip()
                title      = row.get("Title", "").strip()
                desc       = row.get("Description", "").strip()
                start      = row.get("Started On", "").strip()
                end        = row.get("Finished On", "").strip()
                end_label  = end if end else ("Present" if start else "")
                date_range = f"{start} – {end_label}".strip(" –") if (start or end) else ""
                bullets    = [d.strip() for d in re.split(r"[.•\n]+", desc) if d.strip() and len(d.strip()) > 3]
                if company or title:
                    extracted["experience"].append({
                        "company":    company,
                        "title":      title,
                        "date_range": date_range,
                        "bullets":    bullets,
                    })

            for row in _read_csv("Education.csv"):
                school = row.get("School Name", "").strip()
                degree = row.get("Degree Name", "").strip()
                field  = row.get("Field Of Study", "").strip()
                start  = row.get("Start Date", "").strip()
                end    = row.get("End Date", "").strip()
                dates  = f"{start} – {end}".strip(" –") if start or end else ""
                if school or degree:
                    extracted["education"].append({
                        "school": school,
                        "degree": degree,
                        "field":  field,
                        "dates":  dates,
                    })

            for row in _read_csv("Skills.csv"):
                skill = row.get("Name", "").strip()
                if skill:
                    extracted["skills"].append(skill)

            for row in _read_csv("Certifications.csv"):
                name = row.get("Name", "").strip()
                if name:
                    extracted["achievements"].append(name)

    except zipfile.BadZipFile as e:
        raise ValueError(f"Not a valid zip file: {e}")

    _write_stage(stage_path, {
        "url":        None,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source":     "export_zip",
        "raw_html":   None,
        "extracted":  extracted,
    })
    return extracted
