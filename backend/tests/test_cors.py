from fastapi.testclient import TestClient

from app.main import app


def test_local_frontend_can_preflight_policy_upload() -> None:
    client = TestClient(app)

    response = client.options(
        "/policies/parse",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
