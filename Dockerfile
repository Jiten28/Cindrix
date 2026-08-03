# Nimbus AI — production container
#
# Uses gunicorn instead of `python run.py`'s Flask dev server (that server
# prints its own "do not use in production" warning — this is the fix).
# PORT is read at container start, not baked in, because Render/Railway
# both inject their own PORT value dynamically; hardcoding 5000 would break
# on either platform.

FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (separate layer) so `docker build` doesn't
# re-install everything just because application code changed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# data/ subdirectories are created automatically at runtime by
# conversation_store.py / attachment_store.py / etc. (os.makedirs(...,
# exist_ok=True) everywhere) — nothing needs to be pre-created here.

ENV PORT=5000
EXPOSE 5000

# Shell form (not exec-array form) so ${PORT} actually gets expanded —
# Render/Railway set PORT themselves; ${PORT:-5000} falls back to 5000 for
# plain `docker run` with nothing set.
CMD gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 2 --threads 4 --timeout 300 run:app
