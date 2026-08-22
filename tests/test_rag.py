"""Tests for the RAG path: chunking, vector store, guardrails, retry/fallback,
parquet ingest, provider routing, and weather/city extraction. No real API key
needed — the embedding-backed paths are mocked."""

import os
import sys
import types
from unittest.mock import patch

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.rag import vector_store as vector_store_module
from app.rag.chunking import (
    fixed_size_chunks,
    hybrid_chunks,
    metadata_aware_chunks,
    semantic_chunks,
)
from app.rag.dataset import _shard_path, resolve_target_lang_code
from app.rag.guardrails import (
    KB_ANSWER,
    KB_DECLINE,
    KB_FALLTHROUGH,
    check_grounding,
    is_offtopic_for_kb,
    is_unsafe,
    kb_decision,
)
from app.rag.vector_store import VectorStore

# The dataset card's documented example row.
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
    for sentence in prose.split(". "):
        stripped = sentence.strip().rstrip(".")
        assert any(stripped in c.text for c in chunks), f"sentence fragment lost: {stripped!r}"


def test_semantic_chunks_overlap_repeats_boundary_sentences():
    prose = (
        "Alpha one is here. Bravo two follows after it. Charlie three comes next in line. "
        "Delta four then arrives. Echo five closes out the passage."
    )
    plain = semantic_chunks(prose, target_size=60, min_size=20)
    overlapped = semantic_chunks(prose, target_size=60, min_size=20, overlap_sentences=1)
    assert len(overlapped) >= 2
    # Each chunk after the first restates the previous chunk's last sentence, so
    # a fact spanning a boundary is retrievable from either side.
    for prev, nxt in zip(overlapped, overlapped[1:]):
        assert prev.text.split(". ")[-1].rstrip(".") in nxt.text
    assert sum(len(c.text) for c in overlapped) > sum(len(c.text) for c in plain)


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


def test_hybrid_chunks_routes_by_passage_length():
    long_sentences = " ".join(f"Sentence number {i} carries enough words to matter here." for i in range(20))
    unsplittable = "x" * 1500  # no sentence boundary anywhere
    row = dict(_SAMPLE_ROW)
    row["passages"] = {
        "is_selected": [1, 0, 0],
        "English_passages": ["A", "B", "C"],
        "Translated_passages": ["a short self-contained passage", long_sentences, unsplittable],
    }
    chunks = hybrid_chunks(row)
    strategies = {c.strategy for c in chunks}
    # Short passage stays whole; long prose splits on sentences; a passage with
    # no sentence boundary can only fall back to a fixed-size window.
    assert strategies == {"metadata_aware", "semantic", "fixed_size"}
    assert sum(1 for c in chunks if c.strategy == "metadata_aware") == 1


def test_hybrid_chunks_sub_chunks_keep_dataset_metadata():
    row = dict(_SAMPLE_ROW)
    row["passages"] = {
        "is_selected": [1],
        "English_passages": ["A"],
        "Translated_passages": [" ".join(f"Fact {i} lives in this passage body." for i in range(25))],
    }
    chunks = hybrid_chunks(row)
    assert len(chunks) > 1
    for c in chunks:
        assert c.metadata["query_id"] == 1185869
        assert c.metadata["is_selected"] is True
        assert c.metadata["parent_strategy"] == "metadata_aware"
        assert c.metadata["sub_chunk_count"] == len(chunks)
    assert [c.metadata["sub_chunk_index"] for c in chunks] == list(range(len(chunks)))


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


def test_vector_store_save_writes_a_numpy_sidecar(tmp_path):
    """Every save must leave behind raw vectors, whichever backend is active —
    it's what makes the index loadable where faiss isn't importable."""
    store = VectorStore(dim=3)
    store.add([[1, 0, 0], [0, 1, 0]], ["chunk-a", "chunk-b"], [{}, {}])
    path = str(tmp_path / "test_index")
    store.save(path)

    sidecar = tmp_path / "test_index.vectors.npy"
    assert sidecar.exists()
    vectors = np.load(sidecar)
    assert vectors.shape == (2, 3)
    # Stored normalized, so inner product is cosine similarity.
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0)


def test_vector_store_loads_faiss_index_without_faiss(tmp_path, monkeypatch):
    """A faiss-saved index must still load and search where faiss can't be
    imported — the deployment case this guards is a slim base image missing
    the OpenMP runtime faiss's wheel needs."""
    store = VectorStore(dim=3)
    store.add([[1, 0, 0], [0, 1, 0]], ["chunk-a", "chunk-b"], [{"x": 1}, {"x": 2}])
    path = str(tmp_path / "test_index")
    store.save(path)

    # Pretend faiss vanished after the index was written. The meta file still
    # says backend: faiss when faiss was available at save time.
    monkeypatch.setattr(vector_store_module, "_FAISS_AVAILABLE", False)
    loaded = VectorStore.load(path)

    assert len(loaded) == 2
    results = loaded.search([1, 0, 0], k=1)
    assert results[0][0] == "chunk-a"
    assert results[0][2]["x"] == 1
    assert results[0][1] > 0.99


