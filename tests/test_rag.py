"""Automated tests for the hackathon-track RAG additions (Priorities 2/4/5
— chunking, vector store, guardrails, retry). Runs for real in CI (see
.github/workflows/ci.yml — installs from requirements.txt, so faiss-cpu/
datasets/numpy are genuinely present there, unlike the sandboxed session
this was originally built and manually verified in — see docs/Memory.md
and docs/Testing.md section 17 for that distinction).

Doesn't require GOOGLE_API_KEY for anything except the embeddings-backed
top_k_chunks test, which mocks embed_query rather than calling the real
API — consistent with how the rest of this project's test suite avoids
needing a real key (see test_health.py).
"""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.rag.chunking import fixed_size_chunks, metadata_aware_chunks, semantic_chunks
from app.rag.dataset import _shard_path, resolve_target_lang_code
from app.rag.guardrails import check_grounding, is_offtopic_for_kb, is_unsafe
from app.rag.vector_store import VectorStore

# The dataset card's own documented example row — same shape used
# throughout app/rag/dataset.py's fixture, kept in sync deliberately.
_SAMPLE_ROW = {
    "query": "मेनहाटन प्रकल्प की सफलता का तत्काल प्रभाव क्या था?",
    "query_id": 1185869,
    "query_type": "DESCRIPTION",
    "target_lang": "hin_Deva",
    "passages": {
        "is_selected": [1, 0, 0],
        "English_passages": ["A", "B", "C"],
        "Translated_passages": ["वैज्ञानिक मस्तिष्कों के बीच संचार...", "एक और अनुच्छेद।", "तीसरा।"],
    },
}


# --- chunking -----------------------------------------------------------

def test_fixed_size_chunks_respects_size_and_overlap():
    text = "A" * 1000
    chunks = fixed_size_chunks(text, chunk_size=200, overlap=30)
    assert len(chunks) > 1
    assert all(len(c.text) <= 200 for c in chunks)


def test_fixed_size_chunks_rejects_overlap_ge_chunk_size():
    try:
        fixed_size_chunks("some text", chunk_size=100, overlap=100)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_semantic_chunks_never_splits_a_sentence():
    prose = (
        "Sentence one is short. Sentence two is a bit longer than the first one. "
        "Sentence three continues on with even more words in it than before. "
        "Sentence four wraps up this short passage nicely at the very end."
    )
    chunks = semantic_chunks(prose, target_size=80, min_size=20)
    assert len(chunks) >= 2
    rejoined = " ".join(c.text for c in chunks)
    # every sentence-ending period in the original appears in some chunk's
    # text, not orphaned mid-chunk with its second half elsewhere
    for sentence in prose.split(". "):
        stripped = sentence.strip().rstrip(".")
        assert any(stripped in c.text for c in chunks), f"sentence fragment lost: {stripped!r}"


def test_metadata_aware_chunks_preserves_is_selected_link():
    chunks = metadata_aware_chunks(_SAMPLE_ROW)
    assert len(chunks) == 3
    assert chunks[0].metadata["is_selected"] is True
    assert chunks[1].metadata["is_selected"] is False
    assert chunks[2].metadata["is_selected"] is False
    assert all(c.metadata["query_id"] == 1185869 for c in chunks)


def test_metadata_aware_chunks_skips_empty_passages():
    row = dict(_SAMPLE_ROW)
    row["passages"] = {
        "is_selected": [1, 0],
        "English_passages": ["A", "B"],
        "Translated_passages": ["real content here", "   "],  # second is blank
    }
    chunks = metadata_aware_chunks(row)
    assert len(chunks) == 1


# --- vector store ---------------------------------------------------------

def test_vector_store_retrieves_nearest_vector():
    store = VectorStore(dim=4)
    store.add(
        vectors=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]],
        chunks=["about cats", "about dogs", "about the taj mahal"],
        metadata=[{}, {}, {}],
    )
    results = store.search([1, 0, 0, 0], k=2)
    assert results[0][0] == "about cats"
    assert results[0][1] > 0.99


def test_vector_store_save_and_load_round_trip(tmp_path):
    store = VectorStore(dim=3)
    store.add([[1, 0, 0], [0, 1, 0]], ["chunk-a", "chunk-b"], [{"x": 1}, {"x": 2}])
    path = str(tmp_path / "test_index")
    store.save(path)

    loaded = VectorStore.load(path)
    assert len(loaded) == 2
    results = loaded.search([1, 0, 0], k=1)
    assert results[0][0] == "chunk-a"
    assert results[0][2]["x"] == 1


def test_vector_store_rejects_mismatched_lengths():
    store = VectorStore(dim=3)
    try:
        store.add([[1, 0, 0]], ["only one chunk", "but two chunks"], [{}])
        assert False, "expected ValueError"
    except ValueError:
        pass


# --- guardrails -----------------------------------------------------------

def test_is_unsafe_blocks_clear_cases():
    assert is_unsafe("how do i make a bomb") is True
    assert is_unsafe("how do i kill myself") is True


