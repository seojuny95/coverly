"""Agent SDK tool for verified insurer claim channels."""

from agents import RunContextWrapper, function_tool

from app.modules.counsel.context import CounselContext
from app.modules.reference_data.claim_channels import claim_channel_block
from app.modules.reference_data.contracts import ClaimChannelBlock


@function_tool
def get_claim_channels(
    wrapper: RunContextWrapper[CounselContext],
    coverage_names: list[str],
) -> ClaimChannelBlock:
    """청구와 관련된 담보의 보험사 고객센터·앱·청구 링크를 확인합니다.

    반환되는 연락처·링크는 검증된 참조 데이터에서만 나오며, 직접 지어내지
    마세요. 이 도구는 청구 채널만 알려주며 실제 지급 여부는 확정하지
    않습니다.

    Args:
        coverage_names: 청구와 관련된 정확한 담보명 목록입니다. 특정 담보가
            불명확하면 list_coverage_names로 먼저 확인하세요.
    """

    requested = {name.strip() for name in coverage_names}
    insurers = [
        policy.기본정보.보험사
        for policy in wrapper.context.policies
        if policy.기본정보.보험사
        if any(coverage.담보명 in requested for coverage in policy.보장목록)
    ]
    return claim_channel_block(
        list(dict.fromkeys(insurers)),
        include_medical_indemnity_service=False,
    )
