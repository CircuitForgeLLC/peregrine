# scripts/linkedin_parser.py
"""
LinkedIn staging file reader.

parse_stage(stage_path) reads an existing staging file and returns
a structured dict. For url_scrape sources it re-runs the HTML parser
so improvements to linkedin_utils take effect without a new scrape.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.linkedin_utils import parse_html


def parse_stage(stage_path: Path) -> tuple[dict, str]:
    """
    Read and return the extracted profile data from a staging file.

    For url_scrape sources: re-runs parse_html on stored raw_html so
    parser improvements are applied without re-scraping.

    Returns (extracted_dict, error_string).
    On any failure returns ({}, error_message).
    """
    if not stage_path.exists():
        return {}, f"No staged data found at {stage_path}"

    try:
        data = json.loads(stage_path.read_text())
    except Exception as e:
        return {}, f"Could not read staging file: {e}"

    source   = data.get("source")
    raw_html = data.get("raw_html")

    if source == "url_scrape" and raw_html:
        # Re-run the parser — picks up any selector improvements
        extracted = parse_html(raw_html)
        # Preserve linkedin URL — parse_html always returns "" for this field
        extracted["linkedin"] = extracted.get("linkedin") or data.get("url") or ""

        # Write updated extracted back to staging file atomically
        data["extracted"] = extracted
        tmp = stage_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        tmp.rename(stage_path)

        return extracted, ""

    extracted = data.get("extracted")
    if not extracted:
        return {}, "Staging file has no extracted data"

    return extracted, ""
