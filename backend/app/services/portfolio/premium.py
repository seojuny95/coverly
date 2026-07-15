"""Deterministic monthly-premium aggregation at policy level.

Only 월납 premiums are summed; annual/lump-sum/unknown are reported separately
rather than converted, to avoid inventing a monthly figure.
"""

from app.schemas.portfolio import PolicyInput, PremiumOverview, PremiumPolicyItem

_MONTHLY_CYCLE = "월납"


def summarize_premiums(policies: list[PolicyInput]) -> PremiumOverview:
    items: list[PremiumPolicyItem] = []
    monthly_total = 0
    monthly_policy_count = 0
    unconfirmed_policy_count = 0

    for policy in policies:
        premium = policy.기본정보.보험료
        cycle = premium.납입주기 if premium else None
        amount = premium.금액 if premium else None

        is_monthly = cycle == _MONTHLY_CYCLE and amount is not None
        monthly_amount = amount if is_monthly else None

        if monthly_amount is not None:
            monthly_total += monthly_amount
            monthly_policy_count += 1
        else:
            unconfirmed_policy_count += 1

        items.append(
            PremiumPolicyItem(
                policy_id=policy.id,
                insurer=policy.기본정보.보험사,
                product_name=policy.기본정보.상품명,
                monthly_amount=monthly_amount,
                cycle=cycle,
            )
        )

    return PremiumOverview(
        monthly_total=monthly_total,
        monthly_policy_count=monthly_policy_count,
        unconfirmed_policy_count=unconfirmed_policy_count,
        items=sorted(
            items,
            key=lambda item: (
                item.policy_id or "",
                item.insurer or "",
                item.product_name or "",
                item.monthly_amount or -1,
                item.cycle or "",
            ),
        ),
    )
