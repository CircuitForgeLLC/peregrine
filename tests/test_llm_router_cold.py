"""complete_cold asks for a low temperature only when the router can take it."""
from unittest.mock import patch

from scripts.experience_facts import ExperienceFact
from scripts.llm_router import complete_cold
from scripts.resume_optimizer import frame_skill_gaps, rewrite_for_ats


class _WithTemp:
    def __init__(self):
        self.seen = None

    def complete(self, prompt, system=None, temperature=None):
        self.seen = {"prompt": prompt, "temperature": temperature}
        return "warm-text"


class _WithoutTemp:
    def __init__(self):
        self.prompts = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        return "plain-text"


def test_passes_temperature_when_the_router_accepts_it():
    router = _WithTemp()
    complete_cold(router, "hi", temperature=0.5)
    assert router.seen == {"prompt": "hi", "temperature": 0.5}


def test_omits_it_when_the_router_does_not():
    router = _WithoutTemp()
    complete_cold(router, "hi")
    assert router.prompts == ["hi"]


def test_returns_the_routers_text_either_way():
    assert complete_cold(_WithTemp(), "x") == "warm-text"
    assert complete_cold(_WithoutTemp(), "x") == "plain-text"


def test_default_temperature_is_0_2():
    router = _WithTemp()
    complete_cold(router, "x")
    assert router.seen["temperature"] == 0.2


# Call sites: the real functions must ask the router for 0.2.


class _RecordingRouter(_WithTemp):
    """Stands in for the LLMRouter class the optimizer constructs."""

    last = None

    def __init__(self, *args, **kwargs):
        super().__init__()
        type(self).last = self


def _usable_fact(term):
    return ExperienceFact(
        id=1, kind="experience", requirement=term, text=f"I used {term} daily.",
        visibility="document", status="active", source="user",
        origin_job_id=None, created_at="2026-01-01", updated_at="2026-01-01",
    )


def test_rewrite_for_ats_asks_the_router_for_a_low_temperature():
    _RecordingRouter.last = None
    resume = {"career_summary": "Engineer who ships software.", "skills": [], "experience": []}
    gaps = [{"term": "kubernetes", "section": "summary"}]
    with patch("scripts.llm_router.LLMRouter", _RecordingRouter):
        rewrite_for_ats(
            resume, gaps, {"title": "SRE", "company": "Acme", "description": ""},
            facts={"kubernetes": _usable_fact("kubernetes")},
        )
    assert _RecordingRouter.last.seen["temperature"] == 0.2


def test_frame_skill_gaps_asks_the_router_for_a_low_temperature():
    _RecordingRouter.last = None
    struct = {"experience": [{"title": "Dev", "company": "X", "start_date": "2020",
                              "end_date": "2022", "bullets": ["Built services."]}]}
    framings = [{"skill": "kubernetes", "mode": "adjacent", "context": "I ran Docker Swarm."}]
    with patch("scripts.llm_router.LLMRouter", _RecordingRouter):
        frame_skill_gaps(struct, framings, {"title": "SRE", "company": "Acme"})
    assert _RecordingRouter.last.seen["temperature"] == 0.2
