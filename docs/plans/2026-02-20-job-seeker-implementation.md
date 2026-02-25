# Job Seeker Platform — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stand up a job discovery pipeline (JobSpy → Notion) with LLM routing, resume matching, and automated LinkedIn application support for Meghan McCann.

**Architecture:** JobSpy scrapes listings from multiple boards and pushes deduplicated results into a Notion database. A local LLM router with 5-backend fallback chain powers AIHawk's application answer generation. Resume Matcher scores each listing against Meghan's resume and writes keyword gaps back to Notion.

**Tech Stack:** Python 3.12, conda env `job-seeker`, `python-jobspy`, `notion-client`, `openai` SDK, `anthropic` SDK, `pyyaml`, `pandas`, Resume-Matcher (cloned), Auto_Jobs_Applier_AIHawk (cloned), pytest, pytest-mock

**Priority order:** Discovery (Tasks 1–5) must be running before Match or AIHawk setup.

**Document storage rule:** Resumes and cover letters live in `/Library/Documents/JobSearch/` — never committed to this repo.

---

## Task 1: Conda Environment + Project Scaffold

**Files:**
- Create: `/devl/job-seeker/environment.yml`
- Create: `/devl/job-seeker/.gitignore`
- Create: `/devl/job-seeker/tests/__init__.py`

**Step 1: Write environment.yml**

```yaml
# /devl/job-seeker/environment.yml
name: job-seeker
channels:
  - conda-forge
  - defaults
dependencies:
  - python=3.12
  - pip
  - pip:
    - python-jobspy
    - notion-client
    - openai
    - anthropic
    - pyyaml
    - pandas
    - requests
    - pytest
    - pytest-mock
```

**Step 2: Create the conda env**

```bash
conda env create -f /devl/job-seeker/environment.yml
```

Expected: env `job-seeker` created with no errors.

**Step 3: Verify the env**

```bash
conda run -n job-seeker python -c "import jobspy, notion_client, openai, anthropic; print('all good')"
```

Expected: `all good`

**Step 4: Write .gitignore**

```gitignore
# /devl/job-seeker/.gitignore
.env
config/notion.yaml          # contains Notion token
__pycache__/
*.pyc
.pytest_cache/
output/
aihawk/
resume_matcher/
```

Note: `aihawk/` and `resume_matcher/` are cloned externally — don't commit them.

**Step 5: Create tests directory**

```bash
mkdir -p /devl/job-seeker/tests
touch /devl/job-seeker/tests/__init__.py
```

**Step 6: Commit**

```bash
cd /devl/job-seeker
git add environment.yml .gitignore tests/__init__.py
git commit -m "feat: add conda env spec and project scaffold"
```

---

## Task 2: Config Files

**Files:**
- Create: `config/search_profiles.yaml`
- Create: `config/llm.yaml`
- Create: `config/notion.yaml.example` (the real `notion.yaml` is gitignored)

**Step 1: Write search_profiles.yaml**

```yaml
# config/search_profiles.yaml
profiles:
  - name: cs_leadership
    titles:
      - "Customer Success Manager"
      - "Director of Customer Success"
      - "VP Customer Success"
      - "Head of Customer Success"
      - "Technical Account Manager"
      - "Revenue Operations Manager"
      - "Customer Experience Lead"
    locations:
      - "Remote"
      - "San Francisco Bay Area, CA"
    boards:
      - linkedin
      - indeed
      - glassdoor
      - zip_recruiter
    results_per_board: 25
    hours_old: 72
```

**Step 2: Write llm.yaml**

```yaml
# config/llm.yaml
fallback_order:
  - claude_code
  - ollama
  - vllm
  - github_copilot
  - anthropic

backends:
  claude_code:
    type: openai_compat
    base_url: http://localhost:3009/v1
    model: claude-code-terminal
    api_key: "any"

  ollama:
    type: openai_compat
    base_url: http://localhost:11434/v1
    model: llama3.2
    api_key: "ollama"

  vllm:
    type: openai_compat
    base_url: http://localhost:8000/v1
    model: __auto__
    api_key: ""

  github_copilot:
    type: openai_compat
    base_url: http://localhost:3010/v1
    model: gpt-4o
    api_key: "any"

  anthropic:
    type: anthropic
    model: claude-sonnet-4-6
    api_key_env: ANTHROPIC_API_KEY
```

