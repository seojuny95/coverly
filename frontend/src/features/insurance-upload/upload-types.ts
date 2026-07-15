import type { InsuranceUploadResult } from "./upload-insurance";

type UploadInsuranceInput = {
  file: File;
  password?: string;
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
