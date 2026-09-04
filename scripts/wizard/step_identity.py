"""Step 3 — Identity (name, email, phone, linkedin, career_summary)."""


def validate(data: dict) -> list[str]:
    """Return list of validation errors. Empty list = step passes."""
    errors = []
    if not (data.get("name") or "").strip():
        errors.append("Full name is required.")
    if not (data.get("email") or "").strip():
        errors.append("Email address is required.")
    if not (data.get("career_summary") or "").strip():
        errors.append("Career summary is required.")
    return errors
