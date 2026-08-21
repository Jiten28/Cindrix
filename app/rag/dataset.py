"""Loads ai4bharat/MSMARCO-XI by reading a language's parquet shard directly with
huggingface_hub + pyarrow. The HF `datasets` library is bypassed on purpose: it
can't decode the nested `passages` struct (ArrowNotImplementedError), whereas
pyarrow reads it into plain dicts via .to_pylist().

Shards are per-language parquet files named `{split}/{iso3}{suffix}.parquet`
(Hindi = train/hintrain.parquet). The Hindi shard is one ~3.72 GB row group, so
it's downloaded once to the HF cache and read locally.
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


# Short code -> full target_lang value in the dataset rows (ISO 639-3 + script,
# e.g. "hin_Deva"). The ISO 639-3 prefix doubles as the shard filename prefix.
# A wrong value fails on the shard's first row (see load_msmarco_xi), not after
# scanning millions.
LANGUAGE_CODE_MAP = {
    "as": "asm_Beng", "bn": "ben_Beng", "gu": "guj_Gujr", "hi": "hin_Deva",
    "kn": "kan_Knda", "ml": "mal_Mlym", "mr": "mar_Deva", "ne": "npi_Deva",
    "or": "ory_Orya", "pa": "pan_Guru", "sa": "san_Deva", "ta": "tam_Taml",
    "te": "tel_Telu", "ur": "urd_Arab",
}


def resolve_target_lang_code(language: str) -> str:
    """Accept a short code ("hi") or a full code ("hin_Deva"); return the full code."""
    if "_" in language:
        return language
    if language in LANGUAGE_CODE_MAP:
        return LANGUAGE_CODE_MAP[language]
    raise ValueError(
        f"Unknown language code {language!r} — expected one of "
        f"{sorted(LANGUAGE_CODE_MAP)} or an already-full target_lang value "
        f"like 'hin_Deva'."
    )


# split -> shard filename suffix: train/hintrain.parquet, validation/telval.parquet.
_SHARD_SUFFIX_BY_SPLIT = {"train": "train", "validation": "val"}


def _shard_path(target_lang_code: str, split: str) -> str:
    """Repo-relative shard path, e.g. ("hin_Deva", "train") -> "train/hintrain.parquet"."""
    if split not in _SHARD_SUFFIX_BY_SPLIT:
        raise ValueError(
            f"Don't know the shard filename pattern for split {split!r} — "
            f"only {sorted(_SHARD_SUFFIX_BY_SPLIT)} are confirmed. Check the "
            f"dataset's real file tree and add it to _SHARD_SUFFIX_BY_SPLIT "
            f"once confirmed, rather than guessing."
        )
    iso3 = target_lang_code.split("_")[0]
    suffix = _SHARD_SUFFIX_BY_SPLIT[split]
    return f"{split}/{iso3}{suffix}.parquet"


# Only the columns metadata_aware_chunks() consumes — pyarrow decodes less this way.
_INGEST_COLUMNS = ["target_lang", "query", "query_id", "query_type", "passages"]

# pyarrow decodes the row group in batches of this many rows.
_READ_BATCH_SIZE = 1024

# How often to log scan progress while reading through the shard.
_SCAN_LOG_EVERY = 5_000

# Documented example rows — used ONLY when huggingface_hub/pyarrow aren't installed.
# A real load that *fails* re-raises instead (see load_msmarco_xi).
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
    """Yields up to max_rows rows from ai4bharat/MSMARCO-XI matching `language`.

    Downloads the language's parquet shard via huggingface_hub (cached across
    runs) and reads it with pyarrow. target_lang is still checked per row as a
    cheap guard on the shard-filename assumption. Falls back to the fixture ONLY
    if huggingface_hub/pyarrow aren't installed; a real load that fails is logged
    and re-raised, never masked."""
    language = language or settings.RAG_DATASET_LANGUAGE
    split = split or settings.RAG_DATASET_SPLIT
    max_rows = max_rows if max_rows is not None else settings.RAG_INGEST_MAX_ROWS
    target_lang_code = resolve_target_lang_code(language)

    if not _PARQUET_STACK_AVAILABLE:
        logger.warning(
            "[rag.dataset] huggingface_hub/pyarrow not installed — yielding "
            "FIXTURE rows, NOT the real ai4bharat/MSMARCO-XI dataset. Run "
            "`pip install huggingface_hub pyarrow` and re-ingest before "
            "trusting anything downstream of this.",
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
        # A failed real load must be loud — never swap in the fixture here.
        # A 404 usually means _shard_path() built the wrong filename for this
        # language/split.
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
                    # A mismatch in the first rows means the shard-selection
                    # assumption is likely wrong — flag it immediately.
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
