"""Agent SDK tool for verified insurer claim channels."""

from agents import RunContextWrapper, function_tool

from app.modules.counsel.context import CounselContext
from app.modules.counsel.facts import claims as claim_facts
from app.modules.counsel.facts.claims import get_claim_channel_facts

ClaimChannelsResult = claim_facts.ClaimChannelsResult

# Deliberately not stripped: every field this tool returns (customer-center
# numbers, app names, claim links) comes from Coverly's own verified reference
# data (app/modules/reference_data), never from an uploaded PDF. Coverage names
# passed in only steer which insurer's reference data is looked up; they never
# reach the output. If a future field here starts carrying user-uploaded free
# text, it needs its own stripping — this exemption does not cover it.


@function_tool
def get_claim_channels(
    wrapper: RunContextWrapper[CounselContext],
    coverage_names: list[str],
) -> ClaimChannelsResult:
    """청구와 관련된 담보의 보험사 고객센터·앱·청구 링크를 확인합니다.

    반환되는 연락처·링크는 검증된 참조 데이터에서만 나오며, 직접 지어내지
    마세요. 이 도구는 청구 채널만 알려주며 실제 지급 여부는 확정하지
    않습니다.

    Args:
        coverage_names: 청구와 관련된 정확한 담보명 목록입니다. unmatched에
            candidates가 있으면, 그중 정확한 이름으로 다시 호출하세요 —
            채널을 못 찾았다고 바로 답하지 마세요.
    """

    return get_claim_channel_facts(wrapper.context.policies, coverage_names)
