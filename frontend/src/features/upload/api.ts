import { apiUrl, readApiErrorPayload } from "../../shared/api/client";
import type {
  ApiErrorCode,
  CoveragePeriod,
  InsuredDemographics,
  PolicyCoverage,
  PolicyParseResponse,
  PolicySummary,
  PremiumSummary,
  VehicleInfo,
} from "../../shared/api/contracts";

export type InsurancePeriod = CoveragePeriod;
export type InsurancePremium = PremiumSummary;
export type InsuranceVehicleInfo = VehicleInfo;
export type InsuranceDemographics = InsuredDemographics;
export type InsuranceBasicInfo = PolicySummary;
export type InsuranceCoverage = PolicyCoverage;
export type InsuranceUploadResult = PolicyParseResponse;

export type InsurancePolicyResult = Omit<InsuranceUploadResult, "documentId">;

export type LocalUploadErrorCode =
  | "UPLOAD_NETWORK_ERROR"
  | "UPLOAD_FAILED"
  | "DUPLICATE_POLICY"
  | "MISSING_INSURED_PERSON";
export type UploadErrorCode = ApiErrorCode | LocalUploadErrorCode;

const GENERIC_UPLOAD_MESSAGE =
  "업로드에 실패했어요. 잠시 후 다시 시도해주세요.";
const SERVER_UPLOAD_MESSAGE =
  "서버에서 파일을 처리하지 못했어요. 잠시 후 다시 시도해주세요.";

// The backend runs several sequential LLM calls (summary, coverage
// extraction, indexing), each with its own retry budget, so a legitimate
// parse can run well past the "보통 1~2분" the UI sets as the typical
// expectation (progress.tsx). This only needs to catch a truly stalled
// connection (dead socket, captive portal) — not shave time off slow but
// working uploads — so it is set generously above that typical range.
const UPLOAD_TIMEOUT_MS = 5 * 60 * 1000;

export class UploadInsuranceError extends Error {
  readonly code: UploadErrorCode;
  readonly requestId?: string;
  readonly status?: number;
  readonly userMessage: string;

  constructor({
    code,
    requestId,
    status,
    userMessage,
  }: {
    code: UploadErrorCode;
    requestId?: string;
    status?: number;
    userMessage: string;
  }) {
    super(userMessage);
    this.name = "UploadInsuranceError";
    this.code = code;
    this.requestId = requestId;
    this.status = status;
    this.userMessage = userMessage;
  }
}

export async function uploadInsurance({
  file,
  documentId,
  password,
  portfolioSessionToken,
}: {
  file: File;
  documentId: string;
  password?: string;
  portfolioSessionToken: string;
}): Promise<InsuranceUploadResult> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("documentId", documentId);
  if (password) {
    formData.append("password", password);
  }
  formData.append("portfolioSessionToken", portfolioSessionToken);

  let response: Response;
  try {
    response = await fetch(apiUrl("/policies/parse"), {
      method: "POST",
      body: formData,
      signal: AbortSignal.timeout(UPLOAD_TIMEOUT_MS),
    });
  } catch {
    throw new UploadInsuranceError({
      code: "UPLOAD_NETWORK_ERROR",
      userMessage: "서버에 연결하지 못했어요. 잠시 후 다시 시도해주세요.",
    });
  }

  if (!response.ok) {
    let code: UploadErrorCode = "UPLOAD_FAILED";
    let requestId = response.headers.get("x-request-id") ?? undefined;
    let userMessage = GENERIC_UPLOAD_MESSAGE;
    const { detail: error, isJson } = await readApiErrorPayload(response);
    if (error) {
      code = error.code;
      requestId = error.request_id;
      if (response.status >= 500) {
        userMessage = SERVER_UPLOAD_MESSAGE;
      } else {
        userMessage = error.message;
      }
    } else if (isJson && response.status >= 500) {
      userMessage = SERVER_UPLOAD_MESSAGE;
    }
    throw new UploadInsuranceError({
      code,
      requestId,
      status: response.status,
      userMessage,
    });
  }

  return (await response.json()) as InsuranceUploadResult;
}
