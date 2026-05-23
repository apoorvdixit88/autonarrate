from fastapi.testclient import TestClient

from app import __version__
from app.main import app


client = TestClient(app)


def test_health_returns_ok_and_version():
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok", "version": __version__}


def test_health_version_is_non_empty_string():
    response = client.get("/health")

    body = response.json()
    assert isinstance(body["version"], str)
    assert body["version"]
