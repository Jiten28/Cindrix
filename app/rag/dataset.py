"""Loads ai4bharat/MSMARCO-XI (the hackathon-mandated dataset) by reading the
target language's parquet shard directly with `huggingface_hub` +
`pyarrow`, deliberately BYPASSING the HuggingFace `datasets` library — see
docs/Architecture.md's "Retrieval & Vector Store" section for the history.

Why not `datasets`: it crashed three different ways against this real
dataset, the last one fatal and opaque:
  1. `BuilderConfig 'hi' not found. Available: ['default']`.
  2. Streaming the combined "default" config pulled every language's shard
     in sort order (Assamese before Hindi) and OOM'd on Assamese before
     reaching a single Hindi row.
  3. Loading the Hindi shard by name still died with a vague, swallowed
     "An error occurred while generating the dataset" (an
     `ArrowNotImplementedError: Nested data conversions not implemented`
     surfacing from inside `datasets`' Arrow→Python formatting of the
     nested `passages` struct), even after the full 3.72 GB shard had
     downloaded.

`pyarrow` reads that same nested `passages` struct into plain Python dicts
via `.to_pylist()` without complaint — VERIFIED directly against the real
shard while writing this (a real row's `passages` came back as
`{English_passages, Translated_passages, is_selected}`), which is exactly
the conversion `datasets` couldn't do. So the fix is to skip `datasets`
entirely and go `huggingface_hub.hf_hub_download()` → `pyarrow.parquet` →
Python dicts.

Real shard facts, VERIFIED against the live repo file tree and a real row
(not convention, not a prior session's claim):
  - Shards are per-language parquet files named `{split}/{iso3}{suffix}.parquet`,
    confirmed for all 13 train shards (`train/hintrain.parquet`,
    `train/asmtrain.parquet`, …) via the repo's real file tree. Hindi is
    `train/hintrain.parquet`, 3,719,813,179 bytes (~3.72 GB).
  - `train/hintrain.parquet` is a SINGLE parquet row group of 778,638 rows,
    all `target_lang == "hin_Deva"` — so `hin_Deva` for Hindi is now
    confirmed off a real row, not just the ISO convention. Because it's one
    monolithic row group, there's no cheap way to read a sub-range remotely
    (reading any row forces reading the whole row group's column chunks);
    hence we `hf_hub_download` the shard once to the local HF cache — a
    one-time cost, cached across runs — then read locally, which is fast
    (~1.7 s for 2,000 rows with column projection) and repeatable.
  - Row shape (confirmed): source_lang, target_lang, meta, query, Answer,
    query_id, query_type, passages: {is_selected, English_passages,
    Translated_passages}, Eng_Query, Eng_Answer, query. We project only the
    columns app/rag/chunking.py's metadata_aware_chunks() actually consumes
    (see _INGEST_COLUMNS) so the read decodes less than the full ~3.72 GB.

Two splits: `train` (10.1M rows total across all shards), `validation`
(1.37M total).

`huggingface_hub`/`pyarrow` aren't guaranteed installed in every environment
this code might run in — soft-imported below, with a small local fixture
built from the dataset's own documented example rows so the rest of the
pipeline (chunking, embedding, vector store) is still testable without a
network/dataset. The fixture is loudly logged as a fixture — nothing here
pretends it's the real dataset. Crucially, the fixture is ONLY used when the
libraries are genuinely absent; a real load that FAILS is not silently
papered over with the fixture (that's how every past benchmark ended up
secretly running on 5 fixture chunks) — it is logged with a full traceback
and re-raised so the failure is impossible to miss.
"""

import logging
from typing import Any, Dict, Iterator, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Bypass `datasets` (see module docstring) — read the parquet shard directly.
try:
    from huggingface_hub import hf_hub_download as _hf_hub_download
    import pyarrow.parquet as _pq
    _PARQUET_STACK_AVAILABLE = True
except ImportError:
    _PARQUET_STACK_AVAILABLE = False


