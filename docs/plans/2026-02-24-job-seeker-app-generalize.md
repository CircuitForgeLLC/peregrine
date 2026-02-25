# Job Seeker App — Generalization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fork the personal job-seeker app into a fully generalized, Docker-Compose-based version at `/Library/Development/devl/job-seeker-app/` that any job seeker can run.

**Architecture:** A `UserProfile` class backed by `config/user.yaml` replaces all hard-coded personal references across the codebase. A Docker Compose stack with four named profiles (`remote`, `cpu`, `single-gpu`, `dual-gpu`) controls which services start. A first-run wizard gates the app on first launch and writes `user.yaml` on completion.

**Tech Stack:** Python 3.11, Streamlit, SQLite, Docker Compose v2, NVIDIA Container Toolkit (optional), PyYAML, Requests

**Reference:** Design doc at `docs/plans/2026-02-24-generalize-design.md` in the personal repo.

---

## Task 1: Bootstrap — New Repo From Personal Source

**Files:**
- Create: `/Library/Development/devl/job-seeker-app/` (new directory)

**Step 1: Copy source, strip personal config**

```bash
mkdir -p /Library/Development/devl/job-seeker-app
rsync -av --exclude='.git' \
  --exclude='staging.db' \
  --exclude='config/email.yaml' \
  --exclude='config/notion.yaml' \
  --exclude='config/tokens.yaml' \
  --exclude='aihawk/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.streamlit.pid' \
  --exclude='.streamlit.log' \
  /devl/job-seeker/ \
  /Library/Development/devl/job-seeker-app/
```

**Step 2: Init fresh git repo**

```bash
cd /Library/Development/devl/job-seeker-app
git init
git add .
git commit -m "chore: seed from personal job-seeker (pre-generalization)"
```

**Step 3: Verify structure**

```bash
ls /Library/Development/devl/job-seeker-app/
# Expected: app/ config/ scripts/ tests/ docs/ environment.yml etc.
# NOT expected: staging.db, config/notion.yaml, config/email.yaml
```

---

## Task 2: UserProfile Class

**Files:**
- Create: `scripts/user_profile.py`
- Create: `config/user.yaml.example`
- Create: `tests/test_user_profile.py`

**Step 1: Write failing tests**

```python
# tests/test_user_profile.py
import pytest
from pathlib import Path
import tempfile, yaml
from scripts.user_profile import UserProfile

@pytest.fixture
def profile_yaml(tmp_path):
    data = {
        "name": "Jane Smith",
        "email": "jane@example.com",
        "phone": "555-1234",
        "linkedin": "linkedin.com/in/janesmith",
        "career_summary": "Experienced CSM with 8 years in SaaS.",
        "nda_companies": ["AcmeCorp"],
        "docs_dir": "~/Documents/JobSearch",
        "ollama_models_dir": "~/models/ollama",
        "vllm_models_dir": "~/models/vllm",
        "inference_profile": "single-gpu",
        "services": {
            "streamlit_port": 8501,
            "ollama_host": "localhost",
            "ollama_port": 11434,
            "ollama_ssl": False,
            "ollama_ssl_verify": True,
            "vllm_host": "localhost",
            "vllm_port": 8000,
            "vllm_ssl": False,
            "vllm_ssl_verify": True,
            "searxng_host": "localhost",
            "searxng_port": 8888,
            "searxng_ssl": False,
            "searxng_ssl_verify": True,
        }
    }
    p = tmp_path / "user.yaml"
    p.write_text(yaml.dump(data))
    return p

def test_loads_fields(profile_yaml):
    p = UserProfile(profile_yaml)
    assert p.name == "Jane Smith"
    assert p.email == "jane@example.com"
    assert p.nda_companies == ["AcmeCorp"]
    assert p.inference_profile == "single-gpu"

def test_service_url_http(profile_yaml):
    p = UserProfile(profile_yaml)
    assert p.ollama_url == "http://localhost:11434"
    assert p.vllm_url == "http://localhost:8000"
    assert p.searxng_url == "http://localhost:8888"

def test_service_url_https(tmp_path):
    data = yaml.safe_load(open(profile_yaml)) if False else {
        "name": "X", "services": {
            "ollama_host": "myserver.com", "ollama_port": 443,
            "ollama_ssl": True, "ollama_ssl_verify": True,
            "vllm_host": "localhost", "vllm_port": 8000,
            "vllm_ssl": False, "vllm_ssl_verify": True,
            "searxng_host": "localhost", "searxng_port": 8888,
            "searxng_ssl": False, "searxng_ssl_verify": True,
        }
    }
    p2 = tmp_path / "user2.yaml"
    p2.write_text(yaml.dump(data))
    prof = UserProfile(p2)
    assert prof.ollama_url == "https://myserver.com:443"

def test_nda_mask(profile_yaml):
    p = UserProfile(profile_yaml)
    assert p.is_nda("AcmeCorp")
    assert p.is_nda("acmecorp")  # case-insensitive
    assert not p.is_nda("Google")

def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        UserProfile(Path("/nonexistent/user.yaml"))

def test_exists_check(profile_yaml, tmp_path):
    assert UserProfile.exists(profile_yaml)
    assert not UserProfile.exists(tmp_path / "missing.yaml")

def test_docs_dir_expanded(profile_yaml):
    p = UserProfile(profile_yaml)
    assert not str(p.docs_dir).startswith("~")
    assert p.docs_dir.is_absolute()
```

**Step 2: Run tests to verify they fail**

```bash
cd /Library/Development/devl/job-seeker-app
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_user_profile.py -v
# Expected: ImportError — scripts/user_profile.py does not exist yet
```

**Step 3: Implement UserProfile**

