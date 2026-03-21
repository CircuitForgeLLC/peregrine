# Survey Assistant Vue SPA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port `app/pages/7_Survey.py` to a Vue 3 SPA view at `/survey/:id` with text/screenshot input, Quick/Detailed mode, synchronous LLM analysis, save-to-job, and response history.

**Architecture:** Three independent layers — backend (4 new FastAPI endpoints in `dev-api.py`), a Pinia store (`survey.ts`) that wraps those endpoints, and a single-column Vue view (`SurveyView.vue`) that reads from the store. The InterviewCard kanban component gains a "Survey →" emit button wired to the parent `InterviewsView`.

**Tech Stack:** Python/FastAPI (`dev-api.py`), Pinia + Vue 3 Composition API, Vitest (store tests), pytest + FastAPI TestClient (backend tests).

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `dev-api.py` | 4 new survey endpoints: vision health, analyze, save response, get history |
| Create | `tests/test_dev_api_survey.py` | Backend tests for all 4 endpoints |
| Create | `web/src/stores/survey.ts` | Pinia store: `fetchFor`, `analyze`, `saveResponse`, `clear` |
| Create | `web/src/stores/survey.test.ts` | Unit tests for survey store |
| Modify | `web/src/router/index.ts` | Add `/survey/:id` route (currently only `/survey` exists) |
| Modify | `web/src/views/SurveyView.vue` | Replace placeholder stub with full implementation |
| Modify | `web/src/components/InterviewCard.vue` | Add `emit('survey', job.id)` button |
| Modify | `web/src/views/InterviewsView.vue` | Add `@survey` on 3 kanban InterviewCard instances + "Survey →" button in pre-list row for `survey`-stage jobs |

---

## Task 1: Backend — 4 survey endpoints + tests

**Files:**
- Modify: `dev-api.py` — add after the interview prep block (~line 367)
- Create: `tests/test_dev_api_survey.py`

### Context for the implementer

`dev-api.py` already imports: `datetime`, `Path`, `BaseModel`, `Optional`, `HTTPException`. **`requests` is NOT currently imported** — add `import requests` to the module-level imports section at the top of the file. The LLMRouter is NOT pre-imported — use a lazy import inside the endpoint function (consistent with `submit_task` pattern).

The prompt builders below use **lowercase** mode (`"quick"` / `"detailed"`) because the frontend sends lowercase. The existing Streamlit page uses capitalized mode but the Vue version standardizes to lowercase throughout.

`insert_survey_response` signature (from `scripts/db.py`):
```python
def insert_survey_response(
    db_path, job_id, survey_name, received_at, source,
    raw_input, image_path, mode, llm_output, reported_score
) -> int
```

`get_survey_responses(db_path, job_id)` returns `list[dict]`, newest first.

Test import pattern (from `tests/test_dev_api_prep.py`):
```python
@pytest.fixture
def client():
    import sys
    sys.path.insert(0, "/Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa")
    from dev_api import app
    return TestClient(app)
```

Note: the module name is `dev_api` (underscore) even though the file is `dev-api.py`.

Mock pattern for DB: `patch("dev_api._get_db", return_value=mock_db)`.
Mock pattern for LLMRouter: `patch("dev_api.LLMRouter")` — the lazy import means we patch at the `dev_api` module level after it's been imported.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dev_api_survey.py`:

