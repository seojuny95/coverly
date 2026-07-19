export const CORE_COVERAGE_DESCRIPTION = {
  death:
    "사망 보장은 피보험자가 사망했을 때 남은 가족의 생활비, 부채 상환처럼 생길 수 있는 경제적 공백을 대비하는 보장이에요.",
  diagnosis:
    "진단 보장은 큰 질병을 진단받은 뒤 치료와 회복 기간에 생길 수 있는 생활비 공백을 대비하는 보장이에요.",
  medicalIndemnity:
    "실손의료보험은 실제로 부담한 의료비를 약관의 보장 범위 안에서 보상하는 보험이에요. 의료비 부담을 줄이는 보장이라 가입 세대, 자기부담금, 중복 여부를 함께 확인해야 해요.",
} as const;

export type DiagnosisKind = "cancer" | "cerebrovascular" | "ischemic_heart";

const DIAGNOSIS_DESCRIPTION: Record<DiagnosisKind, string> = {
  cancer:
    "암 진단 시 약정된 금액을 지급하는 정액 보장으로, 치료와 회복 중 생활비 공백을 대비해요.",
  cerebrovascular:
    "뇌혈관질환 진단 시 약정된 금액을 지급하는 정액 보장으로, 재활과 간병에 드는 비용을 대비해요.",
  ischemic_heart:
    "심장질환 진단 시 약정된 금액을 지급하는 정액 보장으로, 시술·수술과 회복 기간의 비용을 대비해요.",
};

export function diagnosisDescription(kind: DiagnosisKind) {
  return DIAGNOSIS_DESCRIPTION[kind];
}
