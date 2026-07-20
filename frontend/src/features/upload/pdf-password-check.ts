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
  const timeout = new Promise<boolean>((resolve) => {
    timeoutId = setTimeout(() => resolve(false), PASSWORD_CHECK_TIMEOUT_MS);
    // Node's test runner would otherwise wait out the timer even after the
    // check settles first.
    timeoutId.unref?.();
  });

  try {
    return await Promise.race([checkPdfPassword(file), timeout]);
  } finally {
    clearTimeout(timeoutId);
  }
}

async function checkPdfPassword(file: File): Promise<boolean> {
  try {
    const pdfjsLib = await import("pdfjs-dist");
    pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
      "pdfjs-dist/build/pdf.worker.min.mjs",
      import.meta.url,
    ).toString();

    const data = await file.arrayBuffer();
    const loadingTask = pdfjsLib.getDocument({ data });
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
    } finally {
      await loadingTask.destroy();
    }
  } catch {
    return false;
  }
}