**Step 3: Write notion.yaml.example**

```yaml
# config/notion.yaml.example
# Copy to config/notion.yaml and fill in your values.
# notion.yaml is gitignored — never commit it.
token: "secret_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
database_id: "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
```

**Step 4: Commit**

```bash
cd /devl/job-seeker
git add config/search_profiles.yaml config/llm.yaml config/notion.yaml.example
git commit -m "feat: add search profiles, LLM config, and Notion config template"
```

---

## Task 3: Create Notion Database

This task creates the Notion DB that all scripts write to. Do it once manually.

**Step 1: Open Notion and create a new database**

Create a full-page database called **"Meghan's Job Search"** in whatever Notion workspace you use for tracking.

**Step 2: Add the required properties**

Delete the default properties and create exactly these (type matters):

| Property Name  | Type     |
|----------------|----------|
| Job Title      | Title    |
| Company        | Text     |
| Location       | Text     |
| Remote         | Checkbox |
| URL            | URL      |
| Source         | Select   |
| Status         | Select   |
| Match Score    | Number   |
| Keyword Gaps   | Text     |
| Salary         | Text     |
| Date Found     | Date     |
| Notes          | Text     |

For the **Status** select, add these options in order:
`New`, `Reviewing`, `Applied`, `Interview`, `Offer`, `Rejected`

For the **Source** select, add:
`Linkedin`, `Indeed`, `Glassdoor`, `Zip_Recruiter`

**Step 3: Get the database ID**

Open the database as a full page. The URL will look like:
`https://www.notion.so/YourWorkspace/XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX?v=...`

The 32-character hex string before the `?` is the database ID.

**Step 4: Get your Notion integration token**

Go to https://www.notion.so/my-integrations → create integration (or use existing) →
copy the "Internal Integration Token" (starts with `secret_`).

Connect the integration to your database: open the database → `...` menu →
Add connections → select your integration.

**Step 5: Write config/notion.yaml**

```bash
cp /devl/job-seeker/config/notion.yaml.example /devl/job-seeker/config/notion.yaml
# Edit notion.yaml and fill in your token and database_id
```

**Step 6: Verify connection**

```bash
conda run -n job-seeker python3 -c "
from notion_client import Client
import yaml
cfg = yaml.safe_load(open('/devl/job-seeker/config/notion.yaml'))
n = Client(auth=cfg['token'])
db = n.databases.retrieve(cfg['database_id'])
print('Connected to:', db['title'][0]['plain_text'])
"
```

Expected: `Connected to: Meghan's Job Search`

---

## Task 4: LLM Router

**Files:**
- Create: `scripts/llm_router.py`
- Create: `tests/test_llm_router.py`

**Step 1: Write the failing tests**

```python
# tests/test_llm_router.py
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import yaml

# Point tests at the real config
CONFIG_PATH = Path(__file__).parent.parent / "config" / "llm.yaml"


def test_config_loads():
    """Config file is valid YAML with required keys."""
    cfg = yaml.safe_load(CONFIG_PATH.read_text())
    assert "fallback_order" in cfg
    assert "backends" in cfg
    assert len(cfg["fallback_order"]) >= 1


def test_router_uses_first_reachable_backend(tmp_path):
    """Router skips unreachable backends and uses the first that responds."""
    from scripts.llm_router import LLMRouter

    router = LLMRouter(CONFIG_PATH)

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "hello"

    with patch.object(router, "_is_reachable", side_effect=[False, True, True, True, True]), \
         patch("scripts.llm_router.OpenAI") as MockOpenAI:
        instance = MockOpenAI.return_value
        instance.chat.completions.create.return_value = mock_response
        # Also mock models.list for __auto__ case
        mock_model = MagicMock()
        mock_model.id = "test-model"
        instance.models.list.return_value.data = [mock_model]

        result = router.complete("say hello")

    assert result == "hello"


def test_router_raises_when_all_backends_fail():
    """Router raises RuntimeError when every backend is unreachable or errors."""
    from scripts.llm_router import LLMRouter

    router = LLMRouter(CONFIG_PATH)

    with patch.object(router, "_is_reachable", return_value=False):
        with pytest.raises(RuntimeError, match="All LLM backends exhausted"):
            router.complete("say hello")


def test_is_reachable_returns_false_on_connection_error():
    """_is_reachable returns False when the health endpoint is unreachable."""
    from scripts.llm_router import LLMRouter
    import requests

    router = LLMRouter(CONFIG_PATH)

    with patch("scripts.llm_router.requests.get", side_effect=requests.ConnectionError):
        result = router._is_reachable("http://localhost:9999/v1")

    assert result is False
```

