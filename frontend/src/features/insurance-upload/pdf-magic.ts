// Client-side content check so an obvious non-PDF (an image or docx renamed to
// .pdf) is caught before a full upload + parse. The backend re-validates content
// and remains the authoritative gate — this is only fast, lenient UX feedback.
const PDF_SIGNATURE = "%PDF-";
const SCAN_BYTES = 1024;

export function hasPdfMagicBytes(bytes: Uint8Array): boolean {
  // Real PDFs open with "%PDF-" at byte 0, but some exporters prepend a BOM or
  // whitespace, so scan the first bytes rather than checking only the prefix.
  const head = bytes.subarray(0, SCAN_BYTES);
  let text = "";
  for (const byte of head) {
    text += String.fromCharCode(byte);
  }
  return text.includes(PDF_SIGNATURE);
}

export async function fileHasPdfMagic(file: File): Promise<boolean> {
  const buffer = await file.slice(0, SCAN_BYTES).arrayBuffer();
  return hasPdfMagicBytes(new Uint8Array(buffer));
}