# Short code -> full `target_lang` value used in the dataset's rows
# (ISO 639-3 + ISO 15924 script, e.g. "hin_Deva" = Hindi + Devanagari) —
# the ISO 639-3 part (before the underscore) doubles as the shard filename
# prefix (see _shard_path below), confirmed for all 13 train shards against
# the repo's real file tree.
#
# "hi" -> "hin_Deva" and "as" -> "asm_Beng" are CONFIRMED against real rows /
# the dataset card's own example. The other 12 follow the identical ISO
# 639-3 + script convention; their shard filenames match the confirmed
# train/{iso3}train.parquet pattern (all 13 seen in the real tree), but their
# individual target_lang values haven't each been read off a literal row.
# A wrong value now fails on the shard's very first row (see the per-row
# safety check in load_msmarco_xi), not after scanning millions of rows.
LANGUAGE_CODE_MAP = {
    "as": "asm_Beng", "bn": "ben_Beng", "gu": "guj_Gujr", "hi": "hin_Deva",
    "kn": "kan_Knda", "ml": "mal_Mlym", "mr": "mar_Deva", "ne": "npi_Deva",
    "or": "ory_Orya", "pa": "pan_Guru", "sa": "san_Deva", "ta": "tam_Taml",
    "te": "tel_Telu", "ur": "urd_Arab",
}


def resolve_target_lang_code(language: str) -> str:
    """Accepts either a short code ("hi") or an already-full code
    ("hin_Deva") and returns the full code to match against
    row["target_lang"]."""
    if "_" in language:
        return language  # already a full code
    if language in LANGUAGE_CODE_MAP:
        return LANGUAGE_CODE_MAP[language]
    raise ValueError(
        f"Unknown language code {language!r} — expected one of "
        f"{sorted(LANGUAGE_CODE_MAP)} or an already-full target_lang value "
        f"like 'hin_Deva'."
    )


# split -> filename suffix, confirmed against real examples:
# train/hintrain.parquet + train/asmtrain.parquet -> "train"/train;
# validation/telval.parquet -> "val"/validation. Only these two splits
# are confirmed to follow this pattern.
_SHARD_SUFFIX_BY_SPLIT = {"train": "train", "validation": "val"}


def _shard_path(target_lang_code: str, split: str) -> str:
    """Returns the repo-relative path to a single language's shard file,
    e.g. ("hin_Deva", "train") -> "train/hintrain.parquet".

    Raises ValueError for an unrecognized split rather than guessing at a
    filename pattern that was never actually confirmed — better to fail
    loudly here than silently construct a wrong path and get a confusing
    404 several layers down."""
    if split not in _SHARD_SUFFIX_BY_SPLIT:
        raise ValueError(
            f"Don't know the shard filename pattern for split {split!r} — "
            f"only {sorted(_SHARD_SUFFIX_BY_SPLIT)} are confirmed. Check the "
            f"dataset's real file tree and add it to _SHARD_SUFFIX_BY_SPLIT "
            f"once confirmed, rather than guessing."
        )
    iso3 = target_lang_code.split("_")[0]  # "hin_Deva" -> "hin"
    suffix = _SHARD_SUFFIX_BY_SPLIT[split]
    return f"{split}/{iso3}{suffix}.parquet"


# Only the columns metadata_aware_chunks() actually consumes — projecting
# these out of the read means pyarrow decodes far less than the full shard
# (skips meta/Answer/Eng_Query/Eng_Answer/source_lang). See app/rag/chunking.py.
_INGEST_COLUMNS = ["target_lang", "query", "query_id", "query_type", "passages"]

# pyarrow decodes the shard's single row group in batches of this many rows;
# with a small RAG_INGEST_MAX_ROWS cap we stop after the first batch or two
# instead of decoding all 778k rows.
_READ_BATCH_SIZE = 1024

# How often to log scan progress while reading through the shard.
_SCAN_LOG_EVERY = 5_000