**Step 2: Run tests to verify they fail**

```bash
cd /devl/job-seeker
conda run -n job-seeker pytest tests/test_llm_router.py -v
```

Expected: `ImportError` — `scripts.llm_router` doesn't exist yet.

**Step 3: Create scripts/__init__.py**

```bash
touch /devl/job-seeker/scripts/__init__.py
```

**Step 4: Write scripts/llm_router.py**

```python
# scripts/llm_router.py
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

    def complete(self, prompt: str, system: str | None = None) -> str:
        """
        Generate a completion. Tries each backend in fallback_order.
        Raises RuntimeError if all backends are exhausted.
        """
        for name in self.config["fallback_order"]:
            backend = self.config["backends"][name]

            if backend["type"] == "openai_compat":
                if not self._is_reachable(backend["base_url"]):
                    print(f"[LLMRouter] {name}: unreachable, skipping")
                    continue
                try:
                    client = OpenAI(
                        base_url=backend["base_url"],
                        api_key=backend.get("api_key", "any"),
                    )
                    model = self._resolve_model(client, backend["model"])
                    messages = []
                    if system:
                        messages.append({"role": "system", "content": system})
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
                    kwargs: dict = {
                        "model": backend["model"],
                        "max_tokens": 4096,
                        "messages": [{"role": "user", "content": prompt}],
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
```

**Step 5: Run tests to verify they pass**

```bash
conda run -n job-seeker pytest tests/test_llm_router.py -v
```

Expected: 4 tests PASS.

**Step 6: Smoke-test against live Ollama**

```bash
conda run -n job-seeker python3 -c "
from scripts.llm_router import complete
print(complete('Say: job-seeker LLM router is working'))
"
```

Expected: A short response from Ollama (or next reachable backend).

**Step 7: Commit**

```bash
cd /devl/job-seeker
git add scripts/__init__.py scripts/llm_router.py tests/test_llm_router.py
git commit -m "feat: add LLM router with 5-backend fallback chain"
```

---

## Task 5: Job Discovery (discover.py) — PRIORITY

**Files:**
- Create: `scripts/discover.py`
- Create: `tests/test_discover.py`

**Step 1: Write the failing tests**

```python
# tests/test_discover.py
import pytest
from unittest.mock import patch, MagicMock, call
import pandas as pd
from pathlib import Path


SAMPLE_JOB = {
    "title": "Customer Success Manager",
    "company": "Acme Corp",
    "location": "Remote",
    "is_remote": True,
    "job_url": "https://linkedin.com/jobs/view/123456",
    "site": "linkedin",
    "salary_source": "$90,000 - $120,000",
}


def make_jobs_df(jobs=None):
    return pd.DataFrame(jobs or [SAMPLE_JOB])


def test_get_existing_urls_returns_set():
    """get_existing_urls returns a set of URL strings from Notion pages."""
    from scripts.discover import get_existing_urls

    mock_notion = MagicMock()
    mock_notion.databases.query.return_value = {
        "results": [
            {"properties": {"URL": {"url": "https://example.com/job/1"}}},
            {"properties": {"URL": {"url": "https://example.com/job/2"}}},
        ],
        "has_more": False,
        "next_cursor": None,
    }

    urls = get_existing_urls(mock_notion, "fake-db-id")
    assert urls == {"https://example.com/job/1", "https://example.com/job/2"}


def test_discover_skips_duplicate_urls():
    """discover does not push a job whose URL is already in Notion."""
    from scripts.discover import run_discovery

    existing = {"https://linkedin.com/jobs/view/123456"}

    with patch("scripts.discover.scrape_jobs", return_value=make_jobs_df()), \
         patch("scripts.discover.get_existing_urls", return_value=existing), \
         patch("scripts.discover.push_to_notion") as mock_push, \
         patch("scripts.discover.Client"):
        run_discovery()

    mock_push.assert_not_called()


def test_discover_pushes_new_jobs():
    """discover pushes jobs whose URLs are not already in Notion."""
    from scripts.discover import run_discovery

    with patch("scripts.discover.scrape_jobs", return_value=make_jobs_df()), \
         patch("scripts.discover.get_existing_urls", return_value=set()), \
         patch("scripts.discover.push_to_notion") as mock_push, \
         patch("scripts.discover.Client"):
        run_discovery()

    assert mock_push.call_count == 1


def test_push_to_notion_sets_status_new():
    """push_to_notion always sets Status to 'New'."""
    from scripts.discover import push_to_notion

    mock_notion = MagicMock()
    push_to_notion(mock_notion, "fake-db-id", SAMPLE_JOB)

    call_kwargs = mock_notion.pages.create.call_args[1]
    status = call_kwargs["properties"]["Status"]["select"]["name"]
    assert status == "New"
```

