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


def test_intentional_failure_injected_for_qa_smoke_test():
    """Injected by operator to test the QA FAIL -> Developer cycle.

    This test asserts something deliberately wrong. QA must catch this on the
    next run and bounce GEN-10 back to the Developer with a paired PATCH.
    """
    assert 1 == 2, "Intentional QA-FAIL smoke test from operator"