```python
# scripts/user_profile.py
"""
UserProfile — wraps config/user.yaml and provides typed accessors.

All hard-coded personal references in the app should import this instead
of reading strings directly. URL construction for services is centralised
here so port/host/SSL changes propagate everywhere automatically.
"""
from __future__ import annotations
from pathlib import Path
import yaml

_DEFAULTS = {
    "name": "",
    "email": "",
    "phone": "",
    "linkedin": "",
    "career_summary": "",
    "nda_companies": [],
    "docs_dir": "~/Documents/JobSearch",
    "ollama_models_dir": "~/models/ollama",
    "vllm_models_dir": "~/models/vllm",
    "inference_profile": "remote",
    "services": {
        "streamlit_port": 8501,
        "ollama_host": "localhost",
        "ollama_port": 11434,
        "ollama_ssl": False,
        "ollama_ssl_verify": True,
        "vllm_host": "localhost",
        "vllm_port": 8000,
        "vllm_ssl": False,
        "vllm_ssl_verify": True,
        "searxng_host": "localhost",
        "searxng_port": 8888,
        "searxng_ssl": False,
        "searxng_ssl_verify": True,
    },
}


class UserProfile:
    def __init__(self, path: Path):
        if not path.exists():
            raise FileNotFoundError(f"user.yaml not found at {path}")
        raw = yaml.safe_load(path.read_text()) or {}
        data = {**_DEFAULTS, **raw}
        svc_defaults = dict(_DEFAULTS["services"])
        svc_defaults.update(raw.get("services", {}))
        data["services"] = svc_defaults

        self.name: str = data["name"]
        self.email: str = data["email"]
        self.phone: str = data["phone"]
        self.linkedin: str = data["linkedin"]
        self.career_summary: str = data["career_summary"]
        self.nda_companies: list[str] = [c.lower() for c in data["nda_companies"]]
        self.docs_dir: Path = Path(data["docs_dir"]).expanduser().resolve()
        self.ollama_models_dir: Path = Path(data["ollama_models_dir"]).expanduser().resolve()
        self.vllm_models_dir: Path = Path(data["vllm_models_dir"]).expanduser().resolve()
        self.inference_profile: str = data["inference_profile"]
        self._svc = data["services"]

    # ── Service URLs ──────────────────────────────────────────────────────────
    def _url(self, host: str, port: int, ssl: bool) -> str:
        scheme = "https" if ssl else "http"
        return f"{scheme}://{host}:{port}"

    @property
    def ollama_url(self) -> str:
        s = self._svc
        return self._url(s["ollama_host"], s["ollama_port"], s["ollama_ssl"])

    @property
    def vllm_url(self) -> str:
        s = self._svc
        return self._url(s["vllm_host"], s["vllm_port"], s["vllm_ssl"])

    @property
    def searxng_url(self) -> str:
        s = self._svc
        return self._url(s["searxng_host"], s["searxng_port"], s["searxng_ssl"])

    def ssl_verify(self, service: str) -> bool:
        """Return ssl_verify flag for a named service (ollama/vllm/searxng)."""
        return bool(self._svc.get(f"{service}_ssl_verify", True))

    # ── NDA helpers ───────────────────────────────────────────────────────────
    def is_nda(self, company: str) -> bool:
        return company.lower() in self.nda_companies

    def nda_label(self, company: str, score: int = 0, threshold: int = 3) -> str:
        """Return masked label if company is NDA and score below threshold."""
        if self.is_nda(company) and score < threshold:
            return "previous employer (NDA)"
        return company

    # ── Existence check (used by app.py before load) ─────────────────────────
    @staticmethod
    def exists(path: Path) -> bool:
        return path.exists()

    # ── llm.yaml URL generation ───────────────────────────────────────────────
    def generate_llm_urls(self) -> dict[str, str]:
        """Return base_url values for each backend, derived from services config."""
        return {
            "ollama":          f"{self.ollama_url}/v1",
            "ollama_research": f"{self.ollama_url}/v1",
            "vllm":            f"{self.vllm_url}/v1",
        }
```

**Step 4: Run tests to verify they pass**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_user_profile.py -v
# Expected: all PASS
```

**Step 5: Create config/user.yaml.example**

```yaml
# config/user.yaml.example
# Copy to config/user.yaml and fill in your details.
# The first-run wizard will create this file automatically.

name: "Your Name"
email: "you@example.com"
phone: "555-000-0000"
linkedin: "linkedin.com/in/yourprofile"
career_summary: >
  Experienced professional with X years in [your field].
  Specialise in [key skills]. Known for [strength].

nda_companies: []   # e.g. ["FormerEmployer"] — masked in research briefs

docs_dir: "~/Documents/JobSearch"
ollama_models_dir: "~/models/ollama"
vllm_models_dir: "~/models/vllm"

inference_profile: "remote"  # remote | cpu | single-gpu | dual-gpu

services:
  streamlit_port: 8501
  ollama_host: localhost
  ollama_port: 11434
  ollama_ssl: false
  ollama_ssl_verify: true
  vllm_host: localhost
  vllm_port: 8000
  vllm_ssl: false
  vllm_ssl_verify: true
  searxng_host: localhost
  searxng_port: 8888
  searxng_ssl: false
  searxng_ssl_verify: true
```

**Step 6: Commit**

```bash
git add scripts/user_profile.py config/user.yaml.example tests/test_user_profile.py
git commit -m "feat: add UserProfile class with service URL generation and NDA helpers"
```

---

## Task 3: Extract Hard-Coded References — Scripts

**Files:**
- Modify: `scripts/company_research.py`
- Modify: `scripts/generate_cover_letter.py`
- Modify: `scripts/match.py`
- Modify: `scripts/finetune_local.py`
- Modify: `scripts/prepare_training_data.py`

**Step 1: Add UserProfile loading helper to company_research.py**

In `scripts/company_research.py`, remove the hard-coded `_SCRAPER_DIR` path and
replace personal references. The scraper is now bundled in the Docker image so its
path is always `/app/companyScraper.py` inside the container.

Replace:
```python
_SCRAPER_DIR = Path("/Library/Development/scrapers")
_SCRAPER_AVAILABLE = False

if _SCRAPER_DIR.exists():
    sys.path.insert(0, str(_SCRAPER_DIR))
    try:
        from companyScraper import EnhancedCompanyScraper, Config as _ScraperConfig
        _SCRAPER_AVAILABLE = True
    except (ImportError, SystemExit):
        pass
```

With:
```python
# companyScraper is bundled into the Docker image at /app/scrapers/
_SCRAPER_AVAILABLE = False
for _scraper_candidate in [
    Path("/app/scrapers"),          # Docker container path
    Path(__file__).parent.parent / "scrapers",  # local dev fallback
]:
    if _scraper_candidate.exists():
        sys.path.insert(0, str(_scraper_candidate))
        try:
            from companyScraper import EnhancedCompanyScraper, Config as _ScraperConfig
            _SCRAPER_AVAILABLE = True
        except (ImportError, SystemExit):
            pass
        break
```

Replace `_searxng_running()` to use profile URL:
```python
def _searxng_running(searxng_url: str = "http://localhost:8888") -> bool:
    try:
        import requests
        r = requests.get(f"{searxng_url}/", timeout=3)
        return r.status_code == 200
    except Exception:
        return False
```

Replace all `"Meghan McCann"` / `"Meghan's"` / `_NDA_COMPANIES` references:
```python
# At top of research_company():
from scripts.user_profile import UserProfile
from scripts.db import DEFAULT_DB
_USER_YAML = Path(__file__).parent.parent / "config" / "user.yaml"
_profile = UserProfile(_USER_YAML) if UserProfile.exists(_USER_YAML) else None

# In _build_resume_context(), replace _company_label():
def _company_label(exp: dict) -> str:
    company = exp.get("company", "")
    score = exp.get("score", 0)
    if _profile:
        return _profile.nda_label(company, score)
    return company

# Replace "## Meghan's Matched Experience":
lines = [f"## {_profile.name if _profile else 'Candidate'}'s Matched Experience"]

