"""Policy-processing orchestrator: PDF bytes -> structured result.

Runs the pipeline stages in order (parse -> classify+summary -> coverage) and
assembles the response payload. HTTP concerns stay in the route; this layer is
plain-bytes-in, dict-out so it can be exercised without the web stack.

Every insurance type takes the same path — there is no product-specific branch.
Raises EmptyTextError when the PDF has no extractable text (the only hard-fail);
coverage failures degrade to 부분 inside extract_coverages.
"""

from collections.abc import Callable
from typing import NotRequired, TypedDict

from app.modules.policy.coverage.service import extract_coverages
from app.modules.policy.models import Coverage, ParsedDocument, PolicySummary
from app.modules.policy.parsing import parse_document
from app.modules.policy.summary.service import extract_policy_summary
from app.rag.policy.indexing import index_policy_document


class PipelineResult(TypedDict):
    기본정보: PolicySummary
    보장목록: list[Coverage]
    분석상태: str
    문자수: int
    문서세션ID: NotRequired[str]


class EmptyTextError(Exception):
    """The PDF yielded no extractable text; the route maps this to HTTP 422."""


def run_pipeline(
    pdf_bytes: bytes,
    *,
    password: str | None = None,
    parse: Callable[[bytes], ParsedDocument] = parse_document,
    summarize: Callable[[str], PolicySummary] = extract_policy_summary,
    extract: Callable[[ParsedDocument], tuple[list[Coverage], str]] = extract_coverages,
    index: Callable[[ParsedDocument], str | None] = index_policy_document,
) -> PipelineResult:
    if parse is parse_document:
        doc = parse_document(pdf_bytes, password=password)
    else:
        doc = parse(pdf_bytes)
    if not doc.text:
        raise EmptyTextError
    summary = summarize(doc.text)
    coverages, status = extract(doc)
    result: PipelineResult = {
        "기본정보": summary,
        "보장목록": coverages,
        "분석상태": status,
        "문자수": len(doc.text),
    }
    try:
        session_id = (
            index_policy_document(doc, sensitive_values=policy_sensitive_values(summary))
            if index is index_policy_document
            else index(doc)
        )
    except Exception:
        session_id = None
    if session_id:
        result["문서세션ID"] = session_id
    return result


def policy_sensitive_values(summary: PolicySummary) -> tuple[str, ...]:
    values = [
        summary.get("증권번호"),
        summary.get("계약자"),
        summary.get("피보험자"),
    ]
    vehicle = summary.get("차량정보")
    if vehicle is not None:
        values.append(vehicle.get("차량번호"))
    return tuple(value for value in values if value)
