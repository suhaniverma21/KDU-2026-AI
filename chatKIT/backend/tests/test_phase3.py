from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app, settings


client = TestClient(app)


def login_and_session(user_id: str, thread_id: str) -> tuple[dict[str, str], str]:
    login_response = client.post("/api/dev/login", json={"user_id": user_id})
    assert login_response.status_code == 200
    cookies = login_response.cookies
    session_response = client.post("/api/session", json={"thread_id": thread_id}, cookies=cookies)
    assert session_response.status_code == 200
    client_secret = session_response.json()["client_secret"]
    return cookies, client_secret


def test_agent_takeover_switches_thread_to_human_mode() -> None:
    cookies, client_secret = login_and_session("usr_alice", "thread_alice_paris")

    response = client.post(
        "/api/agent/takeover",
        json={"thread_id": "thread_alice_paris", "agent_name": "Maya"},
        headers={"x-agent-key": settings.agent_demo_key},
    )
    assert response.status_code == 200
    assert response.json()["thread_mode"] == "human"

    stream_response = client.post(
        "/api/chat/message",
        json={"thread_id": "thread_alice_paris", "client_secret": client_secret, "text": "I still need help"},
        cookies=cookies,
    )
    assert stream_response.status_code == 200
    assert "event: human_mode" in stream_response.text


def test_agent_message_reaches_user_websocket() -> None:
    cookies, _ = login_and_session("usr_bob", "thread_bob_tokyo")
    client.post(
        "/api/agent/takeover",
        json={"thread_id": "thread_bob_tokyo", "agent_name": "Maya"},
        headers={"x-agent-key": settings.agent_demo_key},
    )

    with client.websocket_connect("/ws/handoff/thread_bob_tokyo?role=user", cookies=cookies) as websocket:
        connected = websocket.receive_json()
        assert connected["event"] == "connected"

        message_response = client.post(
            "/api/agent/message",
            json={"thread_id": "thread_bob_tokyo", "agent_name": "Maya", "text": "I can take over from here."},
            headers={"x-agent-key": settings.agent_demo_key},
        )
        assert message_response.status_code == 200

        event = websocket.receive_json()
        assert event["event"] == "human_agent_message"
        assert event["message"]["content"].startswith("Maya:")


def test_return_to_ai_restores_ai_mode() -> None:
    client.post(
        "/api/agent/takeover",
        json={"thread_id": "thread_alice_delhi", "agent_name": "Maya"},
        headers={"x-agent-key": settings.agent_demo_key},
    )
    response = client.post(
        "/api/agent/return-to-ai",
        json={"thread_id": "thread_alice_delhi", "summary": "Collected passenger details.", "agent_name": "Maya"},
        headers={"x-agent-key": settings.agent_demo_key},
    )
    assert response.status_code == 200
    assert response.json()["thread_mode"] == "ai"
