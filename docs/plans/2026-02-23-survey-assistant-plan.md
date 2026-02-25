# Survey Assistant Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a real-time Survey Assistant page that helps users answer culture-fit surveys via text paste or screenshot, backed by a local moondream2 vision service, with a new `survey` pipeline stage and kanban consolidation.

**Architecture:** Six sequential tasks build foundation-up: DB → LLM Router → Email Classifier → Vision Service → Interviews Kanban → Survey Page. Each task is independently testable and committed before the next begins.

**Tech Stack:** SQLite (db.py migrations), FastAPI + moondream2 (vision service, separate conda env), streamlit-paste-button (clipboard paste), Python requests (vision service client in LLM router).

---

## Task 1: DB — survey_responses table + survey_at column + CRUD

**Files:**
- Modify: `scripts/db.py`
- Test: `tests/test_db.py`

### Step 1: Write the failing tests

Add to `tests/test_db.py`:

```python
def test_survey_responses_table_created(tmp_path):
    """init_db creates survey_responses table."""
    from scripts.db import init_db
    db_path = tmp_path / "test.db"
    init_db(db_path)
    import sqlite3
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='survey_responses'"
    )
    assert cur.fetchone() is not None
    conn.close()


def test_survey_at_column_exists(tmp_path):
    """jobs table has survey_at column after init_db."""
    from scripts.db import init_db
    db_path = tmp_path / "test.db"
    init_db(db_path)
    import sqlite3
    conn = sqlite3.connect(db_path)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()]
    assert "survey_at" in cols
    conn.close()


def test_insert_and_get_survey_response(tmp_path):
    """insert_survey_response inserts a row; get_survey_responses returns it."""
    from scripts.db import init_db, insert_job, insert_survey_response, get_survey_responses
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/1",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-23",
    })
    row_id = insert_survey_response(
        db_path, job_id=job_id, survey_name="Culture Fit",
        source="text_paste", raw_input="Q1: A B C", mode="quick",
        llm_output="1. B — collaborative", reported_score="82%",
    )
    assert isinstance(row_id, int)
    responses = get_survey_responses(db_path, job_id=job_id)
    assert len(responses) == 1
    assert responses[0]["survey_name"] == "Culture Fit"
    assert responses[0]["reported_score"] == "82%"


def test_get_interview_jobs_includes_survey(tmp_path):
    """get_interview_jobs returns survey-stage jobs."""
    from scripts.db import init_db, insert_job, update_job_status, get_interview_jobs
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/2",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-23",
    })
    update_job_status(db_path, [job_id], "survey")
    result = get_interview_jobs(db_path)
    assert any(j["id"] == job_id for j in result.get("survey", []))


def test_advance_to_survey_sets_survey_at(tmp_path):
    """advance_to_stage('survey') sets survey_at timestamp."""
    from scripts.db import init_db, insert_job, update_job_status, advance_to_stage, get_job_by_id
    db_path = tmp_path / "test.db"
    init_db(db_path)
    job_id = insert_job(db_path, {
        "title": "CSM", "company": "Acme", "url": "https://ex.com/3",
        "source": "linkedin", "location": "Remote", "is_remote": True,
        "salary": "", "description": "", "date_found": "2026-02-23",
    })
    update_job_status(db_path, [job_id], "applied")
    advance_to_stage(db_path, job_id=job_id, stage="survey")
    job = get_job_by_id(db_path, job_id=job_id)
    assert job["status"] == "survey"
    assert job["survey_at"] is not None
```

