import type {
  ApiErrorCode,
  PolicyParseResponse,
} from "../../shared/api/contracts";

export type PolicyUploadResult = PolicyParseResponse;

export type LocalUploadErrorCode =
  | "UPLOAD_NETWORK_ERROR"
  | "UPLOAD_FAILED"
  | "DUPLICATE_POLICY"
  | "MISSING_INSURED_PERSON";

export type UploadErrorCode = ApiErrorCode | LocalUploadErrorCode;

export type UploadPolicyDocumentInput = {
  file: File;
  documentId: string;
  password?: string;
  portfolioSessionToken: string;
  signal?: AbortSignal;
};

export type UploadPolicyDocument = (
  input: UploadPolicyDocumentInput,
) => Promise<PolicyUploadResult>;

export type SelectedFileStatus =
  "idle" | "checking" | "reading" | "done" | "failed";

export type SelectedPolicyFile = {
  id: string;
  file: File;
  status: SelectedFileStatus;
  password?: string;
  errorCode?: UploadErrorCode;
  errorMessage?: string;
};

export type UploadSurface = "page" | "modal";
