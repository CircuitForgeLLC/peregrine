"""Step 5 — LLM inference backend configuration and key entry."""


def validate(data: dict) -> list[str]:
    """Return list of validation errors. Empty list = step passes."""
    errors = []
    if not data.get("endpoint_confirmed"):
        errors.append("At least one working LLM endpoint must be confirmed.")
    return errors
