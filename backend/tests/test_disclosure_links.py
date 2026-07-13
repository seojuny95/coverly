from app.services.coverage_knowledge.disclosure_links import disclosure_links_for_insurer


def test_disclosure_links_route_life_and_non_life_insurers_to_association_portals() -> None:
    life = disclosure_links_for_insurer("교보생명")
    non_life = disclosure_links_for_insurer("삼성화재")

    assert any(link.kind == "life" for link in life)
    assert any("생명보험협회" in link.name for link in life)
    assert any(link.kind == "non_life" for link in non_life)
    assert any("손해보험협회" in link.name for link in non_life)
    assert all(link.url.startswith("https://") for link in life + non_life)
