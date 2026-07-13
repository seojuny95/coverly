from app.services.policy.models import Coverage, ParsedDocument, Table


def test_parsed_document_is_frozen_and_carries_text_and_tables() -> None:
    table: Table = (("담보명", "가입금액"), ("암진단비", "3,000만원"))
    doc = ParsedDocument(text="plain", layout_text="laid  out", tables=(table,))

    assert doc.text == "plain"
    assert doc.layout_text == "laid  out"
    assert doc.tables[0][1][0] == "암진단비"

    try:
        doc.text = "mutated"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("ParsedDocument must be frozen")


def test_coverage_shape() -> None:
    coverage: Coverage = {
        "담보명": "암진단비",
        "가입금액": "3,000만원",
        "보장내용": None,
        "해설": None,
    }
    assert set(coverage) == {"담보명", "가입금액", "보장내용", "해설"}


def test_coverage_optional_type_field() -> None:
    tagged: Coverage = {
        "담보명": "안전운전할인특약",
        "가입금액": "",
        "보장내용": None,
        "해설": None,
        "유형": "부가",
    }
    untagged: Coverage = {"담보명": "암진단비", "가입금액": "1억원", "보장내용": None, "해설": None}
    assert tagged["유형"] == "부가"
    assert untagged.get("유형", "담보") == "담보"


def test_vehicle_info_shape() -> None:
    from app.services.policy.models import PolicyCoreSummary, VehicleInfo

    vehicle: VehicleInfo = {"차량명": "아이오닉5", "차량번호": "TEST-PLATE-001", "연식": "2024"}
    summary: PolicyCoreSummary = {"차량정보": vehicle}
    assert summary["차량정보"]["차량번호"] == "TEST-PLATE-001"
