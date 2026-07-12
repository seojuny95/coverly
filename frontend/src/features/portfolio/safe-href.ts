// Backend-provided links (claim channels, markdown) are rendered as anchors.
// A spoofed or compromised response could carry a `javascript:`/`data:` href,
// so only well-known safe schemes are allowed through; anything else is dropped.
const SAFE_PROTOCOLS = new Set(["http:", "https:", "tel:", "mailto:"]);
const HAS_SCHEME = /^[a-z][a-z0-9+.-]*:/i;

export function safeHref(href: string | undefined): string | undefined {
  if (!href) return undefined;

  // Browsers strip ASCII tab/newline/CR from URL attributes before parsing, so
  // "java\tscript:alert(1)" would execute as javascript:. Strip them the same
  // way first, then evaluate — otherwise the scheme check is trivially bypassed.
  const cleaned = href.replace(/[\t\n\r]/g, "").trim();
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
