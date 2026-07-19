"""Agent SDK tool for verified insurer claim channels."""

from agents import RunContextWrapper, function_tool
from pydantic import BaseModel

from app.modules.counsel.agent.tools.coverages import (
    UnmatchedCoverageName,
    match_coverage_names,
)
from app.modules.counsel.context import CounselContext
from app.modules.reference_data.claim_channels import claim_channel_block
from app.modules.reference_data.contracts import ClaimChannelBlock


class ClaimChannelsResult(BaseModel):
    channels: ClaimChannelBlock
    unmatched: list[UnmatchedCoverageName]


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

    matches, unmatched = match_coverage_names(wrapper.context.policies, coverage_names)
    insurers = [match.보험사 for match in matches if match.보험사]
    channels = claim_channel_block(
        list(dict.fromkeys(insurers)),
        include_medical_indemnity_service=False,
    )
    return ClaimChannelsResult(channels=channels, unmatched=unmatched)
