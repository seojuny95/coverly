"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { forwardRef, type ReactNode, useMemo, useState } from "react";

import { SectionLabel } from "../../shared/components/section-label";
import { Button } from "@/shared/components/ui/button";

import { UploadInsuranceModal } from "./upload-modal";
import {
  type AnalyzedInsurance,
  type InsuranceAnalysis,
  useInsuranceData,
} from "./store";
import { usePortfolioSessionRefresh } from "./use-session-refresh";
import { useBeforeUnloadGuard } from "./use-leave-guard";
import { useTabNavigation } from "./use-tab-navigation";
import { useExpandedRows } from "./use-expanded-rows";
import { InsuranceListPanel } from "./insurance-list-panel";
import type { UploadInsurance } from "../upload/form";
import { PortfolioAnalysisPanel } from "./portfolio/panel";
import { usePortfolioSummary } from "./portfolio/use-summary";
import type { DeathBenefitGuideInput } from "./portfolio/api";

// Lazy-load the chatbot (and its react-markdown dependency) so they stay out of
// the initial /analysis bundle — it only mounts after the user opens it.
const InsuranceChatbot = dynamic(
  () => import("./portfolio/chatbot").then((m) => m.InsuranceChatbot),
  { ssr: false },
);

type InsuranceAnalysisPageProps = {
  uploadInsurance?: UploadInsurance;
};

