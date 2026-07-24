import { apiUrl, readApiErrorPayload } from "../../shared/api/client";
import { AppRequestError } from "../../shared/api/errors";
import { retryOperation } from "../../shared/api/retry";
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

export class UploadInsuranceError extends AppRequestError {
  readonly code: UploadErrorCode;
  readonly requestId?: string;
  readonly retryAfterMs?: number;
  readonly status?: number;
  readonly userMessage: string;

  constructor({
    code,
    requestId,
    retryAfterMs,
    status,
    userMessage,
  }: {
    code: UploadErrorCode;
    requestId?: string;
    retryAfterMs?: number;
    status?: number;
    userMessage: string;
  }) {
    super({
      developerMessage: `Policy upload failed (status=${status ?? "NETWORK"}, code=${code})`,
      name: "UploadInsuranceError",
      userMessage,
    });
    this.code = code;
    this.requestId = requestId;
    this.retryAfterMs = retryAfterMs;
    this.status = status;
    this.userMessage = userMessage;
  }
}

export async function uploadInsurance({
  file,
  documentId,
  password,
  portfolioSessionToken,
  signal,
}: {
  file: File;
  documentId: string;
  password?: string;
  portfolioSessionToken: string;
  signal?: AbortSignal;
}): Promise<InsuranceUploadResult> {
  return retryOperation(
    () =>
      uploadInsuranceOnce({
        file,
        documentId,
        password,
        portfolioSessionToken,
        signal,
      }),
    {
      maxAttempts: 2,
      signal,
      shouldRetry: (error) =>
        error instanceof UploadInsuranceError &&
        error.code === "PDF_PARSING_BUSY",
    },
  );
}

async function uploadInsuranceOnce({
  file,
  documentId,
  password,
  portfolioSessionToken,
  signal,
}: {
  file: File;
  documentId: string;
  password?: string;
  portfolioSessionToken: string;
  signal?: AbortSignal;
}): Promise<InsuranceUploadResult> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("documentId", documentId);
  if (password) formData.append("password", password);
  formData.append("portfolioSessionToken", portfolioSessionToken);

  let response: Response;
  try {
    response = await fetch(apiUrl("/policies/parse"), {
      method: "POST",
      body: formData,
      signal: signal
        ? AbortSignal.any([signal, AbortSignal.timeout(UPLOAD_TIMEOUT_MS)])
        : AbortSignal.timeout(UPLOAD_TIMEOUT_MS),
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new UploadInsuranceError({
      code: "UPLOAD_NETWORK_ERROR",
      userMessage:
        error instanceof DOMException && error.name === "TimeoutError"
          ? "PDF 분석 시간이 오래 걸리고 있어요. 잠시 후 다시 시도해주세요."
          : "서버에 연결하지 못했어요. 잠시 후 다시 시도해주세요.",
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
      if (code === "PDF_PARSING_BUSY") {
        userMessage =
          "PDF 분석 요청이 많아요. 잠시 기다린 뒤 다시 시도해주세요.";
      } else if (response.status >= 500) {
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
      retryAfterMs:
        code === "PDF_PARSING_BUSY"
          ? retryAfterMilliseconds(response.headers.get("retry-after"))
          : undefined,
    });
  }

  return (await response.json()) as InsuranceUploadResult;
}

function retryAfterMilliseconds(value: string | null): number | undefined {
  if (!value) return undefined;
  const seconds = Number(value);
  return Number.isFinite(seconds) && seconds >= 0 ? seconds * 1000 : undefined;
}
