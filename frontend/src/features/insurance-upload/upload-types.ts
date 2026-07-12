import type { InsuranceUploadResult } from "./upload-insurance";

export type UploadInsurance = (file: File) => Promise<InsuranceUploadResult>;

export type FileReadStatus = "idle" | "reading" | "done" | "failed";

export type SelectedUploadFile = {
  id: string;
  file: File;
  status: FileReadStatus;
  errorCode?: string;
  errorMessage?: string;
};