# In research_company() prompt, replace "Meghan McCann":
name = _profile.name if _profile else "the candidate"
summary = _profile.career_summary if _profile else ""
# Replace "You are preparing Meghan McCann for a job interview." with:
prompt = f"""You are preparing {name} for a job interview.\n{summary}\n..."""
```

**Step 2: Update generate_cover_letter.py**

Replace:
```python
LETTERS_DIR = Path("/Library/Documents/JobSearch")
SYSTEM_CONTEXT = """You are writing cover letters for Meghan McCann..."""
```

With:
```python
from scripts.user_profile import UserProfile
_USER_YAML = Path(__file__).parent.parent / "config" / "user.yaml"
_profile = UserProfile(_USER_YAML) if UserProfile.exists(_USER_YAML) else None

LETTERS_DIR = _profile.docs_dir if _profile else Path.home() / "Documents" / "JobSearch"
SYSTEM_CONTEXT = (
    f"You are writing cover letters for {_profile.name}. {_profile.career_summary}"
    if _profile else
    "You are a professional cover letter writer. Write in first person."
)
```

**Step 3: Update match.py**

Replace hard-coded resume path with a config lookup:
```python
# match.py — read RESUME_PATH from config/user.yaml or fall back to auto-discovery
from scripts.user_profile import UserProfile
_USER_YAML = Path(__file__).parent.parent / "config" / "user.yaml"
_profile = UserProfile(_USER_YAML) if UserProfile.exists(_USER_YAML) else None

def _find_resume(docs_dir: Path) -> Path | None:
    """Find the most recently modified PDF in docs_dir matching *resume* or *cv*."""
    candidates = list(docs_dir.glob("*[Rr]esume*.pdf")) + list(docs_dir.glob("*[Cc][Vv]*.pdf"))
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None

RESUME_PATH = (
    _find_resume(_profile.docs_dir) if _profile else None
) or Path(__file__).parent.parent / "config" / "resume.pdf"
```

**Step 4: Update finetune_local.py and prepare_training_data.py**

Replace all `/Library/` paths with profile-driven paths:
```python
from scripts.user_profile import UserProfile
_USER_YAML = Path(__file__).parent.parent / "config" / "user.yaml"
_profile = UserProfile(_USER_YAML) if UserProfile.exists(_USER_YAML) else None

_docs = _profile.docs_dir if _profile else Path.home() / "Documents" / "JobSearch"
LETTERS_JSONL = _docs / "training_data" / "cover_letters.jsonl"
OUTPUT_DIR    = _docs / "training_data" / "finetune_output"
GGUF_DIR      = _docs / "training_data" / "gguf"
OLLAMA_NAME   = f"{_profile.name.split()[0].lower()}-cover-writer" if _profile else "cover-writer"
SYSTEM_PROMPT = (
    f"You are {_profile.name}'s personal cover letter writer. "
    f"{_profile.career_summary}"
    if _profile else
    "You are a professional cover letter writer. Write in first person."
)
```

**Step 5: Run existing tests to verify nothing broken**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v
# Expected: all existing tests PASS
```

**Step 6: Commit**

```bash
git add scripts/
git commit -m "feat: extract hard-coded personal references from all scripts via UserProfile"
```

---

## Task 4: Extract Hard-Coded References — App Pages

**Files:**
- Modify: `app/Home.py`
- Modify: `app/pages/4_Apply.py`
- Modify: `app/pages/5_Interviews.py`
- Modify: `app/pages/6_Interview_Prep.py`
- Modify: `app/pages/2_Settings.py`

**Step 1: Add profile loader utility to app pages**

Add to the top of each modified page (after sys.path insert):
```python
from scripts.user_profile import UserProfile
from scripts.db import DEFAULT_DB

_USER_YAML = Path(__file__).parent.parent.parent / "config" / "user.yaml"
_profile = UserProfile(_USER_YAML) if UserProfile.exists(_USER_YAML) else None
_name = _profile.name if _profile else "Job Seeker"
```

**Step 2: Home.py**

Replace:
```python
st.title("🔍 Meghan's Job Search")
# and:
st.caption(f"Run TF-IDF match scoring against Meghan's resume...")
```
With:
```python
st.title(f"🔍 {_name}'s Job Search")
# and:
st.caption(f"Run TF-IDF match scoring against {_name}'s resume...")
```

**Step 3: 4_Apply.py — PDF contact block and DOCS_DIR**

Replace:
```python
DOCS_DIR = Path("/Library/Documents/JobSearch")
# and the contact paragraph:
Paragraph("MEGHAN McCANN", name_style)
Paragraph("meghan.m.mccann@gmail.com  ·  (510) 764-3155  ·  ...", contact_style)
Paragraph("Warm regards,<br/><br/>Meghan McCann", body_style)
```
With:
```python
DOCS_DIR = _profile.docs_dir if _profile else Path.home() / "Documents" / "JobSearch"
# and:
display_name = (_profile.name.upper() if _profile else "YOUR NAME")
contact_line = " · ".join(filter(None, [
    _profile.email if _profile else "",
    _profile.phone if _profile else "",
    _profile.linkedin if _profile else "",
]))
Paragraph(display_name, name_style)
Paragraph(contact_line, contact_style)
Paragraph(f"Warm regards,<br/><br/>{_profile.name if _profile else 'Your Name'}", body_style)
```

**Step 4: 5_Interviews.py — email assistant prompt**

Replace hard-coded persona strings with:
```python
_persona = (
    f"{_name} is a {_profile.career_summary[:120] if _profile and _profile.career_summary else 'professional'}"
)
# Replace all occurrences of "Meghan McCann is a Customer Success..." with _persona
```

**Step 5: 6_Interview_Prep.py — interviewer and Q&A prompts**

Replace all occurrences of `"Meghan"` in f-strings with `_name`.

**Step 6: 2_Settings.py — Services tab**

Remove `PFP_DIR` and the Claude Code Wrapper / Copilot Wrapper service entries entirely.

Replace the vLLM service entry's `model_dir` with:
```python
"model_dir": str(_profile.vllm_models_dir) if _profile else str(Path.home() / "models" / "vllm"),
```

Replace the SearXNG entry to use Docker Compose instead of a host path:
```python
{
    "name": "SearXNG (company scraper)",
    "port": _profile._svc["searxng_port"] if _profile else 8888,
    "start": ["docker", "compose", "--profile", "searxng", "up", "-d", "searxng"],
    "stop":  ["docker", "compose", "stop", "searxng"],
    "cwd":   str(Path(__file__).parent.parent.parent),
    "note":  "Privacy-respecting meta-search for company research",
},
```

Replace all caption strings containing "Meghan's" with `f"{_name}'s"`.

**Step 7: Commit**

```bash
git add app/
git commit -m "feat: extract hard-coded personal references from all app pages via UserProfile"
```

---

