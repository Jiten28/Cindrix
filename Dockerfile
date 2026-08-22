# Cindrix — production container
#
# Uses gunicorn instead of `python run.py`'s Flask dev server (that server
# prints its own "do not use in production" warning — this is the fix).
# PORT is read at container start, not baked in, because Render/Railway
# both inject their own PORT value dynamically; hardcoding 5000 would break
# on either platform.

FROM python:3.12-slim

WORKDIR /app

# libgomp1 — the OpenMP runtime faiss-cpu's wheel links against. Debian slim
# images don't ship it, and its absence is silent at build time: `pip install
# faiss-cpu` succeeds (it's a prebuilt wheel), then `import faiss` fails at
# runtime with "libgomp.so.1: cannot open shared object file". The app catches
# that and degrades to conversational answers, so the container looks healthy
# while knowledge-base retrieval is entirely off. Without this line the whole
# RAG path is dead in the image but works locally.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first (separate layer) so `docker build` doesn't
# re-install everything just because application code changed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Fail the build, not the request, if faiss can't be imported in this image.
RUN python -c "import faiss; print('faiss', faiss.__version__, 'importable')"

COPY . .

# Verify the shipped index actually loads in this image, for the same reason:
# a load failure at runtime is caught and degrades silently, so it has to be
# caught here instead. Path built inline rather than imported from
# app.rag.ingest, which pulls in the dataset-download dependencies.
RUN python -c "\
from app.config import settings; \
from app.rag.vector_store import VectorStore; \
p = f'{settings.RAG_INDEX_DIR}/msmarco_xi_{settings.RAG_DATASET_LANGUAGE}'; \
s = VectorStore.load(p); \
print('knowledge-base index loaded:', len(s), 'chunks from', p); \
assert len(s) > 0"

# data/ subdirectories are created automatically at runtime by
# conversation_store.py / attachment_store.py / etc. (os.makedirs(...,
# exist_ok=True) everywhere) — nothing needs to be pre-created here.

ENV PORT=5000
EXPOSE 5000

# Shell form (not exec-array form) so ${PORT} actually gets expanded —
# Render/Railway set PORT themselves; ${PORT:-5000} falls back to 5000 for
# plain `docker run` with nothing set.
CMD gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 2 --threads 4 --timeout 300 run:app
