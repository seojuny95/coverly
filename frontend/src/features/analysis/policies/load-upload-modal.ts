export function loadUploadPolicyDocumentModal() {
  return import("./upload-modal");
}

export function preloadUploadPolicyDocumentModal() {
  void loadUploadPolicyDocumentModal().catch(() => undefined);
}
