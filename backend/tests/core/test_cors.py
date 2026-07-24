from uuid import UUID

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.core.config import get_settings
from app.main import app, create_app


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


def test_unconfigured_frontend_origin_cannot_preflight_policy_upload() -> None:
    client = TestClient(app)

    response = client.options(
        "/policies/parse",
        headers={
            "Origin": "http://localhost:3001",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_configured_frontend_origin_can_preflight_policy_upload(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "BACKEND_CORS_ORIGINS",
        "http://localhost:3000, https://allowed-origin.test",
    )
    get_settings.cache_clear()
    client = TestClient(create_app())

    response = client.options(
        "/policies/parse",
        headers={
            "Origin": "https://allowed-origin.test",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://allowed-origin.test"
    get_settings.cache_clear()


def test_unexpected_error_keeps_cors_and_uses_safe_common_envelope() -> None:
    test_app = create_app()

    @test_app.get("/_test/unexpected-error")
    def raise_unexpected_error() -> None:
        raise RuntimeError("sensitive implementation detail")

    response = TestClient(test_app).get(
        "/_test/unexpected-error",
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["access-control-expose-headers"] == ("X-Request-ID, Retry-After")
    request_id = response.headers["x-request-id"]
    UUID(request_id)
    assert response.json() == {
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "예기치 않은 오류가 발생했어요. 잠시 후 다시 시도해주세요.",
            "request_id": request_id,
        }
    }
    assert "sensitive implementation detail" not in response.text