**Step 2: Run tests to verify they fail**

```bash
conda run -n job-seeker pytest tests/test_discover.py -v
```

Expected: `ImportError` — `scripts.discover` doesn't exist yet.

**Step 3: Write scripts/discover.py**

```python
# scripts/discover.py
"""
JobSpy → Notion discovery pipeline.
Scrapes job boards, deduplicates against existing Notion records,
and pushes new listings with Status=New.

Usage:
    conda run -n job-seeker python scripts/discover.py
"""
import yaml
from datetime import datetime
from pathlib import Path

import pandas as pd
from jobspy import scrape_jobs
from notion_client import Client

CONFIG_DIR = Path(__file__).parent.parent / "config"
NOTION_CFG = CONFIG_DIR / "notion.yaml"
PROFILES_CFG = CONFIG_DIR / "search_profiles.yaml"


def load_config() -> tuple[dict, dict]:
    profiles = yaml.safe_load(PROFILES_CFG.read_text())
    notion_cfg = yaml.safe_load(NOTION_CFG.read_text())
    return profiles, notion_cfg


def get_existing_urls(notion: Client, db_id: str) -> set[str]:
    """Return the set of all job URLs already tracked in Notion."""
    existing: set[str] = set()
    has_more = True
    start_cursor = None

    while has_more:
        kwargs: dict = {"database_id": db_id, "page_size": 100}
        if start_cursor:
            kwargs["start_cursor"] = start_cursor
        resp = notion.databases.query(**kwargs)

        for page in resp["results"]:
            url = page["properties"].get("URL", {}).get("url")
            if url:
                existing.add(url)

        has_more = resp.get("has_more", False)
        start_cursor = resp.get("next_cursor")

    return existing


def push_to_notion(notion: Client, db_id: str, job: dict) -> None:
    """Create a new page in the Notion jobs database for a single listing."""
    notion.pages.create(
        parent={"database_id": db_id},
        properties={
            "Job Title": {"title": [{"text": {"content": str(job.get("title", "Unknown"))}}]},
            "Company":   {"rich_text": [{"text": {"content": str(job.get("company", ""))}}]},
            "Location":  {"rich_text": [{"text": {"content": str(job.get("location", ""))}}]},
            "Remote":    {"checkbox": bool(job.get("is_remote", False))},
            "URL":       {"url": str(job.get("job_url", ""))},
            "Source":    {"select": {"name": str(job.get("site", "unknown")).title()}},
            "Status":    {"select": {"name": "New"}},
            "Salary":    {"rich_text": [{"text": {"content": str(job.get("salary_source") or "")}}]},
            "Date Found": {"date": {"start": datetime.now().isoformat()[:10]}},
        },
    )


def run_discovery() -> None:
    profiles_cfg, notion_cfg = load_config()
    notion = Client(auth=notion_cfg["token"])
    db_id = notion_cfg["database_id"]

    existing_urls = get_existing_urls(notion, db_id)
    print(f"[discover] {len(existing_urls)} existing listings in Notion")

    new_count = 0

    for profile in profiles_cfg["profiles"]:
        print(f"\n[discover] Profile: {profile['name']}")
        for location in profile["locations"]:
            print(f"  Scraping: {location}")
            jobs: pd.DataFrame = scrape_jobs(
                site_name=profile["boards"],
                search_term=" OR ".join(f'"{t}"' for t in profile["titles"]),
                location=location,
                results_wanted=profile.get("results_per_board", 25),
                hours_old=profile.get("hours_old", 72),
                linkedin_fetch_description=True,
            )

            for _, job in jobs.iterrows():
                url = str(job.get("job_url", ""))
                if not url or url in existing_urls:
                    continue
                push_to_notion(notion, db_id, job.to_dict())
                existing_urls.add(url)
                new_count += 1
                print(f"  + {job.get('title')} @ {job.get('company')}")

    print(f"\n[discover] Done — {new_count} new listings pushed to Notion.")


if __name__ == "__main__":
    run_discovery()
```