## Task 5: llm.yaml URL Auto-Generation

**Files:**
- Modify: `scripts/user_profile.py` (already has `generate_llm_urls()`)
- Modify: `app/pages/2_Settings.py` (My Profile save button)
- Create: `scripts/generate_llm_config.py`

**Step 1: Write failing test**

```python
# tests/test_llm_config_generation.py
from pathlib import Path
import tempfile, yaml
from scripts.user_profile import UserProfile
from scripts.generate_llm_config import apply_service_urls

def test_urls_applied_to_llm_yaml(tmp_path):
    user_yaml = tmp_path / "user.yaml"
    user_yaml.write_text(yaml.dump({
        "name": "Test",
        "services": {
            "ollama_host": "myserver", "ollama_port": 11434, "ollama_ssl": False,
            "ollama_ssl_verify": True,
            "vllm_host": "localhost", "vllm_port": 8000, "vllm_ssl": False,
            "vllm_ssl_verify": True,
            "searxng_host": "localhost", "searxng_port": 8888,
            "searxng_ssl": False, "searxng_ssl_verify": True,
        }
    }))
    llm_yaml = tmp_path / "llm.yaml"
    llm_yaml.write_text(yaml.dump({"backends": {
        "ollama": {"base_url": "http://old:11434/v1", "type": "openai_compat"},
        "vllm":   {"base_url": "http://old:8000/v1",  "type": "openai_compat"},
    }}))

    profile = UserProfile(user_yaml)
    apply_service_urls(profile, llm_yaml)

    result = yaml.safe_load(llm_yaml.read_text())
    assert result["backends"]["ollama"]["base_url"] == "http://myserver:11434/v1"
    assert result["backends"]["vllm"]["base_url"] == "http://localhost:8000/v1"
```

**Step 2: Run to verify it fails**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_llm_config_generation.py -v
# Expected: ImportError
```

**Step 3: Implement generate_llm_config.py**

```python
# scripts/generate_llm_config.py
"""Update config/llm.yaml base_url values from the user profile's services block."""
from pathlib import Path
import yaml
from scripts.user_profile import UserProfile


def apply_service_urls(profile: UserProfile, llm_yaml_path: Path) -> None:
    """Rewrite base_url for ollama, ollama_research, and vllm backends."""
    if not llm_yaml_path.exists():
        return
    cfg = yaml.safe_load(llm_yaml_path.read_text()) or {}
    urls = profile.generate_llm_urls()
    backends = cfg.get("backends", {})
    for backend_name, url in urls.items():
        if backend_name in backends:
            backends[backend_name]["base_url"] = url
    cfg["backends"] = backends
    llm_yaml_path.write_text(yaml.dump(cfg, default_flow_style=False, allow_unicode=True))
```

**Step 4: Run test to verify it passes**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/test_llm_config_generation.py -v
# Expected: PASS
```

**Step 5: Wire into Settings My Profile save**

In `app/pages/2_Settings.py`, after the "Save My Profile" button writes `user.yaml`, add:
```python
from scripts.generate_llm_config import apply_service_urls
apply_service_urls(UserProfile(_USER_YAML), LLM_CFG)
st.success("Profile saved and service URLs updated.")
```

**Step 6: Commit**

```bash
git add scripts/generate_llm_config.py tests/test_llm_config_generation.py app/pages/2_Settings.py
git commit -m "feat: auto-generate llm.yaml base_url values from user profile services config"
```

---

## Task 6: Settings — My Profile Tab

**Files:**
- Modify: `app/pages/2_Settings.py`

**Step 1: Add My Profile tab to the tab list**

Replace the existing `st.tabs(...)` call to add the new tab first:
```python
tab_profile, tab_search, tab_llm, tab_notion, tab_services, tab_resume, tab_email, tab_skills = st.tabs(
    ["👤 My Profile", "🔎 Search", "🤖 LLM Backends", "📚 Notion",
     "🔌 Services", "📝 Resume Profile", "📧 Email", "🏷️ Skills"]
)
```

**Step 2: Implement the My Profile tab**

