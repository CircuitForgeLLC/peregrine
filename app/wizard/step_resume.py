"""Step 4 — Resume (upload or guided form builder)."""


def validate(data: dict) -> list[str]:
    """Return list of validation errors. Empty list = step passes."""
    errors = []
    experience = data.get("experience") or []
    if not experience:
        errors.append("At least one work experience entry is required.")
    return errors
