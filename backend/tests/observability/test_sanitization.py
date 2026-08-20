from app.observability.sanitization import sanitize_trace_payload


def test_trace_payload_masks_pii_and_drops_secret_keys() -> None:
    payload = {
        "question": "주민번호 900101-1234567, 전화 010-1234-5678, 메일 a@b.com",
        "session_token": "v1.secret-token",
        "nested": {
            "address": "주소: 서울시 강남구 테헤란로 123",
            "api_key": "sk-secret",
        },
    }

    sanitized = sanitize_trace_payload(payload)
    rendered = str(sanitized)

    assert "900101-1234567" not in rendered
    assert "010-1234-5678" not in rendered
    assert "a@b.com" not in rendered
    assert "서울시 강남구 테헤란로 123" not in rendered
    assert "v1.secret-token" not in rendered
    assert "sk-secret" not in rendered
    assert "session_token" not in rendered
    assert "api_key" not in rendered


def test_trace_payload_keeps_allowed_operational_metadata() -> None:
    sanitized = sanitize_trace_payload(
        {
            "matched": True,
            "evidence_count": 2,
            "source_ids": ["official-source"],
            "citation_labels": ["표준약관 제1조"],
            "usage_metadata": {
                "input_tokens": 120,
                "output_tokens": 30,
                "total_tokens": 150,
            },
        }
    )

    assert sanitized == {
        "matched": True,
        "evidence_count": 2,
        "source_ids": ["official-source"],
        "citation_labels": ["표준약관 제1조"],
        "usage_metadata": {
            "input_tokens": 120,
            "output_tokens": 30,
            "total_tokens": 150,
        },
    }


def test_agent_trace_payload_keeps_masked_tool_results() -> None:
    sanitized = sanitize_trace_payload(
        {
            "input": [
                {"role": "user", "content": "전화번호 010-1234-5678"},
                {
                    "type": "function_call_output",
                    "call_id": "call-1",
                    "output": "증권 원문 주소: 서울시 강남구 테헤란로 123",
                },
            ]
        }
    )

    rendered = str(sanitized)
    assert "010-1234-5678" not in rendered
    assert "서울시 강남구 테헤란로 123" not in rendered
    assert "function_call_output" in rendered
    assert "증권 원문" in rendered
    assert "[주소]" in rendered


def test_unknown_trace_value_is_masked_after_string_conversion() -> None:
    class TraceValue:
        def __str__(self) -> str:
            return "연락처 010-1234-5678"

    sanitized = sanitize_trace_payload({"custom": TraceValue()})

    assert sanitized == {"custom": "연락처 [전화번호]"}
