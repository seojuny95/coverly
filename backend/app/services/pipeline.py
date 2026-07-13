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

from app.services.coverage import extract_coverages
from app.services.parsing import parse_document
from app.services.rag.policy import index_policy_document
from app.services.summary import extract_policy_summary
from app.services.types import Coverage, ParsedDocument, PolicySummary


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
    parse: Callable[[bytes], ParsedDocument] = parse_document,
    summarize: Callable[[str], PolicySummary] = extract_policy_summary,
    extract: Callable[[ParsedDocument], tuple[list[Coverage], str]] = extract_coverages,
    index: Callable[[ParsedDocument], str | None] = index_policy_document,
) -> PipelineResult:
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
        session_id = index(doc)
    except Exception:
        session_id = None
    if session_id:
        result["문서세션ID"] = session_id
    return result
