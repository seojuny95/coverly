// Client-side pre-check only: flags encrypted PDFs right after file selection
// so the password field appears before the user submits, instead of after a
// round trip to the server. The server remains the source of truth for PDF
// validation (see use-orchestration.ts) — any failure here fails open (false)
// and lets the upload proceed to the server's own check.
export async function isPdfPasswordProtected(file: File): Promise<boolean> {
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
