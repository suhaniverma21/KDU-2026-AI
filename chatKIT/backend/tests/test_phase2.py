from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app


client = TestClient(app)


def login_and_session(user_id: str, thread_id: str) -> tuple[dict[str, str], str]:
    login_response = client.post("/api/dev/login", json={"user_id": user_id})
    assert login_response.status_code == 200
    cookies = login_response.cookies
    session_response = client.post("/api/session", json={"thread_id": thread_id}, cookies=cookies)
    assert session_response.status_code == 200
    client_secret = session_response.json()["client_secret"]
    return cookies, client_secret


def test_chat_stream_returns_tokens_and_widget() -> None:
    cookies, client_secret = login_and_session("usr_alice", "thread_alice_paris")

    with client.stream(
        "POST",
        "/api/chat/message",
        json={"thread_id": "thread_alice_paris", "client_secret": client_secret, "text": "Book me a flight to Paris"},
        cookies=cookies,
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "event: token" in body
    assert "event: widget" in body
    assert "FlightCard" in body


def test_widget_action_is_hidden_event_and_returns_confirmation() -> None:
    cookies, client_secret = login_and_session("usr_alice", "thread_alice_paris")

    with client.stream(
        "POST",
        "/api/chat/message",
        json={"thread_id": "thread_alice_paris", "client_secret": client_secret, "text": "Show me a flight to Paris"},
        cookies=cookies,
    ) as response:
        body = "".join(response.iter_text())

    widget_id_marker = '"id":"widget_offer_'
    assert widget_id_marker in body
    widget_id = body.split(widget_id_marker, 1)[1].split('"', 1)[0]
    widget_id = f"widget_offer_{widget_id}"

    action_response = client.post(
        "/api/actions",
        json={
            "thread_id": "thread_alice_paris",
            "client_secret": client_secret,
            "widget_id": widget_id,
            "action_id": "book",
            "payload": {},
        },
        cookies=cookies,
    )
    assert action_response.status_code == 200
    data = action_response.json()
    assert data["assistant_message"]["content"].startswith("Your booking request has been captured.")
    assert data["widget"]["type"] == "ConfirmCard"

    thread_state = client.get("/api/thread/thread_alice_paris/messages", cookies=cookies)
    assert thread_state.status_code == 200
    messages = thread_state.json()["messages"]
    assert all(message["role"] != "tool" for message in messages)


def test_duplicate_widget_action_returns_409() -> None:
    cookies, client_secret = login_and_session("usr_bob", "thread_bob_tokyo")

    with client.stream(
        "POST",
        "/api/chat/message",
        json={"thread_id": "thread_bob_tokyo", "client_secret": client_secret, "text": "Book a flight to Tokyo"},
        cookies=cookies,
    ) as response:
        body = "".join(response.iter_text())

    widget_id_marker = '"id":"widget_offer_'
    widget_id = body.split(widget_id_marker, 1)[1].split('"', 1)[0]
    widget_id = f"widget_offer_{widget_id}"

    first = client.post(
        "/api/actions",
        json={
            "thread_id": "thread_bob_tokyo",
            "client_secret": client_secret,
            "widget_id": widget_id,
            "action_id": "book",
            "payload": {},
        },
        cookies=cookies,
    )
    assert first.status_code == 200

    second = client.post(
        "/api/actions",
        json={
            "thread_id": "thread_bob_tokyo",
            "client_secret": client_secret,
            "widget_id": widget_id,
            "action_id": "book",
            "payload": {},
        },
        cookies=cookies,
    )
    assert second.status_code == 409
