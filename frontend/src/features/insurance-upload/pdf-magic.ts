// Client-side content check so an obvious non-PDF (an image or docx renamed to
// .pdf) is caught before a full upload + parse. The backend re-validates content
// and remains the authoritative gate — this is only fast, lenient UX feedback.
const PDF_SIGNATURE = "%PDF-";
const SCAN_BYTES = 1024;
const ENCRYPT_SCAN_BYTES = 64 * 1024;
const PDF_ENCRYPT_MARKER = "/Encrypt";

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

function includesPdfEncryptMarker(bytes: Uint8Array): boolean {
  if (bytes.length === 0) return false;
  let text = "";
  for (const byte of bytes) {
    text += String.fromCharCode(byte);
  }
  return text.includes(PDF_ENCRYPT_MARKER);
}

export async function fileLooksEncryptedPdf(file: File): Promise<boolean> {
  if (!(await fileHasPdfMagic(file))) {
    return false;
  }

  const head = new Uint8Array(
    await file.slice(0, ENCRYPT_SCAN_BYTES).arrayBuffer(),
  );
  if (includesPdfEncryptMarker(head)) {
    return true;
  }

  const tailStart = Math.max(file.size - ENCRYPT_SCAN_BYTES, 0);
  const tail = new Uint8Array(await file.slice(tailStart).arrayBuffer());
  return includesPdfEncryptMarker(tail);
}