```python
USER_CFG = CONFIG_DIR / "user.yaml"

with tab_profile:
    from scripts.user_profile import UserProfile, _DEFAULTS
    import yaml as _yaml

    st.caption("Your identity and service configuration. Saved values drive all LLM prompts, PDF headers, and service connections.")

    _u = _yaml.safe_load(USER_CFG.read_text()) or {} if USER_CFG.exists() else {}
    _svc = {**_DEFAULTS["services"], **_u.get("services", {})}

    with st.expander("👤 Identity", expanded=True):
        c1, c2 = st.columns(2)
        u_name     = c1.text_input("Full Name",   _u.get("name", ""))
        u_email    = c1.text_input("Email",        _u.get("email", ""))
        u_phone    = c2.text_input("Phone",        _u.get("phone", ""))
        u_linkedin = c2.text_input("LinkedIn URL", _u.get("linkedin", ""))
        u_summary  = st.text_area("Career Summary (used in LLM prompts)",
                                   _u.get("career_summary", ""), height=100)

    with st.expander("🔒 Sensitive Employers (NDA)"):
        st.caption("Companies listed here appear as 'previous employer (NDA)' in research briefs.")
        nda_list = list(_u.get("nda_companies", []))
        nda_cols = st.columns(max(len(nda_list), 1))
        _to_remove = None
        for i, company in enumerate(nda_list):
            if nda_cols[i % len(nda_cols)].button(f"× {company}", key=f"rm_nda_{company}"):
                _to_remove = company
        if _to_remove:
            nda_list.remove(_to_remove)
        nc, nb = st.columns([4, 1])
        new_nda = nc.text_input("Add employer", key="new_nda", label_visibility="collapsed", placeholder="Employer name…")
        if nb.button("＋ Add", key="add_nda") and new_nda.strip():
            nda_list.append(new_nda.strip())

    with st.expander("📁 File Paths"):
        u_docs   = st.text_input("Documents directory",       _u.get("docs_dir", "~/Documents/JobSearch"))
        u_ollama = st.text_input("Ollama models directory",   _u.get("ollama_models_dir", "~/models/ollama"))
        u_vllm   = st.text_input("vLLM models directory",     _u.get("vllm_models_dir", "~/models/vllm"))

    with st.expander("⚙️ Inference Profile"):
        profiles = ["remote", "cpu", "single-gpu", "dual-gpu"]
        u_profile = st.selectbox("Active profile", profiles,
                                  index=profiles.index(_u.get("inference_profile", "remote")))

    with st.expander("🔌 Service Ports & Hosts"):
        st.caption("Advanced — change only if services run on non-default ports or remote hosts.")
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            st.markdown("**Ollama**")
            svc_ollama_host = st.text_input("Host##ollama", _svc["ollama_host"], key="svc_ollama_host")
            svc_ollama_port = st.number_input("Port##ollama", value=_svc["ollama_port"], key="svc_ollama_port")
            svc_ollama_ssl  = st.checkbox("SSL##ollama",  _svc["ollama_ssl"],  key="svc_ollama_ssl")
            svc_ollama_verify = st.checkbox("Verify cert##ollama", _svc["ollama_ssl_verify"], key="svc_ollama_verify")
        with sc2:
            st.markdown("**vLLM**")
            svc_vllm_host   = st.text_input("Host##vllm",   _svc["vllm_host"],   key="svc_vllm_host")
            svc_vllm_port   = st.number_input("Port##vllm", value=_svc["vllm_port"], key="svc_vllm_port")
            svc_vllm_ssl    = st.checkbox("SSL##vllm",  _svc["vllm_ssl"],  key="svc_vllm_ssl")
            svc_vllm_verify = st.checkbox("Verify cert##vllm", _svc["vllm_ssl_verify"], key="svc_vllm_verify")
        with sc3:
            st.markdown("**SearXNG**")
            svc_sxng_host   = st.text_input("Host##sxng",   _svc["searxng_host"],   key="svc_sxng_host")
            svc_sxng_port   = st.number_input("Port##sxng", value=_svc["searxng_port"], key="svc_sxng_port")
            svc_sxng_ssl    = st.checkbox("SSL##sxng",  _svc["searxng_ssl"],  key="svc_sxng_ssl")
            svc_sxng_verify = st.checkbox("Verify cert##sxng", _svc["searxng_ssl_verify"], key="svc_sxng_verify")

    if st.button("💾 Save Profile", type="primary", key="save_user_profile"):
        new_data = {
            "name": u_name, "email": u_email, "phone": u_phone,
            "linkedin": u_linkedin, "career_summary": u_summary,
            "nda_companies": nda_list,
            "docs_dir": u_docs, "ollama_models_dir": u_ollama, "vllm_models_dir": u_vllm,
            "inference_profile": u_profile,
            "services": {
                "streamlit_port": _svc["streamlit_port"],
                "ollama_host": svc_ollama_host, "ollama_port": int(svc_ollama_port),
                "ollama_ssl": svc_ollama_ssl, "ollama_ssl_verify": svc_ollama_verify,
                "vllm_host": svc_vllm_host, "vllm_port": int(svc_vllm_port),
                "vllm_ssl": svc_vllm_ssl, "vllm_ssl_verify": svc_vllm_verify,
                "searxng_host": svc_sxng_host, "searxng_port": int(svc_sxng_port),
                "searxng_ssl": svc_sxng_ssl, "searxng_ssl_verify": svc_sxng_verify,
            }
        }
        save_yaml(USER_CFG, new_data)
        from scripts.user_profile import UserProfile
        from scripts.generate_llm_config import apply_service_urls
        apply_service_urls(UserProfile(USER_CFG), LLM_CFG)
        st.success("Profile saved and service URLs updated.")
```

**Step 2: Commit**

```bash
git add app/pages/2_Settings.py
git commit -m "feat: add My Profile tab to Settings with full user.yaml editing + URL auto-generation"
```

---

## Task 7: First-Run Wizard

**Files:**
- Create: `app/pages/0_Setup.py`
- Modify: `app/app.py`

**Step 1: Create the wizard page**