export function InsuranceAnalysisPage({
  uploadInsurance,
}: InsuranceAnalysisPageProps = {}) {
  const {
    analysis,
    hasData,
    sessionExpired,
    mergeDocuments,
    replacePortfolioSession,
    expireSession,
  } = useInsuranceData();
  useBeforeUnloadGuard(hasData);

  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const {
    activeTab,
    setActiveTab,
    handleTabListKeyDown,
    insuranceTabRef,
    analysisTabRef,
    chatTabRef,
  } = useTabNavigation();
  const { isExpanded, toggle: toggleInsurance } = useExpandedRows();
  const [deathBenefitContext, setDeathBenefitContext] =
    useState<DeathBenefitGuideInput>({
      has_dependent_family: false,
      has_minor_children: false,
      has_major_debt: false,
    });

  const insuranceDocuments = useMemo(
    () => analysis?.insuranceDocuments ?? [],
    [analysis],
  );
  const portfolioSession = useMemo(
    () =>
      analysis
        ? {
            portfolioSessionToken: analysis.portfolioSessionToken,
            expiresAt: analysis.portfolioSessionExpiresAt,
            counselTurnsRemaining: analysis.counselTurnsRemaining,
          }
        : undefined,
    [analysis],
  );
  const groupedInsuranceDocuments = useMemo(
    () => groupInsuranceDocuments(insuranceDocuments),
    [insuranceDocuments],
  );

  usePortfolioSessionRefresh({
    session: portfolioSession,
    enabled: hasData && !sessionExpired,
    onRefreshed: replacePortfolioSession,
    onExpired: expireSession,
  });
  const portfolioSummary = usePortfolioSummary(
    insuranceDocuments,
    deathBenefitContext,
    analysis?.portfolioSessionToken,
    expireSession,
  );

  const openUploadModal = () => setIsUploadModalOpen(true);
  const closeUploadModal = () => setIsUploadModalOpen(false);

  const handleAdditionalAnalysisComplete = (
    nextAnalysis: InsuranceAnalysis,
  ) => {
    mergeDocuments(nextAnalysis);
  };

  if (!analysis || insuranceDocuments.length === 0) {
    return (
      <main className="relative flex min-h-screen items-center justify-center bg-white px-5 text-zinc-950">
        <section className="w-full max-w-lg rounded-2xl border border-zinc-200 bg-white px-6 py-8 text-center shadow-[10px_10px_0_#e8edff]">
          <div className="mb-5 flex justify-center">
            <SectionLabel>분석 결과</SectionLabel>
          </div>
          <h1 className="text-2xl font-semibold tracking-[-0.04em]">
            분석할 보험증권이 없어요
          </h1>
          <p className="mt-3 text-sm leading-6 text-zinc-500">
            보험증권 PDF를 올리면 AI가 정리한 결과를 여기에서 볼 수 있어요.
          </p>
          <Button asChild className="mt-6">
            <Link href="/upload">보험증권 올리기</Link>
          </Button>
        </section>
      </main>
    );
  }

  return (
    <main
      className={`flex min-h-dvh flex-col bg-white px-5 py-6 text-zinc-950 sm:px-6 ${activeTab === "chat" ? "h-dvh overflow-hidden" : ""}`}
    >
      <section className="mx-auto mt-10 flex min-h-0 w-full max-w-6xl flex-1 flex-col">
        <nav
          role="tablist"
          aria-label="보험 정보 보기"
          onKeyDown={handleTabListKeyDown}
          className="mb-8 flex gap-1 border-b border-zinc-200"
        >
          <TabButton
            ref={insuranceTabRef}
            id="insurance-tab"
            controls="insurance-tabpanel"
            active={activeTab === "insurance"}
            onClick={() => setActiveTab("insurance")}
          >
            내 보험
          </TabButton>
          <TabButton
            ref={analysisTabRef}
            id="analysis-tab"
            controls="analysis-tabpanel"
            active={activeTab === "analysis"}
            onClick={() => setActiveTab("analysis")}
            badge={
              portfolioSummary.state.status === "loading" ? (
                <span className="ml-2 inline-flex items-center rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-600">
                  분석 중…
                </span>
              ) : null
            }
          >
            보험 분석
          </TabButton>
          <TabButton
            ref={chatTabRef}
            id="chat-tab"
            controls="chat-tabpanel"
            active={activeTab === "chat"}
            onClick={() => setActiveTab("chat")}
          >
            AI 보험 상담
          </TabButton>
        </nav>
        {sessionExpired ? <PolicySessionExpiredNotice /> : null}
        {/* Deliberately no flex/height classes: flex-1 here would compete with
            InsuranceChatbot's full-mode root and halve the chat scroll area. */}
        <div key={activeTab} className="animate-enter">
          {activeTab === "insurance" ? (
            <InsuranceListPanel
              selectedName={analysis.selectedName}
              generatedAt={analysis.generatedAt}
              groupedInsuranceDocuments={groupedInsuranceDocuments}
              coverageTotalStatus={portfolioSummary.state.status}
              coverageTotalSummary={
                portfolioSummary.state.status === "success"
                  ? portfolioSummary.state.summary
                  : undefined
              }
              onRetryCoverageTotal={portfolioSummary.retry}
              isRetryingCoverageTotal={portfolioSummary.isRetrying}
              coverageTotalRetryFailed={portfolioSummary.retryFailed}
              isExpanded={isExpanded}
              onToggle={toggleInsurance}
              onOpenUploadModal={openUploadModal}
            />
          ) : activeTab === "analysis" ? (
            <div
              id="analysis-tabpanel"
              role="tabpanel"
              aria-labelledby="analysis-tab"
              tabIndex={0}
            >
              <div className="mb-7">
                <SectionLabel>내 보험 분석</SectionLabel>
                <h1 className="mt-4 text-3xl font-semibold tracking-[-0.05em] sm:text-4xl">
                  가입한 보험을 한눈에 확인해요
                </h1>
                <p className="mt-3 text-sm leading-6 text-zinc-500">
                  전체 보험에서 사망·3대 진단비·실손의료비를 확인하고, 보험
                  종류별 보장도 함께 정리해요.
                </p>
              </div>
              <PortfolioAnalysisPanel
                status={portfolioSummary.state.status}
                summary={
                  portfolioSummary.state.status === "success"
                    ? portfolioSummary.state.summary
                    : undefined
                }
                deathBenefitContext={deathBenefitContext}
                onDeathBenefitContextChange={setDeathBenefitContext}
                isDeathBenefitRefreshing={portfolioSummary.isRefreshing}
                policyCount={insuranceDocuments.length}
                onRetry={portfolioSummary.retry}
                isRetrying={portfolioSummary.isRetrying}
                retryFailed={portfolioSummary.retryFailed}
                onRetryOverview={portfolioSummary.retryOverview}
                isOverviewRetrying={portfolioSummary.isOverviewRetrying}
                overviewRetryFailed={portfolioSummary.overviewRetryFailed}
              />
            </div>
          ) : (
            <div>
              <div className="mb-7">
                <SectionLabel>근거 기반 Q&A</SectionLabel>
                <h1 className="mt-4 text-3xl font-semibold tracking-[-0.05em] sm:text-4xl">
                  내 보험을 AI 상담사와 함께 살펴봐요
                </h1>
                <p className="mt-3 text-sm leading-6 text-zinc-500">
                  올린 보험증권에서 확인한 내용을 근거로 답하고, 확인하기 어려운
                  내용은 한계도 함께 알려드려요.
                </p>
              </div>
            </div>
          )}
        </div>

        <InsuranceChatbot
          portfolioSessionToken={analysis.portfolioSessionToken}
          sessionExpired={sessionExpired}
          turnsRemaining={analysis.counselTurnsRemaining}
          mode={activeTab === "chat" ? "full" : "floating"}
          onExpand={() => setActiveTab("chat")}
          onSessionExpired={expireSession}
        />
      </section>

      {isUploadModalOpen ? (
        <UploadInsuranceModal
          selectedName={analysis.selectedName}
          existingDocuments={insuranceDocuments}
          uploadInsurance={uploadInsurance}
          onClose={closeUploadModal}
          onAnalysisComplete={handleAdditionalAnalysisComplete}
        />
      ) : null}
    </main>
  );
}

