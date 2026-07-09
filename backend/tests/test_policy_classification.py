from app.services.policy.classification import classify_policy


def test_classify_policy_detects_auto_policy_from_product_and_coverages() -> None:
    result = classify_policy(
        text="""
        삼성화재해상보험(주)
        보험종목 개인용자동차보험
        대인배상I 대인배상II 대물배상 자기차량손해 무보험차상해
        """,
        product_name="개인용자동차보험",
    )

    assert result == {
        "보험분류": "자동차",
        "상품태그": ["자동차"],
    }


def test_classify_policy_keeps_driver_policy_out_of_auto_bucket() -> None:
    result = classify_policy(
        text="""
        DB손해보험
        무배당 운전자보험
        자동차보험에 가입되어 있어도 별도 보장됩니다.
        벌금, 변호사선임비용, 교통사고처리지원금
        """,
        product_name="무배당 운전자보험",
    )

    assert result == {
        "보험분류": "배상·화재·기타",
        "상품태그": ["운전자"],
    }


def test_classify_policy_detects_indemnity_medical_policy() -> None:
    result = classify_policy(
        text="""
        메리츠화재
        상품명 메리츠 실비보험
        실손의료비 급여 비급여 자기부담금 보상
        """,
        product_name="메리츠 실비보험",
    )

    assert result == {
        "보험분류": "상해·질병·실손",
        "상품태그": ["실손"],
    }


def test_classify_policy_detects_health_style_policy_and_multiple_tags() -> None:
    result = classify_policy(
        text="""
        흥국화재
        무배당 흥국화재 맘편한 자녀사랑보험
        암진단비, 질병입원일당, 일반상해후유장해
        """,
        product_name="무배당 흥국화재 맘편한 자녀사랑보험",
    )

    assert result == {
        "보험분류": "상해·질병·실손",
        "상품태그": ["암", "상해", "질병", "어린이"],
    }


def test_classify_policy_detects_life_bucket_from_life_product_names() -> None:
    result = classify_policy(
        text="""
        교보생명
        무배당 교보New종신보험
        사망보험금, 해약환급금, 20년납 종신
        """,
        product_name="무배당 교보New종신보험",
    )

    assert result == {
        "보험분류": "생명·연금",
        "상품태그": ["종신"],
    }


def test_classify_policy_detects_fire_and_liability_bucket() -> None:
    result = classify_policy(
        text="""
        주택화재보험
        화재손해, 화재배상책임, 임차자배상책임
        """,
        product_name="주택화재보험",
    )

    assert result == {
        "보험분류": "배상·화재·기타",
        "상품태그": ["화재", "배상책임"],
    }


def test_classify_policy_returns_unclassified_when_evidence_is_too_weak() -> None:
    result = classify_policy(
        text="""
        보험상품 안내
        계약자 유의사항
        자세한 내용은 상담원을 통해 확인하세요.
        """,
        product_name=None,
    )

    assert result == {
        "보험분류": "미분류",
        "상품태그": [],
    }
