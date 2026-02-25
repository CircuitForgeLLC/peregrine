"""
LLM abstraction layer with priority fallback chain.
Reads config/llm.yaml. Tries backends in order; falls back on any error.
"""
import os
import yaml
import requests
from pathlib import Path
from openai import OpenAI

CONFIG_PATH = Path(__file__).parent.parent / "config" / "llm.yaml"


class LLMRouter:
    def __init__(self, config_path: Path = CONFIG_PATH):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

    def _is_reachable(self, base_url: str) -> bool:
        """Quick health-check ping. Returns True if backend is up."""
        health_url = base_url.rstrip("/").removesuffix("/v1") + "/health"
        try:
            resp = requests.get(health_url, timeout=2)
            return resp.status_code < 500
        except Exception:
            return False

    def _resolve_model(self, client: OpenAI, model: str) -> str:
        """Resolve __auto__ to the first model served by vLLM."""
        if model != "__auto__":
            return model
        models = client.models.list()
        return models.data[0].id

    def complete(self, prompt: str, system: str | None = None,
                 model_override: str | None = None,
                 fallback_order: list[str] | None = None,
                 images: list[str] | None = None) -> str:
        """
        Generate a completion. Tries each backend in fallback_order.

        model_override: when set, replaces the configured model for
        openai_compat backends (e.g. pass a research-specific ollama model).
        fallback_order: when set, overrides config fallback_order for this
        call (e.g. pass config["research_fallback_order"] for research tasks).
        images: optional list of base64-encoded PNG/JPG strings. When provided,
        backends without supports_images=true are skipped. vision_service backends
        are only tried when images is provided.
        Raises RuntimeError if all backends are exhausted.
        """
        order = fallback_order if fallback_order is not None else self.config["fallback_order"]
        for name in order:
            backend = self.config["backends"][name]

            if not backend.get("enabled", True):
                print(f"[LLMRouter] {name}: disabled, skipping")
                continue

            supports_images = backend.get("supports_images", False)
            is_vision_service = backend["type"] == "vision_service"

            # vision_service only used when images provided
            if is_vision_service and not images:
                print(f"[LLMRouter] {name}: vision_service skipped (no images)")
                continue

            # non-vision backends skipped when images provided and they don't support it
            if images and not supports_images and not is_vision_service:
                print(f"[LLMRouter] {name}: no image support, skipping")
                continue

            if is_vision_service:
                if not self._is_reachable(backend["base_url"]):
                    print(f"[LLMRouter] {name}: unreachable, skipping")
                    continue
                try:
                    resp = requests.post(
                        backend["base_url"].rstrip("/") + "/analyze",
                        json={
                            "prompt": prompt,
                            "image_base64": images[0] if images else "",
                        },
                        timeout=60,
                    )
                    resp.raise_for_status()
                    print(f"[LLMRouter] Used backend: {name} (vision_service)")
                    return resp.json()["text"]
                except Exception as e:
                    print(f"[LLMRouter] {name}: error — {e}, trying next")
                    continue

            elif backend["type"] == "openai_compat":
                if not self._is_reachable(backend["base_url"]):
                    print(f"[LLMRouter] {name}: unreachable, skipping")
                    continue
                try:
                    client = OpenAI(
                        base_url=backend["base_url"],
                        api_key=backend.get("api_key") or "any",
                    )
                    raw_model = model_override or backend["model"]
                    model = self._resolve_model(client, raw_model)
                    messages = []
                    if system:
                        messages.append({"role": "system", "content": system})
                    if images and supports_images:
                        content = [{"type": "text", "text": prompt}]
                        for img in images:
                            content.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{img}"},
                            })
                        messages.append({"role": "user", "content": content})
                    else:
                        messages.append({"role": "user", "content": prompt})

                    resp = client.chat.completions.create(
                        model=model, messages=messages
                    )
                    print(f"[LLMRouter] Used backend: {name} ({model})")
                    return resp.choices[0].message.content

                except Exception as e:
                    print(f"[LLMRouter] {name}: error — {e}, trying next")
                    continue

            elif backend["type"] == "anthropic":
                api_key = os.environ.get(backend["api_key_env"], "")
                if not api_key:
                    print(f"[LLMRouter] {name}: {backend['api_key_env']} not set, skipping")
                    continue
                try:
                    import anthropic as _anthropic
                    client = _anthropic.Anthropic(api_key=api_key)
                    if images and supports_images:
                        content = []
                        for img in images:
                            content.append({
                                "type": "image",
                                "source": {"type": "base64", "media_type": "image/png", "data": img},
                            })
                        content.append({"type": "text", "text": prompt})
                    else:
                        content = prompt
                    kwargs: dict = {
                        "model": backend["model"],
                        "max_tokens": 4096,
                        "messages": [{"role": "user", "content": content}],
                    }
                    if system:
                        kwargs["system"] = system
                    msg = client.messages.create(**kwargs)
                    print(f"[LLMRouter] Used backend: {name}")
                    return msg.content[0].text
                except Exception as e:
                    print(f"[LLMRouter] {name}: error — {e}, trying next")
                    continue

        raise RuntimeError("All LLM backends exhausted")


# Module-level singleton for convenience
_router: LLMRouter | None = None


def complete(prompt: str, system: str | None = None) -> str:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router.complete(prompt, system)