def test_is_unsafe_does_not_false_positive_on_legitimate_questions():
    assert is_unsafe("how do bomb disposal robots work") is False
    assert is_unsafe("what is the taj mahal") is False
    assert is_unsafe("how does a nuclear power plant generate electricity") is False


def test_is_offtopic_for_kb_skips_greetings_and_tool_intent():
    assert is_offtopic_for_kb("hi", "general") is True
    assert is_offtopic_for_kb("what's the weather in Delhi", "weather") is True
    assert is_offtopic_for_kb("where is the taj mahal located", "general") is False


def test_check_grounding_respects_threshold():
    assert check_grounding([]) is False
    assert check_grounding([("passage", 0.8, {})]) is True
    assert check_grounding([("passage", 0.2, {})]) is False
    assert check_grounding([("passage", 0.5, {})], min_relevance=0.6) is False


# --- retry / structured error recovery ------------------------------------

def test_retry_recovers_from_transient_error():
    from app.ai.retry import stream_with_retry

    call_count = [0]

    def flaky():
        call_count[0] += 1
        if call_count[0] == 1:
            yield "(Gemini error: 503 UNAVAILABLE. temporarily overloaded)"
        else:
            yield "real answer"

    with patch("app.ai.retry.time.sleep"):  # don't actually wait during tests
        result = list(stream_with_retry(flaky))
    assert result == ["real answer"]
    assert call_count[0] == 2


def test_retry_gives_up_after_max_attempts_with_friendly_message():
    from app.ai.retry import stream_with_retry

    def always_fails():
        yield "(Gemini error: 503 UNAVAILABLE. still down)"

    with patch("app.ai.retry.time.sleep"):
        result = list(stream_with_retry(always_fails))
    assert len(result) == 1
    assert "503" not in result[0]  # never leak the raw error to the user
    assert "temporary issue" in result[0]


def test_retry_does_not_retry_nontransient_errors():
    from app.ai.retry import stream_with_retry

    call_count = [0]

    def auth_error():
        call_count[0] += 1
        yield "(Gemini error: 403 PERMISSION_DENIED. bad api key)"

    result = list(stream_with_retry(auth_error))
    assert call_count[0] == 1  # no retry wasted on a non-transient error
    assert "temporary issue" in result[0]


def test_retry_closes_gracefully_on_mid_stream_failure():
    from app.ai.retry import stream_with_retry

    def breaks_mid_stream():
        yield "Part one. "
        raise ConnectionError("dropped")

    result = list(stream_with_retry(breaks_mid_stream))
    assert result[0] == "Part one. "
    assert "interrupted" in result[1]


# --- Groq-primary / Gemini-fallback generation provider chain -------------
# See app/ai/retry.py's stream_with_fallback/stream_generation and
# docs/Architecture.md's "Generation Provider Chain" section. Groq is
# primary (published-benchmark rationale — see that doc section for the
# honest caveat that this project's own benchmark.py hasn't confirmed it
# yet), Gemini is the fallback if Groq exhausts its retry budget.

def test_fallback_chain_groq_succeeds_gemini_never_called():
    from app.ai.retry import stream_with_fallback

    def groq_ok():
        yield "Groq answer."

    def gemini_should_not_be_called():
        raise AssertionError("Gemini should not have been called when Groq succeeds")
        yield "unused"  # pragma: no cover — unreachable, keeps this a generator

    result = list(stream_with_fallback(groq_ok, gemini_should_not_be_called, "Groq", "Gemini"))
    assert result == ["Groq answer."]


def test_fallback_chain_groq_exhausts_retries_then_gemini_used():
    from app.ai.retry import stream_with_fallback

    groq_call_count = [0]

    def groq_always_fails():
        groq_call_count[0] += 1
        yield "(Groq error: 503 UNAVAILABLE. overloaded)"

    def gemini_ok():
        yield "Gemini fallback answer."

    with patch("app.ai.retry.time.sleep"):
        result = list(stream_with_fallback(groq_always_fails, gemini_ok, "Groq", "Gemini"))
    assert result == ["Gemini fallback answer."]
    assert groq_call_count[0] == 3  # 1 initial + 2 retries, all on Groq, before falling back


def test_fallback_chain_both_providers_fail_clean_error():
    from app.ai.retry import stream_with_fallback

    def groq_fails():
        yield "(Groq error: 503 UNAVAILABLE. still down)"

    def gemini_fails():
        yield "(Gemini error: 503 UNAVAILABLE. also down)"

    with patch("app.ai.retry.time.sleep"):
        result = list(stream_with_fallback(groq_fails, gemini_fails, "Groq", "Gemini"))
    assert len(result) == 1
    assert "503" not in result[0]  # never leak either provider's raw error
    assert "couldn't reach either" in result[0]


