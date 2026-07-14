export type InsurancePeriod = {
  시작일?: string;
  종료일?: string;
};

export type InsurancePremium = {
  금액?: number;
  납입주기?: string;
};

export type InsuranceVehicleInfo = {
  차량명?: string;
  차량번호?: string;
  연식?: string;
};

export type InsuranceDemographics = {
  나이?: number;
  성별?: string;
  생애단계?: string;
};

export type InsuranceBasicInfo = {
  보험사?: string;
  상품명?: string;
  증권번호?: string;
  계약자?: string;
  피보험자?: string;
  보험분류?: string;
  상품태그?: string[];
  납입기간?: string;
  만기일?: string;
  보험기간?: InsurancePeriod;
  보험료?: InsurancePremium;
  피보험자정보?: InsuranceDemographics;
  차량정보?: InsuranceVehicleInfo;
};

export type InsuranceCoverage = {
  담보명: string;
  가입금액: string;
  보장내용: string | null;
  해설: string | null;
  // Absent means "담보" (a real coverage row); "부가" marks name-only rider/rate rows.
  유형?: "담보" | "부가";
};

export type InsuranceUploadResult = {
  status: "accepted";
  문자수: number;
  문서세션ID?: string;
  기본정보?: InsuranceBasicInfo;
  보장목록?: InsuranceCoverage[];
  분석상태?: "완료" | "부분";
};

type ApiErrorResponse = {
  error?: {
    code?: string;
    message?: string;
    request_id?: string;
  };
};

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const GENERIC_UPLOAD_MESSAGE =
  "업로드에 실패했어요. 잠시 후 다시 시도해주세요.";
const SERVER_UPLOAD_MESSAGE =
  "서버에서 파일을 처리하지 못했어요. 잠시 후 다시 시도해주세요.";

export class UploadInsuranceError extends Error {
  readonly code: string;
  readonly requestId?: string;
  readonly status?: number;
  readonly userMessage: string;

  constructor({
    code,
    requestId,
    status,
    userMessage,
  }: {
    code: string;
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
  password,
}: {
  file: File;
  password?: string;
}): Promise<InsuranceUploadResult> {
  const formData = new FormData();
  formData.append("file", file);
  if (password) {
    formData.append("password", password);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/policies/parse`, {
      method: "POST",
      body: formData,
    });
  } catch {
    throw new UploadInsuranceError({
      code: "UPLOAD_NETWORK_ERROR",
      userMessage: "서버에 연결하지 못했어요. 잠시 후 다시 시도해주세요.",
    });
  }

  if (!response.ok) {
    let code = "UPLOAD_FAILED";
    let requestId = response.headers.get("x-request-id") ?? undefined;
    let userMessage = GENERIC_UPLOAD_MESSAGE;
    try {
      const error = (await response.json()) as ApiErrorResponse;
      code = error.error?.code ?? code;
      requestId = error.error?.request_id ?? requestId;
      if (response.status >= 500) {
        userMessage = SERVER_UPLOAD_MESSAGE;
      } else {
        userMessage = error.error?.message ?? userMessage;
      }
    } catch {
      // Keep the generic message when the backend response is not JSON.
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
