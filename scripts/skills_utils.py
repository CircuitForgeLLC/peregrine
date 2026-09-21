"""
skills_utils.py — Content filter and suggestion loader for the skills tagging system.

load_suggestions(category)  → list[str]   bundled suggestions for a category
filter_tag(tag)             → str | None   cleaned tag, or None if rejected
"""
from __future__ import annotations

import re
from pathlib import Path

_SUGGESTIONS_FILE = Path(__file__).parent.parent / "config" / "skills_suggestions.yaml"

# ── Content filter ─────────────────────────────────────────────────────────────
# Tags must be short, human-readable skill/domain labels. No URLs, no abuse.

_BLOCKED = {
    # profanity placeholder — extend as needed
    "fuck", "shit", "ass", "bitch", "cunt", "dick", "bastard", "damn",
}

_URL_RE = re.compile(r"https?://|www\.|\.com\b|\.net\b|\.org\b", re.IGNORECASE)
_ALLOWED_CHARS = re.compile(r"^[\w\s\-\.\+\#\/\&\(\)]+$", re.UNICODE)


def filter_tag(raw: str) -> str | None:
    """Return a cleaned tag string, or None if the tag should be rejected.

    Rejection criteria:
    - Blank after stripping
    - Too short (< 2 chars) or too long (> 60 chars)
    - Contains a URL pattern
    - Contains disallowed characters
    - Matches a blocked term (case-insensitive, whole-word)
    - Repeated character run (e.g. 'aaaaa')
    """
    tag = " ".join(raw.strip().split())  # normalise whitespace
    if not tag or len(tag) < 2:
        return None
    if len(tag) > 60:
        return None
    if _URL_RE.search(tag):
        return None
    if not _ALLOWED_CHARS.match(tag):
        return None
    lower = tag.lower()
    for blocked in _BLOCKED:
        if re.search(rf"\b{re.escape(blocked)}\b", lower):
            return None
    if re.search(r"(.)\1{4,}", lower):  # 5+ repeated chars
        return None
    return tag


# ── Suggestion loader ──────────────────────────────────────────────────────────

def load_suggestions(category: str) -> list[str]:
    """Return the bundled suggestion list for a category ('skills'|'domains'|'keywords').
    Returns an empty list if the file is missing or the category is not found.
    """
    if not _SUGGESTIONS_FILE.exists():
        return []
    try:
        import yaml
        data = yaml.safe_load(_SUGGESTIONS_FILE.read_text()) or {}
        return list(data.get(category, []))
    except Exception:  # noqa: BLE001 -- the try block mixes read_text()
        # (OSError subclasses, plus UnicodeDecodeError which is NOT an
        # OSError subclass), yaml.safe_load() (yaml.YAMLError on malformed
        # YAML), and data.get()/list() (AttributeError/TypeError if the
        # bundled YAML's shape doesn't match, e.g. a list at the document
        # root). This feeds a non-critical UI suggestion list, so returning
        # [] is the intended graceful-degradation contract, matching the
        # existing "file missing -> []" branch above. This module has no
        # logging setup and the suggestions file ships with the package
        # (not user-editable in normal operation), so adding a new logging
        # import for this fallback isn't warranted.
        return []
