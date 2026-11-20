"""Deterministic checks on what a rewritten resume section claims.

Pure functions, no model calls. A rewrite is compared against the text it came from so that terms
the user has not backed (or words that are simply new) can be caught without trusting an LLM.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

_WORD_RE = re.compile(r"[A-Za-z]+")

# Common function words plus resume filler that is not a claim about the user's experience.
_STOPWORDS = frozenset(
    """
    about above across after again against also among and another any are around because been before
    being below between both but can could did does doing down during each either else even ever every
    for from further had has have having her here hers him his how however into its itself just like
    made make many may more most much must myself near nor not now off often once only onto other our
    ours out over own per same shall she should since some such than that the their theirs them then
    there these they this those through thus too under until upon very was were what when where whether
    which while who whom whose why will with within without would yet you your yours
    achieved achieving across activities additionally assisted assisting collaborated collaborating
    contributed contributing delivered delivering demonstrated effective effectively efficient
    efficiently ensured ensuring experience experienced helped helping improved improving including
    key managed managing major oversaw overseeing participated participating performed performing
    provided providing responsible responsibilities results resulted role roles successful
    successfully supported supporting team teams used using utilized utilizing worked working
    """.split()  # noqa: SIM905 (a word list reads better as prose than as a quoted literal)
)


def _term_pattern(term: str) -> re.Pattern[str]:
    """Whole-word, case-insensitive matcher allowing a plural (cat, cats), symbols literal."""
    return re.compile(
        r"(?<![a-z0-9])" + re.escape(term.strip().lower()) + r"(?:s|es)?(?![a-z0-9])"
    )


def find_unbacked_terms(
    original_text: str, rewritten_text: str, unbacked_terms: Sequence[str]
) -> list[str]:
    """Terms present in the rewrite but absent from the original, each once, in the order given."""
    original = original_text.lower()
    rewritten = rewritten_text.lower()
    found: list[str] = []
    for term in unbacked_terms:
        if not term.strip() or term in found:
            continue
        pattern = _term_pattern(term)
        if pattern.search(rewritten) and not pattern.search(original):
            found.append(term)
    return found


def _stem(word: str) -> str:
    return word.removesuffix("s")


def _content_words(text: str) -> list[str]:
    words = (w.lower() for w in _WORD_RE.findall(text))
    return [w for w in words if len(w) >= 4 and w not in _STOPWORDS]


def find_novel_words(
    original_text: str, rewritten_text: str, allowed_texts: Sequence[str] = ()
) -> list[str]:
    """Content words in the rewrite that appear in neither the original nor any allowed text."""
    known = {_stem(w) for w in _WORD_RE.findall(original_text.lower())}
    for text in allowed_texts:
        known.update(_stem(w) for w in _WORD_RE.findall(text.lower()))
    novel: list[str] = []
    seen: set[str] = set()
    for word in _content_words(rewritten_text):
        stem = _stem(word)
        if stem in known or stem in seen:
            continue
        seen.add(stem)
        novel.append(word)
    return novel