**Step 4: Run tests to verify they pass**

```bash
conda run -n job-seeker pytest tests/test_discover.py -v
```

Expected: 4 tests PASS.

**Step 5: Run a live discovery (requires notion.yaml to be set up from Task 3)**

```bash
conda run -n job-seeker python scripts/discover.py
```

Expected: listings printed and pushed to Notion. Check the Notion DB to confirm rows appear with Status=New.

**Step 6: Commit**

```bash
cd /devl/job-seeker
git add scripts/discover.py tests/test_discover.py
git commit -m "feat: add JobSpy discovery pipeline with Notion deduplication"
```

---

## Task 6: Clone and Configure Resume Matcher

**Step 1: Clone Resume Matcher**

```bash
cd /devl/job-seeker
git clone https://github.com/srbhr/Resume-Matcher.git resume_matcher
```

**Step 2: Install Resume Matcher dependencies into the job-seeker env**

```bash
conda run -n job-seeker pip install -r /devl/job-seeker/resume_matcher/requirements.txt
```

If there are conflicts, install only the core matching library:
```bash
conda run -n job-seeker pip install sentence-transformers streamlit qdrant-client pypdf2
```

**Step 3: Verify it launches**

```bash
conda run -n job-seeker streamlit run /devl/job-seeker/resume_matcher/streamlit_app.py --server.port 8501
```

Expected: Streamlit opens on http://localhost:8501 (port confirmed clear).
Stop it with Ctrl+C — we'll run it on-demand.

**Step 4: Note the resume path to use**

The ATS-clean resume to use with Resume Matcher:
```
/Library/Documents/JobSearch/Meghan_McCann_Resume_02-19-2025.pdf
```

---

## Task 7: Resume Match Script (match.py)

**Files:**
- Create: `scripts/match.py`
- Create: `tests/test_match.py`

**Step 1: Write the failing tests**

```python
# tests/test_match.py
import pytest
from unittest.mock import patch, MagicMock


def test_extract_job_description_from_url():
    """extract_job_description fetches and returns text from a URL."""
    from scripts.match import extract_job_description

    with patch("scripts.match.requests.get") as mock_get:
        mock_get.return_value.text = "<html><body><p>We need a CSM with Salesforce.</p></body></html>"
        mock_get.return_value.raise_for_status = MagicMock()
        result = extract_job_description("https://example.com/job/123")

    assert "CSM" in result
    assert "Salesforce" in result


def test_score_is_between_0_and_100():
    """match_score returns a float in [0, 100]."""
    from scripts.match import match_score

    # Provide minimal inputs that the scorer can handle
    score, gaps = match_score(
        resume_text="Customer Success Manager with Salesforce experience",
        job_text="Looking for a Customer Success Manager who knows Salesforce and Gainsight",
    )
    assert 0 <= score <= 100
    assert isinstance(gaps, list)


def test_write_score_to_notion():
    """write_match_to_notion updates the Notion page with score and gaps."""
    from scripts.match import write_match_to_notion

    mock_notion = MagicMock()
    write_match_to_notion(mock_notion, "page-id-abc", 85.5, ["Gainsight", "Churnzero"])

    mock_notion.pages.update.assert_called_once()
    call_kwargs = mock_notion.pages.update.call_args[1]
    assert call_kwargs["page_id"] == "page-id-abc"
    score_val = call_kwargs["properties"]["Match Score"]["number"]
    assert score_val == 85.5
```

