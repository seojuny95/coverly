import type { InsuranceUploadResult } from "./api";

export type UploadInsuranceInput = {
  file: File;
  documentId: string;
  password?: string;
  portfolioSessionToken: string;
};

export type UploadInsurance = (
  input: UploadInsuranceInput,
) => Promise<InsuranceUploadResult>;

export type FileReadStatus = "idle" | "reading" | "done" | "failed";

export type SelectedUploadFile = {
  id: string;
  file: File;
  status: FileReadStatus;
  password?: string;
  errorCode?: string;
  errorMessage?: string;
};