### Step 2: Run to verify they fail

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_db.py::test_survey_responses_table_created tests/test_db.py::test_survey_at_column_exists tests/test_db.py::test_insert_and_get_survey_response tests/test_db.py::test_get_interview_jobs_includes_survey tests/test_db.py::test_advance_to_survey_sets_survey_at -v
```
Expected: FAIL with `ImportError` or `AssertionError`

### Step 3: Implement

In `scripts/db.py`, make the following changes:

**a) Add `CREATE_SURVEY_RESPONSES` constant** after `CREATE_BACKGROUND_TASKS`:

```python
CREATE_SURVEY_RESPONSES = """
CREATE TABLE IF NOT EXISTS survey_responses (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id         INTEGER NOT NULL REFERENCES jobs(id),
    survey_name    TEXT,
    received_at    DATETIME,
    source         TEXT,
    raw_input      TEXT,
    image_path     TEXT,
    mode           TEXT,
    llm_output     TEXT,
    reported_score TEXT,
    created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""
```

**b) Add `survey_at` to `_MIGRATIONS`** (after `hired_at`):

```python
    ("survey_at", "TEXT"),
```

**c) Add `"survey"` to `_STAGE_TS_COL`**:

```python
_STAGE_TS_COL = {
    "phone_screen": "phone_screen_at",
    "interviewing":  "interviewing_at",
    "offer":         "offer_at",
    "hired":         "hired_at",
    "survey":        "survey_at",
}
```

**d) Add `survey_responses` to `init_db`**:

```python
def init_db(db_path: Path = DEFAULT_DB) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_JOBS)
    conn.execute(CREATE_JOB_CONTACTS)
    conn.execute(CREATE_COMPANY_RESEARCH)
    conn.execute(CREATE_BACKGROUND_TASKS)
    conn.execute(CREATE_SURVEY_RESPONSES)
    conn.commit()
    conn.close()
    _migrate_db(db_path)
```

**e) Add `survey` to `get_interview_jobs`**:

```python
def get_interview_jobs(db_path: Path = DEFAULT_DB) -> dict[str, list[dict]]:
    stages = ["applied", "survey", "phone_screen", "interviewing", "offer", "hired", "rejected"]
    ...  # rest unchanged
```

**f) Add CRUD helpers at the end of the file** (before the background task helpers section):

```python
# ── Survey response helpers ───────────────────────────────────────────────────

def insert_survey_response(
    db_path: Path = DEFAULT_DB,
    job_id: int = None,
    survey_name: str = "",
    received_at: str = "",
    source: str = "text_paste",
    raw_input: str = "",
    image_path: str = "",
    mode: str = "quick",
    llm_output: str = "",
    reported_score: str = "",
) -> int:
    """Insert a survey response row. Returns the new row id."""
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        """INSERT INTO survey_responses
           (job_id, survey_name, received_at, source, raw_input,
            image_path, mode, llm_output, reported_score)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (job_id, survey_name or None, received_at or None,
         source, raw_input or None, image_path or None,
         mode, llm_output, reported_score or None),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def get_survey_responses(db_path: Path = DEFAULT_DB, job_id: int = None) -> list[dict]:
    """Return all survey responses for a job, newest first."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM survey_responses WHERE job_id = ? ORDER BY created_at DESC",
        (job_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
```

### Step 4: Run tests to verify they pass

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_db.py -v
```
Expected: all DB tests PASS

### Step 5: Commit

```bash
git add scripts/db.py tests/test_db.py
git commit -m "feat: survey_responses table, survey_at column, CRUD helpers"
```

---

## Task 2: LLM Router — images= parameter + vision_service backend

**Files:**
- Modify: `scripts/llm_router.py`
- Modify: `config/llm.yaml`
- Modify: `config/llm.yaml.example` (same change)
- Test: `tests/test_llm_router.py`

### Step 1: Write the failing tests

Read `tests/test_llm_router.py` first to see existing test style, then add:

```python
def test_complete_skips_backend_without_image_support(tmp_path):
    """When images= is passed, backends without supports_images are skipped."""
    import yaml
    from scripts.llm_router import LLMRouter

    cfg = {
        "fallback_order": ["ollama", "vision_service"],
        "backends": {
            "ollama": {
                "type": "openai_compat",
                "base_url": "http://localhost:11434/v1",
                "model": "llava",
                "api_key": "ollama",
                "enabled": True,
                "supports_images": False,
            },
            "vision_service": {
                "type": "vision_service",
                "base_url": "http://localhost:8002",
                "enabled": True,
                "supports_images": True,
            },
        },
    }
    cfg_file = tmp_path / "llm.yaml"
    cfg_file.write_text(yaml.dump(cfg))

    from unittest.mock import patch, MagicMock
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"text": "B — collaborative"}

    with patch("scripts.llm_router.requests.get") as mock_get, \
         patch("scripts.llm_router.requests.post") as mock_post:
        # health check returns ok for vision_service
        mock_get.return_value = MagicMock(status_code=200)
        mock_post.return_value = mock_resp

        router = LLMRouter(config_path=cfg_file)
        result = router.complete("Which option?", images=["base64data"])

    assert result == "B — collaborative"
    # ollama should never have been called (no supports_images)
    # vision_service POST /analyze should have been called
    assert mock_post.called


def test_complete_without_images_skips_vision_service(tmp_path):
    """When images=None, vision_service backend is skipped."""
    import yaml
    from scripts.llm_router import LLMRouter
    from unittest.mock import patch, MagicMock

    cfg = {
        "fallback_order": ["vision_service"],
        "backends": {
            "vision_service": {
                "type": "vision_service",
                "base_url": "http://localhost:8002",
                "enabled": True,
                "supports_images": True,
            },
        },
    }
    cfg_file = tmp_path / "llm.yaml"
    cfg_file.write_text(yaml.dump(cfg))

    router = LLMRouter(config_path=cfg_file)
    with patch("scripts.llm_router.requests.post") as mock_post:
        try:
            router.complete("text only prompt")
        except RuntimeError:
            pass  # all backends exhausted is expected
        assert not mock_post.called
```

### Step 2: Run to verify they fail

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_llm_router.py::test_complete_skips_backend_without_image_support tests/test_llm_router.py::test_complete_without_images_skips_vision_service -v
```
Expected: FAIL

### Step 3: Implement

**a) Update `scripts/llm_router.py`** — change the `complete()` signature and add image routing logic:

```python
def complete(self, prompt: str, system: str | None = None,
             model_override: str | None = None,
             fallback_order: list[str] | None = None,
             images: list[str] | None = None) -> str:
    """
    Generate a completion. Tries each backend in fallback_order.

    images: optional list of base64-encoded PNG/JPG strings. When provided,
    backends without supports_images=true are skipped. vision_service backends
    are only tried when images is provided.
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
```

**b) Update `config/llm.yaml`** — add `vision_service` backend and `vision_fallback_order`, and add `supports_images` to relevant backends:

```yaml
backends:
  anthropic:
    api_key_env: ANTHROPIC_API_KEY
    enabled: false
    model: claude-sonnet-4-6
    type: anthropic
    supports_images: true
  claude_code:
    api_key: any
    base_url: http://localhost:3009/v1
    enabled: false
    model: claude-code-terminal
    type: openai_compat
    supports_images: true
  github_copilot:
    api_key: any
    base_url: http://localhost:3010/v1
    enabled: false
    model: gpt-4o
    type: openai_compat
    supports_images: false
  ollama:
    api_key: ollama
    base_url: http://localhost:11434/v1
    enabled: true
    model: meghan-cover-writer:latest
    type: openai_compat
    supports_images: false
  ollama_research:
    api_key: ollama
    base_url: http://localhost:11434/v1
    enabled: true
    model: llama3.1:8b
    type: openai_compat
    supports_images: false
  vllm:
    api_key: ''
    base_url: http://localhost:8000/v1
    enabled: true
    model: __auto__
    type: openai_compat
    supports_images: false
  vision_service:
    base_url: http://localhost:8002
    enabled: false
    type: vision_service
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
# Note: 'ollama' (meghan-cover-writer) intentionally excluded — research
# must never use the fine-tuned writer model.
```

Make the same `vision_service` backend and `supports_images` changes to `config/llm.yaml.example`.

### Step 4: Run tests

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_llm_router.py -v
```
Expected: all PASS

