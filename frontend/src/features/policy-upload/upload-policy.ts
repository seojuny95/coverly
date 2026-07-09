export type PolicyUploadResult = {
  status: "accepted";
  문자수: number;
  문서판정: {
    보험증권추정: boolean;
    점수: number;
    근거: string[];
  };
};

type ApiErrorResponse = {
  detail?: string;
};

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

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
    throw new Error(
      "서버에 연결할 수 없습니다. 백엔드 실행 상태를 확인해주세요.",
    );
  }

  if (!response.ok) {
    let detail = "업로드에 실패했습니다.";
    try {
      const error = (await response.json()) as ApiErrorResponse;
      detail = error.detail ?? detail;
    } catch {
      // Keep the generic message when the backend response is not JSON.
    }
    throw new Error(detail);
  }

  return (await response.json()) as PolicyUploadResult;
}
