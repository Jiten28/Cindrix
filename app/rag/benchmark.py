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
# that's the guardrail working, and it's part of what this measures. They double
# as the negative class the RAG_MIN_RELEVANCE band is calibrated against, so the
# set is deliberately varied: general knowledge, how-to, current-value lookups,
# entertainment, sport, and programming, in Hindi and English shapes. A single
# out-of-corpus query can't tell you where the non-match ceiling is.
OUT_OF_CORPUS_QUERIES = [
    "भारत की राजधानी क्या है?",
    "पिज़्ज़ा कैसे बनाते हैं?",
    "क्रिकेट में सचिन तेंदुलकर के कुल रन कितने हैं?",
    "बॉलीवुड की सबसे महंगी फिल्म कौन सी है?",
    "मेरे लैपटॉप की बैटरी जल्दी खत्म हो जाती है, क्या करूं?",
    "क्वांटम कंप्यूटिंग क्या है?",
    "दिल्ली से मुंबई की ट्रेन का किराया कितना है?",
    "आज का सोने का भाव क्या है?",
    "ताजमहल किसने बनवाया था?",
    "पाइथन में लिस्ट को कैसे सॉर्ट करें?",
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


def run_benchmark(
    queries: Optional[List[str]] = None,
    model: Optional[str] = None,
    corpus_query_count: int = _DEFAULT_CORPUS_QUERIES,
) -> Dict:
    store = get_kb_store()
    index_size = len(store) if store is not None else 0

    if queries is not None:
        timings = [time_one_query(q, model=model, in_corpus=True) for q in queries]
    else:
        in_corpus = corpus_queries(corpus_query_count)
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

    # Keys can be set and the embedding call still fail — an exhausted daily
    # quota returns 429 and embed_query fails fast to an empty vector. Against a
    # loaded index a real search always returns k hits, so a missing top_score
    # means the query never got embedded. Every stage after it then measures a
    # no-op, and retrieval_ms looks *better* than a working run because there was
    # no network round trip in it. Counting the failures is what stops a dead run
    # from reporting a passing latency.
    embed_failures = sum(1 for t in timings if t.top_score is None)
    all_embeds_failed = bool(timings) and embed_failures == len(timings)

    # Separation between the two classes — the number the relevance band is
    # calibrated on. A false positive here (an out-of-corpus query scoring above
    # the threshold) would mean the guardrail can be talked into grounding an
    # answer in unrelated passages, which is the failure mode it exists to stop.
    in_scores = [t.top_score for t in timings if t.in_corpus and t.top_score is not None]
    out_scores = [t.top_score for t in timings if not t.in_corpus and t.top_score is not None]
    false_positives = [s for s in out_scores if s >= settings.RAG_MIN_RELEVANCE]

    # A provider fallback costs the primary's whole retry budget before the
    # secondary even starts, so one fallback dominates the generation tail. Say so
    # rather than leaving a 30s P100 to look like normal inference latency.
    slowest_grounded = max(grounded, key=lambda t: t.generate_ms) if grounded else None
    tail_note = None
    if slowest_grounded and slowest_grounded.served_by and "fallback" in slowest_grounded.served_by:
        tail_note = (
            f"The generation/end-to-end P100 is one query that fell back to "
            f"{slowest_grounded.served_by}: the primary's retry budget elapsed "
            f"before the secondary was called. That's the harness recovering "
            f"rather than a representative inference time — see per_query."
        )

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
        "embed_failure_count": embed_failures,
        "embed_failure_note": (
            f"{embed_failures} of {len(timings)} queries could not be embedded — "
            f"embed_query returned an empty vector, so retrieval and generation "
            f"never ran for them. The usual cause is the Gemini free-tier daily "
            f"embedding quota (1000 requests/day/model); check the log for a 429. "
            f"Latency figures from those queries measure a failed call, not the "
            f"pipeline, and any that made it into the percentiles bias them low."
            if embed_failures else None
        ),
        "grounded_count": len(grounded),
        "expected_grounded_count": expected_grounded,
        "grounding_note": (
            f"{len(grounded)}/{expected_grounded} in-corpus queries retrieved a "
            f"chunk above RAG_MIN_RELEVANCE={settings.RAG_MIN_RELEVANCE}; the "
            f"{len(timings) - expected_grounded} out-of-corpus queries are "
            f"expected to ground 0 times (the guardrail declining, not a miss)."
        ),
        "served_by_breakdown": served_by_counts,
        "generation_tail_note": tail_note,
        "calibration": {
            "min_relevance": settings.RAG_MIN_RELEVANCE,
            "decline_floor": settings.RAG_DECLINE_FLOOR,
            "in_corpus_score_range": [min(in_scores), max(in_scores)] if in_scores else None,
            "out_of_corpus_score_range": [min(out_scores), max(out_scores)] if out_scores else None,
            "highest_out_of_corpus_score": max(out_scores) if out_scores else None,
            "margin_above_highest_non_match": (
                round(settings.RAG_MIN_RELEVANCE - max(out_scores), 4) if out_scores else None
            ),
            "false_positives": len(false_positives),
            "note": (
                f"{len(false_positives)} of {len(out_scores)} out-of-corpus queries "
                f"scored at or above RAG_MIN_RELEVANCE={settings.RAG_MIN_RELEVANCE}. "
                f"Zero is the requirement: an out-of-corpus query must never reach "
                f"the grounded-answer path."
            ),
        },
        "statistical_note": (
            f"Nearest-rank percentiles over {len(timings)} distinct test queries "
            f"({expected_grounded} drawn from the index, "
            f"{len(timings) - expected_grounded} deliberately out-of-corpus), one "
            f"cold run each — not a single best-case run, and not a load test "
            f"either. Enough to show where the time goes and that the shape holds "
            f"across queries; the tail (P100) is a single observation by "
            f"definition."
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
        "retrieval_meets_target": (
            (not is_self_test) and (not all_embeds_failed) and p70_retrieval <= 200
        ),
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
    parser.add_argument(
        "--queries",
        type=int,
        default=_DEFAULT_CORPUS_QUERIES,
        help=(
            "How many in-corpus queries to draw from the index (default "
            f"{_DEFAULT_CORPUS_QUERIES}). The two out-of-corpus decline-path "
            "queries are always added on top. Raise this for percentiles over a "
            "wider sample; each query costs one embedding call and, if it "
            "grounds, one generation."
        ),
    )
    parser.add_argument("--out", default=f"{settings.RAG_INDEX_DIR}/latency_report.json")
    args = parser.parse_args()

    # The report echoes Devanagari test queries, which a default Windows console
    # (cp1252) can't encode — printing would raise UnicodeEncodeError and lose
    # the run. Force UTF-8 on stdout, replacing anything the terminal font
    # still can't show.
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    report = run_benchmark(model=args.model, corpus_query_count=args.queries)
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
    if report["embed_failure_note"]:
        print(f"\n⚠️  {report['embed_failure_note']}")
        if report["embed_failure_count"] == report["query_count"]:
            print(
                "\n❌ EVERY query failed to embed, so this run measured nothing. "
                "The numbers below are the cost of a failed API call, not of the "
                "pipeline — do not report them. Re-run once the quota resets."
            )
            return
    if report["served_by_breakdown"]:
        print("\nProvider breakdown:", report["served_by_breakdown"])
    if report["generation_tail_note"]:
        print(f"\nNote: {report['generation_tail_note']}")
    print(f"\nGrounding: {report['grounding_note']}")

    cal = report["calibration"]
    if cal["out_of_corpus_score_range"]:
        lo, hi = cal["out_of_corpus_score_range"]
        in_lo, in_hi = cal["in_corpus_score_range"]
        print(
            f"\nCalibration: in-corpus top scores {in_lo:.3f}-{in_hi:.3f}, "
            f"out-of-corpus {lo:.3f}-{hi:.3f}."
        )
        if cal["false_positives"]:
            print(
                f"   ❌ {cal['false_positives']} out-of-corpus query/queries scored "
                f">= RAG_MIN_RELEVANCE={cal['min_relevance']} — raise the threshold."
            )
        else:
            print(
                f"   ✅ no out-of-corpus query reached RAG_MIN_RELEVANCE="
                f"{cal['min_relevance']} ({cal['margin_above_highest_non_match']} margin "
                f"above the highest non-match)."
            )

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