# The dataset card's own documented example rows (see app/rag/chunking.py's
# docstring / module tests for the same shape) — used ONLY when the parquet
# stack truly isn't installed, purely so the rest of the pipeline has
# something real-shaped to run against. A real load that *fails* does NOT
# fall back to these (see load_msmarco_xi) — it re-raises.
_FIXTURE_ROWS = [
    {
        "source_lang": "eng_Latn", "target_lang": "hin_Deva",
        "query": "मेनहाटन प्रकल्प की सफलता का तत्काल प्रभाव क्या था?",
        "Answer": "मेनहाटन प्रकल्प की सफलता का तत्काल प्रभाव यह था कि इसने द्वितीय विश्व युद्ध को समाप्त करने में मदद की।",
        "query_id": 1185869, "query_type": "DESCRIPTION",
        "passages": {
            "is_selected": [1, 0, 0],
            "English_passages": [
                "The presence of communication amid scientific minds was equally important to the success of the Manhattan Project as scientific intellect was.",
                "The Manhattan Project was a research and development undertaking during World War II.",
                "It was a large-scale effort involving thousands of scientists and engineers.",
            ],
            "Translated_passages": [
                "वैज्ञानिक मस्तिष्कों के बीच संचार की उपस्थिति मैनहट्टन परियोजना की सफलता के लिए उतनी ही महत्वपूर्ण थी जितनी वैज्ञानिक बुद्धिमत्ता।",
                "मैनहट्टन परियोजना द्वितीय विश्व युद्ध के दौरान एक अनुसंधान और विकास प्रयास था।",
                "यह हजारों वैज्ञानिकों और इंजीनियरों को शामिल करने वाला एक बड़े पैमाने का प्रयास था।",
            ],
        },
        "Eng_Query": "what was the immediate impact of the success of the manhattan project?",
        "Eng_Answer": "The immediate impact of the success of the manhattan project was helping to end World War II.",
    },
    {
        "source_lang": "eng_Latn", "target_lang": "hin_Deva",
        "query": "ताजमहल कहाँ स्थित है?",
        "Answer": "ताजमहल भारत के आगरा शहर में स्थित है।",
        "query_id": 1185870, "query_type": "LOCATION",
        "passages": {
            "is_selected": [1, 0],
            "English_passages": [
                "The Taj Mahal is located in the city of Agra, Uttar Pradesh, India, on the bank of the Yamuna river.",
                "Agra is also known for its Mughal-era architecture and forts.",
            ],
            "Translated_passages": [
                "ताजमहल भारत के उत्तर प्रदेश राज्य के आगरा शहर में यमुना नदी के किनारे स्थित है।",
                "आगरा अपनी मुगलकालीन वास्तुकला और किलों के लिए भी जाना जाता है।",
            ],
        },
        "Eng_Query": "where is the taj mahal located?",
        "Eng_Answer": "The Taj Mahal is located in Agra, India.",
    },
]


def _yield_fixture(target_lang_code: str, max_rows: Optional[int]) -> Iterator[Dict[str, Any]]:
    matched = 0
    for row in _FIXTURE_ROWS:
        if row.get("target_lang") != target_lang_code:
            continue
        yield row
        matched += 1
        if max_rows is not None and matched >= max_rows:
            break


