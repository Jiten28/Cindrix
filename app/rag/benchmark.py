"""Latency harness: per-stage P50/P70/P100 for the RAG pipeline.

Two numbers matter and they are reported separately, because conflating them
would misrepresent the result:

  retrieval_ms  embed the query + search the index. This is the RAG pipeline
                proper and the number the <200ms target applies to.
  end_to_end_ms retrieval plus a fully generated answer. Bounded below by LLM
                inference (~1s), so no index can bring it under 200ms.

Time-to-first-token is also recorded, since the UI streams — that's what a user
actually waits for before seeing text.
"""

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

from app.agents.router import get_kb_store
from app.ai import embeddings
from app.ai.embeddings import embed_query
from app.ai.retry import stream_generation
from app.config import settings
from app.rag import guardrails

logger = logging.getLogger(__name__)

# Queries with no answer in the corpus. They must return 0 grounded hits —
# that's the guardrail working, and it's part of what this measures.
OUT_OF_CORPUS_QUERIES = [
    "भारत की राजधानी क्या है?",
    "पिज़्ज़ा कैसे बनाते हैं?",
]

# How many in-corpus queries to draw from the index when none are given.
_DEFAULT_CORPUS_QUERIES = 8


@dataclass
class QueryTiming:
    query: str
    in_corpus: bool
    embed_ms: float
    embed_cached_ms: float  # same query re-embedded; the query-cache hit path
    retrieve_ms: float
    retrieval_ms: float  # embed + retrieve — the stage the target applies to
    ttft_ms: Optional[float]  # time to first generated token; None if ungrounded
    generate_ms: float
    total_ms: float
    grounded: bool
    top_score: Optional[float] = None
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


def corpus_queries(limit: int = _DEFAULT_CORPUS_QUERIES) -> List[str]:
    """Distinct source queries of the chunks actually in the index.

    Benchmarking with queries that aren't in the corpus measures the decline
    path only: retrieval finds nothing, generation never runs, and the
    end-to-end number silently excludes the most expensive stage.
    """
    store = get_kb_store()
    if store is None:
        return []
    seen: List[str] = []
    for meta in store.metadatas:
        q = (meta.get("query") or "").strip()
        if q and q not in seen:
            seen.append(q)
            if len(seen) >= limit:
                break
    return seen


def time_one_query(query: str, model: Optional[str] = None, in_corpus: bool = True) -> QueryTiming:
    """Time the live per-query stages: embed (cold and cached), retrieve, generate."""
    store = get_kb_store()

    # Cold embed: drop any cached vector for this query so the first timing is
    # a real network round trip, not a dictionary lookup.
    embeddings._query_cache.pop(query.strip(), None)

    t0 = time.perf_counter()
    query_vec = embed_query(query)
    t1 = time.perf_counter()
    embed_query(query)  # second call — served from the query cache
    t2 = time.perf_counter()

    retrieved = []
    if store is not None and query_vec:
        retrieved = store.search(query_vec, k=4)
    t3 = time.perf_counter()

    grounded = guardrails.check_grounding(retrieved)
    top_score = retrieved[0][1] if retrieved else None
    served_by = None
    ttft_ms = None
    if grounded:
        context_block = "\n\n---\n\n".join(text for text, _s, _m in retrieved)
        prompt = f"Answer using only this context:\n{context_block}\n\nQuestion: {query}\nAnswer:"
        capture = _ProviderCapture()
        retry_logger = logging.getLogger("app.ai.retry")
        retry_logger.addHandler(capture)
        try:
            for chunk in stream_generation(prompt, model=model):
                if ttft_ms is None and chunk:
                    ttft_ms = (time.perf_counter() - t3) * 1000
        finally:
            retry_logger.removeHandler(capture)
        served_by = capture.served_by
    t4 = time.perf_counter()

    return QueryTiming(
        query=query,
        in_corpus=in_corpus,
        embed_ms=(t1 - t0) * 1000,
        embed_cached_ms=(t2 - t1) * 1000,
        retrieve_ms=(t3 - t2) * 1000,
        retrieval_ms=((t1 - t0) + (t3 - t2)) * 1000,
        ttft_ms=ttft_ms,
        generate_ms=(t4 - t3) * 1000,
        total_ms=((t1 - t0) + (t3 - t2) + (t4 - t3)) * 1000,
        grounded=grounded,
        top_score=top_score,
        served_by=served_by,
    )


