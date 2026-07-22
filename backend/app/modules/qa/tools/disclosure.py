"""Agent SDK tool for official insurer/association disclosure links."""

from agents import RunContextWrapper, function_tool

from app.modules.qa.context import QaContext
from app.modules.qa.facts import disclosure as disclosure_facts


@function_tool
def get_disclosure_links(
    wrapper: RunContextWrapper[QaContext],
) -> disclosure_facts.DisclosureLinksResult:
    """사용자가 가입한 보험사·협회의 공식 약관·공시 포털 링크를 확인합니다.

    이 도구는 사용자가 업로드한 증권에서 이미 추출된 텍스트를 검색하는
    retrieve_policy_terms와는 다릅니다. retrieve_policy_terms가 증권 원문에서
    답을 찾지 못했거나, 사용자가 "약관 원문은 어디서 보나요?", "공식 약관
    링크 있어요?"처럼 출처 자체를 직접 확인하고 싶어 할 때 이 도구를
    사용하세요. 반환되는 URL은 검증된 참조 데이터에서 그대로 가져온 것이며,
    있는 그대로만 안내하고 URL을 새로 만들거나 추측하지 마세요.
    """

    return disclosure_facts.get_disclosure_link_facts(wrapper.context.policies)
