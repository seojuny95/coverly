// Backend-provided links (claim channels, markdown) are rendered as anchors.
// A spoofed or compromised response could carry a `javascript:`/`data:` href,
// so only well-known safe schemes are allowed through; anything else is dropped.
const SAFE_PROTOCOLS = new Set(["http:", "https:", "tel:", "mailto:"]);
const HAS_SCHEME = /^[a-z][a-z0-9+.-]*:/i;

function stripControlChars(value: string): string {
  // Browsers strip ASCII control chars (including leading ones) from URL
  // attributes before parsing, so "\x01javascript:" or "java\tscript:" would
  // execute as javascript:. Drop all C0 controls + DEL so the scheme check
  // below can't be bypassed by hiding a scheme behind a control byte.
  return Array.from(value)
    .filter((char) => {
      const code = char.charCodeAt(0);
      return code > 0x1f && code !== 0x7f;
    })
    .join("");
}

export function safeHref(href: string | undefined): string | undefined {
  if (!href) return undefined;

  const cleaned = stripControlChars(href).trim();
  if (cleaned === "") return undefined;

  // Protocol-relative ("//host") and backslash-authority ("/\\host", "\\\\host")
  // URLs navigate cross-origin like an absolute link, so treat them as unsafe —
  // backend links should be absolute http(s)/tel/mailto or a same-origin path.
  if (/^[/\\]{2}/.test(cleaned)) return undefined;

  // No scheme → ordinary same-origin relative path. Safe.
  if (!HAS_SCHEME.test(cleaned)) return cleaned;

  try {
    const { protocol } = new URL(cleaned);
    return SAFE_PROTOCOLS.has(protocol) ? cleaned : undefined;
  } catch {
    return undefined;
  }
}
