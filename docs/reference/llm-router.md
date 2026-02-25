# LLM Router

`scripts/llm_router.py` provides a unified LLM interface with automatic fallback. All LLM calls in Peregrine go through `LLMRouter.complete()`.

---

## How It Works

`LLMRouter` reads `config/llm.yaml` on instantiation. When `complete()` is called:

1. It iterates through the active fallback order
2. For each backend, it checks:
   - Is the backend `enabled`?
   - Is it reachable (health check ping)?
   - Does it support the request type (text-only vs. vision)?
3. On the first backend that succeeds, it returns the completion
4. On any error (network, model error, timeout), it logs the failure and tries the next backend
5. If all backends are exhausted, it raises `RuntimeError("All LLM backends exhausted")`

```
fallback_order: [ollama, claude_code, vllm, github_copilot, anthropic]
                    ↓ try
                    ↓ unreachable? → skip
                    ↓ disabled? → skip
                    ↓ error? → next
                    → return completion
```

---

## Backend Types

### `openai_compat`

Any backend that speaks the OpenAI Chat Completions API. This includes:
- Ollama (`http://localhost:11434/v1`)
- vLLM (`http://localhost:8000/v1`)
- Claude Code wrapper (`http://localhost:3009/v1`)
- GitHub Copilot wrapper (`http://localhost:3010/v1`)

Health check: `GET {base_url}/health` (strips `/v1` suffix)

### `anthropic`

Calls the Anthropic Python SDK directly. Reads the API key from the environment variable named in `api_key_env`.

Health check: skips health check; proceeds if `api_key_env` is set in the environment.

### `vision_service`

The local Moondream2 inference service. Only used when `images` is provided to `complete()`.

Health check: `GET {base_url}/health`

Request: `POST {base_url}/analyze` with `{"prompt": ..., "image_base64": ...}`

---

## `complete()` Signature

```python
def complete(
    prompt: str,
    system: str | None = None,
    model_override: str | None = None,
    fallback_order: list[str] | None = None,
    images: list[str] | None = None,
) -> str:
```

| Parameter | Description |
|-----------|-------------|
| `prompt` | The user message |
| `system` | Optional system prompt (passed as the `system` role) |
| `model_override` | Overrides the configured model for `openai_compat` backends (e.g. pass a research-specific Ollama model) |
| `fallback_order` | Override the fallback chain for this call only (e.g. `config["research_fallback_order"]`) |
| `images` | Optional list of base64-encoded PNG/JPG strings. When provided, backends without `supports_images: true` are skipped automatically. |

---

## Fallback Chains

Three named chains are defined in `config/llm.yaml`:

| Config key | Used for |
|-----------|---------|
| `fallback_order` | Cover letter generation and general tasks |
| `research_fallback_order` | Company research briefs |
| `vision_fallback_order` | Survey screenshot analysis (requires `images`) |

Pass a chain explicitly:

```python
router = LLMRouter()

# Use the research chain
result = router.complete(
    prompt=research_prompt,
    system=system_prompt,
    fallback_order=router.config["research_fallback_order"],
)

# Use the vision chain with an image
result = router.complete(
    prompt="Describe what you see in this survey",
    fallback_order=router.config["vision_fallback_order"],
    images=[base64_image_string],
)
```

---

## Vision Routing

When `images` is provided:

- Backends with `supports_images: false` are skipped
- `vision_service` backends are tried (POST to `/analyze`)
- `openai_compat` backends with `supports_images: true` receive images as multipart content in the user message
- `anthropic` backends with `supports_images: true` receive images as base64 content blocks

When `images` is NOT provided:

- `vision_service` backends are skipped entirely

---

## `__auto__` Model Resolution

vLLM can serve different models depending on what is loaded. Set `model: __auto__` in `config/llm.yaml` for the vLLM backend:

```yaml
vllm:
  type: openai_compat
  base_url: http://localhost:8000/v1
  model: __auto__
```

`LLMRouter` calls `client.models.list()` and uses the first model returned. This avoids hard-coding a model name that may change when you swap the loaded model.

---

## Adding a Backend

1. Add an entry to `config/llm.yaml`:

```yaml
backends:
  my_backend:
    type: openai_compat          # or "anthropic" | "vision_service"
    base_url: http://localhost:9000/v1
    api_key: my-key
    model: my-model-name
    enabled: true
    supports_images: false
```

2. Add it to one or more fallback chains:

```yaml
fallback_order:
  - ollama
  - my_backend      # add here
  - claude_code
  - anthropic
```

3. No code changes are needed — the router reads the config at startup.

---

## Module-Level Convenience Function

A module-level singleton is provided for simple one-off calls:

```python
from scripts.llm_router import complete

result = complete("Write a brief summary of this company.", system="You are a research assistant.")
```

This uses the default `fallback_order` from `config/llm.yaml`. For per-task chain overrides, instantiate `LLMRouter` directly.

---

## Config Reference

```yaml
# config/llm.yaml

backends:
  ollama:
    type: openai_compat
    base_url: http://localhost:11434/v1
    api_key: ollama
    model: llama3.1:8b
    enabled: true
    supports_images: false

  anthropic:
    type: anthropic
    api_key_env: ANTHROPIC_API_KEY    # env var name (not the key itself)
    model: claude-sonnet-4-6
    enabled: false
    supports_images: true

  vision_service:
    type: vision_service
    base_url: http://localhost:8002
    enabled: true
    supports_images: true

fallback_order:
  - ollama
  - claude_code
  - vllm
  - github_copilot
  - anthropic

research_fallback_order:
  - claude_code
  - vllm
  - ollama_research
  - github_copilot
  - anthropic

vision_fallback_order:
  - vision_service
  - claude_code
  - anthropic
```
