from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_version_returns_200_and_expected_shape():
    response = client.get("/version")

    assert response.status_code == 200

    body = response.json()
    assert set(body.keys()) == {"version"}
    assert isinstance(body["version"], str)
    assert body["version"]