```python
"""Tests for survey endpoints: vision health, analyze, save response, get history."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    import sys
    sys.path.insert(0, "/Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa")
    from dev_api import app
    return TestClient(app)


# ── GET /api/vision/health ───────────────────────────────────────────────────

def test_vision_health_available(client):
    """Returns available=true when vision service responds 200."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("dev_api.requests.get", return_value=mock_resp):
        resp = client.get("/api/vision/health")
    assert resp.status_code == 200
    assert resp.json() == {"available": True}


def test_vision_health_unavailable(client):
    """Returns available=false when vision service times out or errors."""
    with patch("dev_api.requests.get", side_effect=Exception("timeout")):
        resp = client.get("/api/vision/health")
    assert resp.status_code == 200
    assert resp.json() == {"available": False}


# ── POST /api/jobs/{id}/survey/analyze ──────────────────────────────────────

def test_analyze_text_quick(client):
    """Text mode quick analysis returns output and source=text_paste."""
    mock_router = MagicMock()
    mock_router.complete.return_value = "1. B — best option"
    mock_router.config.get.return_value = ["claude_code", "vllm"]
    with patch("dev_api.LLMRouter", return_value=mock_router):
        resp = client.post("/api/jobs/1/survey/analyze", json={
            "text": "Q1: Do you prefer teamwork?\nA. Solo  B. Together",
            "mode": "quick",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "text_paste"
    assert "B" in data["output"]
    # System prompt must be passed for text path
    call_kwargs = mock_router.complete.call_args[1]
    assert "system" in call_kwargs
    assert "culture-fit survey" in call_kwargs["system"]


def test_analyze_text_detailed(client):
    """Text mode detailed analysis passes correct prompt."""
    mock_router = MagicMock()
    mock_router.complete.return_value = "Option A: good for... Option B: better because..."
    mock_router.config.get.return_value = []
    with patch("dev_api.LLMRouter", return_value=mock_router):
        resp = client.post("/api/jobs/1/survey/analyze", json={
            "text": "Q1: Describe your work style.",
            "mode": "detailed",
        })
    assert resp.status_code == 200
    assert resp.json()["source"] == "text_paste"


def test_analyze_image(client):
    """Image mode routes through vision path with NO system prompt."""
    mock_router = MagicMock()
    mock_router.complete.return_value = "1. C — collaborative choice"
    mock_router.config.get.return_value = ["vision_service", "claude_code"]
    with patch("dev_api.LLMRouter", return_value=mock_router):
        resp = client.post("/api/jobs/1/survey/analyze", json={
            "image_b64": "aGVsbG8=",
            "mode": "quick",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "screenshot"
    # No system prompt on vision path
    call_kwargs = mock_router.complete.call_args[1]
    assert "system" not in call_kwargs


def test_analyze_llm_failure(client):
    """Returns 500 when LLM raises an exception."""
    mock_router = MagicMock()
    mock_router.complete.side_effect = Exception("LLM unavailable")
    mock_router.config.get.return_value = []
    with patch("dev_api.LLMRouter", return_value=mock_router):
        resp = client.post("/api/jobs/1/survey/analyze", json={
            "text": "Q1: test",
            "mode": "quick",
        })
    assert resp.status_code == 500


# ── POST /api/jobs/{id}/survey/responses ────────────────────────────────────

def test_save_response_text(client):
    """Save text response writes to DB and returns id."""
    mock_db = MagicMock()
    with patch("dev_api._get_db", return_value=mock_db):
        with patch("dev_api.insert_survey_response", return_value=42) as mock_insert:
            resp = client.post("/api/jobs/1/survey/responses", json={
                "mode": "quick",
                "source": "text_paste",
                "raw_input": "Q1: test question",
                "llm_output": "1. B — good reason",
            })
    assert resp.status_code == 200
    assert resp.json()["id"] == 42
    # received_at generated by backend — not None
    call_args = mock_insert.call_args
    assert call_args[1]["received_at"] is not None or call_args[0][3] is not None


def test_save_response_with_image(client, tmp_path, monkeypatch):
    """Save image response writes PNG file and stores path in DB."""
    monkeypatch.setenv("STAGING_DB", str(tmp_path / "test.db"))
    # Patch DATA_DIR inside dev_api to a temp path
    with patch("dev_api.insert_survey_response", return_value=7) as mock_insert:
        with patch("dev_api.Path") as mock_path_cls:
            mock_path_cls.return_value.__truediv__ = lambda s, o: tmp_path / o
            resp = client.post("/api/jobs/1/survey/responses", json={
                "mode": "quick",
                "source": "screenshot",
                "image_b64": "aGVsbG8=",  # valid base64
                "llm_output": "1. B — reason",
            })
    assert resp.status_code == 200
    assert resp.json()["id"] == 7


# ── GET /api/jobs/{id}/survey/responses ─────────────────────────────────────

def test_get_history_empty(client):
    """Returns empty list when no history exists."""
    with patch("dev_api.get_survey_responses", return_value=[]):
        resp = client.get("/api/jobs/1/survey/responses")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_history_populated(client):
    """Returns history rows newest first."""
    rows = [
        {"id": 2, "survey_name": "Round 2", "mode": "detailed", "source": "text_paste",
         "raw_input": None, "image_path": None, "llm_output": "Option A is best",
         "reported_score": "90%", "received_at": "2026-03-21T14:00:00", "created_at": "2026-03-21T14:00:01"},
        {"id": 1, "survey_name": "Round 1", "mode": "quick", "source": "text_paste",
         "raw_input": "Q1: test", "image_path": None, "llm_output": "1. B",
         "reported_score": None, "received_at": "2026-03-21T12:00:00", "created_at": "2026-03-21T12:00:01"},
    ]
    with patch("dev_api.get_survey_responses", return_value=rows):
        resp = client.get("/api/jobs/1/survey/responses")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["id"] == 2
    assert data[0]["survey_name"] == "Round 2"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_dev_api_survey.py -v
```