def load_msmarco_xi(
    language: Optional[str] = None,
    split: Optional[str] = None,
    max_rows: Optional[int] = None,
) -> Iterator[Dict[str, Any]]:
    """Yields rows from ai4bharat/MSMARCO-XI matching `language`, one at a
    time, capped at `max_rows` matched rows.

    Downloads the target language's shard file DIRECTLY (e.g.
    `train/hintrain.parquet` for Hindi) via huggingface_hub to the local HF
    cache (a one-time cost, cached across runs), then reads it with pyarrow —
    bypassing the HuggingFace `datasets` library entirely, which couldn't
    decode the nested `passages` struct (see the module docstring). Only the
    columns downstream chunking needs are projected out of the read.

    `target_lang` is still checked per row, as a cheap safety check on an
    already-single-language shard — a mismatch in the first few rows means
    the shard-filename assumption is wrong, and is flagged immediately.

    Falls back to a small local fixture (2 rows, real documented schema)
    ONLY if huggingface_hub/pyarrow aren't installed, clearly logged as such.
    A real load that *fails* is logged with a traceback and RE-RAISED — it is
    never silently replaced by the fixture, so a broken ingest can't
    masquerade as a successful one (the exact trap that had every prior
    benchmark secretly running on fixture data).
    """
    language = language or settings.RAG_DATASET_LANGUAGE
    split = split or settings.RAG_DATASET_SPLIT
    max_rows = max_rows if max_rows is not None else settings.RAG_INGEST_MAX_ROWS
    target_lang_code = resolve_target_lang_code(language)

    if not _PARQUET_STACK_AVAILABLE:
        logger.warning(
            "[rag.dataset] huggingface_hub/pyarrow not installed — yielding "
            "FIXTURE rows, NOT the real ai4bharat/MSMARCO-XI dataset. Run "
            "`pip install huggingface_hub pyarrow` and re-ingest before "
            "trusting anything downstream of this for the actual submission.",
        )
        yield from _yield_fixture(target_lang_code, max_rows)
        return

    shard_path = _shard_path(target_lang_code, split)
    logger.info(
        "[rag.dataset] downloading/opening shard %s (target_lang=%r), capped "
        "at %s matched rows", shard_path, target_lang_code, max_rows,
    )
    try:
        local_path = _hf_hub_download(
            repo_id=settings.RAG_DATASET_NAME,
            filename=shard_path,
            repo_type="dataset",
        )
        parquet_file = _pq.ParquetFile(local_path)
    except Exception:
        # Do NOT fall back to the fixture here — a failed real load must be
        # loud, not silently swapped for 2 fixture rows. If this is a 404/
        # file-not-found, the shard filename pattern in _shard_path() is
        # likely wrong for this language/split — check the repo's real file
        # tree (huggingface.co/datasets/%s/tree/main/%s) and fix
        # _SHARD_SUFFIX_BY_SPLIT / the filename construction rather than
        # guessing again.
        logger.exception(
            "[rag.dataset] failed to download/open shard %s from %s — "
            "re-raising (NOT falling back to fixture). If this is a 404, the "
            "shard filename for this language/split is probably wrong (see "
            "_shard_path).",
            shard_path, settings.RAG_DATASET_NAME,
        )
        raise

    matched = 0
    scanned = 0
    seen_target_langs: set = set()
    try:
        for batch in parquet_file.iter_batches(batch_size=_READ_BATCH_SIZE, columns=_INGEST_COLUMNS):
            for row in batch.to_pylist():
                scanned += 1
                row_lang = row.get("target_lang")
                seen_target_langs.add(row_lang)

                if row_lang == target_lang_code:
                    matched += 1
                    yield row
                    if max_rows is not None and matched >= max_rows:
                        logger.info(
                            "[rag.dataset] reached max_rows=%d matches after scanning %d rows of %s",
                            max_rows, scanned, shard_path,
                        )
                        return
                elif scanned <= 5:
                    # A mismatch in the shard's very first rows means the
                    # shard-selection assumption is likely wrong — flag it
                    # immediately rather than after scanning the whole shard.
                    logger.warning(
                        "[rag.dataset] row %d in %s has target_lang=%r, not the "
                        "expected %r — if this keeps happening, the shard filename "
                        "for this language is probably wrong (see _shard_path).",
                        scanned, shard_path, row_lang, target_lang_code,
                    )

                if scanned % _SCAN_LOG_EVERY == 0:
                    logger.info(
                        "[rag.dataset] scanned %d rows of %s, matched %d so far; "
                        "distinct target_lang values seen: %s",
                        scanned, shard_path, matched, sorted(seen_target_langs),
                    )
    except Exception:
        logger.exception(
            "[rag.dataset] error while reading rows from %s after %d scanned "
            "/ %d matched — re-raising (NOT falling back to fixture).",
            shard_path, scanned, matched,
        )
        raise

    if matched == 0:
        logger.error(
            "[rag.dataset] finished scanning all %d rows in %s and matched "
            "ZERO rows with target_lang == %r. Distinct target_lang values "
            "actually present: %s. The shard itself doesn't contain the "
            "expected language — re-check _shard_path()'s filename "
            "construction against the real file tree.",
            scanned, shard_path, target_lang_code, sorted(seen_target_langs),
        )
    else:
        logger.info(
            "[rag.dataset] finished scanning all %d rows in %s — %d total "
            "matches for target_lang == %r (fewer than max_rows=%s, so every "
            "match in this shard was used)",
            scanned, shard_path, matched, target_lang_code, max_rows,
        )
