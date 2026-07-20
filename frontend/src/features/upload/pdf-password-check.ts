import type { PDFDocumentLoadingTask } from "pdfjs-dist";

// A hanging worker load or loadingTask.promise (corrupt input, worker fetch
// stall) must not lock submit forever now that "checking" blocks it. 8s comfortably
// covers a large legitimate policy PDF on a slow connection while still failing
// open well within a user's patience.
export const PASSWORD_CHECK_TIMEOUT_MS = 8000;

// Client-side pre-check only: flags encrypted PDFs right after file selection
// so the password field appears before the user submits, instead of after a
// round trip to the server. The server remains the source of truth for PDF
// validation (see use-orchestration.ts) — any failure or timeout here fails
// open (false) and lets the upload proceed to the server's own check.
export async function isPdfPasswordProtected(file: File): Promise<boolean> {
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  let loadingTask: PDFDocumentLoadingTask | undefined;
  let destroyed = false;

  // Guarded so the loading task is torn down exactly once, from whichever
  // path reaches it first: the normal check settling, or the timeout firing
  // while pdf.js is still stalled. A throw here must not surface — cleanup
  // failure can't be allowed to break the fail-open contract.
  const destroyLoadingTask = async (): Promise<void> => {
    if (destroyed || !loadingTask) return;
    destroyed = true;
    try {
      await loadingTask.destroy();
    } catch {
      // ignore
    }
  };

  const timeout = new Promise<boolean>((resolve) => {
    timeoutId = setTimeout(() => {
      void destroyLoadingTask();
      resolve(false);
    }, PASSWORD_CHECK_TIMEOUT_MS);
  });

  const check = checkPdfPassword(file, (task) => {
    loadingTask = task;
  }).finally(destroyLoadingTask);

  try {
    return await Promise.race([check, timeout]);
  } finally {
    clearTimeout(timeoutId);
  }
}

async function checkPdfPassword(
  file: File,
  registerLoadingTask: (task: PDFDocumentLoadingTask) => void,
): Promise<boolean> {
  try {
    const pdfjsLib = await import("pdfjs-dist");
    pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
      "pdfjs-dist/build/pdf.worker.min.mjs",
      import.meta.url,
    ).toString();

    const data = await file.arrayBuffer();
    const loadingTask = pdfjsLib.getDocument({ data });
    registerLoadingTask(loadingTask);

    try {
      await loadingTask.promise;
      return false;
    } catch (err) {
      return (
        err instanceof Error &&
        err.name === "PasswordException" &&
        (err as { code?: number }).code ===
          pdfjsLib.PasswordResponses.NEED_PASSWORD
      );
    }
  } catch {
    return false;
  }
}