```python
# app/pages/0_Setup.py
"""
First-run setup wizard — shown by app.py when config/user.yaml is absent.
Five steps: hardware detection → identity → NDA companies → inference/keys → Notion.
Writes config/user.yaml (and optionally config/notion.yaml) on completion.
"""
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import yaml

CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
USER_CFG   = CONFIG_DIR / "user.yaml"
NOTION_CFG = CONFIG_DIR / "notion.yaml"
LLM_CFG    = CONFIG_DIR / "llm.yaml"

PROFILES = ["remote", "cpu", "single-gpu", "dual-gpu"]

def _detect_gpus() -> list[str]:
    """Return list of GPU names via nvidia-smi, or [] if none."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            text=True, timeout=5
        )
        return [l.strip() for l in out.strip().splitlines() if l.strip()]
    except Exception:
        return []

def _suggest_profile(gpus: list[str]) -> str:
    if len(gpus) >= 2:
        return "dual-gpu"
    if len(gpus) == 1:
        return "single-gpu"
    return "remote"

# ── Wizard state ──────────────────────────────────────────────────────────────
if "wizard_step" not in st.session_state:
    st.session_state.wizard_step = 1
if "wizard_data" not in st.session_state:
    st.session_state.wizard_data = {}

step = st.session_state.wizard_step
data = st.session_state.wizard_data

st.title("👋 Welcome to Job Seeker")
st.caption("Let's get you set up. This takes about 2 minutes.")
st.progress(step / 5, text=f"Step {step} of 5")
st.divider()

# ── Step 1: Hardware detection ────────────────────────────────────────────────
if step == 1:
    st.subheader("Step 1 — Hardware Detection")
    gpus = _detect_gpus()
    suggested = _suggest_profile(gpus)

    if gpus:
        st.success(f"Found {len(gpus)} GPU(s): {', '.join(gpus)}")
    else:
        st.info("No NVIDIA GPUs detected. Remote or CPU mode recommended.")

    profile = st.selectbox(
        "Inference mode",
        PROFILES,
        index=PROFILES.index(suggested),
        help="This controls which Docker services start. You can change it later in Settings → My Profile.",
    )
    if profile in ("single-gpu", "dual-gpu") and not gpus:
        st.warning("No GPUs detected — GPU profiles require NVIDIA Container Toolkit. See the README for install instructions.")

    if st.button("Next →", type="primary"):
        data["inference_profile"] = profile
        data["gpus_detected"] = gpus
        st.session_state.wizard_step = 2
        st.rerun()

# ── Step 2: Identity ──────────────────────────────────────────────────────────
elif step == 2:
    st.subheader("Step 2 — Your Identity")
    st.caption("Used in cover letter PDFs, LLM prompts, and the app header.")
    c1, c2 = st.columns(2)
    name     = c1.text_input("Full Name *",   data.get("name", ""))
    email    = c1.text_input("Email *",        data.get("email", ""))
    phone    = c2.text_input("Phone",          data.get("phone", ""))
    linkedin = c2.text_input("LinkedIn URL",   data.get("linkedin", ""))
    summary  = st.text_area(
        "Career Summary *",
        data.get("career_summary", ""),
        height=120,
        placeholder="Experienced professional with X years in [field]. Specialise in [skills].",
        help="This paragraph is injected into cover letter and research prompts as your professional context.",
    )

    col_back, col_next = st.columns([1, 4])
    if col_back.button("← Back"):
        st.session_state.wizard_step = 1
        st.rerun()
    if col_next.button("Next →", type="primary"):
        if not name or not email or not summary:
            st.error("Name, email, and career summary are required.")
        else:
            data.update({"name": name, "email": email, "phone": phone,
                         "linkedin": linkedin, "career_summary": summary})
            st.session_state.wizard_step = 3
            st.rerun()

# ── Step 3: NDA Companies ─────────────────────────────────────────────────────
elif step == 3:
    st.subheader("Step 3 — Sensitive Employers (Optional)")
    st.caption(
        "Previous employers listed here will appear as 'previous employer (NDA)' in "
        "research briefs and talking points. Skip if not applicable."
    )
    nda_list = list(data.get("nda_companies", []))
    if nda_list:
        cols = st.columns(min(len(nda_list), 5))
        to_remove = None
        for i, c in enumerate(nda_list):
            if cols[i % 5].button(f"× {c}", key=f"rm_{c}"):
                to_remove = c
        if to_remove:
            nda_list.remove(to_remove)
            data["nda_companies"] = nda_list
            st.rerun()
    nc, nb = st.columns([4, 1])
    new_c = nc.text_input("Add employer", key="new_nda_wiz", label_visibility="collapsed", placeholder="Employer name…")
    if nb.button("＋ Add") and new_c.strip():
        nda_list.append(new_c.strip())
        data["nda_companies"] = nda_list
        st.rerun()

    col_back, col_skip, col_next = st.columns([1, 1, 3])
    if col_back.button("← Back"):
        st.session_state.wizard_step = 2
        st.rerun()
    if col_skip.button("Skip"):
        data.setdefault("nda_companies", [])
        st.session_state.wizard_step = 4
        st.rerun()
    if col_next.button("Next →", type="primary"):
        data["nda_companies"] = nda_list
        st.session_state.wizard_step = 4
        st.rerun()

# ── Step 4: Inference & API Keys ──────────────────────────────────────────────
elif step == 4:
    profile = data.get("inference_profile", "remote")
    st.subheader("Step 4 — Inference & API Keys")

    if profile == "remote":
        st.info("Remote mode: LLM calls go to external APIs. At least one key is needed.")
        anthropic_key = st.text_input("Anthropic API Key", type="password",
                                       placeholder="sk-ant-…")
        openai_url = st.text_input("OpenAI-compatible endpoint (optional)",
                                    placeholder="https://api.together.xyz/v1")
        openai_key = st.text_input("Endpoint API Key (optional)", type="password") if openai_url else ""
        data.update({"anthropic_key": anthropic_key, "openai_url": openai_url, "openai_key": openai_key})
    else:
        st.info(f"Local mode ({profile}): Ollama handles cover letters. Configure model below.")
        ollama_model = st.text_input("Cover letter model name",
                                      data.get("ollama_model", "llama3.2:3b"),
                                      help="This model will be pulled by Ollama on first start.")
        data["ollama_model"] = ollama_model

    st.divider()
    with st.expander("Advanced — Service Ports & Hosts"):
        st.caption("Change only if services run on non-default ports or remote hosts.")
        svc = data.get("services", {})
        for svc_name, default_host, default_port in [
            ("ollama", "localhost", 11434),
            ("vllm",   "localhost", 8000),
            ("searxng","localhost", 8888),
        ]:
            c1, c2, c3, c4 = st.columns([2, 1, 0.5, 0.5])
            svc[f"{svc_name}_host"]       = c1.text_input(f"{svc_name} host", svc.get(f"{svc_name}_host", default_host), key=f"adv_{svc_name}_host")
            svc[f"{svc_name}_port"]       = c2.number_input(f"port", value=svc.get(f"{svc_name}_port", default_port), key=f"adv_{svc_name}_port")
            svc[f"{svc_name}_ssl"]        = c3.checkbox("SSL",    svc.get(f"{svc_name}_ssl", False),        key=f"adv_{svc_name}_ssl")
            svc[f"{svc_name}_ssl_verify"] = c4.checkbox("Verify", svc.get(f"{svc_name}_ssl_verify", True),  key=f"adv_{svc_name}_verify")
        data["services"] = svc

    col_back, col_next = st.columns([1, 4])
    if col_back.button("← Back"):
        st.session_state.wizard_step = 3
        st.rerun()
    if col_next.button("Next →", type="primary"):
        st.session_state.wizard_step = 5
        st.rerun()

# ── Step 5: Notion (optional) ─────────────────────────────────────────────────
elif step == 5:
    st.subheader("Step 5 — Notion Sync (Optional)")
    st.caption("Syncs approved and applied jobs to a Notion database. Skip if not using Notion.")
    notion_token = st.text_input("Integration Token", type="password", placeholder="secret_…")
    notion_db    = st.text_input("Database ID", placeholder="32-character ID from Notion URL")

    if notion_token and notion_db:
        if st.button("🔌 Test connection"):
            with st.spinner("Connecting…"):
                try:
                    from notion_client import Client
                    db = Client(auth=notion_token).databases.retrieve(notion_db)
                    st.success(f"Connected: {db['title'][0]['plain_text']}")
                except Exception as e:
                    st.error(f"Connection failed: {e}")

    col_back, col_skip, col_finish = st.columns([1, 1, 3])
    if col_back.button("← Back"):
        st.session_state.wizard_step = 4
        st.rerun()

    def _finish(save_notion: bool):
        # Build user.yaml
        svc_defaults = {
            "streamlit_port": 8501,
            "ollama_host": "localhost", "ollama_port": 11434, "ollama_ssl": False, "ollama_ssl_verify": True,
            "vllm_host":   "localhost", "vllm_port":   8000,  "vllm_ssl":   False, "vllm_ssl_verify":   True,
            "searxng_host":"localhost", "searxng_port": 8888,  "searxng_ssl":False,  "searxng_ssl_verify": True,
        }
        svc_defaults.update(data.get("services", {}))
        user_data = {
            "name":             data.get("name", ""),
            "email":            data.get("email", ""),
            "phone":            data.get("phone", ""),
            "linkedin":         data.get("linkedin", ""),
            "career_summary":   data.get("career_summary", ""),
            "nda_companies":    data.get("nda_companies", []),
            "docs_dir":         "~/Documents/JobSearch",
            "ollama_models_dir":"~/models/ollama",
            "vllm_models_dir":  "~/models/vllm",
            "inference_profile":data.get("inference_profile", "remote"),
            "services":         svc_defaults,
        }
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        USER_CFG.write_text(yaml.dump(user_data, default_flow_style=False, allow_unicode=True))

        # Update llm.yaml URLs
        if LLM_CFG.exists():
            from scripts.user_profile import UserProfile
            from scripts.generate_llm_config import apply_service_urls
            apply_service_urls(UserProfile(USER_CFG), LLM_CFG)

        # Optionally write notion.yaml
        if save_notion and notion_token and notion_db:
            NOTION_CFG.write_text(yaml.dump({"token": notion_token, "database_id": notion_db}))

        st.session_state.wizard_step = 1
        st.session_state.wizard_data = {}
        st.success("Setup complete! Redirecting…")
        st.rerun()

    if col_skip.button("Skip & Finish"):
        _finish(save_notion=False)
    if col_finish.button("💾 Save & Finish", type="primary"):
        _finish(save_notion=True)
```

