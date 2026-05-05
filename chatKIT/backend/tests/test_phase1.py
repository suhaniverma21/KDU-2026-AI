from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app


client = TestClient(app)


def login_as(user_id: str) -> dict[str, str]:
    response = client.post("/api/dev/login", json={"user_id": user_id})
    assert response.status_code == 200
    return response.cookies


def test_session_returns_client_secret_for_owned_thread() -> None:
    cookies = login_as("usr_alice")
    response = client.post("/api/session", json={"thread_id": "thread_alice_paris"}, cookies=cookies)
    assert response.status_code == 200
    data = response.json()
    assert data["client_secret"].startswith("ck_local_")
    assert data["thread_id"] == "thread_alice_paris"


def test_cross_thread_access_returns_403() -> None:
    cookies = login_as("usr_alice")
    response = client.post("/api/session", json={"thread_id": "thread_bob_tokyo"}, cookies=cookies)
    assert response.status_code == 403
    assert response.text == ""


def test_unknown_thread_returns_404() -> None:
    cookies = login_as("usr_bob")
    response = client.post("/api/session", json={"thread_id": "thread_missing"}, cookies=cookies)
    assert response.status_code == 404