### Step 5: Commit

```bash
git add scripts/llm_router.py config/llm.yaml config/llm.yaml.example tests/test_llm_router.py
git commit -m "feat: LLM router images= parameter + vision_service backend type"
```

---

## Task 3: Email classifier — survey_received label

**Files:**
- Modify: `scripts/imap_sync.py`
- Test: `tests/test_imap_sync.py`

### Step 1: Write the failing test

Add to `tests/test_imap_sync.py`:

```python
def test_classify_labels_includes_survey_received():
    """_CLASSIFY_LABELS includes survey_received."""
    from scripts.imap_sync import _CLASSIFY_LABELS
    assert "survey_received" in _CLASSIFY_LABELS


def test_classify_stage_signal_returns_survey_received():
    """classify_stage_signal returns 'survey_received' when LLM outputs that label."""
    from unittest.mock import patch
    from scripts.imap_sync import classify_stage_signal

    with patch("scripts.imap_sync._CLASSIFIER_ROUTER") as mock_router:
        mock_router.complete.return_value = "survey_received"
        result = classify_stage_signal("Complete our culture survey", "Please fill out this form")
    assert result == "survey_received"
```

### Step 2: Run to verify they fail

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_imap_sync.py::test_classify_labels_includes_survey_received tests/test_imap_sync.py::test_classify_stage_signal_returns_survey_received -v
```
Expected: FAIL

### Step 3: Implement

In `scripts/imap_sync.py`, make two changes:

**a) Update `_CLASSIFY_SYSTEM`** — add survey_received to the category list:

```python
_CLASSIFY_SYSTEM = (
    "You are an email classifier. Classify the recruitment email into exactly ONE of these categories:\n"
    "  interview_scheduled, offer_received, rejected, positive_response, survey_received, neutral\n\n"
    "Rules:\n"
    "- interview_scheduled: recruiter wants to book a call/interview\n"
    "- offer_received: job offer is being extended\n"
    "- rejected: explicitly not moving forward\n"
    "- positive_response: interested/impressed but no interview booked yet\n"
    "- survey_received: link or request to complete a survey, assessment, or questionnaire\n"
    "- neutral: auto-confirmation, generic update, no clear signal\n\n"
    "Respond with ONLY the category name. No explanation."
)
```

**b) Update `_CLASSIFY_LABELS`**:

```python
_CLASSIFY_LABELS = [
    "interview_scheduled", "offer_received", "rejected",
    "positive_response", "survey_received", "neutral",
]
```

### Step 4: Run tests

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_imap_sync.py -v
```
Expected: all PASS

