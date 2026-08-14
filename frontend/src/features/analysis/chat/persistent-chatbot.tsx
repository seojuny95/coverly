"use client";

import dynamic from "next/dynamic";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ChatLauncher } from "./launcher";
import { loadInsuranceChatbot } from "./load-chatbot";
import { ANALYSIS_ROUTES } from "../routes";
import { useInsuranceData } from "../session/store";

const LazyInsuranceChatbot = dynamic(
  () => loadInsuranceChatbot().then((module) => module.InsuranceChatbot),
  { ssr: false, loading: () => <ChatLoading /> },
);

export function PersistentChatbot() {
  const pathname = usePathname();
  const router = useRouter();
  const { analysis, sessionExpired, expireSession } = useInsuranceData();
  const fullPage = pathname === ANALYSIS_ROUTES.chat;
  const [chatbotLoaded, setChatbotLoaded] = useState(fullPage);
  const [openWhenLoaded, setOpenWhenLoaded] = useState(false);

  useEffect(() => {
    if (fullPage) {
      // Keep the loaded chat mounted after route changes so its conversation survives.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setChatbotLoaded(true);
    }
  }, [fullPage]);

  if (!analysis) return null;

  if (!chatbotLoaded && !fullPage) {
    return (
      <ChatLauncher
        disabled={sessionExpired}
        onOpen={() => {
          setOpenWhenLoaded(true);
          setChatbotLoaded(true);
        }}
      />
    );
  }

  return (
    <LazyInsuranceChatbot
      portfolioSessionToken={analysis.portfolioSessionToken}
      sessionExpired={sessionExpired}
      turnsRemaining={analysis.counselTurnsRemaining}
      mode={fullPage ? "full" : "floating"}
      initiallyOpen={openWhenLoaded}
      onExpand={() => router.push(ANALYSIS_ROUTES.chat)}
      onSessionExpired={expireSession}
    />
  );
}

function ChatLoading() {
  const pathname = usePathname();

  if (pathname !== ANALYSIS_ROUTES.chat) return <ChatLauncher loading />;

  return (
    <div
      role="status"
      className="mb-4 flex min-h-0 flex-1 items-center justify-center rounded-2xl border border-zinc-200 bg-zinc-50 text-sm text-zinc-500 sm:mb-6"
    >
      상담창을 준비하고 있어요…
    </div>
  );
}
