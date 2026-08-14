export const ANALYSIS_ROUTES = {
  policies: "/analysis",
  coverage: "/analysis/coverage",
  chat: "/analysis/chat",
} as const;

export function isAnalysisPath(pathname: string) {
  return (
    pathname === ANALYSIS_ROUTES.policies || pathname.startsWith("/analysis/")
  );
}