def test_fallback_chain_nontransient_primary_error_still_falls_back():
    from app.ai.retry import stream_with_fallback

    groq_call_count = [0]

    def groq_nontransient_error():
        groq_call_count[0] += 1
        yield "(Groq error: 401 invalid api key)"

    def gemini_ok():
        yield "Gemini answered instead."

    result = list(stream_with_fallback(groq_nontransient_error, gemini_ok, "Groq", "Gemini"))
    assert result == ["Gemini answered instead."]
    assert groq_call_count[0] == 1  # non-transient — no retry wasted, straight to fallback


# --- call_generation (non-streaming fallback chain) ------------------------
# Used by app/tools/weather.py and anything else that needs a single
# complete string rather than a stream. Built on stream_with_fallback (a
# non-streaming call is just a one-chunk "stream"), so these mostly
# confirm that reuse actually works end to end, not re-testing the retry
# mechanics themselves (already covered above).

# --- dataset shard-path fix (Task 1 — was streaming+filtering the whole
# combined 10.1M-row "default" config, crashing on other languages' shards
# before ever reaching a match; now loads the target language's shard file
# directly) ------------------------------------------------------------

def test_shard_path_construction_for_confirmed_splits():
    assert _shard_path("hin_Deva", "train") == "train/hintrain.parquet"
    assert _shard_path("asm_Beng", "train") == "train/asmtrain.parquet"
    assert _shard_path("tel_Telu", "validation") == "validation/telval.parquet"


def test_shard_path_rejects_unconfirmed_split():
    try:
        _shard_path("hin_Deva", "test")
        assert False, "expected ValueError for an unconfirmed split pattern"
    except ValueError:
        pass


def test_load_msmarco_xi_loads_only_target_language_shard():
    """The actual bug fix: confirms load_dataset is called with
    data_files pointing at ONE shard (not the combined "default" config),
    so it never has to stream through other languages' shards first."""
    import importlib
    import sys
    import types

    if "datasets" not in sys.modules:
        sys.modules["datasets"] = types.ModuleType("datasets")

    import app.rag.dataset as ds_module
    importlib.reload(ds_module)

    fake_rows = [{"target_lang": "hin_Deva", "query_id": i} for i in range(3)]
    call_kwargs = {}

    def fake_load_dataset(name, data_files=None, split=None, streaming=None):
        call_kwargs["name"] = name
        call_kwargs["data_files"] = data_files
        call_kwargs["split"] = split
        call_kwargs["streaming"] = streaming
        return iter(fake_rows)

    ds_module._hf_datasets = types.SimpleNamespace(load_dataset=fake_load_dataset)
    ds_module._HF_DATASETS_AVAILABLE = True

    rows = list(ds_module.load_msmarco_xi(language="hi", split="train", max_rows=10))
    assert len(rows) == 3
    assert call_kwargs["data_files"] == {"train": "train/hintrain.parquet"}
    assert call_kwargs["streaming"] is True


def test_call_generation_groq_succeeds_gemini_never_called():
    from app.ai.retry import call_generation

    with patch("app.ai.retry.call_groq", return_value="Groq's answer."):
        with patch("app.ai.retry.call_gemini") as mock_gemini:
            result = call_generation("some prompt")
    assert result == "Groq's answer."
    assert not mock_gemini.called


def test_call_generation_groq_fails_gemini_used():
    from app.ai.retry import call_generation

    with patch("app.ai.retry.call_groq", return_value="(Groq error: 503 UNAVAILABLE. overloaded)"):
        with patch("app.ai.retry.call_gemini", return_value="Gemini's answer."):
            with patch("app.ai.retry.time.sleep"):
                result = call_generation("some prompt")
    assert result == "Gemini's answer."


def test_call_generation_both_fail_clean_error_not_leaked():
    from app.ai.retry import call_generation

    with patch("app.ai.retry.call_groq", return_value="(Groq error: 503 UNAVAILABLE. down)"):
        with patch("app.ai.retry.call_gemini", return_value="(Gemini error: 503 UNAVAILABLE. also down)"):
            with patch("app.ai.retry.time.sleep"):
                result = call_generation("some prompt")
    assert "503" not in result
    assert "couldn't reach either" in result


def test_weather_gemini_fallback_does_not_leak_raw_error():
    """Regression test for the exact bug reported live: weather questions
    showing raw '(Gemini error: 503 UNAVAILABLE...)' text as the answer.
    call_gemini's return value is truthy even when it's an error string,
    so `txt or "Sorry..."` used to let it straight through — this
    confirms get_weather_gemini's fallback now goes through the
    Groq/Gemini chain and never surfaces a raw provider error."""
    from app.tools import weather

    with patch("app.tools.weather.call_gemini_json", return_value=None):
        with patch("app.ai.retry.call_groq", return_value="(Groq error: 503 UNAVAILABLE. down)"):
            with patch("app.ai.retry.call_gemini", return_value="(Gemini error: 503 UNAVAILABLE. also down)"):
                with patch("app.ai.retry.time.sleep"):
                    result = weather.get_weather_gemini("Delhi")
    assert "503" not in result
    assert "UNAVAILABLE" not in result
    assert "couldn't reach either" in result

