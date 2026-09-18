"""Thin cf-orch task-allocation client.

Deliberately not a dependency on the circuitforge-orch package -- that
package bundles the full coordinator server (fastapi, typer, mcp, psutil),
far more than Peregrine's runtime needs for a single allocate/release round
trip. Mirrors the wire protocol CFOrchClient.task_allocate() uses
(circuitforge_orch/client.py) without the extra weight.
"""
from __future__ import annotations

import httpx


class CfOrchTaskError(Exception):
    """Raised when cf-orch has no assignment for this product/task, or the
    allocation or inference call itself fails. Callers get one exception
    type to catch regardless of which step failed."""


def complete_via_cf_orch(
    orch_url: str,
    product: str,
    task: str,
    prompt: str,
    *,
    user_id: str | None = None,
    model_override: str | None = None,
    system: str | None = None,
    max_tokens: int = 1200,
    ttl_s: float = 300.0,
) -> str:
    """Allocate a service through cf-orch's task-allocation API, run one
    chat completion against it, and release the allocation.

    model_override lets a premium user's own fine-tuned model alias be
    tried ahead of the product's shared task assignment (cf-orch's
    UserModelRegistry only overrides a candidate whose exact alias string
    is offered -- passing it here is what makes that override reachable;
    see circuitforge-orch#113).
    """
    orch_url = orch_url.rstrip("/")
    body: dict = {"product": product, "task": task, "ttl_s": ttl_s, "payload": {}}
    if user_id:
        body["user_id"] = user_id
    if model_override:
        body["model_override"] = model_override

    try:
        alloc_resp = httpx.post(f"{orch_url}/api/inference/task", json=body, timeout=120.0)
    except httpx.HTTPError as exc:
        raise CfOrchTaskError(f"cf-orch unreachable at {orch_url}: {exc}") from exc

    if alloc_resp.status_code == 404:
        raise CfOrchTaskError(f"No cf-orch assignment for {product}.{task}")
    if not alloc_resp.is_success:
        raise CfOrchTaskError(
            f"cf-orch allocation failed for {product}.{task}: "
            f"HTTP {alloc_resp.status_code} — {alloc_resp.text[:200]}"
        )

    alloc = alloc_resp.json()
    svc_url = alloc.get("url", "")
    allocation_id = alloc.get("allocation_id")
    service = alloc.get("service")
    if not svc_url:
        raise CfOrchTaskError(f"cf-orch allocation for {product}.{task} returned no service URL")

    try:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            resp = httpx.post(
                f"{svc_url.rstrip('/')}/v1/chat/completions",
                json={"messages": messages, "max_tokens": max_tokens},
                timeout=180.0,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise CfOrchTaskError(f"cf-orch inference call failed: {exc}") from exc
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    finally:
        if allocation_id and service:
            try:
                httpx.delete(
                    f"{orch_url}/api/services/{service}/allocations/{allocation_id}",
                    timeout=10.0,
                )
            except Exception:
                pass