### Step 5: Commit

```bash
git add scripts/imap_sync.py tests/test_imap_sync.py
git commit -m "feat: add survey_received classifier label to email sync"
```

---

## Task 4: Vision service — moondream2 FastAPI server

**Files:**
- Create: `scripts/vision_service/environment.yml`
- Create: `scripts/vision_service/main.py`
- Create: `scripts/manage-vision.sh`

No unit tests for this task — the service is tested manually via the health endpoint. The survey page (Task 6) will degrade gracefully if the service is absent.

### Step 1: Create `scripts/vision_service/environment.yml`

```yaml
name: job-seeker-vision
channels:
  - conda-forge
  - defaults
dependencies:
  - python=3.11
  - pip
  - pip:
    - torch>=2.0.0
    - torchvision>=0.15.0
    - transformers>=4.40.0
    - accelerate>=0.26.0
    - bitsandbytes>=0.43.0
    - einops>=0.7.0
    - Pillow>=10.0.0
    - fastapi>=0.110.0
    - "uvicorn[standard]>=0.27.0"
```

### Step 2: Create `scripts/vision_service/main.py`

```python
"""
Vision service — moondream2 inference for survey screenshot analysis.

Start: conda run -n job-seeker-vision uvicorn scripts.vision_service.main:app --port 8002
Or use: bash scripts/manage-vision.sh start
"""
import base64
import io
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Job Seeker Vision Service")

# Module-level model state — lazy loaded on first request
_model = None
_tokenizer = None
_device = "cpu"
_loading = False


def _load_model() -> None:
    global _model, _tokenizer, _device, _loading
    if _model is not None:
        return
    _loading = True
    print("[vision] Loading moondream2…")
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model_id = "vikhyatk/moondream2"
    revision = "2025-01-09"
    _device = "cuda" if torch.cuda.is_available() else "cpu"

    if _device == "cuda":
        from transformers import BitsAndBytesConfig
        bnb = BitsAndBytesConfig(load_in_4bit=True)
        _model = AutoModelForCausalLM.from_pretrained(
            model_id, revision=revision,
            quantization_config=bnb,
            trust_remote_code=True,
            device_map="auto",
        )
    else:
        _model = AutoModelForCausalLM.from_pretrained(
            model_id, revision=revision,
            trust_remote_code=True,
        )
        _model.to(_device)

    _tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision)
    _loading = False
    print(f"[vision] moondream2 ready on {_device}")


class AnalyzeRequest(BaseModel):
    prompt: str
    image_base64: str


class AnalyzeResponse(BaseModel):
    text: str


@app.get("/health")
def health():
    import torch
    return {
        "status": "loading" if _loading else "ok",
        "model": "moondream2",
        "gpu": torch.cuda.is_available(),
        "loaded": _model is not None,
    }


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest):
    from PIL import Image
    import torch

    _load_model()

    try:
        image_data = base64.b64decode(req.image_base64)
        image = Image.open(io.BytesIO(image_data)).convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {e}")

    with torch.no_grad():
        enc_image = _model.encode_image(image)
        answer = _model.answer_question(enc_image, req.prompt, _tokenizer)

    return AnalyzeResponse(text=answer)
```

### Step 3: Create `scripts/manage-vision.sh`

```bash
#!/usr/bin/env bash
# scripts/manage-vision.sh — manage the moondream2 vision service
# Usage: bash scripts/manage-vision.sh start|stop|restart|status|logs

set -euo pipefail

CONDA_ENV="job-seeker-vision"
UVICORN_BIN="/devl/miniconda3/envs/${CONDA_ENV}/bin/uvicorn"
PID_FILE="/tmp/vision-service.pid"
LOG_FILE="/tmp/vision-service.log"
PORT=8002
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

is_running() {
    if [[ -f "$PID_FILE" ]]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

start() {
    if is_running; then
        echo "Already running (PID $(cat "$PID_FILE"))."
        return 0
    fi

    if [[ ! -f "$UVICORN_BIN" ]]; then
        echo "ERROR: conda env '$CONDA_ENV' not found."
        echo "Install with: conda env create -f scripts/vision_service/environment.yml"
        exit 1
    fi

    echo "Starting vision service (moondream2) on port $PORT…"
    cd "$REPO_ROOT"
    PYTHONPATH="$REPO_ROOT" "$UVICORN_BIN" \
        scripts.vision_service.main:app \
        --host 0.0.0.0 \
        --port "$PORT" \
        > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 2

    if is_running; then
        echo "Started (PID $(cat "$PID_FILE")). Logs: $LOG_FILE"
        echo "Health: http://localhost:$PORT/health"
    else
        echo "Failed to start. Check logs: $LOG_FILE"
        tail -20 "$LOG_FILE"
        rm -f "$PID_FILE"
        exit 1
    fi
}

stop() {
    if ! is_running; then
        echo "Not running."
        rm -f "$PID_FILE"
        return 0
    fi
    PID=$(cat "$PID_FILE")
    echo "Stopping PID $PID…"
    kill "$PID" 2>/dev/null || true
    sleep 2
    if kill -0 "$PID" 2>/dev/null; then
        kill -9 "$PID" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
    echo "Stopped."
}

restart() { stop; sleep 1; start; }

status() {
    if is_running; then
        echo "Running (PID $(cat "$PID_FILE")) — http://localhost:$PORT"
        curl -s "http://localhost:$PORT/health" | python3 -m json.tool 2>/dev/null || true
    else
        echo "Not running."
    fi
}

logs() {
    if [[ -f "$LOG_FILE" ]]; then
        tail -50 "$LOG_FILE"
    else
        echo "No log file at $LOG_FILE"
    fi
}

CMD="${1:-help}"
case "$CMD" in
    start)   start ;;
    stop)    stop ;;
    restart) restart ;;
    status)  status ;;
    logs)    logs ;;
    *)
        echo "Usage: bash scripts/manage-vision.sh start|stop|restart|status|logs"
        echo ""
        echo "  Manages the moondream2 vision service on port $PORT."
        echo "  First-time setup: conda env create -f scripts/vision_service/environment.yml"
        ;;
esac
```

