"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import {
  forwardRef,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
  useMemo,
  useRef,
  useState,
} from "react";

import { SectionLabel } from "../../shared/components/section-label";
import { Button } from "../../shared/components/ui/button";
import { POLICY_CLASSIFICATIONS } from "../../shared/api/generated-runtime";

import { UploadInsuranceModal } from "./upload-modal";
import { InsurerLogo, InsuranceDetail, TagBadge } from "./policy-detail";
import {
  type AnalyzedInsurance,
  type InsuranceAnalysis,
  useInsuranceData,
} from "./store";
import { usePortfolioSessionRefresh } from "./use-session-refresh";
import { useBeforeUnloadGuard } from "./use-leave-guard";
import type { UploadInsurance } from "../upload/form";
import { CoverageTotalTable } from "./portfolio/total-table";
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

type AnalysisTab = "insurance" | "analysis" | "chat";

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
  const [activeTab, setActiveTab] = useState<AnalysisTab>("insurance");
  const insuranceTabRef = useRef<HTMLButtonElement>(null);
  const analysisTabRef = useRef<HTMLButtonElement>(null);
  const chatTabRef = useRef<HTMLButtonElement>(null);
  const [deathBenefitContext, setDeathBenefitContext] =
    useState<DeathBenefitGuideInput>({
      has_dependent_family: false,
      has_minor_children: false,
      has_major_debt: false,
    });

  // Arrow-key navigation between the tabs (WAI-ARIA tabs pattern,
  // automatic activation): moves focus and switches the panel in one step.
  const handleTabListKeyDown = (event: ReactKeyboardEvent<HTMLElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const tabs: AnalysisTab[] = ["insurance", "analysis", "chat"];
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const nextIndex =
      (tabs.indexOf(activeTab) + direction + tabs.length) % tabs.length;
    const next = tabs[nextIndex];
    setActiveTab(next);
    const tabRefs = {
      insurance: insuranceTabRef,
      analysis: analysisTabRef,
      chat: chatTabRef,
    };
    tabRefs[next].current?.focus();
  };
  const [expandedInsuranceIds, setExpandedInsuranceIds] = useState<Set<string>>(
    () => new Set(),
  );

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
          }
        : undefined,
    [analysis],
  );
  usePortfolioSessionRefresh({
    session: portfolioSession,
    enabled: hasData && !sessionExpired,
    onRefreshed: replacePortfolioSession,
    onExpired: expireSession,
  });
  const groupedInsuranceDocuments = useMemo(
    () => groupInsuranceDocuments(insuranceDocuments),
    [insuranceDocuments],
  );
  const classificationTypeCount = POLICY_CLASSIFICATIONS.length;
  const portfolioSummary = usePortfolioSummary(
    insuranceDocuments,
    deathBenefitContext,
    analysis?.portfolioSessionToken,
  );

  const toggleInsurance = (policyId: string) => {
    setExpandedInsuranceIds((current) => {
      const next = new Set(current);
      if (next.has(policyId)) {
        next.delete(policyId);
      } else {
        next.add(policyId);
      }
      return next;
    });
  };

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
        {activeTab === "insurance" ? (
          <div
            id="insurance-tabpanel"
            role="tabpanel"
            aria-labelledby="insurance-tab"
            tabIndex={0}
          >
            <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <div className="mb-4">
                  <SectionLabel>나의 보장 지도</SectionLabel>
                </div>
                <h1 className="text-3xl font-semibold tracking-[-0.05em] text-zinc-950 sm:text-4xl">
                  내 보험을 종류별로 정리했어요
                </h1>
                <p className="mt-3 text-sm leading-6 text-zinc-500">
                  {analysis.selectedName
                    ? `${analysis.selectedName}님의 보험을 ${classificationTypeCount}가지 종류로 보기 쉽게 정리했어요.`
                    : `보험을 ${classificationTypeCount}가지 종류로 보기 쉽게 정리했어요.`}
                </p>
              </div>
              <div className="flex flex-col items-start gap-3 sm:items-end">
                <Button type="button" onClick={openUploadModal}>
                  보험증권 더 올리기
                </Button>
                <p className="font-mono text-[10px] tracking-[0.04em] text-zinc-400">
                  정리한 시각 {formatDateTime(analysis.generatedAt)}
                </p>
              </div>
            </div>

            <dl className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {POLICY_CLASSIFICATIONS.map((classification) => (
                <div
                  key={classification}
                  className="relative rounded-xl border border-zinc-200 bg-white px-4 py-4 shadow-[4px_4px_0_#f4f4f5]"
                >
                  <dt className="text-xs font-medium text-zinc-500">
                    {classification}
                  </dt>
                  <dd className="mt-3 text-3xl font-semibold tracking-[-0.05em] text-blue-600">
                    {groupedInsuranceDocuments[classification]?.length ?? 0}
                  </dd>
                </div>
              ))}
            </dl>

            <CoverageTotalTable
              status={portfolioSummary.state.status}
              summary={
                portfolioSummary.state.status === "success"
                  ? portfolioSummary.state.summary
                  : undefined
              }
              onRetry={portfolioSummary.retry}
            />

            <div className="mt-8 space-y-5">
              {POLICY_CLASSIFICATIONS.map((classification) => {
                const classificationInsuranceDocuments =
                  groupedInsuranceDocuments[classification] ?? [];
                if (classificationInsuranceDocuments.length === 0) return null;

                return (
                  <section
                    key={classification}
                    className="overflow-hidden rounded-2xl border border-zinc-200 bg-white"
                  >
                    <div className="border-b border-zinc-100 bg-zinc-50/60 px-5 py-4">
                      <h2 className="text-lg font-semibold tracking-[-0.03em]">
                        {classification}
                      </h2>
                      <p className="mt-1 text-sm text-zinc-500">
                        보험 {classificationInsuranceDocuments.length}개
                      </p>
                    </div>

                    <ul className="divide-y divide-zinc-100">
                      {classificationInsuranceDocuments.map(
                        (insuranceDocument) => {
                          const isExpanded = expandedInsuranceIds.has(
                            insuranceDocument.id,
                          );
                          const basicInfo = insuranceDocument.result.기본정보;

                          return (
                            <li key={insuranceDocument.id}>
                              <button
                                type="button"
                                aria-expanded={isExpanded}
                                onClick={() =>
                                  toggleInsurance(insuranceDocument.id)
                                }
                                className="flex w-full flex-col gap-4 px-5 py-4 text-left transition-colors hover:bg-zinc-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-inset sm:flex-row sm:items-center sm:justify-between"
                              >
                                <span className="flex min-w-0 items-start gap-3">
                                  <InsurerLogo
                                    insurerName={basicInfo?.보험사 ?? undefined}
                                  />
                                  <span className="min-w-0 flex-1">
                                    <span className="flex min-w-0 items-center gap-2">
                                      <span className="truncate text-base font-semibold text-zinc-950">
                                        {basicInfo?.상품명 ??
                                          insuranceDocument.fileName}
                                      </span>
                                      {basicInfo?.상품태그?.length ? (
                                        <span className="flex shrink-0 flex-wrap gap-1.5">
                                          {basicInfo.상품태그.map((tag) => (
                                            <TagBadge key={tag} tag={tag} />
                                          ))}
                                        </span>
                                      ) : null}
                                    </span>
                                    <span className="mt-1 block truncate text-sm text-zinc-500">
                                      {insuranceDocument.fileName}
                                    </span>
                                  </span>
                                </span>
                                <span className="inline-flex shrink-0 items-center rounded-lg border border-blue-100 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
                                  {isExpanded ? "접기" : "자세히 보기"}
                                </span>
                              </button>

                              <div
                                className={`grid transition-[grid-template-rows] duration-200 ease-out ${
                                  isExpanded
                                    ? "grid-rows-[1fr]"
                                    : "grid-rows-[0fr]"
                                }`}
                              >
                                <div className="overflow-hidden">
                                  <InsuranceDetail
                                    insuranceDocument={insuranceDocument}
                                    isExpanded={isExpanded}
                                  />
                                </div>
                              </div>
                            </li>
                          );
                        },
                      )}
                    </ul>
                  </section>
                );
              })}
            </div>
          </div>
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
                전체 보험에서 사망·3대 진단비·실손의료비를 확인하고, 보험 종류별
                보장도 함께 정리해요.
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

        <InsuranceChatbot
          documents={insuranceDocuments}
          portfolioSessionToken={analysis.portfolioSessionToken}
          sessionExpired={sessionExpired}
          mode={activeTab === "chat" ? "full" : "floating"}
          onExpand={() => setActiveTab("chat")}
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

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
