from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_returns_200_and_expected_shape():
    response = client.get("/health")

    assert response.status_code == 200

    body = response.json()
    assert set(body.keys()) == {"status", "version"}
    assert body["status"] == "ok"
    assert isinstance(body["version"], str)
    assert body["version"]