### Step 4: Make the script executable and verify

```bash
chmod +x scripts/manage-vision.sh
bash scripts/manage-vision.sh status
```
Expected: "Not running."

### Step 5: Commit

```bash
git add scripts/vision_service/ scripts/manage-vision.sh
git commit -m "feat: moondream2 vision service + manage-vision.sh"
```

---

## Task 5: Interviews page — kanban consolidation + survey stage

**Files:**
- Modify: `app/pages/5_Interviews.py`

No unit tests for UI pages. Verify manually by running the app.

### Step 1: Read the current Interviews page

Read `app/pages/5_Interviews.py` in full before making any changes.

### Step 2: Implement all changes

The following changes are needed in `5_Interviews.py`:

**a) Update imports** — add `insert_survey_response`, `get_survey_responses` from db (needed for survey banner action):

```python
from scripts.db import (
    DEFAULT_DB, init_db,
    get_interview_jobs, advance_to_stage, reject_at_stage,
    set_interview_date, add_contact, get_contacts,
    get_research, get_task_for_job, get_job_by_id,
    get_unread_stage_signals, dismiss_stage_signal,
)
```
(No new db imports needed here — advance_to_stage handles survey_at already.)

**b) Update `STAGE_LABELS`, `STAGE_NEXT`, `STAGE_NEXT_LABEL`**:

```python
STAGE_LABELS = {
    "phone_screen": "📞 Phone Screen",
    "interviewing":  "🎯 Interviewing",
    "offer":         "📜 Offer / Hired",
}
STAGE_NEXT = {
    "survey":       "phone_screen",
    "applied":      "phone_screen",
    "phone_screen": "interviewing",
    "interviewing": "offer",
    "offer":        "hired",
}
STAGE_NEXT_LABEL = {
    "survey":       "📞 Phone Screen",
    "applied":      "📞 Phone Screen",
    "phone_screen": "🎯 Interviewing",
    "interviewing": "📜 Offer",
    "offer":        "🎉 Hired",
}
```

**c) Update `_render_card` — add `survey_received` to `_SIGNAL_TO_STAGE`**:

```python
_SIGNAL_TO_STAGE = {
    "interview_scheduled": ("phone_screen", "📞 Phone Screen"),
    "positive_response":   ("phone_screen", "📞 Phone Screen"),
    "offer_received":      ("offer",        "📜 Offer"),
    "survey_received":     ("survey",       "📋 Survey"),
}
```

**d) Update stats bar** — add survey metric, remove hired as separate metric (now in offer column):

```python
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Applied",      len(jobs_by_stage.get("applied", [])))
c2.metric("Survey",       len(jobs_by_stage.get("survey", [])))
c3.metric("Phone Screen", len(jobs_by_stage.get("phone_screen", [])))
c4.metric("Interviewing", len(jobs_by_stage.get("interviewing", [])))
c5.metric("Offer/Hired",  len(jobs_by_stage.get("offer", [])) + len(jobs_by_stage.get("hired", [])))
c6.metric("Rejected",     len(jobs_by_stage.get("rejected", [])))
```

**e) Update pre-kanban section** — show both applied and survey jobs.

Replace the current "Applied queue" section with:

