"""Minimal smoke test — the first real automated test in this repo (see
docs/Memory.md's Known Issues: "no automated tests yet" was true until this).
Doesn't require a real GOOGLE_API_KEY — just confirms the app factory wires
up correctly and /health responds, which is exactly what CI checks on every
push.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app


def test_health_endpoint():
    app = create_app()
    client = app.test_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_index_serves_frontend():
    app = create_app()
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Cindrix" in resp.data


def test_models_endpoint_lists_available_models():
    app = create_app()
    client = app.test_client()
    resp = client.get("/api/models")
    assert resp.status_code == 200
    models = resp.get_json()
    assert isinstance(models, list)
    assert len(models) > 0
    assert "id" in models[0] and "label" in models[0]


def test_chat_requires_a_message():
    app = create_app()
    client = app.test_client()
    resp = client.post("/api/chat", json={})
    assert resp.status_code == 400
