"""Latency harness — Priority 3.

Instruments the RAG pipeline stage by stage per query (embed query ->
vector retrieval -> generation) across a set of test queries, and reports
P50/P70/P100 for each stage plus end-to-end. Target from the hackathon
brief: under 200ms end-to-end.

Scope note, disclosed rather than hidden: chunking + embedding the corpus
(app/rag/ingest.py) is a one-time INGEST-time cost, not something a live
query pays — a real user's question doesn't wait for the whole dataset to
re-chunk. This harness reports ingest cost once, separately, and measures
what an actual deployed query actually pays: embed the query, search the
index, generate the answer. Re-chunking the corpus per query would be
straightforwardly bad engineering, not a stricter reading of "instrument
the full pipeline" — see docs/Architecture.md's Latency Harness section.

Honesty note this module enforces in its own output: five to ten test
queries produce a real P50/P70 but not a statistically rigorous one — the
report says so rather than presenting these numbers with false precision.
And when GOOGLE_API_KEY/network aren't available (e.g. this was built in
a sandboxed session with neither), running this produces a report clearly
marked as a self-test of the harness mechanics, not a production number —
see run_benchmark()'s `is_self_test` field.
"""

import argparse
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

from app.agents.router import get_kb_store
from app.ai.embeddings import embed_query
from app.ai.gemini_client import stream_gemini
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


def percentile(values: List[float], pct: float) -> float:
    """Nearest-rank percentile. pct in [0, 100]."""
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round(pct / 100 * (len(ordered) - 1))))
    return ordered[idx]


def time_one_query(query: str, model: Optional[str] = None) -> QueryTiming:
    """Times the three live, per-query stages. Does NOT include ingest-time
    chunking/embedding — see module docstring."""
    store = get_kb_store()

    t0 = time.perf_counter()
    query_vec = embed_query(query)
    t1 = time.perf_counter()

    retrieved = []
    if store is not None and query_vec:
        retrieved = store.search(query_vec, k=4)
    t2 = time.perf_counter()

    grounded = guardrails.check_grounding(retrieved)
    if grounded:
        context_block = "\n\n---\n\n".join(text for text, _s, _m in retrieved)
        prompt = f"Answer using only this context:\n{context_block}\n\nQuestion: {query}\nAnswer:"
        for _chunk in stream_gemini(prompt, model=model):
            pass  # timing generation, not collecting the text here
    t3 = time.perf_counter()

    return QueryTiming(
        query=query,
        embed_ms=(t1 - t0) * 1000,
        retrieve_ms=(t2 - t1) * 1000,
        generate_ms=(t3 - t2) * 1000,
        total_ms=(t3 - t0) * 1000,
        grounded=grounded,
    )


def run_benchmark(queries: Optional[List[str]] = None, model: Optional[str] = None) -> Dict:
    queries = queries or DEFAULT_TEST_QUERIES
    timings = [time_one_query(q, model=model) for q in queries]

    totals = [t.total_ms for t in timings]
    embeds = [t.embed_ms for t in timings]
    retrieves = [t.retrieve_ms for t in timings]
    generates = [t.generate_ms for t in timings]

    is_self_test = not settings.GOOGLE_API_KEY
    p70_total = percentile(totals, 70)

    return {
        "target_ms": 200,
        "is_self_test": is_self_test,
        "self_test_note": (
            "GOOGLE_API_KEY is not set — embed_query/stream_gemini returned "
            "immediately without a real network call. These numbers measure "
            "the harness's own overhead, NOT production latency. Set "
            "GOOGLE_API_KEY and re-run before reporting these numbers as real."
            if is_self_test else None
        ),
        "query_count": len(queries),
        "grounded_count": sum(1 for t in timings if t.grounded),
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
    parser = argparse.ArgumentParser(description="Latency benchmark for the RAG pipeline (Priority 3).")
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
        print("\n⚠️  SELF-TEST MODE — no GOOGLE_API_KEY set. Not a real latency number.")
        return
    p70 = report["end_to_end_ms"]["p70"]
    if report["meets_target"]:
        print(f"\n✅ P70 end-to-end = {p70:.1f}ms — meets the <200ms target.")
    else:
        print(f"\n⚠️  P70 end-to-end = {p70:.1f}ms — ABOVE the <200ms target.")
        print("   See 'stages_ms' in the JSON for where the time is going.")


if __name__ == "__main__":
    main()