```python
# ── Pre-kanban: Applied + Survey ───────────────────────────────────────────────
applied_jobs = jobs_by_stage.get("applied", [])
survey_jobs  = jobs_by_stage.get("survey", [])
pre_kanban   = survey_jobs + applied_jobs  # survey shown first

if pre_kanban:
    st.subheader(f"📋 Pre-pipeline ({len(pre_kanban)})")
    st.caption(
        "Move a job to **Phone Screen** once you receive an outreach. "
        "A company research brief will be auto-generated to help you prepare."
    )
    for job in pre_kanban:
        _pre_kanban_row_fragment(job["id"])
    st.divider()
```

**f) Add `_pre_kanban_row_fragment`** — handles both applied and survey jobs in one fragment:

```python
@st.fragment
def _pre_kanban_row_fragment(job_id: int) -> None:
    job = get_job_by_id(DEFAULT_DB, job_id)
    if job is None or job.get("status") not in ("applied", "survey"):
        return
    stage = job["status"]
    contacts = get_contacts(DEFAULT_DB, job_id=job_id)
    last_contact = contacts[-1] if contacts else None

    with st.container(border=True):
        left, mid, right = st.columns([3, 2, 2])
        badge = " 📋 **Survey**" if stage == "survey" else ""
        left.markdown(f"**{job.get('company')}** — {job.get('title', '')}{badge}")
        left.caption(f"Applied: {_days_ago(job.get('applied_at'))}")
        if last_contact:
            mid.caption(f"Last contact: {_days_ago(last_contact.get('received_at'))}")

        with right:
            if st.button(
                "→ 📞 Phone Screen", key=f"adv_pre_{job_id}",
                use_container_width=True, type="primary",
            ):
                advance_to_stage(DEFAULT_DB, job_id=job_id, stage="phone_screen")
                submit_task(DEFAULT_DB, "company_research", job_id)
                st.rerun(scope="app")
            col_a, col_b = st.columns(2)
            if stage == "applied" and col_a.button(
                "📋 Survey", key=f"to_survey_{job_id}", use_container_width=True,
            ):
                advance_to_stage(DEFAULT_DB, job_id=job_id, stage="survey")
                st.rerun(scope="app")
            if col_b.button("✗ Reject", key=f"rej_pre_{job_id}", use_container_width=True):
                reject_at_stage(DEFAULT_DB, job_id=job_id, rejection_stage=stage)
                st.rerun()
```

**g) Update kanban columns** — merge offer+hired into one column, 3 total:

```python
kanban_stages = ["phone_screen", "interviewing", "offer"]
cols = st.columns(len(kanban_stages))

for col, stage in zip(cols, kanban_stages):
    with col:
        stage_jobs = jobs_by_stage.get(stage, [])
        hired_jobs = jobs_by_stage.get("hired", []) if stage == "offer" else []
        all_col_jobs = stage_jobs + hired_jobs
        st.markdown(f"### {STAGE_LABELS[stage]}")
        st.caption(f"{len(all_col_jobs)} job{'s' if len(all_col_jobs) != 1 else ''}")
        st.divider()

        if not all_col_jobs:
            st.caption("_Empty_")
        else:
            for job in stage_jobs:
                _card_fragment(job["id"], stage)
            for job in hired_jobs:
                _hired_card_fragment(job["id"])
```

**h) Add `_hired_card_fragment`** for visually differentiated hired jobs:

```python
@st.fragment
def _hired_card_fragment(job_id: int) -> None:
    job = get_job_by_id(DEFAULT_DB, job_id)
    if job is None or job.get("status") != "hired":
        return
    with st.container(border=True):
        st.markdown(f"✅ **{job.get('company', '?')}**")
        st.caption(job.get("title", ""))
        st.caption(f"Hired {_days_ago(job.get('hired_at'))}")
```

**i) Remove the old `_applied_row_fragment`** — replaced by `_pre_kanban_row_fragment`.

### Step 3: Verify visually

```bash
bash scripts/manage-ui.sh restart
```

Open http://localhost:8501 → Interviews page. Verify:
- Pre-kanban section shows applied and survey jobs
- Kanban has 3 columns (Phone Screen, Interviewing, Offer/Hired)
- Stats bar has Survey metric

### Step 4: Commit

```bash
git add app/pages/5_Interviews.py
git commit -m "feat: kanban consolidation — survey pre-section, merged offer/hired column"
```

---

## Task 6: Add streamlit-paste-button to environment.yml

**Files:**
- Modify: `environment.yml`

### Step 1: Add the dependency

In `environment.yml`, under `# ── Web UI ─────`:

```yaml
    - streamlit-paste-button>=0.1.0
```

### Step 2: Install into the active env

```bash
/devl/miniconda3/envs/job-seeker/bin/pip install streamlit-paste-button
```

### Step 3: Commit

```bash
git add environment.yml
git commit -m "chore: add streamlit-paste-button dependency"
```

---

## Task 7: Survey Assistant page