**Step 2: Gate navigation in app.py**

In `app/app.py`, after `init_db()`, add:
```python
from scripts.user_profile import UserProfile

_USER_YAML = Path(__file__).parent.parent / "config" / "user.yaml"

if not UserProfile.exists(_USER_YAML):
    # Show wizard only — no nav, no sidebar tasks
    setup_page = st.Page("pages/0_Setup.py", title="Setup", icon="👋")
    st.navigation({"": [setup_page]}).run()
    st.stop()
```

This must appear before the normal `st.navigation(pages)` call.

**Step 3: Commit**

```bash
git add app/pages/0_Setup.py app/app.py
git commit -m "feat: first-run setup wizard gates app until user.yaml is created"
```

---

## Task 8: Docker Compose Stack

**Files:**
- Create: `Dockerfile`
- Create: `compose.yml`
- Create: `docker/searxng/settings.yml`
- Create: `docker/ollama/entrypoint.sh`
- Create: `.dockerignore`
- Create: `.env.example`

**Step 1: Dockerfile**

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# System deps for companyScraper (beautifulsoup4, fake-useragent, lxml)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bundle companyScraper
COPY scrapers/ /app/scrapers/

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app/app.py", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--server.fileWatcherType=none"]
```

**Step 2: compose.yml**

```yaml
# compose.yml
services:

  app:
    build: .
    ports:
      - "${STREAMLIT_PORT:-8501}:8501"
    volumes:
      - ./config:/app/config
      - ./data:/app/data
      - ${DOCS_DIR:-~/Documents/JobSearch}:/docs
    environment:
      - STAGING_DB=/app/data/staging.db
    depends_on:
      searxng:
        condition: service_healthy
    restart: unless-stopped

  searxng:
    image: searxng/searxng:latest
    ports:
      - "${SEARXNG_PORT:-8888}:8080"
    volumes:
      - ./docker/searxng:/etc/searxng:ro
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:8080/"]
      interval: 10s
      timeout: 5s
      retries: 3
    restart: unless-stopped

  ollama:
    image: ollama/ollama:latest
    ports:
      - "${OLLAMA_PORT:-11434}:11434"
    volumes:
      - ${OLLAMA_MODELS_DIR:-~/models/ollama}:/root/.ollama
      - ./docker/ollama/entrypoint.sh:/entrypoint.sh
    environment:
      - OLLAMA_MODELS=/root/.ollama
    entrypoint: ["/bin/bash", "/entrypoint.sh"]
    profiles: [cpu, single-gpu, dual-gpu]
    restart: unless-stopped

  ollama-gpu:
    extends:
      service: ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ["0"]
              capabilities: [gpu]
    profiles: [single-gpu, dual-gpu]

  vllm:
    image: vllm/vllm-openai:latest
    ports:
      - "${VLLM_PORT:-8000}:8000"
    volumes:
      - ${VLLM_MODELS_DIR:-~/models/vllm}:/models
    command: >
      --model /models/${VLLM_MODEL:-Ouro-1.4B}
      --trust-remote-code
      --max-model-len 4096
      --gpu-memory-utilization 0.75
      --enforce-eager
      --max-num-seqs 8
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ["1"]
              capabilities: [gpu]
    profiles: [dual-gpu]
    restart: unless-stopped
```

**Step 3: SearXNG settings.yml**

```yaml
# docker/searxng/settings.yml
use_default_settings: true
search:
  formats:
    - html
    - json
server:
  secret_key: "change-me-in-production"
  bind_address: "0.0.0.0:8080"
```

**Step 4: Ollama entrypoint**

```bash
#!/usr/bin/env bash
# docker/ollama/entrypoint.sh
# Start Ollama server and pull a default model if none are present
ollama serve &
sleep 5
if [ -z "$(ollama list 2>/dev/null | tail -n +2)" ]; then
    MODEL="${DEFAULT_OLLAMA_MODEL:-llama3.2:3b}"
    echo "No models found — pulling $MODEL..."
    ollama pull "$MODEL"
fi
wait
```

**Step 5: .env.example**

```bash
# .env.example — copy to .env (auto-generated by wizard, or fill manually)
STREAMLIT_PORT=8501
OLLAMA_PORT=11434
VLLM_PORT=8000
SEARXNG_PORT=8888
DOCS_DIR=~/Documents/JobSearch
OLLAMA_MODELS_DIR=~/models/ollama
VLLM_MODELS_DIR=~/models/vllm
VLLM_MODEL=Ouro-1.4B
```

**Step 6: .dockerignore**

```
.git
__pycache__
*.pyc
staging.db
config/user.yaml
config/notion.yaml
config/email.yaml
config/tokens.yaml
.streamlit.pid
.streamlit.log
aihawk/
docs/
tests/
```

**Step 7: Update .gitignore**

Add to `.gitignore`:
```
.env
config/user.yaml
data/
```

**Step 8: Commit**

```bash
git add Dockerfile compose.yml docker/ .dockerignore .env.example
git commit -m "feat: add Docker Compose stack with remote/cpu/single-gpu/dual-gpu profiles"
```

---

## Task 9: Services Tab — Compose-Driven Start/Stop

**Files:**
- Modify: `app/pages/2_Settings.py`

**Step 1: Replace SERVICES list with compose-driven definitions**

```python
COMPOSE_DIR = str(Path(__file__).parent.parent.parent)
_profile_name = _profile.inference_profile if _profile else "remote"

SERVICES = [
    {
        "name": "Streamlit UI",
        "port": _profile._svc["streamlit_port"] if _profile else 8501,
        "start": ["docker", "compose", "--profile", _profile_name, "up", "-d", "app"],
        "stop":  ["docker", "compose", "stop", "app"],
        "cwd":   COMPOSE_DIR,
        "note":  "Job Seeker web interface",
    },
    {
        "name": "Ollama (local LLM)",
        "port": _profile._svc["ollama_port"] if _profile else 11434,
        "start": ["docker", "compose", "--profile", _profile_name, "up", "-d", "ollama"],
        "stop":  ["docker", "compose", "stop", "ollama"],
        "cwd":   COMPOSE_DIR,
        "note":  f"Local inference engine — profile: {_profile_name}",
        "hidden": _profile_name == "remote",
    },
    {
        "name": "vLLM Server",
        "port": _profile._svc["vllm_port"] if _profile else 8000,
        "start": ["docker", "compose", "--profile", _profile_name, "up", "-d", "vllm"],
        "stop":  ["docker", "compose", "stop", "vllm"],
        "cwd":   COMPOSE_DIR,
        "model_dir": str(_profile.vllm_models_dir) if _profile else str(Path.home() / "models" / "vllm"),
        "note":  "vLLM inference — dual-gpu profile only",
        "hidden": _profile_name != "dual-gpu",
    },
    {
        "name": "SearXNG (company scraper)",
        "port": _profile._svc["searxng_port"] if _profile else 8888,
        "start": ["docker", "compose", "up", "-d", "searxng"],
        "stop":  ["docker", "compose", "stop", "searxng"],
        "cwd":   COMPOSE_DIR,
        "note":  "Privacy-respecting meta-search for company research",
    },
]
# Filter hidden services
SERVICES = [s for s in SERVICES if not s.get("hidden")]
```

**Step 2: Update health checks to use SSL**

Replace the `_port_open()` helper:
```python
def _port_open(port: int, host: str = "127.0.0.1",
               ssl: bool = False, verify: bool = True) -> bool:
    try:
        import requests as _r
        scheme = "https" if ssl else "http"
        _r.get(f"{scheme}://{host}:{port}/", timeout=1, verify=verify)
        return True
    except Exception:
        return False
