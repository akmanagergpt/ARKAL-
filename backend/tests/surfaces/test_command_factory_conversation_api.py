from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from arkali.surfaces.command.factory import _build_factory_router


def test_conversation_uses_guide_without_submitting_factory_goal() -> None:
    submissions: list[object] = []

    def sessions():
        yield object()

    def submitter(session, body):
        submissions.append((session, body))
        raise AssertionError("conversation must not enqueue generation")

    def guide(body):
        assert body.messages[-1].content == "Doğal Türkçe fikrim"
        return {
            "assistant_message": "Önce kullanıcıları netleştirelim.",
            "questions": ["Kaç kullanıcı olacak?"],
            "proposed_goal_text": None,
            "model_id": "qwen2.5-coder:14b",
        }

    app = FastAPI()
    app.include_router(_build_factory_router(sessions, lambda operation: None, "WRITE", submitter, guide))
    response = TestClient(app).post("/api/factory/conversation", json={
        "messages": [{"role": "user", "content": "Doğal Türkçe fikrim"}],
    })
    assert response.status_code == 200
    assert response.json()["model_id"] == "qwen2.5-coder:14b"
    assert submissions == []


def test_conversation_requires_a_bounded_valid_history() -> None:
    def sessions():
        yield object()

    app = FastAPI()
    app.include_router(_build_factory_router(
        sessions, lambda operation: None, "WRITE", lambda session, body: None,
        lambda body: {},
    ))
    response = TestClient(app).post("/api/factory/conversation", json={"messages": []})
    assert response.status_code == 422
