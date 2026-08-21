"""Guardrails for the RAG path: unsafe-input block, off-topic screening, grounding check."""

import re
from typing import Dict, List, Optional, Tuple

from app.config import settings

# Conservative first-pass filter — matches clear intent phrasing, not single
# trigger words, to keep false positives low.
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

# Questions about the user or the assistant itself. A web-passage corpus can
# never hold the answer, but they still score in the same similarity range as a
# real match, so they're routed away from retrieval before it runs.
_META_RE = re.compile(
    r"\b(?:who|what) (?:are|created|made|built|trained) you\b|"
    r"\byour name\b|\bwho am i\b|\bmy name\b|"
    r"मेरा नाम|आपका नाम|तुम्हारा नाम|तुम कौन हो|आप कौन ह|किसने बनाया",
    re.IGNORECASE,
)


def is_unsafe(text: str) -> bool:
    """True if the input trips a hard-block pattern; caller should decline."""
    return any(p.search(text) for p in _UNSAFE_PATTERNS)


def is_offtopic_for_kb(text: str, detected_tool: str) -> bool:
    """True = skip KB retrieval and handle conversationally (tools, greetings, tiny input)."""
    if detected_tool != "general":
        return True  # tools have their own path
    stripped = text.strip()
    if len(stripped) < 3:
        return True
    if _GREETING_RE.match(stripped):
        return True
    if _META_RE.search(stripped):
        return True
    return False


def check_grounding(
    retrieved: List[Tuple[str, float, Dict]],
    min_relevance: Optional[float] = None,
) -> bool:
    """True if the top retrieved passage clears the relevance floor."""
    if not retrieved:
        return False
    threshold = settings.RAG_MIN_RELEVANCE if min_relevance is None else min_relevance
    top_score = retrieved[0][1]
    return top_score >= threshold


# Outcomes of kb_decision().
KB_ANSWER = "answer"
KB_DECLINE = "decline"
KB_FALLTHROUGH = "fallthrough"


def kb_decision(retrieved: List[Tuple[str, float, Dict]]) -> str:
    """What to do with a knowledge-base search result.

    KB_ANSWER      top hit clears RAG_MIN_RELEVANCE — answer from the excerpts.
    KB_DECLINE     related material came back but nothing is a confident match.
                   Answering from it is the hallucination this guards against,
                   so the system says it doesn't know instead.
    KB_FALLTHROUGH the corpus simply isn't about this question. Declining here
                   would be wrong — it's a general question, not an unanswerable
                   one — so it goes to the normal conversational path.
    """
    if check_grounding(retrieved):
        return KB_ANSWER
    if retrieved and retrieved[0][1] >= settings.RAG_DECLINE_FLOOR:
        return KB_DECLINE
    return KB_FALLTHROUGH


UNSAFE_DECLINE_MESSAGE = (
    "I can't help with that request."
)

DECLINE_MESSAGE = (
    "I don't have grounded information for that in the indexed knowledge base, "
    "so I don't want to guess at an answer. Try rephrasing, or ask something "
    "closer to what's in the corpus."
)