**Files:**
- Create: `app/pages/7_Survey.py`
- Create: `data/survey_screenshots/.gitkeep`
- Modify: `.gitignore`

### Step 1: Create the screenshots directory and gitignore

```bash
mkdir -p data/survey_screenshots
touch data/survey_screenshots/.gitkeep
```

Add to `.gitignore`:
```
data/survey_screenshots/
```
(Keep `.gitkeep` but ignore the content. Actually, add `data/survey_screenshots/*` and `!data/survey_screenshots/.gitkeep`.)

### Step 2: Create `app/pages/7_Survey.py`

```python
# app/pages/7_Survey.py
"""
Survey Assistant — real-time help with culture-fit surveys.

Supports text paste and screenshot (via clipboard or file upload).
Quick mode: "pick B" + one-liner. Detailed mode: option-by-option breakdown.
"""
import base64
import io
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
import streamlit as st

from scripts.db import (
    DEFAULT_DB, init_db,
    get_interview_jobs, get_job_by_id,
    insert_survey_response, get_survey_responses,
)
from scripts.llm_router import LLMRouter

st.title("📋 Survey Assistant")

init_db(DEFAULT_DB)

# ── Vision service health check ────────────────────────────────────────────────
def _vision_available() -> bool:
    try:
        r = requests.get("http://localhost:8002/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False

vision_up = _vision_available()

# ── Job selector ───────────────────────────────────────────────────────────────
jobs_by_stage = get_interview_jobs(DEFAULT_DB)
survey_jobs = jobs_by_stage.get("survey", [])
other_jobs  = (
    jobs_by_stage.get("applied", []) +
    jobs_by_stage.get("phone_screen", []) +
    jobs_by_stage.get("interviewing", []) +
    jobs_by_stage.get("offer", [])
)
all_jobs = survey_jobs + other_jobs

if not all_jobs:
    st.info("No active jobs found. Add jobs in Job Review first.")
    st.stop()

job_labels = {j["id"]: f"{j.get('company', '?')} — {j.get('title', '')}" for j in all_jobs}
selected_job_id = st.selectbox(
    "Job",
    options=[j["id"] for j in all_jobs],
    format_func=lambda jid: job_labels[jid],
    index=0,
)
selected_job = get_job_by_id(DEFAULT_DB, selected_job_id)

# ── Layout ─────────────────────────────────────────────────────────────────────
left_col, right_col = st.columns([1, 1], gap="large")

with left_col:
    survey_name = st.text_input(
        "Survey name (optional)",
        placeholder="e.g. Culture Fit Round 1",
        key="survey_name",
    )
    mode = st.radio("Mode", ["Quick", "Detailed"], horizontal=True, key="survey_mode")
    st.caption(
        "**Quick** — best answer + one-liner per question  |  "
        "**Detailed** — option-by-option breakdown"
    )

    # Input tabs
    if vision_up:
        tab_text, tab_screenshot = st.tabs(["📝 Paste Text", "🖼️ Screenshot"])
    else:
        tab_text = st.container()
        st.info(
            "📷 Screenshot input unavailable — vision service not running.  \n"
            "Start it with: `bash scripts/manage-vision.sh start`"
        )
        tab_screenshot = None

    image_b64: str | None = None
    raw_text: str = ""

    with tab_text:
        raw_text = st.text_area(
            "Paste survey questions here",
            height=280,
            placeholder="Q1: Which describes your ideal work environment?\nA. Solo focused work\nB. Collaborative team\nC. Mix of both\nD. Depends on the task",
            key="survey_text",
        )

    if tab_screenshot is not None:
        with tab_screenshot:
            st.caption("Paste from clipboard or upload a screenshot file.")
            paste_col, upload_col = st.columns(2)

            with paste_col:
                try:
                    from streamlit_paste_button import paste_image_button
                    paste_result = paste_image_button("📋 Paste from clipboard", key="paste_btn")
                    if paste_result and paste_result.image_data:
                        buf = io.BytesIO()
                        paste_result.image_data.save(buf, format="PNG")
                        image_b64 = base64.b64encode(buf.getvalue()).decode()
                        st.image(paste_result.image_data, caption="Pasted image", use_container_width=True)
                except ImportError:
                    st.warning("streamlit-paste-button not installed. Use file upload.")

            with upload_col:
                uploaded = st.file_uploader(
                    "Upload screenshot",
                    type=["png", "jpg", "jpeg"],
                    key="survey_upload",
                    label_visibility="collapsed",
                )
                if uploaded:
                    image_b64 = base64.b64encode(uploaded.read()).decode()
                    st.image(uploaded, caption="Uploaded image", use_container_width=True)

    # Analyze button
    has_input = bool(raw_text.strip()) or bool(image_b64)
    if st.button("🔍 Analyze", type="primary", disabled=not has_input, use_container_width=True):
        with st.spinner("Analyzing…"):
            try:
                router = LLMRouter()
                if image_b64:
                    prompt = _build_image_prompt(mode)
                    output = router.complete(
                        prompt,
                        images=[image_b64],
                        fallback_order=router.config.get("vision_fallback_order"),
                    )
                    source = "screenshot"
                else:
                    prompt = _build_text_prompt(raw_text, mode)
                    output = router.complete(
                        prompt,
                        system=_SURVEY_SYSTEM,
                        fallback_order=router.config.get("research_fallback_order"),
                    )
                    source = "text_paste"
                st.session_state["survey_output"] = output
                st.session_state["survey_source"] = source
                st.session_state["survey_image_b64"] = image_b64
                st.session_state["survey_raw_text"] = raw_text
            except Exception as e:
                st.error(f"Analysis failed: {e}")

with right_col:
    output = st.session_state.get("survey_output")
    if output:
        st.markdown("### Analysis")
        st.markdown(output)

        st.divider()
        with st.form("save_survey_form"):
            reported_score = st.text_input(
                "Reported score (optional)",
                placeholder="e.g. 82% or 4.2/5",
                key="reported_score_input",
            )
            if st.form_submit_button("💾 Save to Job"):
                source = st.session_state.get("survey_source", "text_paste")
                image_b64_saved = st.session_state.get("survey_image_b64")
                raw_text_saved  = st.session_state.get("survey_raw_text", "")

                image_path = ""
                if image_b64_saved:
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    save_dir = Path(__file__).parent.parent.parent / "data" / "survey_screenshots" / str(selected_job_id)
                    save_dir.mkdir(parents=True, exist_ok=True)
                    img_file = save_dir / f"{ts}.png"
                    img_file.write_bytes(base64.b64decode(image_b64_saved))
                    image_path = str(img_file)

                insert_survey_response(
                    DEFAULT_DB,
                    job_id=selected_job_id,
                    survey_name=survey_name,
                    source=source,
                    raw_input=raw_text_saved,
                    image_path=image_path,
                    mode=mode.lower(),
                    llm_output=output,
                    reported_score=reported_score,
                )
                st.success("Saved!")
                # Clear output so form resets
                del st.session_state["survey_output"]
                st.rerun()
    else:
        st.markdown("### Analysis")
        st.caption("Results will appear here after analysis.")

# ── History ────────────────────────────────────────────────────────────────────
st.divider()
st.subheader("📂 Response History")
history = get_survey_responses(DEFAULT_DB, job_id=selected_job_id)

if not history:
    st.caption("No saved responses for this job yet.")
else:
    for resp in history:
        label = resp.get("survey_name") or "Survey response"
        ts    = (resp.get("created_at") or "")[:16]
        score = resp.get("reported_score")
        score_str = f" · Score: {score}" if score else ""
        with st.expander(f"{label} · {ts}{score_str}"):
            st.caption(f"Mode: {resp.get('mode', '?')} · Source: {resp.get('source', '?')}")
            if resp.get("raw_input"):
                with st.expander("Original input"):
                    st.text(resp["raw_input"])
            st.markdown(resp.get("llm_output", ""))


# ── LLM prompt builders ────────────────────────────────────────────────────────
_SURVEY_SYSTEM = (
    "You are a job application advisor helping a candidate answer a culture-fit survey. "
    "The candidate values collaborative teamwork, clear communication, growth, and impact. "
    "Choose answers that present them in the best professional light."
)


def _build_text_prompt(text: str, mode: str) -> str:
    if mode == "Quick":
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
    if mode == "Quick":
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
```

### Step 3: Verify the page loads

```bash
bash scripts/manage-ui.sh restart
```

Open http://localhost:8501 → navigate to "Survey Assistant" in the sidebar. Verify:
- Job selector shows survey-stage jobs first
- Text paste tab works
- Screenshot tab shows "not running" message when vision service is down
- History section loads (empty is fine)

### Step 4: Commit

```bash
git add app/pages/7_Survey.py data/survey_screenshots/.gitkeep .gitignore
git commit -m "feat: Survey Assistant page with text paste, screenshot, and response history"
```

---

## Final: Full test run + wrap-up

### Step 1: Run all tests

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v
```
Expected: all existing tests pass, new tests in test_db.py and test_imap_sync.py pass.

### Step 2: Smoke-test the full flow

1. Trigger an email sync — verify a survey_received signal can be classified
2. Open Interviews — confirm pre-kanban section shows applied/survey jobs, kanban has 3 columns
3. Manually promote a job to survey stage via the "📋 Survey" button
4. Open Survey Assistant — job appears in selector
5. Paste a sample survey question, click Analyze, save response
6. Verify response appears in history

### Step 3: Final commit

```bash
git add -A
git commit -m "feat: survey assistant complete — vision service, survey stage, kanban consolidation"
```