def test_vector_store_load_without_faiss_or_sidecar_raises_clearly(tmp_path, monkeypatch):
    """The one case that genuinely can't be recovered should say why, not
    fail with a bare file-not-found."""
    store = VectorStore(dim=3)
    store.add([[1, 0, 0]], ["chunk-a"], [{}])
    path = str(tmp_path / "test_index")
    store.save(path)
    if not vector_store_module._FAISS_AVAILABLE:
        return  # nothing saved a .faiss file, so this case doesn't apply here
    (tmp_path / "test_index.vectors.npy").unlink()

    monkeypatch.setattr(vector_store_module, "_FAISS_AVAILABLE", False)
    try:
        VectorStore.load(path)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "sidecar" in str(e)


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


def test_is_offtopic_for_kb_skips_self_and_user_meta_questions():
    # A web-passage corpus can't answer these, but they score like a real match.
    assert is_offtopic_for_kb("who created you", "general") is True
    assert is_offtopic_for_kb("मेरा नाम क्या है?", "general") is True
    assert is_offtopic_for_kb("Cindrix ऐप किसने बनाया?", "general") is True


def test_check_grounding_respects_threshold():
    assert check_grounding([]) is False
    assert check_grounding([("passage", 0.8, {})]) is True
    assert check_grounding([("passage", 0.2, {})]) is False
    assert check_grounding([("passage", 0.5, {})], min_relevance=0.6) is False


def test_kb_decision_separates_answer_decline_and_fallthrough():
    # Bands calibrated against the built index: confident match, related-but-not
    # confident (the case that would otherwise hallucinate), and off-corpus.
    # Pinned here so a local .env override can't change what this asserts.
    with patch.object(settings, "RAG_MIN_RELEVANCE", 0.75), \
         patch.object(settings, "RAG_DECLINE_FLOOR", 0.62):
        assert kb_decision([("passage", 0.81, {})]) == KB_ANSWER
        assert kb_decision([("passage", 0.68, {})]) == KB_DECLINE
        assert kb_decision([("passage", 0.58, {})]) == KB_FALLTHROUGH
        assert kb_decision([]) == KB_FALLTHROUGH


def test_kb_decision_defaults_are_calibrated_not_permissive():
    # The shipped default has to sit above the measured out-of-domain ceiling
    # (~0.72); a lower floor answers general questions from unrelated passages.
    assert settings.RAG_MIN_RELEVANCE >= 0.72
    assert settings.RAG_DECLINE_FLOOR < settings.RAG_MIN_RELEVANCE


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

    with patch("app.ai.retry.time.sleep"):
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
    assert "503" not in result[0]
    assert "temporary issue" in result[0]


def test_retry_does_not_retry_nontransient_errors():
    from app.ai.retry import stream_with_retry

    call_count = [0]

    def auth_error():
        call_count[0] += 1
        yield "(Gemini error: 403 PERMISSION_DENIED. bad api key)"

    result = list(stream_with_retry(auth_error))
    assert call_count[0] == 1  # non-transient — no retry
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

def test_fallback_chain_groq_succeeds_gemini_never_called():
    from app.ai.retry import stream_with_fallback

    def groq_ok():
        yield "Groq answer."

    def gemini_should_not_be_called():
        raise AssertionError("Gemini should not have been called when Groq succeeds")
        yield "unused"  # pragma: no cover — keeps this a generator

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
    assert groq_call_count[0] == 3  # 1 initial + 2 retries before falling back


def test_fallback_chain_both_providers_fail_clean_error():
    from app.ai.retry import stream_with_fallback

    def groq_fails():
        yield "(Groq error: 503 UNAVAILABLE. still down)"

    def gemini_fails():
        yield "(Gemini error: 503 UNAVAILABLE. also down)"

    with patch("app.ai.retry.time.sleep"):
        result = list(stream_with_fallback(groq_fails, gemini_fails, "Groq", "Gemini"))
    assert len(result) == 1
    assert "503" not in result[0]
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
    assert groq_call_count[0] == 1  # non-transient — straight to fallback


# --- dataset shard path + pyarrow ingest -----------------------------------

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


