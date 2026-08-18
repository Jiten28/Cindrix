"""Guardrails layer in front of the RAG path in app/agents/router.py.

Three checks:
1. is_unsafe(text) — fast heuristic block on clearly unsafe/inappropriate
   input, before it reaches the vector store or an LLM call at all.
2. is_offtopic_for_kb(text, detected_tool) — decides whether a query is
   worth attempting knowledge-base retrieval for at all. Tool-intent
   queries, greetings, and other obvious chit-chat skip straight to plain
   conversational handling (unchanged from before this priority) rather
   than being forced through a "not grounded, declining" response for
   something that was never meant to be a factual lookup.
3. check_grounding(retrieved, min_relevance) — for queries that DO attempt
   knowledge-base retrieval, whether the top result actually clears a
   relevance floor. Below it, the caller should visibly decline rather
   than let Gemini answer from weak/irrelevant context — see
   DECLINE_MESSAGE below and how app/agents/router.py uses it.

Deliberately heuristic/keyword-based, not a second LLM call for every
guardrail check — Priority 3's <200ms end-to-end latency target doesn't
leave room for an extra full model round-trip just to gate another one.
This is a real, disclosed scope tradeoff, not a hidden shortcut — a
stronger LLM-based or third-party moderation check would be a reasonable
upgrade later (see Architecture.md's Guardrails section) but is a new
external dependency/cost decision, which Rules.md says to flag rather
than add unprompted.
"""

import re
from typing import Dict, List, Optional, Tuple

from app.config import settings

# Deliberately small and conservative — a first-pass heuristic filter, not
# a moderation system. Matches on clear intent phrasing, not single
# trigger words, to keep false positives low (e.g. a genuine safety
# question like "how do bomb disposal robots work" shouldn't trip this).
_UNSAFE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bhow (?:do|can|would) i (?:make|build|synthesi[sz]e) (?:a |an )?(?:bomb|explosive|pipe bomb|nerve agent)\b",
        r"\bhow to (?:hack|break into) .{0,40}(?:without permission|illegally)\b",
        r"\b(?:kill|hurt) (?:myself|yourself)\b",
        r"\bchild (?:sexual|porn|abuse material)\b",
    ]
]

_GREETING_RE = re.compile(
    r"^\s*(hi|hello|hey|namaste|नमस्ते|thanks?|thank you|ok|okay|bye|good\s?(morning|evening|night)|"
    r"how are you|what'?s up)\b",
    re.IGNORECASE,
)


def is_unsafe(text: str) -> bool:
    """Heuristic pre-check, run before the query ever reaches retrieval or
    generation. True means the caller should decline outright."""
    return any(p.search(text) for p in _UNSAFE_PATTERNS)


def is_offtopic_for_kb(text: str, detected_tool: str) -> bool:
    """Whether it's worth attempting knowledge-base retrieval for this
    query at all. True = skip the KB, handle conversationally as before
    this priority existed (tool-intent messages, greetings, empty/very
    short input)."""
    if detected_tool != "general":
        return True  # weather/crypto/search/vision/document_rag already have their own path
    stripped = text.strip()
    if len(stripped) < 3:
        return True
    if _GREETING_RE.match(stripped):
        return True
    return False


def check_grounding(
    retrieved: List[Tuple[str, float, Dict]],
    min_relevance: Optional[float] = None,
) -> bool:
    """True if the top retrieved passage clears the relevance floor —
    i.e. there's enough support in the corpus to answer this from
    retrieved context. False means the caller should decline rather than
    let Gemini improvise from weak/irrelevant matches."""
    if not retrieved:
        return False
    threshold = settings.RAG_MIN_RELEVANCE if min_relevance is None else min_relevance
    top_score = retrieved[0][1]
    return top_score >= threshold


UNSAFE_DECLINE_MESSAGE = (
    "I can't help with that request."
)

DECLINE_MESSAGE = (
    "I don't have grounded information for that in the indexed knowledge base, "
    "so I don't want to guess at an answer. Try rephrasing, or ask something "
    "closer to what's in the corpus."
)
