import {
  type KeyboardEvent as ReactKeyboardEvent,
  useRef,
  useState,
} from "react";

export type AnalysisTab = "insurance" | "analysis" | "chat";

const ANALYSIS_TABS: AnalysisTab[] = ["insurance", "analysis", "chat"];

// Controlled tab state for the analysis screen. The chat tab is special (it
// drives the floating vs. full chatbot and a layout class), so we keep the tab
// value controlled with a custom tablist instead of radix Tabs, and only lift
// the WAI-ARIA arrow-key navigation and roving refs out of the render body.
export function useTabNavigation() {
  const [activeTab, setActiveTab] = useState<AnalysisTab>("insurance");

  const insuranceTabRef = useRef<HTMLButtonElement>(null);
  const analysisTabRef = useRef<HTMLButtonElement>(null);
  const chatTabRef = useRef<HTMLButtonElement>(null);

  // Automatic activation: arrow keys move focus and switch the panel in one step.
  const handleTabListKeyDown = (event: ReactKeyboardEvent<HTMLElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();

    const direction = event.key === "ArrowRight" ? 1 : -1;
    const nextIndex =
      (ANALYSIS_TABS.indexOf(activeTab) + direction + ANALYSIS_TABS.length) %
      ANALYSIS_TABS.length;
    const next = ANALYSIS_TABS[nextIndex];

    setActiveTab(next);
    const tabRefs = {
      insurance: insuranceTabRef,
      analysis: analysisTabRef,
      chat: chatTabRef,
    };
    tabRefs[next].current?.focus();
  };

  return {
    activeTab,
    setActiveTab,
    handleTabListKeyDown,
    insuranceTabRef,
    analysisTabRef,
    chatTabRef,
  };
}
