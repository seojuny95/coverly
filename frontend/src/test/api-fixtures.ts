import type {
  InsurancePolicyResult,
  InsuranceUploadResult,
} from "../features/upload/api";

export const POLICY_RESULT_DEFAULTS = {
  status: "accepted",
  문자수: 0,
  기본정보: {},
  보장목록: [],
  분석상태: "완료",
} satisfies InsurancePolicyResult;

export const POLICY_PARSE_RESPONSE_DEFAULTS = {
  ...POLICY_RESULT_DEFAULTS,
  documentId: "test-document-id",
} satisfies InsuranceUploadResult;