const TabButton = forwardRef<
  HTMLButtonElement,
  {
    id: string;
    controls: string;
    active: boolean;
    onClick: () => void;
    children: React.ReactNode;
    badge?: ReactNode;
  }
>(function TabButton({ id, controls, active, onClick, children, badge }, ref) {
  return (
    <button
      ref={ref}
      id={id}
      type="button"
      role="tab"
      aria-selected={active}
      aria-controls={controls}
      // Roving tabindex: only the active tab is a Tab stop; arrow keys move
      // focus between tabs (handled by the tablist's onKeyDown).
      tabIndex={active ? 0 : -1}
      onClick={onClick}
      className={`inline-flex items-center border-b-2 px-5 py-3 text-sm font-semibold transition-colors ${active ? "border-blue-600 text-blue-600" : "border-transparent text-zinc-500 hover:text-zinc-900"}`}
    >
      {children}
      {badge}
    </button>
  );
});

function PolicySessionExpiredNotice() {
  return (
    <div
      role="status"
      className="mb-6 rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-950"
    >
      <p className="font-semibold">분석 세션이 만료됐어요</p>
      <p className="mt-1 leading-6">
        개인정보 보호를 위해 업로드한 문서 연결이 종료되었어요. 다시 분석하려면
        보험증권을 다시 올려주세요.
      </p>
      <Button asChild className="mt-3">
        <Link href="/upload">보험증권 다시 올리기</Link>
      </Button>
    </div>
  );
}

function groupInsuranceDocuments(insuranceDocuments: AnalyzedInsurance[]) {
  return insuranceDocuments.reduce<Record<string, AnalyzedInsurance[]>>(
    (groups, insuranceDocument) => {
      const classification = insuranceDocument.result.기본정보.보험분류;
      groups[classification] = [
        ...(groups[classification] ?? []),
        insuranceDocument,
      ];
      return groups;
    },
    {},
  );
}
