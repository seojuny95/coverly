import json
from pathlib import Path

from evals.qa_rag.dataset import load_qa_rag_dataset
from evals.qa_rag.live import _evaluation_fingerprint_paths

DATASET_PATH = Path(__file__).resolve().parents[3] / "evals" / "qa_rag" / "dataset.json"
BACKEND_ROOT = DATASET_PATH.parents[2]


def test_agent_rag_dataset_has_each_evidence_boundary() -> None:
    dataset = load_qa_rag_dataset(DATASET_PATH)
    tags = {tag for case in dataset.cases for tag in case.tags}

    assert len(dataset.cases) == 32
    assert {"policy", "official", "mixed"}.issubset(tags)


def test_agent_rag_dataset_exercises_both_rag_tools() -> None:
    dataset = load_qa_rag_dataset(DATASET_PATH)
    required_tools = {
        tool for case in dataset.cases for turn in case.turns for tool in turn.required_tools
    }

    assert "retrieve_policy_terms" in required_tools
    assert "retrieve_official_guidance" in required_tools


def test_agent_rag_dataset_has_combined_policy_and_official_cases() -> None:
    dataset = load_qa_rag_dataset(DATASET_PATH)
    combined = [
        case
        for case in dataset.cases
        if any(
            {"retrieve_policy_terms", "retrieve_official_guidance"}.issubset(turn.required_tools)
            for turn in case.turns
        )
    ]

    assert len(combined) >= 3


def test_agent_rag_dataset_separates_practice_and_test_cases() -> None:
    dataset = load_qa_rag_dataset(DATASET_PATH)
    practice = [case for case in dataset.cases if case.set == "practice"]
    test = [case for case in dataset.cases if case.set == "test"]

    assert len(practice) == 24
    assert len(test) == 8
    assert all("holdout" in case.tags for case in test)


def test_agent_rag_test_set_contains_multiturn_and_cross_document_cases() -> None:
    dataset = load_qa_rag_dataset(DATASET_PATH)
    test = [case for case in dataset.cases if case.set == "test"]

    assert sum(len(case.turns) > 1 for case in test) >= 3
    assert any("cross_document" in case.tags for case in test)
    assert any("no_evidence" in case.tags for case in test)


def test_judged_turns_have_curated_reference_facts() -> None:
    dataset = load_qa_rag_dataset(DATASET_PATH)
    judged_turns = [turn for case in dataset.cases for turn in case.turns if turn.judge]

    assert judged_turns
    assert all(turn.reference_facts for turn in judged_turns)


def test_fixture_policy_ids_match_policy_rag_documents() -> None:
    dataset = load_qa_rag_dataset(DATASET_PATH)
    policies = json.loads((BACKEND_ROOT / dataset.fixture).read_text(encoding="utf-8"))
    retrieval = json.loads(
        (BACKEND_ROOT / dataset.policy_retrieval_dataset).read_text(encoding="utf-8")
    )

    fixture_ids = {policy["id"] for policy in policies}
    document_ids = {document["session_id"] for document in retrieval["documents"]}

    assert fixture_ids == set(dataset.policy_session_ids)
    assert document_ids == set(dataset.policy_session_ids)


def test_evaluation_fingerprint_covers_agent_and_retrieval_runtime() -> None:
    dataset = load_qa_rag_dataset(DATASET_PATH)
    relative_paths = {
        path.relative_to(BACKEND_ROOT.parent).as_posix()
        for path in _evaluation_fingerprint_paths(dataset)
    }

    assert "backend/app/modules/qa/agent.py" in relative_paths
    assert "backend/app/rag/official/retrieval.py" in relative_paths
    assert "backend/app/rag/official/reranking.py" in relative_paths
    assert "backend/app/rag/policy/retrieval.py" in relative_paths
    assert "backend/app/rag/scoring.py" in relative_paths
    assert "backend/evals/rag/policy/retrieval.py" in relative_paths
    assert "sample_policy/01_건강보험_기본형.pdf" in relative_paths