def test_load_msmarco_xi_reads_only_target_language_shard_via_pyarrow():
    """Downloads the one target-language shard by name, reads it with pyarrow,
    projects only the ingest columns, and filters to the target language."""
    import app.rag.dataset as ds_module

    captured = {}

    def fake_hf_hub_download(repo_id, filename, repo_type):
        captured["repo_id"] = repo_id
        captured["filename"] = filename
        captured["repo_type"] = repo_type
        return "/fake/cache/hintrain.parquet"

    class _FakeBatch:
        def __init__(self, rows):
            self._rows = rows

        def to_pylist(self):
            return self._rows

    class _FakeParquetFile:
        def __init__(self, path):
            captured["opened_path"] = path

        def iter_batches(self, batch_size, columns):
            captured["batch_size"] = batch_size
            captured["columns"] = columns
            yield _FakeBatch([
                {"target_lang": "hin_Deva", "query_id": 1},
                {"target_lang": "hin_Deva", "query_id": 2},
            ])
            # a non-target row mixed in, to check per-row filtering
            yield _FakeBatch([
                {"target_lang": "asm_Beng", "query_id": 999},
                {"target_lang": "hin_Deva", "query_id": 3},
            ])

    fake_pq = types.SimpleNamespace(ParquetFile=_FakeParquetFile)

    with patch.object(ds_module, "_PARQUET_STACK_AVAILABLE", True), \
            patch.object(ds_module, "_hf_hub_download", fake_hf_hub_download), \
            patch.object(ds_module, "_pq", fake_pq):
        rows = list(ds_module.load_msmarco_xi(language="hi", split="train", max_rows=10))

    # downloaded exactly the Hindi train shard, from the dataset repo
    assert captured["filename"] == "train/hintrain.parquet"
    assert captured["repo_type"] == "dataset"
    assert captured["opened_path"] == "/fake/cache/hintrain.parquet"
    assert captured["columns"] == ds_module._INGEST_COLUMNS
    # the asm_Beng row is dropped
    assert [r["query_id"] for r in rows] == [1, 2, 3]
    assert all(r["target_lang"] == "hin_Deva" for r in rows)


def test_load_msmarco_xi_respects_max_rows():
    """max_rows caps matched rows and stops the scan early."""
    import app.rag.dataset as ds_module

    class _FakeBatch:
        def __init__(self, rows):
            self._rows = rows

        def to_pylist(self):
            return self._rows

    class _FakeParquetFile:
        def __init__(self, path):
            pass

        def iter_batches(self, batch_size, columns):
            yield _FakeBatch([{"target_lang": "hin_Deva", "query_id": i} for i in range(100)])

    fake_pq = types.SimpleNamespace(ParquetFile=_FakeParquetFile)

    with patch.object(ds_module, "_PARQUET_STACK_AVAILABLE", True), \
            patch.object(ds_module, "_hf_hub_download", lambda **kw: "/fake.parquet"), \
            patch.object(ds_module, "_pq", fake_pq):
        rows = list(ds_module.load_msmarco_xi(language="hi", split="train", max_rows=5))

    assert len(rows) == 5


def test_load_msmarco_xi_reraises_real_failure_never_falls_back_to_fixture():
    """A failed real load must re-raise, not silently yield fixture rows. The
    fixture is only for when the parquet stack isn't installed."""
    import app.rag.dataset as ds_module

    def boom(**kw):
        raise RuntimeError("simulated download failure")

    with patch.object(ds_module, "_PARQUET_STACK_AVAILABLE", True), \
            patch.object(ds_module, "_hf_hub_download", boom):
        try:
            list(ds_module.load_msmarco_xi(language="hi", split="train", max_rows=5))
            assert False, "expected the real-load failure to propagate, not fall back to fixture"
        except RuntimeError as e:
            assert "simulated download failure" in str(e)


# --- call_generation (non-streaming fallback chain) ------------------------

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
    """call_gemini returns a truthy string even on error, so `txt or "Sorry..."`
    used to let raw provider errors through as the weather answer."""
    from app.tools import weather

    with patch("app.tools.weather.call_gemini_json", return_value=None):
        with patch("app.ai.retry.call_groq", return_value="(Groq error: 503 UNAVAILABLE. down)"):
            with patch("app.ai.retry.call_gemini", return_value="(Gemini error: 503 UNAVAILABLE. also down)"):
                with patch("app.ai.retry.time.sleep"):
                    result = weather.get_weather_gemini("Delhi")
    assert "503" not in result
    assert "UNAVAILABLE" not in result
    assert "couldn't reach either" in result


# --- model selector provider routing ---------------------------------------

