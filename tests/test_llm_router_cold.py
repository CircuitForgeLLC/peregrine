"""complete_cold asks for a low temperature only when the router can take it."""
from scripts.llm_router import complete_cold


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