**Step 2: Run tests to verify they fail**

```bash
conda run -n job-seeker pytest tests/test_match.py -v
```

Expected: `ImportError` — `scripts.match` doesn't exist.

**Step 3: Write scripts/match.py**

```python
# scripts/match.py
"""
Resume Matcher integration: score a Notion job listing against Meghan's resume.
Writes Match Score and Keyword Gaps back to the Notion page.

Usage:
    conda run -n job-seeker python scripts/match.py <notion-page-url-or-id>
"""
import re
import sys
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup
from notion_client import Client

CONFIG_DIR = Path(__file__).parent.parent / "config"
RESUME_PATH = Path("/Library/Documents/JobSearch/Meghan_McCann_Resume_02-19-2025.pdf")


def load_notion() -> tuple[Client, str]:
    cfg = yaml.safe_load((CONFIG_DIR / "notion.yaml").read_text())
    return Client(auth=cfg["token"]), cfg["database_id"]


def extract_page_id(url_or_id: str) -> str:
    """Extract 32-char Notion page ID from a URL or return as-is."""
    match = re.search(r"[0-9a-f]{32}", url_or_id.replace("-", ""))
    if match:
        return match.group(0)
    return url_or_id.strip()


def get_job_url_from_notion(notion: Client, page_id: str) -> str:
    page = notion.pages.retrieve(page_id)
    return page["properties"]["URL"]["url"]


def extract_job_description(url: str) -> str:
    """Fetch a job listing URL and return its visible text."""
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ").split())


def read_resume_text() -> str:
    """Extract text from the ATS-clean PDF resume."""
    try:
        import pypdf
        reader = pypdf.PdfReader(str(RESUME_PATH))
        return " ".join(page.extract_text() or "" for page in reader.pages)
    except ImportError:
        import PyPDF2
        with open(RESUME_PATH, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            return " ".join(p.extract_text() or "" for p in reader.pages)


def match_score(resume_text: str, job_text: str) -> tuple[float, list[str]]:
    """
    Score resume against job description using TF-IDF keyword overlap.
    Returns (score 0-100, list of keywords in job not found in resume).
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np

    vectorizer = TfidfVectorizer(stop_words="english", max_features=200)
    tfidf = vectorizer.fit_transform([resume_text, job_text])
    score = float(cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0]) * 100

    # Keyword gap: terms in job description not present in resume (lowercased)
    job_terms = set(job_text.lower().split())
    resume_terms = set(resume_text.lower().split())
    feature_names = vectorizer.get_feature_names_out()
    job_tfidf = tfidf[1].toarray()[0]
    top_indices = np.argsort(job_tfidf)[::-1][:30]
    top_job_terms = [feature_names[i] for i in top_indices if job_tfidf[i] > 0]
    gaps = [t for t in top_job_terms if t not in resume_terms][:10]

    return round(score, 1), gaps


def write_match_to_notion(notion: Client, page_id: str, score: float, gaps: list[str]) -> None:
    notion.pages.update(
        page_id=page_id,
        properties={
            "Match Score": {"number": score},
            "Keyword Gaps": {"rich_text": [{"text": {"content": ", ".join(gaps)}}]},
        },
    )


def run_match(page_url_or_id: str) -> None:
    notion, _ = load_notion()
    page_id = extract_page_id(page_url_or_id)

    print(f"[match] Page ID: {page_id}")
    job_url = get_job_url_from_notion(notion, page_id)
    print(f"[match] Fetching job description from: {job_url}")

    job_text = extract_job_description(job_url)
    resume_text = read_resume_text()

    score, gaps = match_score(resume_text, job_text)
    print(f"[match] Score: {score}/100")
    print(f"[match] Keyword gaps: {', '.join(gaps) or 'none'}")

    write_match_to_notion(notion, page_id, score, gaps)
    print("[match] Written to Notion.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/match.py <notion-page-url-or-id>")
        sys.exit(1)
    run_match(sys.argv[1])
```