def test_model_provider_routes_by_id():
    from app.config import settings

    assert settings.model_provider(None) == "groq"
    assert settings.model_provider("gemini-flash-latest") == "gemini"
    assert settings.model_provider(settings.GROQ_MODEL) == "groq"
    assert settings.model_provider("totally-unknown-id") == "groq"


def test_stream_generation_default_is_groq_primary():
    from app.ai import retry

    calls = []

    def fake_stream_gemini(prompt, model=None):
        calls.append("gemini")
        yield "Gemini answer."

    def fake_stream_groq(prompt, model=None):
        calls.append("groq")
        yield "Groq answer."

    with patch("app.ai.retry.stream_gemini", fake_stream_gemini):
        with patch("app.ai.retry.stream_groq", fake_stream_groq):
            result = list(retry.stream_generation("q"))
    assert result == ["Groq answer."]
    assert calls[0] == "groq"


def test_stream_generation_gemini_selection_makes_gemini_primary():
    from app.ai import retry

    calls = []

    def fake_stream_gemini(prompt, model=None):
        calls.append(("gemini", model))
        yield "Gemini primary answer."

    def fake_stream_groq(prompt, model=None):
        calls.append(("groq", model))
        yield "Groq answer."

    with patch("app.ai.retry.stream_gemini", fake_stream_gemini):
        with patch("app.ai.retry.stream_groq", fake_stream_groq):
            result = list(retry.stream_generation("q", model="gemini-flash-latest"))
    assert result == ["Gemini primary answer."]
    assert calls[0][0] == "gemini"
    assert calls[0][1] == "gemini-flash-latest"
    assert all(c[0] != "groq" for c in calls)


def test_stream_generation_gemini_selection_still_falls_back_to_groq():
    from app.ai import retry

    calls = []

    def fake_stream_gemini(prompt, model=None):
        calls.append("gemini")
        yield "(Gemini error: 503 UNAVAILABLE. down)"

    def fake_stream_groq(prompt, model=None):
        calls.append("groq")
        yield "Groq rescued it."

    with patch("app.ai.retry.stream_gemini", fake_stream_gemini):
        with patch("app.ai.retry.stream_groq", fake_stream_groq):
            with patch("app.ai.retry.time.sleep"):
                result = list(retry.stream_generation("q", model="gemini-flash-latest"))
    assert result == ["Groq rescued it."]
    assert calls[0] == "gemini"
    assert "groq" in calls


# --- weather: city extraction + Open-Meteo ---------------------------------

def test_extract_city_handles_varied_phrasing():
    from app.agents.router import _extract_city

    assert _extract_city("what's the weather in Delhi") == "Delhi"
    assert _extract_city("weather in New York") == "New York"
    assert _extract_city("forecast for Mumbai") == "Mumbai"
    assert _extract_city("Hyderabad weather") == "Hyderabad"
    assert _extract_city("Pune forecast today") == "Pune"
    assert _extract_city("दिल्ली का मौसम") == "दिल्ली"


def test_extract_city_defaults_when_no_city_present():
    from app.agents.router import _extract_city

    assert _extract_city("what's the weather") == "your area"
    assert _extract_city("मौसम कैसा है") == "your area"


def test_weather_detection_matches_city_first_and_hindi():
    from app.agents.router import _WEATHER_RE

    assert _WEATHER_RE.search("Hyderabad weather") is not None
    assert _WEATHER_RE.search("दिल्ली का मौसम") is not None
    assert _WEATHER_RE.search("give me the forecast") is not None
    assert _WEATHER_RE.search("what is the capital of France") is None


def test_get_weather_open_meteo_formats_current_conditions():
    from app.tools import weather

    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    geocode_payload = {"results": [{"latitude": 28.6, "longitude": 77.2, "name": "Delhi", "country": "India"}]}
    forecast_payload = {"current": {
        "temperature_2m": 31.4, "relative_humidity_2m": 55,
        "wind_speed_10m": 12, "weather_code": 1,
    }}
    responses = [_Resp(geocode_payload), _Resp(forecast_payload)]

    def fake_get(url, params=None, timeout=None):
        return responses.pop(0)

    with patch("app.tools.weather.requests.get", side_effect=fake_get):
        result = weather.get_weather_open_meteo("Delhi")

    assert result is not None
    assert "Delhi, India" in result
    assert "31.4" in result
    assert "mainly clear" in result  # WMO code 1


def test_get_weather_open_meteo_returns_none_when_city_not_found():
    """A geocoding miss returns None so get_weather() falls back to the estimate."""
    from app.tools import weather

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": []}

    with patch("app.tools.weather.requests.get", return_value=_Resp()):
        assert weather.get_weather_open_meteo("Nowhereville") is None

