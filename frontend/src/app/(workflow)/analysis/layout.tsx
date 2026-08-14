import type { ReactNode } from "react";

import { AnalysisContainer } from "./_components/container";
import { AnalysisNavigation } from "./_components/navigation";
import { AnalysisSessionBoundary } from "@/features/analysis/session/boundary";
import { SessionExpiredNotice } from "@/features/analysis/session/expired-notice";
import { PersistentChatbot } from "@/features/analysis/chat/persistent-chatbot";

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <AnalysisSessionBoundary>
      <AnalysisContainer>
        <AnalysisNavigation />
        <SessionExpiredNotice />
        {children}
        <PersistentChatbot />
      </AnalysisContainer>
    </AnalysisSessionBoundary>
  );
}
