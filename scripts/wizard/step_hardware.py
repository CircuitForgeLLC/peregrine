"""Step 1 — Hardware detection and inference profile selection."""

PROFILES = ["cpu", "single-gpu", "dual-gpu", "cf-orch", "remote"]


def validate(data: dict) -> list[str]:
    """Return list of validation errors. Empty list = step passes."""
    errors = []
    profile = data.get("inference_profile", "")
    if not profile:
        errors.append("Inference profile is required.")
    elif profile not in PROFILES:
        errors.append(f"Invalid inference profile '{profile}'. Choose: {', '.join(PROFILES)}.")
    return errors
