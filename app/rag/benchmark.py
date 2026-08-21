"""Latency harness: per-stage and end-to-end P50/P70/P100 for the RAG pipeline."""

import argparse
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

from app.agents.router import get_kb_store
from app.ai.embeddings import embed_query
from app.ai.retry import stream_generation
from app.config import settings
from app.rag import guardrails

logger = logging.getLogger(__name__)

DEFAULT_TEST_QUERIES = [
    "ताजमहल कहाँ स्थित है?",
    "मेनहाटन प्रकल्प की सफलता का तत्काल प्रभाव क्या था?",
    "भारत की राजधानी क्या है?",
    "आगरा शहर के बारे में बताइए",
    "विश्व युद्ध कब समाप्त हुआ?",
]


@dataclass
class QueryTiming:
    query: str
    embed_ms: float
    retrieve_ms: float
    generate_ms: float
    total_ms: float
    grounded: bool
    served_by: Optional[str] = None  # e.g. "Groq (primary)"; None if ungrounded


class _ProviderCapture(logging.Handler):
    """Captures which provider served a call by reading app.ai.retry log records."""

    def __init__(self):
        super().__init__()
        self.served_by: Optional[str] = None

    def emit(self, record):
        msg = record.getMessage()
        if "response served by" in msg:
            self.served_by = msg.split("response served by", 1)[1].strip()


def percentile(values: List[float], pct: float) -> float:
    """Nearest-rank percentile. pct in [0, 100]."""
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round(pct / 100 * (len(ordered) - 1))))
    return ordered[idx]


def time_one_query(query: str, model: Optional[str] = None) -> QueryTiming:
    """Time the three live per-query stages: embed, retrieve, generate."""
    store = get_kb_store()

    t0 = time.perf_counter()
    query_vec = embed_query(query)
    t1 = time.perf_counter()

    retrieved = []
    if store is not None and query_vec:
        retrieved = store.search(query_vec, k=4)
    t2 = time.perf_counter()

    grounded = guardrails.check_grounding(retrieved)
    served_by = None
    if grounded:
        context_block = "\n\n---\n\n".join(text for text, _s, _m in retrieved)
        prompt = f"Answer using only this context:\n{context_block}\n\nQuestion: {query}\nAnswer:"
        capture = _ProviderCapture()
        retry_logger = logging.getLogger("app.ai.retry")
        retry_logger.addHandler(capture)
        try:
            for _chunk in stream_generation(prompt, model=model):
                pass  # drain the stream for timing, not the text
        finally:
            retry_logger.removeHandler(capture)
        served_by = capture.served_by
    t3 = time.perf_counter()

    return QueryTiming(
        query=query,
        embed_ms=(t1 - t0) * 1000,
        retrieve_ms=(t2 - t1) * 1000,
        generate_ms=(t3 - t2) * 1000,
        total_ms=(t3 - t0) * 1000,
        grounded=grounded,
        served_by=served_by,
    )


def run_benchmark(queries: Optional[List[str]] = None, model: Optional[str] = None) -> Dict:
    queries = queries or DEFAULT_TEST_QUERIES
    timings = [time_one_query(q, model=model) for q in queries]

    totals = [t.total_ms for t in timings]
    embeds = [t.embed_ms for t in timings]
    retrieves = [t.retrieve_ms for t in timings]
    generates = [t.generate_ms for t in timings]

    is_self_test = not settings.GOOGLE_API_KEY and not settings.GROQ_API_KEY
    p70_total = percentile(totals, 70)
    served_by_counts: Dict[str, int] = {}
    for t in timings:
        if t.served_by:
            served_by_counts[t.served_by] = served_by_counts.get(t.served_by, 0) + 1

    return {
        "target_ms": 200,
        "is_self_test": is_self_test,
        "self_test_note": (
            "Neither GROQ_API_KEY nor GOOGLE_API_KEY is set — embed_query/"
            "stream_generation returned immediately without a real network "
            "call. These numbers measure the harness's own overhead, NOT "
            "production latency. Set both and re-run before reporting these "
            "numbers as real."
            if is_self_test else None
        ),
        "provider_config_note": (
            "Neither GROQ_API_KEY nor GOOGLE_API_KEY is set."
            if not settings.GROQ_API_KEY and not settings.GOOGLE_API_KEY else
            "GROQ_API_KEY is not set — every call skips straight to the "
            "Gemini fallback, so this doesn't measure Groq at all."
            if not settings.GROQ_API_KEY else
            "GOOGLE_API_KEY is not set — if Groq ever fails, there's no "
            "fallback to measure, and any Groq failure becomes a hard error "
            "instead of a graceful fallback."
            if not settings.GOOGLE_API_KEY else
            None
        ),
        "query_count": len(queries),
        "grounded_count": sum(1 for t in timings if t.grounded),
        "served_by_breakdown": served_by_counts,
        "statistical_note": (
            f"{len(queries)} test queries — enough to sanity-check where time "
            f"goes, not a statistically rigorous P50/P70/P100 in the "
            f"large-sample sense. Widen DEFAULT_TEST_QUERIES for a stronger claim."
        ),
        "stages_ms": {
            "embed_query": {"p50": percentile(embeds, 50), "p70": percentile(embeds, 70), "p100": percentile(embeds, 100)},
            "vector_retrieval": {"p50": percentile(retrieves, 50), "p70": percentile(retrieves, 70), "p100": percentile(retrieves, 100)},
            "generation": {"p50": percentile(generates, 50), "p70": percentile(generates, 70), "p100": percentile(generates, 100)},
        },
        "end_to_end_ms": {"p50": percentile(totals, 50), "p70": p70_total, "p100": percentile(totals, 100)},
        "meets_target": (not is_self_test) and p70_total <= 200,
        "per_query": [asdict(t) for t in timings],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Latency benchmark for the RAG pipeline.")
    parser.add_argument("--model", default=None)
    parser.add_argument("--out", default="data/rag_index/latency_report.json")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    report = run_benchmark(model=args.model)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {args.out}")

    if report["is_self_test"]:
        print("\n⚠️  SELF-TEST MODE — no GROQ_API_KEY/GOOGLE_API_KEY set. Not a real latency number.")
        return
    if report["provider_config_note"]:
        print(f"\n⚠️  {report['provider_config_note']}")
    if report["served_by_breakdown"]:
        print("\nProvider breakdown:", report["served_by_breakdown"])
    p70 = report["end_to_end_ms"]["p70"]
    if report["meets_target"]:
        print(f"\n✅ P70 end-to-end = {p70:.1f}ms — meets the <200ms target.")
    else:
        print(f"\n⚠️  P70 end-to-end = {p70:.1f}ms — ABOVE the <200ms target.")
        print("   See 'stages_ms' in the JSON for where the time is going.")


if __name__ == "__main__":
    main()
