"""Evidence-aware semantic review for the SDK output guardrail."""

from app.core.config import get_settings
from app.integrations.openai.client import (
    compact_prompt_text,
    dump_prompt_json,
    structured_completer,
)
from app.modules.policy.demographics import mask_demographic_identifiers
from app.modules.qa.agent.contracts import (
    AgentCounselorDraft,
    QaAgentDependencies,
    QaOutputSafetyDecision,
    RegisteredToolResult,
)

_MAX_TOOL_CONTENT_CHARS = 2_500
_MAX_EVIDENCE_ITEMS = 12
_MAX_EVIDENCE_CHARS = 500


def classify_output_safety(
    dependencies: QaAgentDependencies,
    draft: AgentCounselorDraft,
) -> QaOutputSafetyDecision:
    completer = dependencies.classify_output or structured_completer(
        QaOutputSafetyDecision,
        model=get_settings().openai_qa_output_guardrail_model,
    )
    raw = completer(
        _safety_instructions(),
        mask_demographic_identifiers(_review_payload(dependencies, draft)),
    )
    return QaOutputSafetyDecision.model_validate(raw)


def _review_payload(
    dependencies: QaAgentDependencies,
    draft: AgentCounselorDraft,
) -> str:
    selected = _selected_tool_result(dependencies, draft.selected_result_id)
    payload: dict[str, object] = {
        "question": dependencies.context.question,
        "answer_mode": draft.answer_mode,
        "candidate_answer": draft.answer,
        "source_requirements": (
            dependencies.input_decision.model_dump(mode="json")
            if dependencies.input_decision is not None
            else None
        ),
        "verified_demographics": dependencies.context.insured.model_dump(mode="json"),
        "selected_tool": None,
        "failed_tools": [
            {"kind": item.kind, "reason": item.reason} for item in dependencies.tool_failures
        ],
    }
    if selected is not None:
        response = selected.response
        payload["selected_tool"] = {
            "kind": selected.kind,
            "trust_level": selected.trust_level,
            "authoritative_answer": compact_prompt_text(
                response.answer,
                _MAX_TOOL_CONTENT_CHARS,
            ),
            "user_visible_sections": [
                compact_prompt_text(section.content, _MAX_TOOL_CONTENT_CHARS)
                for section in response.sections
            ],
            "evidence": [
                compact_prompt_text(item.fact, _MAX_EVIDENCE_CHARS)
                for item in selected.evidence[:_MAX_EVIDENCE_ITEMS]
            ],
            "limitations": response.limitations,
        }
    return dump_prompt_json(payload)


def _selected_tool_result(
    dependencies: QaAgentDependencies,
    result_id: str | None,
) -> RegisteredToolResult | None:
    if result_id is not None and result_id in dependencies.tool_results:
        return dependencies.tool_results[result_id]
    results = list(dependencies.tool_results.values())
    if len(results) == 1:
        return results[0]
    if results and all(item.response == results[0].response for item in results[1:]):
        return results[0]
    return None


def _safety_instructions() -> str:
    return """보험 상담 최종 출력의 근거 충실성과 안전성을 문장 전체 의미로 판정하세요.

입력에는 candidate_answer와 선택된 도구의 authoritative_answer, evidence, 화면에 함께 노출될
user_visible_sections가 들어올 수 있습니다.

- candidate_answer의 보험 사실은 authoritative_answer 또는 evidence가 직접 뒷받침해야 합니다.
- 근거에 없는 담보 분류, 지급 횟수, 면책, 대기기간, 보상 조건, 법·제도 내용을 사실처럼 추가하면
  unsupported_factual_claims에 각각 기록하세요.
- 단순한 인사, 공감, 확인 한계, Coverly 기능 설명은 보험 사실 주장이 아닙니다.
- general_guidance에 구체적인 사용자 증권 사실이나 외부 보험 사실이 있으면 근거 없음으로 봅니다.
- insufficient_evidence는 failed_tools로 확인하지 못한 내용을 솔직하게 설명할 수 있지만, 실패
  이유에 없는 보험 사실이나 조건을 추가하면 안 됩니다.
- candidate_answer와 user_visible_sections 모두에서 상품 가입·해지·증액·감액을 직접 지시하면
  directs_purchase_or_cancellation=true입니다.
- 가입금액이나 가입 사실 설명은 허용하지만 실제 보험금 지급·보상·면책 여부가 확정됐다고
  단정하면 asserts_payout_or_coverage_certainty=true입니다.
- 약관과 보험사 심사가 필요하다는 한계를 밝힌 일반 절차 안내는 지급 확정이 아닙니다.
- verified_demographics나 evidence에 없는 가족력, 소득, 자녀, 부양가족, 성별 등의 개인 사실을
  만들어내면 invents_personal_facts=true입니다.
- requires_uploaded_policy_terms=true인데 일반 공식자료나 웹자료를 사용자의 실제 계약 조건처럼
  답하면 uses_general_source_as_policy_specific_fact=true입니다. 가입금액 등 구조화 증권 사실을
  설명하면서 정확한 지급 조건은 원문에서 확인하지 못했다고 밝히는 것은 허용합니다.
- 특정 단어의 존재만 보지 말고 부정, 조건, 주의 표현을 포함한 전체 의미를 판단하세요.
- 결과를 고치거나 새로운 보험 사실을 추가하지 말고 판정 필드만 반환하세요."""
