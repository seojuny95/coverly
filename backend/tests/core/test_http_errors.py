from fastapi.testclient import TestClient

from app.main import app


def test_unknown_route_uses_the_common_safe_error_envelope() -> None:
    response = TestClient(app).get(
        "/missing",
        headers={"x-request-id": "missing-request"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "HTTP_ERROR",
            "message": "요청한 내용을 찾을 수 없어요.",
            "request_id": "missing-request",
        }
    }


def test_unsupported_method_uses_the_common_safe_error_envelope() -> None:
    response = TestClient(app).delete(
        "/health",
        headers={"x-request-id": "method-request"},
    )

    assert response.status_code == 405
    assert response.json() == {
        "error": {
            "code": "HTTP_ERROR",
            "message": "지원하지 않는 요청 방식이에요.",
            "request_id": "method-request",
        }
    }
