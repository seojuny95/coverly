from fastapi.testclient import TestClient

from app.main import app
from app.modules.portfolio.session.dependencies import get_portfolio_session_service


def test_openapi_exposes_typed_json_api_contracts() -> None:
    schema = app.openapi()
    paths = schema["paths"]

    parse_responses = paths["/policies/parse"]["post"]["responses"]
    assert parse_responses["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PolicyParseResponse"
    }
    assert parse_responses["400"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ApiErrorResponse"
    }
    unprocessable_schema = parse_responses["422"]["content"]["application/json"]["schema"]
    assert unprocessable_schema == {"$ref": "#/components/schemas/ApiErrorResponse"}

    session_responses = paths["/portfolio/sessions"]["post"]["responses"]
    assert session_responses["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PortfolioSessionResponse"
    }

    summary_responses = paths["/portfolio/summary"]["post"]["responses"]
    assert summary_responses["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PortfolioCoverageSummary"
    }


def test_policy_parse_openapi_schema_matches_public_response() -> None:
    schemas = app.openapi()["components"]["schemas"]
    parse_schema = schemas["PolicyParseResponse"]

    assert set(parse_schema["required"]) == {
        "status",
        "documentId",
        "문자수",
        "기본정보",
        "보장목록",
        "분석상태",
    }
    assert parse_schema["properties"]["status"]["const"] == "accepted"
    assert parse_schema["properties"]["documentId"]["format"] == "uuid"
    assert set(parse_schema["properties"]["분석상태"]["enum"]) == {"완료", "부분"}
    assert "문서세션ID" not in parse_schema["properties"]

    upload_body_ref = app.openapi()["paths"]["/policies/parse"]["post"]["requestBody"]["content"][
        "multipart/form-data"
    ]["schema"]["$ref"]
    upload_body = schemas[upload_body_ref.rsplit("/", maxsplit=1)[-1]]
    assert "documentId" in upload_body["required"]
    assert upload_body["properties"]["documentId"]["format"] == "uuid"
    assert upload_body["properties"]["file"] == {
        "type": "string",
        "format": "binary",
        "contentMediaType": "application/pdf",
        "title": "File",
        "description": (
            "PDF document only. The server verifies the %PDF signature and accepts at most 10 MiB."
        ),
        "x-maxBytes": 10 * 1024 * 1024,
    }

    coverage_schema = schemas["Coverage"]
    assert {"가입금액상태", "설명근거", "유형"} <= set(coverage_schema["required"])
    assert set(coverage_schema["properties"]["가입금액상태"]["enum"]) == {
        "confirmed",
        "needs_review",
        "not_applicable",
    }
    assert set(coverage_schema["properties"]["설명근거"]["enum"]) == {
        "policy_wording",
        "generated_guidance",
        "none",
    }
    assert set(coverage_schema["properties"]["유형"]["enum"]) == {"담보", "부가"}
    policy_summary_schema = schemas["PolicySummary"]
    assert {"보험분류", "상품태그"} <= set(policy_summary_schema["required"])
    assert set(policy_summary_schema["properties"]["보험분류"]["enum"]) == {
        "생명보험",
        "제3보험",
        "손해보험",
        "미분류",
    }


def test_api_error_openapi_schema_matches_error_handler_payload() -> None:
    schemas = app.openapi()["components"]["schemas"]

    assert set(schemas["ApiErrorResponse"]["required"]) == {"error"}
    assert set(schemas["ApiErrorDetail"]["required"]) == {
        "code",
        "message",
        "request_id",
    }
    assert set(schemas["ApiErrorCode"]["enum"]) == {
        "PDF_TOO_LARGE",
        "INVALID_PDF",
        "PDF_PASSWORD_REQUIRED",
        "PDF_PASSWORD_INCORRECT",
        "PDF_TEXT_EXTRACTION_FAILED",
        "reference_data_unavailable",
        "INVALID_PORTFOLIO_SESSION",
        "PORTFOLIO_DOCUMENT_LIMIT_EXCEEDED",
        "COUNSEL_TURN_LIMIT_REACHED",
        "POLICY_UPLOAD_CANCELLED",
        "portfolio_session_unavailable",
        "INVALID_POLICY_SELECTION",
        "REQUEST_VALIDATION_ERROR",
        "INVALID_MULTIPART_REQUEST",
    }


def test_openapi_exposes_qa_sse_events_the_client_must_validate() -> None:
    # The frontend generates its stream validator from this schema, so the event
    # union has to be reachable from the route rather than only from the code.
    responses = app.openapi()["paths"]["/qa/stream"]["post"]["responses"]

    assert set(responses["200"]["content"]) == {"text/event-stream"}
    stream_schema = responses["200"]["content"]["text/event-stream"]["schema"]
    assert {item["$ref"] for item in stream_schema["oneOf"]} == {
        "#/components/schemas/QaMetaEvent",
        "#/components/schemas/QaDeltaEvent",
        "#/components/schemas/QaEndEvent",
    }
    assert stream_schema["discriminator"]["propertyName"] == "type"
    assert set(responses["403"]["content"]) == {"application/json"}
    assert set(responses["422"]["content"]) == {"application/json"}


def test_request_validation_uses_common_error_envelope() -> None:
    app.dependency_overrides[get_portfolio_session_service] = lambda: object()
    try:
        response = TestClient(app).post(
            "/qa/stream",
            headers={"x-request-id": "validation-request"},
            json={"question": "", "history": [], "session_id": "portfolio-token"},
        )
    finally:
        app.dependency_overrides.pop(get_portfolio_session_service, None)

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "REQUEST_VALIDATION_ERROR",
            "message": "요청 내용을 확인해주세요.",
            "request_id": "validation-request",
        }
    }


def test_openapi_reuses_shared_claim_and_reference_source_contracts() -> None:
    schemas = app.openapi()["components"]["schemas"]

    claim_schema_names = {name for name in schemas if name.startswith("ClaimChannel")}
    assert claim_schema_names == {
        "ClaimChannelBlock",
        "ClaimChannelInsurer",
        "ClaimChannelLink",
        "ClaimChannelMedicalIndemnity",
    }
    claim_channel_schema = schemas["PortfolioCoverageSummary"]["properties"]["claim_channels"]
    assert claim_channel_schema["anyOf"][0] == {"$ref": "#/components/schemas/ClaimChannelBlock"}

    premium_schema = schemas["PremiumBenchmark"]
    assert premium_schema["properties"]["income_source"] == {
        "$ref": "#/components/schemas/ReferenceSource"
    }
    assert premium_schema["properties"]["guide_source"] == {
        "$ref": "#/components/schemas/ReferenceSource"
    }
    assert "PremiumBenchmarkSource" not in schemas


def test_qa_stream_declares_the_turn_limit_response() -> None:
    responses = app.openapi()["paths"]["/qa/stream"]["post"]["responses"]

    assert "429" in responses
    assert set(responses["429"]["content"]) == {"application/json"}
