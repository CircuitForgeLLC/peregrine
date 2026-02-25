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
    "mission_preferences": {},
    "candidate_accessibility_focus": False,
    "candidate_lgbtq_focus": False,
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
        self.mission_preferences: dict[str, str] = data.get("mission_preferences", {})
        self.candidate_accessibility_focus: bool = bool(data.get("candidate_accessibility_focus", False))
        self.candidate_lgbtq_focus: bool = bool(data.get("candidate_lgbtq_focus", False))
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
