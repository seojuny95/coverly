import logging
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app, create_app


def test_unknown_route_uses_the_common_safe_error_envelope() -> None:
    response = TestClient(app).get("/missing")

    assert response.status_code == 404
    request_id = response.headers["x-request-id"]
    UUID(request_id)
    assert response.json() == {
        "error": {
            "code": "HTTP_ERROR",
            "message": "요청한 내용을 찾을 수 없어요.",
            "request_id": request_id,
        }
    }


def test_unsupported_method_uses_the_common_safe_error_envelope() -> None:
    response = TestClient(app).delete("/health")

    assert response.status_code == 405
    request_id = response.headers["x-request-id"]
    UUID(request_id)
    assert response.json() == {
        "error": {
            "code": "HTTP_ERROR",
            "message": "지원하지 않는 요청 방식이에요.",
            "request_id": request_id,
        }
    }


def test_client_cannot_inject_a_request_id_into_logs_or_responses() -> None:
    response = TestClient(app).get(
        "/missing",
        headers={"x-request-id": "customer@example.com"},
    )

    request_id = response.headers["x-request-id"]
    UUID(request_id)
    assert request_id != "customer@example.com"
    assert response.json()["error"]["request_id"] == request_id


def test_http_exception_cannot_override_server_request_id() -> None:
    test_app = create_app()

    @test_app.get("/header-conflict")
    def header_conflict() -> None:
        raise HTTPException(
            status_code=418,
            headers={"x-request-id": "attacker-value"},
        )

    response = TestClient(test_app).get("/header-conflict")

    request_id = response.headers["x-request-id"]
    UUID(request_id)
    assert request_id != "attacker-value"
    assert response.json()["error"]["request_id"] == request_id


def test_unexpected_error_log_excludes_exception_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    test_app = create_app()
    private_value = "010-1234-5678 contract-123"

    @test_app.get("/unexpected-error")
    def unexpected_error() -> None:
        raise RuntimeError(private_value)

    with caplog.at_level(logging.ERROR):
        response = TestClient(test_app, raise_server_exceptions=False).get("/unexpected-error")

    assert response.status_code == 500
    assert private_value not in caplog.text
    assert "unexpected_server_error" in caplog.text
