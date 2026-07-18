"""HTTP contracts for policy parsing."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.policy.models import Coverage, PolicyAnalysisStatus, PolicySummary


class PolicyParseResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: Literal["accepted"]
    document_id: str = Field(serialization_alias="documentId")
    문자수: int = Field(ge=0)
    기본정보: PolicySummary
    보장목록: list[Coverage]
    분석상태: PolicyAnalysisStatus
