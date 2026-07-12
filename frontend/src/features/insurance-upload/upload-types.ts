export type FileReadStatus = "idle" | "reading" | "done" | "failed";

export type SelectedUploadFile = {
  id: string;
  file: File;
  status: FileReadStatus;
  errorCode?: string;
  errorMessage?: string;
};
