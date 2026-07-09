export type PolicyPeriod = {
  시작일?: string;
  종료일?: string;
};

export type PolicyPremium = {
  금액?: number;
  납입주기?: string;
};

export type PolicyBasicInfo = {
  보험사?: string;
  상품명?: string;
  증권번호?: string;
  계약자?: string;
  피보험자?: string;
  보험분류?: string;
  상품태그?: string[];
  납입기간?: string;
  만기일?: string;
  보험기간?: PolicyPeriod;
  보험료?: PolicyPremium;
};

export type PolicyUploadResult = {
  status: "accepted";
  문자수: number;
  문서판정: {
    보험증권추정: boolean;
    점수: number;
    근거: string[];
  };
  기본정보?: PolicyBasicInfo;
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

const GENERIC_UPLOAD_MESSAGE = "업로드에 실패했어요. 잠시 후 다시 시도해주세요.";
const SERVER_UPLOAD_MESSAGE =
  "서버에서 파일을 처리하지 못했어요. 잠시 후 다시 시도해주세요.";

export class UploadPolicyError extends Error {
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
    this.name = "UploadPolicyError";
    this.code = code;
    this.requestId = requestId;
    this.status = status;
    this.userMessage = userMessage;
  }
}

export async function uploadPolicy(file: File): Promise<PolicyUploadResult> {
  const formData = new FormData();
  formData.append("file", file);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/policies/parse`, {
      method: "POST",
      body: formData,
    });
  } catch {
    throw new UploadPolicyError({
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
    throw new UploadPolicyError({
      code,
      requestId,
      status: response.status,
      userMessage,
    });
  }

  return (await response.json()) as PolicyUploadResult;
}
