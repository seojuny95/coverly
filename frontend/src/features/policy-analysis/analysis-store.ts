import type { PolicyUploadResult } from "../policy-upload/upload-policy";

const STORAGE_KEY = "coverly.policyAnalysis";

export type AnalyzedPolicy = {
  id: string;
  fileName: string;
  result: PolicyUploadResult;
};

export type PolicyAnalysis = {
  generatedAt: string;
  selectedName?: string;
  policies: AnalyzedPolicy[];
};

export function savePolicyAnalysis(analysis: PolicyAnalysis) {
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(analysis));
}

export function loadPolicyAnalysis(): PolicyAnalysis | null {
  const rawAnalysis = window.sessionStorage.getItem(STORAGE_KEY);
  if (!rawAnalysis) return null;

  try {
    const parsed = JSON.parse(rawAnalysis) as Partial<PolicyAnalysis>;
    if (!parsed.generatedAt || !Array.isArray(parsed.policies)) return null;
    return {
      generatedAt: parsed.generatedAt,
      selectedName:
        typeof parsed.selectedName === "string"
          ? parsed.selectedName
          : undefined,
      policies: parsed.policies.filter(isAnalyzedPolicy),
    };
  } catch {
    return null;
  }
}

function isAnalyzedPolicy(value: unknown): value is AnalyzedPolicy {
  if (!value || typeof value !== "object") return false;

  const candidate = value as Partial<AnalyzedPolicy>;
  return (
    typeof candidate.id === "string" &&
    typeof candidate.fileName === "string" &&
    Boolean(candidate.result)
  );
}

export function getPolicyPersonName(policy: AnalyzedPolicy): string | null {
  const insuredName = policy.result.기본정보?.피보험자?.trim();
  if (insuredName) return insuredName;

  return null;
}
