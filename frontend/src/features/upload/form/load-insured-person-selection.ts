export function loadInsuredPersonSelection() {
  return import("./insured-person-selection");
}

export function preloadInsuredPersonSelection() {
  void loadInsuredPersonSelection().catch(() => undefined);
}