**Step 4: Install sklearn (needed by match.py)**

```bash
conda run -n job-seeker pip install scikit-learn beautifulsoup4 pypdf
```

**Step 5: Run tests**

```bash
conda run -n job-seeker pytest tests/test_match.py -v
```

Expected: 3 tests PASS.

**Step 6: Commit**

```bash
cd /devl/job-seeker
git add scripts/match.py tests/test_match.py
git commit -m "feat: add resume match scoring with Notion write-back"
```

---

## Task 8: Clone and Configure AIHawk

**Step 1: Clone AIHawk**

```bash
cd /devl/job-seeker
git clone https://github.com/feder-cr/Auto_Jobs_Applier_AIHawk.git aihawk
```

**Step 2: Install AIHawk dependencies**

```bash
conda run -n job-seeker pip install -r /devl/job-seeker/aihawk/requirements.txt
```

**Step 3: Install Playwright browsers (AIHawk uses Playwright for browser automation)**

```bash
conda run -n job-seeker playwright install chromium
```

**Step 4: Create AIHawk personal info config**

AIHawk reads a `personal_info.yaml`. Create it in AIHawk's data directory:

```bash
cp /devl/job-seeker/aihawk/data_folder/plain_text_resume.yaml \
   /devl/job-seeker/aihawk/data_folder/plain_text_resume.yaml.bak
```

Edit `/devl/job-seeker/aihawk/data_folder/plain_text_resume.yaml` with Meghan's info.
Key fields to fill:
- `personal_information`: name, email, phone, linkedin, github (leave blank), location
- `work_experience`: pull from the SVG content already extracted
- `education`: Texas State University, Mass Communications & PR, 2012-2015
- `skills`: Zendesk, Intercom, Asana, Jira, etc.

**Step 5: Configure AIHawk to use the LLM router**

AIHawk's config (`aihawk/data_folder/config.yaml`) has an `llm_model_type` and `llm_model` field.
Set it to use the local OpenAI-compatible endpoint:

```yaml
# In aihawk/data_folder/config.yaml
llm_model_type: openai
llm_model: claude-code-terminal
openai_api_url: http://localhost:3009/v1   # or whichever backend is running
```

If 3009 is down, change to `http://localhost:11434/v1` (Ollama).

**Step 6: Run AIHawk in dry-run mode first**

```bash
conda run -n job-seeker python /devl/job-seeker/aihawk/main.py --help
```

Review the flags. Start with a test run before enabling real submissions.

**Step 7: Commit the environment update**

```bash
cd /devl/job-seeker
conda env export -n job-seeker > environment.yml
git add environment.yml
git commit -m "chore: update environment.yml with all installed packages"
```

---

## Task 9: End-to-End Smoke Test

**Step 1: Run full test suite**

```bash
conda run -n job-seeker pytest tests/ -v
```

Expected: all tests PASS.

**Step 2: Run discovery**

```bash
conda run -n job-seeker python scripts/discover.py
```

Expected: new listings appear in Notion with Status=New.

**Step 3: Run match on one listing**

Copy the URL of a Notion page from the DB and run:

```bash
conda run -n job-seeker python scripts/match.py "https://www.notion.so/..."
```

Expected: Match Score and Keyword Gaps written back to that Notion page.

**Step 4: Commit anything left**

```bash
cd /devl/job-seeker
git status
git add -p   # stage only code/config, not secrets
git commit -m "chore: final smoke test cleanup"
```

---

## Quick Reference

| Command | What it does |
|---|---|
| `conda run -n job-seeker python scripts/discover.py` | Scrape boards → push new listings to Notion |
| `conda run -n job-seeker python scripts/match.py <url>` | Score a listing → write back to Notion |
| `conda run -n job-seeker streamlit run resume_matcher/streamlit_app.py --server.port 8501` | Open Resume Matcher UI |
| `conda run -n job-seeker pytest tests/ -v` | Run all tests |
| `cd "/Library/Documents/Post Fight Processing" && ./manage.sh start` | Start Claude Code pipeline (port 3009) |
| `cd "/Library/Documents/Post Fight Processing" && ./manage-copilot.sh start` | Start Copilot wrapper (port 3010) |