Expected: All 10 tests FAIL with 404 / import errors (endpoints don't exist yet).

- [ ] **Step 3: Implement the 4 endpoints in `dev-api.py`**

First, add `import requests` to the module-level imports at the top of `dev-api.py` (after the existing `from typing import Optional` line).

Then add the following block after the `# Interview Prep endpoints` section (~line 367), before the `# GET /api/jobs/:id/cover_letter/pdf` section:

```python
# ── Survey endpoints ─────────────────────────────────────────────────────────

_SURVEY_SYSTEM = (
    "You are a job application advisor helping a candidate answer a culture-fit survey. "
    "The candidate values collaborative teamwork, clear communication, growth, and impact. "
    "Choose answers that present them in the best professional light."
)


def _build_text_prompt(text: str, mode: str) -> str:
    if mode == "quick":
        return (
            "Answer each survey question below. For each, give ONLY the letter of the best "
            "option and a single-sentence reason. Format exactly as:\n"
            "1. B — reason here\n2. A — reason here\n\n"
            f"Survey:\n{text}"
        )
    return (
        "Analyze each survey question below. For each question:\n"
        "- Briefly evaluate each option (1 sentence each)\n"
        "- State your recommendation with reasoning\n\n"
        f"Survey:\n{text}"
    )


def _build_image_prompt(mode: str) -> str:
    if mode == "quick":
        return (
            "This is a screenshot of a culture-fit survey. Read all questions and answer each "
            "with the letter of the best option for a collaborative, growth-oriented candidate. "
            "Format: '1. B — brief reason' on separate lines."
        )
    return (
        "This is a screenshot of a culture-fit survey. For each question, evaluate each option "
        "and recommend the best choice for a collaborative, growth-oriented candidate. "
        "Include a brief breakdown per option and a clear recommendation."
    )


@app.get("/api/vision/health")
def vision_health():
    try:
        r = requests.get("http://localhost:8002/health", timeout=2)
        return {"available": r.status_code == 200}
    except Exception:
        return {"available": False}


class SurveyAnalyzeBody(BaseModel):
    text: Optional[str] = None
    image_b64: Optional[str] = None
    mode: str  # "quick" or "detailed"


@app.post("/api/jobs/{job_id}/survey/analyze")
def survey_analyze(job_id: int, body: SurveyAnalyzeBody):
    try:
        from scripts.llm_router import LLMRouter
        router = LLMRouter()
        if body.image_b64:
            prompt = _build_image_prompt(body.mode)
            output = router.complete(
                prompt,
                images=[body.image_b64],
                fallback_order=router.config.get("vision_fallback_order"),
            )
            source = "screenshot"
        else:
            prompt = _build_text_prompt(body.text or "", body.mode)
            output = router.complete(
                prompt,
                system=_SURVEY_SYSTEM,
                fallback_order=router.config.get("research_fallback_order"),
            )
            source = "text_paste"
        return {"output": output, "source": source}
    except Exception as e:
        raise HTTPException(500, str(e))


class SurveySaveBody(BaseModel):
    survey_name: Optional[str] = None
    mode: str
    source: str
    raw_input: Optional[str] = None
    image_b64: Optional[str] = None
    llm_output: str
    reported_score: Optional[str] = None


@app.post("/api/jobs/{job_id}/survey/responses")
def save_survey_response(job_id: int, body: SurveySaveBody):
    from scripts.db import insert_survey_response
    received_at = datetime.now().isoformat()
    image_path = None
    if body.image_b64:
        import base64
        screenshots_dir = Path(DB_PATH).parent / "survey_screenshots" / str(job_id)
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        img_path = screenshots_dir / f"{timestamp}.png"
        img_path.write_bytes(base64.b64decode(body.image_b64))
        image_path = str(img_path)
    row_id = insert_survey_response(
        db_path=Path(DB_PATH),
        job_id=job_id,
        survey_name=body.survey_name,
        received_at=received_at,
        source=body.source,
        raw_input=body.raw_input,
        image_path=image_path,
        mode=body.mode,
        llm_output=body.llm_output,
        reported_score=body.reported_score,
    )
    return {"id": row_id}


@app.get("/api/jobs/{job_id}/survey/responses")
def get_survey_history(job_id: int):
    from scripts.db import get_survey_responses
    return get_survey_responses(db_path=Path(DB_PATH), job_id=job_id)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_dev_api_survey.py -v
```

Expected: 10/10 PASS. If `test_save_response_with_image` needs mock adjustments to the `Path`/directory creation, fix the test mock rather than the implementation.

- [ ] **Step 5: Run full test suite to catch regressions**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v
```

Expected: All previously-passing tests still pass.

- [ ] **Step 6: Commit**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
git add dev-api.py tests/test_dev_api_survey.py
git commit -m "feat(survey): add 4 backend survey endpoints with tests"
```

---

## Task 2: Survey Pinia store + unit tests

**Files:**
- Create: `web/src/stores/survey.ts`
- Create: `web/src/stores/survey.test.ts`

### Context for the implementer

Follow the exact same patterns as `web/src/stores/prep.ts`:
- `defineStore` with setup function (not options API)
- `useApiFetch` imported from `'../composables/useApi'` — returns `{ data: T | null, error: ApiError | null }`
- All refs initialized to their zero values

Test patterns from `web/src/stores/prep.test.ts`:
```typescript
vi.mock('../composables/useApi', () => ({ useApiFetch: vi.fn() }))
import { useApiFetch } from '../composables/useApi'
// ...
const mockApiFetch = vi.mocked(useApiFetch)
mockApiFetch.mockResolvedValueOnce({ data: ..., error: null })
```

The store has NO polling — survey analysis is synchronous. No `setInterval`/`clearInterval` needed.

`saveResponse` constructs the full save body by combining fields from `analysis` (set during `analyze`) with the args passed to `saveResponse`. The `analysis` ref must include `mode` and `rawInput` so `saveResponse` can include them without extra parameters.

- [ ] **Step 1: Write the failing store tests**

Create `web/src/stores/survey.test.ts`:

```typescript
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useSurveyStore } from './survey'

vi.mock('../composables/useApi', () => ({
  useApiFetch: vi.fn(),
}))

import { useApiFetch } from '../composables/useApi'

describe('useSurveyStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('fetchFor loads history and vision availability in parallel', async () => {
    const mockApiFetch = vi.mocked(useApiFetch)
    mockApiFetch
      .mockResolvedValueOnce({ data: [], error: null })                    // history
      .mockResolvedValueOnce({ data: { available: true }, error: null })   // vision

    const store = useSurveyStore()
    await store.fetchFor(1)

    expect(store.history).toEqual([])
    expect(store.visionAvailable).toBe(true)
    expect(store.currentJobId).toBe(1)
    expect(mockApiFetch).toHaveBeenCalledTimes(2)
  })

  it('fetchFor clears state when called for a different job', async () => {
    const mockApiFetch = vi.mocked(useApiFetch)
    // Job 1
    mockApiFetch
      .mockResolvedValueOnce({ data: [{ id: 1, llm_output: 'old' }], error: null })
      .mockResolvedValueOnce({ data: { available: false }, error: null })

    const store = useSurveyStore()
    await store.fetchFor(1)
    expect(store.history.length).toBe(1)

    // Job 2 — state must be cleared before new data arrives
    mockApiFetch
      .mockResolvedValueOnce({ data: [], error: null })
      .mockResolvedValueOnce({ data: { available: true }, error: null })

    await store.fetchFor(2)
    expect(store.history).toEqual([])
    expect(store.currentJobId).toBe(2)
  })

  it('analyze stores result including mode and rawInput', async () => {
    const mockApiFetch = vi.mocked(useApiFetch)
    mockApiFetch.mockResolvedValueOnce({
      data: { output: '1. B — reason', source: 'text_paste' },
      error: null,
    })

    const store = useSurveyStore()
    await store.analyze(1, { text: 'Q1: test', mode: 'quick' })

    expect(store.analysis).not.toBeNull()
    expect(store.analysis!.output).toBe('1. B — reason')
    expect(store.analysis!.source).toBe('text_paste')
    expect(store.analysis!.mode).toBe('quick')
    expect(store.analysis!.rawInput).toBe('Q1: test')
    expect(store.loading).toBe(false)
  })

  it('analyze sets error on failure', async () => {
    const mockApiFetch = vi.mocked(useApiFetch)
    mockApiFetch.mockResolvedValueOnce({
      data: null,
      error: { kind: 'http', status: 500, detail: 'LLM unavailable' },
    })

    const store = useSurveyStore()
    await store.analyze(1, { text: 'Q1: test', mode: 'quick' })

    expect(store.analysis).toBeNull()
    expect(store.error).toBeTruthy()
    expect(store.loading).toBe(false)
  })

  it('saveResponse prepends to history and clears analysis', async () => {
    const mockApiFetch = vi.mocked(useApiFetch)
    // Setup: fetchFor
    mockApiFetch
      .mockResolvedValueOnce({ data: [], error: null })
      .mockResolvedValueOnce({ data: { available: true }, error: null })

    const store = useSurveyStore()
    await store.fetchFor(1)

    // Set analysis state manually (as if analyze() was called)
    store.analysis = {
      output: '1. B — reason',
      source: 'text_paste',
      mode: 'quick',
      rawInput: 'Q1: test',
    }

    // Save
    mockApiFetch.mockResolvedValueOnce({
      data: { id: 42 },
      error: null,
    })

    await store.saveResponse(1, { surveyName: 'Round 1', reportedScore: '85%' })

    expect(store.history.length).toBe(1)
    expect(store.history[0].id).toBe(42)
    expect(store.history[0].llm_output).toBe('1. B — reason')
    expect(store.analysis).toBeNull()
    expect(store.saving).toBe(false)
  })

  it('clear resets all state to initial values', async () => {
    const mockApiFetch = vi.mocked(useApiFetch)
    mockApiFetch
      .mockResolvedValueOnce({ data: [{ id: 1, llm_output: 'test' }], error: null })
      .mockResolvedValueOnce({ data: { available: true }, error: null })

    const store = useSurveyStore()
    await store.fetchFor(1)

    store.clear()

    expect(store.history).toEqual([])
    expect(store.analysis).toBeNull()
    expect(store.visionAvailable).toBe(false)
    expect(store.loading).toBe(false)
    expect(store.saving).toBe(false)
    expect(store.error).toBeNull()
    expect(store.currentJobId).toBeNull()
  })
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web
npm run test -- survey.test.ts
```

Expected: All 6 tests FAIL (store doesn't exist yet).

- [ ] **Step 3: Implement `web/src/stores/survey.ts`**

```typescript
import { ref } from 'vue'
import { defineStore } from 'pinia'
import { useApiFetch } from '../composables/useApi'

export interface SurveyAnalysis {
  output: string
  source: 'text_paste' | 'screenshot'
  mode: 'quick' | 'detailed'
  rawInput: string | null
}

export interface SurveyResponse {
  id: number
  survey_name: string | null
  mode: 'quick' | 'detailed'
  source: string
  raw_input: string | null
  image_path: string | null
  llm_output: string
  reported_score: string | null
  received_at: string | null
  created_at: string | null
}

export const useSurveyStore = defineStore('survey', () => {
  const analysis = ref<SurveyAnalysis | null>(null)
  const history = ref<SurveyResponse[]>([])
  const loading = ref(false)
  const saving = ref(false)
  const error = ref<string | null>(null)
  const visionAvailable = ref(false)
  const currentJobId = ref<number | null>(null)

  async function fetchFor(jobId: number) {
    if (jobId !== currentJobId.value) {
      analysis.value = null
      history.value = []
      error.value = null
      visionAvailable.value = false
      currentJobId.value = jobId
    }

    const [historyResult, visionResult] = await Promise.all([
      useApiFetch<SurveyResponse[]>(`/api/jobs/${jobId}/survey/responses`),
      useApiFetch<{ available: boolean }>('/api/vision/health'),
    ])

    if (historyResult.error) {
      error.value = 'Could not load survey history.'
    } else {
      history.value = historyResult.data ?? []
    }

    visionAvailable.value = visionResult.data?.available ?? false
  }

  async function analyze(
    jobId: number,
    payload: { text?: string; image_b64?: string; mode: 'quick' | 'detailed' }
  ) {
    loading.value = true
    error.value = null
    const { data, error: fetchError } = await useApiFetch<{ output: string; source: string }>(
      `/api/jobs/${jobId}/survey/analyze`,
      { method: 'POST', body: JSON.stringify(payload) }
    )
    loading.value = false
    if (fetchError || !data) {
      error.value = 'Analysis failed. Please try again.'
      return
    }
    analysis.value = {
      output: data.output,
      source: data.source as 'text_paste' | 'screenshot',
      mode: payload.mode,
      rawInput: payload.text ?? null,
    }
  }

  async function saveResponse(
    jobId: number,
    args: { surveyName: string; reportedScore: string; image_b64?: string }
  ) {
    if (!analysis.value) return
    saving.value = true
    error.value = null
    const body = {
      survey_name: args.surveyName || undefined,
      mode: analysis.value.mode,
      source: analysis.value.source,
      raw_input: analysis.value.rawInput,
      image_b64: args.image_b64,
      llm_output: analysis.value.output,
      reported_score: args.reportedScore || undefined,
    }
    const { data, error: fetchError } = await useApiFetch<{ id: number }>(
      `/api/jobs/${jobId}/survey/responses`,
      { method: 'POST', body: JSON.stringify(body) }
    )
    saving.value = false
    if (fetchError || !data) {
      error.value = 'Save failed. Your analysis is preserved — try again.'
      return
    }
    // Prepend the saved response to history
    const saved: SurveyResponse = {
      id: data.id,
      survey_name: args.surveyName || null,
      mode: analysis.value.mode,
      source: analysis.value.source,
      raw_input: analysis.value.rawInput,
      image_path: null,
      llm_output: analysis.value.output,
      reported_score: args.reportedScore || null,
      received_at: new Date().toISOString(),
      created_at: new Date().toISOString(),
    }
    history.value = [saved, ...history.value]
    analysis.value = null
  }

  function clear() {
    analysis.value = null
    history.value = []
    loading.value = false
    saving.value = false
    error.value = null
    visionAvailable.value = false
    currentJobId.value = null
  }

  return {
    analysis,
    history,
    loading,
    saving,
    error,
    visionAvailable,
    currentJobId,
    fetchFor,
    analyze,
    saveResponse,
    clear,
  }
})
```

- [ ] **Step 4: Run store tests — verify they pass**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web
npm run test -- survey.test.ts
```

Expected: 6/6 PASS.

- [ ] **Step 5: Run full frontend test suite**

```bash
npm run test
```

Expected: All previously-passing tests still pass.

- [ ] **Step 6: Commit**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
git add web/src/stores/survey.ts web/src/stores/survey.test.ts
git commit -m "feat(survey): add survey Pinia store with tests"
```

---

## Task 3: SurveyView.vue + router + navigation wiring

**Files:**
- Modify: `web/src/router/index.ts` — add `/survey/:id` route
- Modify: `web/src/views/SurveyView.vue` — replace placeholder stub with full implementation
- Modify: `web/src/components/InterviewCard.vue` — add `emit('survey', job.id)` button
- Modify: `web/src/views/InterviewsView.vue` — add `@survey` on 3 `<InterviewCard>` instances + "Survey →" button in pre-list row for `survey`-stage jobs

### Context for the implementer

**Router:** Currently has `{ path: '/survey', component: ... }` but NOT `/survey/:id`. The spec requires both. Add the `:id` variant.

**SurveyView.vue:** Currently a 18-line placeholder stub. Replace it entirely. Layout spec:
- Single column, `max-width: 760px`, centered (`margin: 0 auto`), padding `var(--space-6)`
- Uses `var(--space-*)` and `var(--color-*)` CSS variables (theme-aware — see other views for examples)
- Sticky context bar at the top
- Tabs: Text paste (always active) / Screenshot (disabled with `aria-disabled` when `!visionAvailable`)
- Mode cards: two full-width stacked cards (⚡ Quick / 📋 Detailed), selected card gets border highlight
- Analyze button: full-width, disabled when no input; spinner while loading
- Results card: appears when `analysis` set; `white-space: pre-wrap`; inline save form below
- History accordion: closed by default; `summary` element for toggle

**InterviewCard.vue:** The established emit pattern:
```typescript
// Line 12-14 (existing)
const emit = defineEmits<{ prep: [jobId: number] }>()
// Add 'survey' to this definition
const emit = defineEmits<{ prep: [jobId: number]; survey: [jobId: number] }>()
```
Existing "Prep →" button (line ~182):
```html
<button v-if="['phone_screen', 'interviewing', 'offer'].includes(job.status)"
  class="card-action" @click.stop="emit('prep', job.id)">Prep →</button>
```
Add "Survey →" button with stages `['survey', 'phone_screen', 'interviewing', 'offer']` using the same `card-action` class.

**InterviewsView.vue:** There are **3** `<InterviewCard>` instances (kanban columns: phoneScreen line ~462, interviewing ~475, offerHired ~488) — NOT 4. The `survey`-stage jobs live in the pre-list section (lines ~372–432) which renders plain `<div class="pre-list-row">` elements, not `<InterviewCard>`.

Two changes needed:
1. Add `@survey="router.push('/survey/' + $event)"` to all 3 `<InterviewCard>` instances (same pattern as `@prep`).
2. Add a "Survey →" button directly to the pre-list row template for `survey`-stage jobs. The pre-list row is at line ~373 inside `v-for="job in pagedApplied"`. Add a button after the existing `btn-move-pre`:
```html
<button
  v-if="job.status === 'survey'"
  class="btn-move-pre"
  @click="router.push('/survey/' + job.id)"
>Survey →</button>
```

**Mount guard:** Read `route.params.id` → redirect to `/interviews` if missing or non-numeric. Look up job in `interviewsStore.jobs`; if status not in `['survey', 'phone_screen', 'interviewing', 'offer']`, redirect. Call `surveyStore.fetchFor(jobId)` on mount; `surveyStore.clear()` on unmount.

**useApiFetch body pattern:** Look at how `InterviewPrepView.vue` makes POST calls if needed — but the store handles all API calls; the view only calls store methods.

Look at `web/src/views/InterviewPrepView.vue` as the reference for how views use stores, handle route guards, and apply CSS variables. The theme variables file is at `web/src/assets/theme.css` or similar — check what exists.

- [ ] **Step 1: Verify existing theme variables and CSS patterns**

```bash
grep -r "var(--space\|var(--color\|var(--font" web/src/assets/ web/src/views/InterviewPrepView.vue 2>/dev/null | head -20
ls web/src/assets/
```

This confirms which CSS variables are available for the layout.

- [ ] **Step 2: Add `/survey/:id` route to router**

In `web/src/router/index.ts`, add after the existing `/survey` line:
```typescript
{ path: '/survey/:id', component: () => import('../views/SurveyView.vue') },
```

The existing `/survey` (no-id) route will continue to load `SurveyView.vue`, which is fine — the component mount guard immediately redirects to `/interviews` when `jobId` is missing/NaN. No router-level redirect needed.

- [ ] **Step 3: Implement SurveyView.vue**

Replace the placeholder stub entirely. Key sections:

```vue
<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useInterviewsStore } from '../stores/interviews'
import { useSurveyStore } from '../stores/survey'

const route = useRoute()
const router = useRouter()
const interviewsStore = useInterviewsStore()
const surveyStore = useSurveyStore()

const VALID_STAGES = ['survey', 'phone_screen', 'interviewing', 'offer']

const rawId = route.params.id
const jobId = rawId ? parseInt(String(rawId), 10) : NaN

// Redirect if no valid id
if (!jobId || isNaN(jobId)) {
  router.replace('/interviews')
}

// UI state
const activeTab = ref<'text' | 'screenshot'>('text')
const textInput = ref('')
const imageB64 = ref<string | null>(null)
const imagePreviewUrl = ref<string | null>(null)
const selectedMode = ref<'quick' | 'detailed'>('quick')
const surveyName = ref('')
const reportedScore = ref('')
const saveSuccess = ref(false)

// Computed job from store
const job = computed(() =>
  interviewsStore.jobs.find(j => j.id === jobId) ?? null
)

onMounted(async () => {
  if (!jobId || isNaN(jobId)) return
  if (interviewsStore.jobs.length === 0) {
    await interviewsStore.fetchAll()
  }
  if (!job.value || !VALID_STAGES.includes(job.value.status)) {
    router.replace('/interviews')
    return
  }
  await surveyStore.fetchFor(jobId)
})

onUnmounted(() => {
  surveyStore.clear()
})

// Screenshot handling
function handlePaste(e: ClipboardEvent) {
  if (!surveyStore.visionAvailable) return
  const items = e.clipboardData?.items
  if (!items) return
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      const file = item.getAsFile()
      if (file) loadImageFile(file)
      break
    }
  }
}

function handleDrop(e: DragEvent) {
  e.preventDefault()
  if (!surveyStore.visionAvailable) return
  const file = e.dataTransfer?.files[0]
  if (file && file.type.startsWith('image/')) loadImageFile(file)
}

function handleFileUpload(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) loadImageFile(file)
}

function loadImageFile(file: File) {
  const reader = new FileReader()
  reader.onload = (ev) => {
    const result = ev.target?.result as string
    imagePreviewUrl.value = result
    imageB64.value = result.split(',')[1]  // strip "data:image/...;base64,"
  }
  reader.readAsDataURL(file)
}

function clearImage() {
  imageB64.value = null
  imagePreviewUrl.value = null
}

// Analysis
const canAnalyze = computed(() =>
  activeTab.value === 'text' ? textInput.value.trim().length > 0 : imageB64.value !== null
)

async function runAnalyze() {
  const payload: { text?: string; image_b64?: string; mode: 'quick' | 'detailed' } = {
    mode: selectedMode.value,
  }
  if (activeTab.value === 'screenshot' && imageB64.value) {
    payload.image_b64 = imageB64.value
  } else {
    payload.text = textInput.value
  }
  await surveyStore.analyze(jobId, payload)
}

// Save
async function saveToJob() {
  await surveyStore.saveResponse(jobId, {
    surveyName: surveyName.value,
    reportedScore: reportedScore.value,
    image_b64: activeTab.value === 'screenshot' ? imageB64.value ?? undefined : undefined,
  })
  if (!surveyStore.error) {
    saveSuccess.value = true
    surveyName.value = ''
    reportedScore.value = ''
    setTimeout(() => { saveSuccess.value = false }, 3000)
  }
}

// Stage label helper
const stageLabel: Record<string, string> = {
  survey: 'Survey', phone_screen: 'Phone Screen',
  interviewing: 'Interviewing', offer: 'Offer',
}

// History accordion
const historyOpen = ref(false)
function formatDate(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}
const expandedHistory = ref<Set<number>>(new Set())
function toggleHistoryEntry(id: number) {
  if (expandedHistory.value.has(id)) expandedHistory.value.delete(id)
  else expandedHistory.value.add(id)
}
</script>

<template>
  <div class="survey-layout">
    <!-- Sticky context bar -->
    <div class="context-bar" v-if="job">
      <span class="context-company">{{ job.company }}</span>
      <span class="context-sep">·</span>
      <span class="context-title">{{ job.title }}</span>
      <span class="stage-badge">{{ stageLabel[job.status] ?? job.status }}</span>
    </div>

    <!-- Load/history error banner -->
    <div class="error-banner" v-if="surveyStore.error && !surveyStore.analysis">
      {{ surveyStore.error }}
    </div>

    <div class="survey-content">
      <!-- Input card -->
      <div class="card">
        <div class="tab-bar">
          <button
            class="tab-btn"
            :class="{ active: activeTab === 'text' }"
            @click="activeTab = 'text'"
          >📝 Paste Text</button>
          <button
            class="tab-btn"
            :class="{ active: activeTab === 'screenshot', disabled: !surveyStore.visionAvailable }"
            :aria-disabled="!surveyStore.visionAvailable"
            :title="!surveyStore.visionAvailable ? 'Vision service not running — start it with: bash scripts/manage-vision.sh start' : undefined"
            @click="surveyStore.visionAvailable && (activeTab = 'screenshot')"
          >📷 Screenshot</button>
        </div>

        <!-- Text tab -->
        <div v-if="activeTab === 'text'" class="tab-panel">
          <textarea
            v-model="textInput"
            class="survey-textarea"
            placeholder="Paste your survey questions here, e.g.:&#10;Q1: Which best describes your work style?&#10;A. I prefer working alone&#10;B. I thrive in teams&#10;C. Depends on the project"
          />
        </div>

        <!-- Screenshot tab -->
        <div
          v-else
          class="screenshot-zone"
          @paste="handlePaste"
          @dragover.prevent
          @drop="handleDrop"
          tabindex="0"
        >
          <div v-if="imagePreviewUrl" class="image-preview">
            <img :src="imagePreviewUrl" alt="Survey screenshot preview" />
            <button class="remove-btn" @click="clearImage">✕ Remove</button>
          </div>
          <div v-else class="drop-hint">
            <p>Paste (Ctrl+V), drag & drop, or upload a screenshot</p>
            <label class="upload-label">
              Choose file
              <input type="file" accept="image/*" class="file-input" @change="handleFileUpload" />
            </label>
          </div>
        </div>
      </div>

      <!-- Mode selection -->
      <div class="mode-cards">
        <button
          class="mode-card"
          :class="{ selected: selectedMode === 'quick' }"
          @click="selectedMode = 'quick'"
        >
          <span class="mode-icon">⚡</span>
          <span class="mode-name">Quick</span>
          <span class="mode-desc">Best answer + one-liner per question</span>
        </button>
        <button
          class="mode-card"
          :class="{ selected: selectedMode === 'detailed' }"
          @click="selectedMode = 'detailed'"
        >
          <span class="mode-icon">📋</span>
          <span class="mode-name">Detailed</span>
          <span class="mode-desc">Option-by-option breakdown with reasoning</span>
        </button>
      </div>

      <!-- Analyze button -->
      <button
        class="analyze-btn"
        :disabled="!canAnalyze || surveyStore.loading"
        @click="runAnalyze"
      >
        <span v-if="surveyStore.loading" class="spinner" aria-hidden="true"></span>
        {{ surveyStore.loading ? 'Analyzing…' : '🔍 Analyze' }}
      </button>

      <!-- Analyze error -->
      <div class="error-inline" v-if="surveyStore.error && !surveyStore.analysis">
        {{ surveyStore.error }}
      </div>

      <!-- Results card -->
      <div class="card results-card" v-if="surveyStore.analysis">
        <div class="results-output">{{ surveyStore.analysis.output }}</div>
        <div class="save-form">
          <input
            v-model="surveyName"
            class="save-input"
            type="text"
            placeholder="Survey name (e.g. Culture Fit Round 1)"
          />
          <input
            v-model="reportedScore"
            class="save-input"
            type="text"
            placeholder="Reported score (e.g. 82% or 4.2/5)"
          />
          <button
            class="save-btn"
            :disabled="surveyStore.saving"
            @click="saveToJob"
          >
            <span v-if="surveyStore.saving" class="spinner" aria-hidden="true"></span>
            💾 Save to job
          </button>
          <div v-if="saveSuccess" class="save-success">Saved!</div>
          <div v-if="surveyStore.error" class="error-inline">{{ surveyStore.error }}</div>
        </div>
      </div>

      <!-- History accordion -->
      <details class="history-accordion" :open="historyOpen" @toggle="historyOpen = ($event.target as HTMLDetailsElement).open">
        <summary class="history-summary">
          Survey history ({{ surveyStore.history.length }} response{{ surveyStore.history.length === 1 ? '' : 's' }})
        </summary>
        <div v-if="surveyStore.history.length === 0" class="history-empty">No responses saved yet.</div>
        <div v-else class="history-list">
          <div v-for="resp in surveyStore.history" :key="resp.id" class="history-entry">
            <button class="history-toggle" @click="toggleHistoryEntry(resp.id)">
              <span class="history-name">{{ resp.survey_name ?? 'Survey response' }}</span>
              <span class="history-meta">{{ formatDate(resp.received_at) }}{{ resp.reported_score ? ` · ${resp.reported_score}` : '' }}</span>
              <span class="history-chevron">{{ expandedHistory.has(resp.id) ? '▲' : '▼' }}</span>
            </button>
            <div v-if="expandedHistory.has(resp.id)" class="history-detail">
              <div class="history-tags">
                <span class="tag">{{ resp.mode }}</span>
                <span class="tag">{{ resp.source }}</span>
                <span v-if="resp.received_at" class="tag">{{ resp.received_at }}</span>
              </div>
              <div class="history-output">{{ resp.llm_output }}</div>
            </div>
          </div>
        </div>
      </details>
    </div>
  </div>
</template>

<style scoped>
.survey-layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.context-bar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 0 var(--space-6);
  height: 40px;
  background: var(--color-surface-raised, #f8f9fa);
  border-bottom: 1px solid var(--color-border, #e2e8f0);
  font-size: 0.875rem;
}

.context-company {
  font-weight: 600;
  color: var(--color-text, #1a202c);
}

.context-sep {
  color: var(--color-text-muted, #718096);
}

.context-title {
  color: var(--color-text-muted, #718096);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stage-badge {
  margin-left: auto;
  padding: 2px 8px;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 600;
  background: var(--color-accent-subtle, #ebf4ff);
  color: var(--color-accent, #3182ce);
}

.survey-content {
  max-width: 760px;
  margin: 0 auto;
  padding: var(--space-6);
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.card {
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-md, 8px);
  overflow: hidden;
}

.tab-bar {
  display: flex;
  border-bottom: 1px solid var(--color-border, #e2e8f0);
}

.tab-btn {
  flex: 1;
  padding: var(--space-3) var(--space-4);
  background: none;
  border: none;
  cursor: pointer;
  font-size: 0.875rem;
  color: var(--color-text-muted, #718096);
  transition: color 0.15s, background 0.15s;
}

.tab-btn.active {
  color: var(--color-accent, #3182ce);
  background: var(--color-accent-subtle, #ebf4ff);
  font-weight: 600;
}

.tab-btn.disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.tab-panel {
  padding: var(--space-4);
}

.survey-textarea {
  width: 100%;
  min-height: 200px;
  padding: var(--space-3);
  font-family: inherit;
  font-size: 0.875rem;
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-sm, 4px);
  resize: vertical;
  background: var(--color-bg, #fff);
  color: var(--color-text, #1a202c);
  box-sizing: border-box;
}

.screenshot-zone {
  min-height: 160px;
  padding: var(--space-6);
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px dashed var(--color-border, #e2e8f0);
  margin: var(--space-4);
  border-radius: var(--radius-md, 8px);
  outline: none;
}

.screenshot-zone:focus {
  border-color: var(--color-accent, #3182ce);
}

.drop-hint {
  text-align: center;
  color: var(--color-text-muted, #718096);
}

.upload-label {
  display: inline-block;
  margin-top: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-sm, 4px);
  cursor: pointer;
  font-size: 0.875rem;
  background: var(--color-surface, #fff);
}

.file-input {
  display: none;
}

.image-preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
}

.image-preview img {
  max-width: 100%;
  max-height: 300px;
  border-radius: var(--radius-sm, 4px);
}

.remove-btn {
  font-size: 0.8rem;
  color: var(--color-text-muted, #718096);
  background: none;
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-sm, 4px);
  padding: 2px 8px;
  cursor: pointer;
}

.mode-cards {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.mode-card {
  display: grid;
  grid-template-columns: 2rem 1fr;
  grid-template-rows: auto auto;
  align-items: center;
  gap: 0 var(--space-2);
  padding: var(--space-4);
  background: var(--color-surface, #fff);
  border: 2px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-md, 8px);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s, background 0.15s;
}

.mode-card.selected {
  border-color: var(--color-accent, #3182ce);
  background: var(--color-accent-subtle, #ebf4ff);
}

.mode-icon {
  grid-row: 1 / 3;
  font-size: 1.25rem;
  line-height: 1;
  align-self: center;
}

.mode-name {
  font-weight: 600;
  color: var(--color-text, #1a202c);
  line-height: 1.3;
}

.mode-desc {
  font-size: 0.8rem;
  color: var(--color-text-muted, #718096);
}

.analyze-btn {
  width: 100%;
  padding: var(--space-3) var(--space-4);
  background: var(--color-accent, #3182ce);
  color: #fff;
  border: none;
  border-radius: var(--radius-md, 8px);
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  transition: opacity 0.15s;
}

.analyze-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.results-card {
  padding: var(--space-4);
}

.results-output {
  white-space: pre-wrap;
  font-size: 0.9rem;
  line-height: 1.6;
  color: var(--color-text, #1a202c);
  margin-bottom: var(--space-4);
}

.save-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-border, #e2e8f0);
}

.save-input {
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-sm, 4px);
  font-size: 0.875rem;
  background: var(--color-bg, #fff);
  color: var(--color-text, #1a202c);
}

.save-btn {
  align-self: flex-start;
  padding: var(--space-2) var(--space-4);
  background: var(--color-surface-raised, #f8f9fa);
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-md, 8px);
  cursor: pointer;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  transition: background 0.15s;
}

.save-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.save-success {
  color: var(--color-success, #38a169);
  font-size: 0.875rem;
  font-weight: 600;
}

.history-accordion {
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-md, 8px);
  background: var(--color-surface, #fff);
}

.history-summary {
  padding: var(--space-3) var(--space-4);
  cursor: pointer;
  font-size: 0.875rem;
  color: var(--color-text-muted, #718096);
  font-weight: 500;
  list-style: none;
}

.history-summary::-webkit-details-marker { display: none; }

.history-empty {
  padding: var(--space-4);
  color: var(--color-text-muted, #718096);
  font-size: 0.875rem;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
  background: var(--color-border, #e2e8f0);
}

.history-entry {
  background: var(--color-surface, #fff);
}

.history-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  background: none;
  border: none;
  cursor: pointer;
  text-align: left;
  font-size: 0.875rem;
}

.history-name {
  font-weight: 500;
  color: var(--color-text, #1a202c);
}

.history-meta {
  color: var(--color-text-muted, #718096);
  font-size: 0.8rem;
  margin-left: auto;
}

.history-chevron {
  font-size: 0.7rem;
  color: var(--color-text-muted, #718096);
}

.history-detail {
  padding: var(--space-3) var(--space-4) var(--space-4);
  border-top: 1px solid var(--color-border, #e2e8f0);
}

.history-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  margin-bottom: var(--space-2);
}

.tag {
  padding: 1px 6px;
  background: var(--color-accent-subtle, #ebf4ff);
  color: var(--color-accent, #3182ce);
  border-radius: 4px;
  font-size: 0.75rem;
}

.history-output {
  white-space: pre-wrap;
  font-size: 0.875rem;
  line-height: 1.6;
  color: var(--color-text, #1a202c);
}

.error-banner {
  background: var(--color-error-subtle, #fff5f5);
  border-bottom: 1px solid var(--color-error, #fc8181);
  padding: var(--space-2) var(--space-6);
  font-size: 0.875rem;
  color: var(--color-error-text, #c53030);
}

.error-inline {
  font-size: 0.875rem;
  color: var(--color-error-text, #c53030);
  padding: var(--space-1) 0;
}

.spinner {
  display: inline-block;
  width: 1em;
  height: 1em;
  border: 2px solid rgba(255,255,255,0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

.analyze-btn .spinner {
  border-color: rgba(255,255,255,0.4);
  border-top-color: #fff;
}

.save-btn .spinner {
  border-color: rgba(0,0,0,0.15);
  border-top-color: var(--color-accent, #3182ce);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
```

- [ ] **Step 4: Update InterviewCard.vue**

First read the file to find the exact emit definition line and the Prep button location:
```bash
grep -n "defineEmits\|emit('prep'\|card-action" web/src/components/InterviewCard.vue
```

Then:
1. Add `survey: [jobId: number]` to the `defineEmits` type
2. Add the Survey button after the Prep button:

```html
<button
  v-if="['survey', 'phone_screen', 'interviewing', 'offer'].includes(job.status)"
  class="card-action"
  @click.stop="emit('survey', job.id)"
>Survey →</button>
```

- [ ] **Step 5: Update InterviewsView.vue**

First verify locations:
```bash
grep -n "InterviewCard\|@prep\|pre-list-row\|btn-move-pre" web/src/views/InterviewsView.vue
```

Then make two changes:

**5a.** Add `@survey="router.push('/survey/' + $event)"` to all **3** `<InterviewCard>` instances (phoneScreen, interviewing, offerHired columns), on the same line as `@prep` or `@move`.

**5b.** In the pre-list row template (inside `v-for="job in pagedApplied"`), add a Survey button after the existing `btn-move-pre` button:
```html
<button
  v-if="job.status === 'survey'"
  class="btn-move-pre"
  @click="router.push('/survey/' + job.id)"
>Survey →</button>
```
Note: `router` is already available in `InterviewsView.vue` (check with `grep -n "useRouter" web/src/views/InterviewsView.vue`).

- [ ] **Step 6: Build verification**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa/web
npm run build
```

Expected: Build succeeds with no TypeScript or template errors.

If there are TypeScript errors (common with `useApiFetch` body option), check how `InterviewPrepView.vue` passes POST bodies — the `useApiFetch` composable may require `body` as a string. The store already uses `JSON.stringify(payload)` which should be correct.

- [ ] **Step 7: Run full test suite one final time**

```bash
npm run test
cd ..
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 8: Commit**

```bash
cd /Library/Development/CircuitForge/peregrine/.worktrees/feature-vue-spa
git add web/src/router/index.ts \
        web/src/views/SurveyView.vue \
        web/src/components/InterviewCard.vue \
        web/src/views/InterviewsView.vue
git commit -m "feat(survey): implement SurveyView with navigation wiring"
```
