from fastapi.testclient import TestClient

from luther.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "luther-core"}


def test_receive_message_valid():
    response = client.post(
        "/webhook/message",
        json={
            "sender": "972501234567@s.whatsapp.net",
            "body": "שלום Luther",
            "message_type": "text",
            "timestamp": 1715600000,
        },
        headers={"X-Gateway-Secret": "shared-secret-between-services"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert data["sender"] == "972501234567@s.whatsapp.net"


def test_receive_message_no_auth():
    response = client.post(
        "/webhook/message",
        json={
            "sender": "972501234567@s.whatsapp.net",
            "body": "test",
            "message_type": "text",
            "timestamp": 1715600000,
        },
    )
    assert response.status_code == 401
