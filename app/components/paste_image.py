"""
Paste-from-clipboard / drag-and-drop image component.

Uses st.components.v1.declare_component so JS can return image bytes to Python
(st.components.v1.html() is one-way only).  No build step required — the
frontend is a single index.html file.
"""
from __future__ import annotations

import base64
from pathlib import Path

import streamlit.components.v1 as components

_FRONTEND = Path(__file__).parent / "paste_image_ui"

_paste_image = components.declare_component("paste_image", path=str(_FRONTEND))


def paste_image_component(key: str | None = None) -> bytes | None:
    """
    Render the paste/drop zone.  Returns PNG/JPEG bytes when an image is
    pasted or dropped, or None if nothing has been submitted yet.
    """
    result = _paste_image(key=key)
    if result:
        try:
            return base64.b64decode(result)
        except Exception:
            return None
    return None