```

Update each service health check call to pass host/ssl/verify from the profile.

**Step 3: Commit**

```bash
git add app/pages/2_Settings.py
git commit -m "feat: services tab uses docker compose commands and SSL-aware health checks"
```

---

## Task 10: Fine-Tune Wizard Tab

**Files:**
- Modify: `app/pages/2_Settings.py`

**Step 1: Add fine-tune tab (GPU profiles only)**

Add `tab_finetune` to the tab list (shown only when profile is single-gpu or dual-gpu).

```python
# In the tab definition, add conditionally:
_show_finetune = _profile and _profile.inference_profile in ("single-gpu", "dual-gpu")

# Add tab:
tab_finetune = st.tabs([..., "🎯 Fine-Tune"])[last_index] if _show_finetune else None
```

**Step 2: Implement the fine-tune tab**

```python
if _show_finetune and tab_finetune:
    with tab_finetune:
        st.subheader("Fine-Tune Your Cover Letter Model")
        st.caption(
            "Upload your existing cover letters to train a personalised writing model. "
            "Requires a GPU. The base model is used until fine-tuning completes."
        )

        step = st.session_state.get("ft_step", 1)

        if step == 1:
            st.markdown("**Step 1: Upload Cover Letters**")
            uploaded = st.file_uploader(
                "Upload cover letters (PDF, DOCX, or TXT)",
                type=["pdf", "docx", "txt"],
                accept_multiple_files=True,
            )
            if uploaded and st.button("Extract Training Pairs →", type="primary"):
                # Save uploads to docs_dir/training_data/uploads/
                upload_dir = (_profile.docs_dir / "training_data" / "uploads")
                upload_dir.mkdir(parents=True, exist_ok=True)
                for f in uploaded:
                    (upload_dir / f.name).write_bytes(f.read())
                st.session_state.ft_step = 2
                st.rerun()

        elif step == 2:
            st.markdown("**Step 2: Preview Training Pairs**")
            st.info("Run `python scripts/prepare_training_data.py` to extract pairs, then return here.")
            jsonl_path = _profile.docs_dir / "training_data" / "cover_letters.jsonl"
            if jsonl_path.exists():
                import json
                pairs = [json.loads(l) for l in jsonl_path.read_text().splitlines() if l.strip()]
                st.caption(f"{len(pairs)} training pairs extracted.")
                for i, p in enumerate(pairs[:3]):
                    with st.expander(f"Pair {i+1}"):
                        st.text(p.get("input", "")[:300])
            col_back, col_next = st.columns([1, 4])
            if col_back.button("← Back"):
                st.session_state.ft_step = 1; st.rerun()
            if col_next.button("Start Training →", type="primary"):
                st.session_state.ft_step = 3; st.rerun()

        elif step == 3:
            st.markdown("**Step 3: Train**")
            epochs = st.slider("Epochs", 3, 20, 10)
            if st.button("🚀 Start Fine-Tune", type="primary"):
                from scripts.task_runner import submit_task
                from scripts.db import DEFAULT_DB
                # finetune task type — extend task_runner for this
                st.info("Fine-tune queued as a background task. Check back in 30–60 minutes.")
            if col_back := st.button("← Back"):
                st.session_state.ft_step = 2; st.rerun()
else:
    if tab_finetune is None and _profile:
        with st.expander("🎯 Fine-Tune (GPU only)"):
            st.info(
                f"Fine-tuning requires a GPU profile. "
                f"Current profile: `{_profile.inference_profile}`. "
                "Change it in My Profile to enable this tab."
            )
```

**Step 3: Commit**

```bash
git add app/pages/2_Settings.py
git commit -m "feat: add fine-tune wizard tab to Settings (GPU profiles only)"
```

---

## Task 11: Final Wiring, Tests & README

**Files:**
- Create: `README.md`
- Create: `requirements.txt` (Docker-friendly, no torch/CUDA)
- Modify: `tests/` (smoke test wizard gating)

**Step 1: Write a smoke test for wizard gating**

```python
# tests/test_app_gating.py
from pathlib import Path
from scripts.user_profile import UserProfile

def test_wizard_gating_logic(tmp_path):
    """app.py should show wizard when user.yaml is absent."""
    missing = tmp_path / "user.yaml"
    assert not UserProfile.exists(missing)

def test_wizard_gating_passes_after_setup(tmp_path):
    import yaml
    p = tmp_path / "user.yaml"
    p.write_text(yaml.dump({"name": "Test User", "services": {}}))
    assert UserProfile.exists(p)
```

**Step 2: Create requirements.txt**

```
streamlit>=1.45
pyyaml>=6.0
requests>=2.31
reportlab>=4.0
jobspy>=1.1
notion-client>=2.2
anthropic>=0.34
openai>=1.40
beautifulsoup4>=4.12
fake-useragent>=1.5
imaplib2>=3.6
```

**Step 3: Create README.md**

Document: quick start (`git clone → docker compose --profile remote up -d`), profile options, first-run wizard, and how to configure each inference mode.

**Step 4: Run full test suite**

```bash
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v
# Expected: all PASS
```

**Step 5: Final commit**

```bash
git add README.md requirements.txt tests/
git commit -m "feat: complete generalization — wizard, UserProfile, compose stack, all personal refs extracted"
```

---

## Execution Checklist

- [ ] Task 1: Bootstrap new repo
- [ ] Task 2: UserProfile class + tests
- [ ] Task 3: Extract references — scripts
- [ ] Task 4: Extract references — app pages
- [ ] Task 5: llm.yaml URL auto-generation
- [ ] Task 6: My Profile tab in Settings
- [ ] Task 7: First-run wizard
- [ ] Task 8: Docker Compose stack
- [ ] Task 9: Services tab — compose-driven
- [ ] Task 10: Fine-tune wizard tab
- [ ] Task 11: Final wiring, tests, README
