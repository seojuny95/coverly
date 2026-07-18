from evals.rag.data import string_groups, string_tuple


def test_string_tuple_coerces_json_values() -> None:
    assert string_tuple(["term", 3, True]) == ("term", "3", "True")


def test_string_groups_preserves_nested_group_boundaries() -> None:
    assert string_groups([["암", "암진단"], ["입원"]]) == (
        ("암", "암진단"),
        ("입원",),
    )
