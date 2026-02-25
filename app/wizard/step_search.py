"""Step 6 — Job search preferences (titles, locations, boards, keywords)."""


def validate(data: dict) -> list[str]:
    """Return list of validation errors. Empty list = step passes."""
    errors = []
    titles = data.get("job_titles") or []
    locations = data.get("locations") or []
    if not titles:
        errors.append("At least one job title is required.")
    if not locations:
        errors.append("At least one location is required.")
    return errors