def run_benchmark(queries: Optional[List[str]] = None, model: Optional[str] = None) -> Dict:
    store = get_kb_store()
    index_size = len(store) if store is not None else 0

    if queries is not None:
        timings = [time_one_query(q, model=model, in_corpus=True) for q in queries]
    else:
        in_corpus = corpus_queries()
        timings = [time_one_query(q, model=model, in_corpus=True) for q in in_corpus]
        timings += [time_one_query(q, model=model, in_corpus=False) for q in OUT_OF_CORPUS_QUERIES]

    retrievals = [t.retrieval_ms for t in timings]
    embeds = [t.embed_ms for t in timings]
    embeds_cached = [t.embed_cached_ms for t in timings]
    retrieves = [t.retrieve_ms for t in timings]

    grounded = [t for t in timings if t.grounded]
    generates = [t.generate_ms for t in grounded]
    ttfts = [t.ttft_ms for t in grounded if t.ttft_ms is not None]
    totals = [t.total_ms for t in grounded]

    is_self_test = not settings.GOOGLE_API_KEY and not settings.GROQ_API_KEY
    p70_retrieval = percentile(retrievals, 70)
    served_by_counts: Dict[str, int] = {}
    for t in timings:
        if t.served_by:
            served_by_counts[t.served_by] = served_by_counts.get(t.served_by, 0) + 1

    expected_grounded = sum(1 for t in timings if t.in_corpus)
    return {
        "retrieval_target_ms": 200,
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
        "index_chunks": index_size,
        "query_count": len(timings),
        "grounded_count": len(grounded),
        "expected_grounded_count": expected_grounded,
        "grounding_note": (
            f"{len(grounded)}/{expected_grounded} in-corpus queries retrieved a "
            f"chunk above RAG_MIN_RELEVANCE={settings.RAG_MIN_RELEVANCE}; the "
            f"{len(timings) - expected_grounded} out-of-corpus queries are "
            f"expected to ground 0 times (the guardrail declining, not a miss)."
        ),
        "served_by_breakdown": served_by_counts,
        "statistical_note": (
            f"{len(timings)} test queries — enough to sanity-check where time "
            f"goes, not a statistically rigorous P50/P70/P100 in the "
            f"large-sample sense."
        ),
        "stages_ms": {
            "embed_query": {"p50": percentile(embeds, 50), "p70": percentile(embeds, 70), "p100": percentile(embeds, 100)},
            "embed_query_cached": {"p50": percentile(embeds_cached, 50), "p70": percentile(embeds_cached, 70), "p100": percentile(embeds_cached, 100)},
            "vector_retrieval": {"p50": percentile(retrieves, 50), "p70": percentile(retrieves, 70), "p100": percentile(retrieves, 100)},
            "generation": {"p50": percentile(generates, 50), "p70": percentile(generates, 70), "p100": percentile(generates, 100)},
            "time_to_first_token": {"p50": percentile(ttfts, 50), "p70": percentile(ttfts, 70), "p100": percentile(ttfts, 100)},
        },
        "retrieval_ms": {"p50": percentile(retrievals, 50), "p70": p70_retrieval, "p100": percentile(retrievals, 100)},
        "end_to_end_ms": {"p50": percentile(totals, 50), "p70": percentile(totals, 70), "p100": percentile(totals, 100)},
        "retrieval_meets_target": (not is_self_test) and p70_retrieval <= 200,
        "end_to_end_note": (
            "end_to_end_ms covers a complete generated answer and is dominated "
            "by LLM inference, so it is not compared against the 200ms "
            "retrieval target. time_to_first_token is what the streaming UI "
            "actually shows the user."
        ),
        "per_query": [asdict(t) for t in timings],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Latency benchmark for the RAG pipeline.")
    parser.add_argument("--model", default=None)
    parser.add_argument("--out", default=f"{settings.RAG_INDEX_DIR}/latency_report.json")
    args = parser.parse_args()

    # The report echoes Devanagari test queries, which a default Windows console
    # (cp1252) can't encode — printing would raise UnicodeEncodeError and lose
    # the run. Force UTF-8 on stdout, replacing anything the terminal font
    # still can't show.
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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
    if report["index_chunks"] == 0:
        print("\n⚠️  No knowledge-base index loaded — run `python -m app.rag.ingest` first.")
        return
    if report["served_by_breakdown"]:
        print("\nProvider breakdown:", report["served_by_breakdown"])
    print(f"\nGrounding: {report['grounding_note']}")

    p70_retrieval = report["retrieval_ms"]["p70"]
    if report["retrieval_meets_target"]:
        print(f"\n✅ P70 retrieval (embed + search) = {p70_retrieval:.1f}ms — meets the <200ms target.")
    else:
        print(f"\n⚠️  P70 retrieval (embed + search) = {p70_retrieval:.1f}ms — ABOVE the <200ms target.")
        print("   See 'stages_ms' in the JSON for where the time is going.")
    print(f"   P70 time-to-first-token = {report['stages_ms']['time_to_first_token']['p70']:.0f}ms")
    print(f"   P70 full answer         = {report['end_to_end_ms']['p70']:.0f}ms (generation-bound)")


if __name__ == "__main__":
    main()
