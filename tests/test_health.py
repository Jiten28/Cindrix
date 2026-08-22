"""Smoke tests for the app factory and the basic endpoints. No API key needed."""

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


def test_config_reports_stt_provider_and_knowledge_base_state():
    """The deployment-diagnostic endpoint. Both fields must always be present —
    they're how a deployed instance is checked for a silently-unset
    SARVAM_API_KEY or an index that didn't load."""
    app = create_app()
    client = app.test_client()
    resp = client.get("/api/config")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["sttProvider"] in {"sarvam", "webspeech"}
    kb = body["knowledgeBase"]
    assert isinstance(kb["loaded"], bool)
    assert isinstance(kb["chunks"], int)
    # Consistency, whichever environment this runs in: an index that didn't
    # load must report zero chunks, and a loaded one must report some.
    assert kb["loaded"] == (kb["chunks"] > 0)


def test_config_never_leaks_api_keys():
    app = create_app()
    resp = app.test_client().get("/api/config")
    body = resp.get_data(as_text=True).lower()
    for secret in ("api_key", "apikey", "sk-", "subscription"):
        assert secret not in body
