"""
BYOK cloud backend detection.

Determines whether LLM backends in llm.yaml send data to third-party cloud
providers. Used by Settings (activation warning) and app.py (sidebar indicator).

No Streamlit dependency — pure Python so it's unit-testable and reusable.
"""

LOCAL_URL_MARKERS = ("localhost", "127.0.0.1", "0.0.0.0")


def is_cloud_backend(name: str, cfg: dict) -> bool:
    """Return True if this backend sends prompts to a third-party cloud provider.

    Classification rules (applied in order):
      1. local: true in cfg → always local (user override)
      2. vision_service type → always local
      3. anthropic or claude_code type → always cloud
      4. openai_compat with a localhost/loopback base_url → local
      5. openai_compat with any other base_url → cloud
      6. anything else → local (unknown types assumed safe)
    """
    if cfg.get("local", False):
        return False

    btype = cfg.get("type", "")

    if btype == "vision_service":
        return False

    if btype in ("anthropic", "claude_code"):
        return True

    if btype == "openai_compat":
        url = cfg.get("base_url", "")
        return not any(marker in url for marker in LOCAL_URL_MARKERS)

    return False


def cloud_backends(llm_cfg: dict) -> list[str]:
    """Return names of enabled cloud backends from a parsed llm.yaml dict.

    Args:
        llm_cfg: parsed contents of config/llm.yaml

    Returns:
        List of backend names that are enabled and classified as cloud.
        Empty list means fully local configuration.
    """
    return [
        name
        for name, cfg in llm_cfg.get("backends", {}).items()
        if cfg.get("enabled", True) and is_cloud_backend(name, cfg)
    ]
