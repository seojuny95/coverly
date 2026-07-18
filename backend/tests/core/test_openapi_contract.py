from app.main import app


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
    assert {item["$ref"] for item in unprocessable_schema["anyOf"]} == {
        "#/components/schemas/ApiErrorResponse",
        "#/components/schemas/RequestValidationErrorResponse",
    }

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
    assert set(parse_schema["properties"]["분석상태"]["enum"]) == {"완료", "부분"}
    assert "문서세션ID" not in parse_schema["properties"]


def test_api_error_openapi_schema_matches_error_handler_payload() -> None:
    schemas = app.openapi()["components"]["schemas"]

    assert set(schemas["ApiErrorResponse"]["required"]) == {"error"}
    assert set(schemas["ApiErrorDetail"]["required"]) == {
        "code",
        "message",
        "request_id",
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
