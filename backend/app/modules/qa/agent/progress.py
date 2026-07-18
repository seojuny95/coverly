"""Progress events emitted while the QA agent is running."""

from queue import Queue
from typing import Any

from agents import RunHooks

from app.modules.qa.agent.contracts import QaAgentDependencies, QaAgentProgress, QaAgentStreamItem

type QueuedAgentStreamItem = QaAgentStreamItem | BaseException | None


class ProgressHooks(RunHooks[QaAgentDependencies]):
    def __init__(self, queue: Queue[QueuedAgentStreamItem]) -> None:
        self._queue = queue
        self._emitted: set[str] = set()

    async def on_agent_start(self, _context: Any, _agent: Any) -> None:
        self._emit("routing", "질문에 맞는 확인 경로를 고르고 있어요.")

    async def on_tool_start(self, _context: Any, _agent: Any, tool: Any) -> None:
        tool_name = str(getattr(tool, "name", ""))
        stage, text = tool_progress(tool_name)
        self._emit(stage, text)

    async def on_agent_end(self, _context: Any, _agent: Any, _output: Any) -> None:
        self._emit("validating", "확인한 근거와 답변을 검토하고 있어요.")

    def _emit(self, stage: str, text: str) -> None:
        if stage in self._emitted:
            return
        self._emitted.add(stage)
        self._queue.put(QaAgentProgress(stage=stage, text=text))


def tool_progress(tool_name: str) -> tuple[str, str]:
    progress = {
        "search_official_web": ("official_web", "공식 자료에서 최신 정보를 확인하고 있어요."),
        "retrieve_official_guidance": ("official_rag", "공식 보험 자료를 확인하고 있어요."),
        "retrieve_policy_terms": ("policy_terms", "증권 원문과 약관 근거를 찾고 있어요."),
        "get_claim_channels": ("claim_channels", "청구에 필요한 보험사 안내를 확인하고 있어요."),
        "list_policies": ("portfolio_facts", "올려주신 보험 목록을 확인하고 있어요."),
        "find_coverages": ("portfolio_facts", "올려주신 증권의 가입 담보를 확인하고 있어요."),
        "calculate_coverage_total": ("portfolio_facts", "확인 가능한 가입금액을 계산하고 있어요."),
        "find_overlapping_coverages": (
            "portfolio_facts",
            "증권 사이의 중복 담보를 확인하고 있어요.",
        ),
        "inspect_portfolio": ("portfolio_facts", "전체 보장 내용을 함께 살펴보고 있어요."),
    }
    return progress.get(tool_name, ("grounding", "확인한 근거로 답변을 정리하고 있어요."))
