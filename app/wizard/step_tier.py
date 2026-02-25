"""Step 2 — Tier selection (free / paid / premium)."""
from app.wizard.tiers import TIERS


def validate(data: dict) -> list[str]:
    """Return list of validation errors. Empty list = step passes."""
    errors = []
    tier = data.get("tier", "")
    if not tier:
        errors.append("Tier selection is required.")
    elif tier not in TIERS:
        errors.append(f"Invalid tier '{tier}'. Choose: {', '.join(TIERS)}.")
    return errors
