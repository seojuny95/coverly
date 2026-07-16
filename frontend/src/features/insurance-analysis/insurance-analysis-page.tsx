"use client";

import Image from "next/image";
import Link from "next/link";
import dynamic from "next/dynamic";
import {
  forwardRef,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  CoverlyLogo,
  CoverlyMark,
  PixelEyebrow,
  coverlyLogoLinkClassName,
  ghostButtonClassName,
  primaryButtonClassName,
} from "../../components/coverly-brand";

import insurerLogos from "./insurer-logos.json";
import {
  type AnalyzedInsurance,
  type InsuranceAnalysis,
  useInsuranceData,
} from "./insurance-analysis-store";
import { LeaveGuardLink } from "./leave-guard-link";
import { normalizeInsurerName } from "./policy-identity";
import { usePolicySessionRefresh } from "./use-policy-session-refresh";
import { useDialogA11y } from "./use-dialog-a11y";
import { useBeforeUnloadGuard } from "./use-leave-guard";
import type {
  InsuranceBasicInfo,
  InsurancePremium,
  InsurancePeriod,
} from "../insurance-upload/upload-insurance";
import {
  InsuranceUploadForm,
  type UploadInsurance,
} from "../insurance-upload/insurance-upload-form";
import { InsuranceCoverageList } from "./insurance-coverage-list";
import { CoverageTotalTable } from "../portfolio/coverage-total-table";
import { PortfolioAnalysisPanel } from "../portfolio/portfolio-analysis-panel";
import { emptyReasonFor } from "../portfolio/analysis-eligibility";
import { usePortfolioSummary } from "../portfolio/use-portfolio-summary";
import { formatWon } from "../portfolio/money-format";
import type { DeathBenefitGuideInput } from "../portfolio/portfolio-api";

// Lazy-load the chatbot (and its react-markdown dependency) so they stay out of
// the initial /analysis bundle — it only mounts after the user opens it.
const InsuranceChatbot = dynamic(
  () =>
    import("../portfolio/insurance-chatbot").then((m) => m.InsuranceChatbot),
  { ssr: false },
);

const CLASSIFICATION_ORDER = ["생명보험", "제3보험", "손해보험", "미분류"];

const CLASSIFICATION_HELP: Record<string, string> = {
  생명보험:
    "사망이나 노후처럼 사람의 생명과 긴 기간의 생활을 준비하는 보험이에요. 종신보험, 정기보험, 연금보험이 여기에 가까워요.",
  제3보험:
    "질병, 상해, 간병처럼 사람의 몸과 건강에 생기는 일을 보장하는 보험이에요. 암보험, 상해보험, 간병보험이 대표적이에요.",
  손해보험:
    "갑작스러운 사고로 생긴 재산 손해나 책임을 보상하는 보험이에요. 자동차보험, 운전자보험, 화재보험이 여기에 들어가요.",
  미분류:
    "증권에서 보험 종류를 확실히 판단할 단서가 부족한 경우예요. 상품명이나 보장 내용을 다시 확인해 주세요.",
};

const CLASSIFICATION_SUMMARY: Record<string, string> = {
  생명보험: "사망·노후 보장",
  제3보험: "질병·상해·간병 보장",
  손해보험: "재산 손해·책임 보장",
  미분류: "종류 확인 필요",
};

const LIFE_CLASSIFICATIONS = new Set(["생명보험", "생명·연금"]);
const THIRD_CLASSIFICATIONS = new Set(["제3보험", "상해·질병·실손"]);
const DAMAGE_CLASSIFICATIONS = new Set([
  "손해보험",
  "자동차",
  "자동차보험",
  "운전자보험",
  "운전자상해보험",
  "여행자보험",
  "화재보험",
  "주택화재보험",
  "배상책임보험",
  "보증보험",
  "배상·화재·기타",
]);

const TAG_STYLES: Record<string, string> = {
  사망보험: "border-[#4F46E5]/10 bg-[#4F46E5]/[0.06] text-[#111827]/60",
  종신보험: "border-[#4F46E5]/10 bg-[#4F46E5]/[0.06] text-[#111827]/60",
  정기보험: "border-[#6366F1]/10 bg-[#6366F1]/[0.06] text-[#111827]/60",
  연금보험: "border-[#0284C7]/10 bg-[#0284C7]/[0.06] text-[#111827]/60",
  양로보험: "border-[#0D9488]/10 bg-[#0D9488]/[0.06] text-[#111827]/60",
  저축보험: "border-[#65A30D]/10 bg-[#65A30D]/[0.06] text-[#111827]/60",
  질병보험: "border-[#0891B2]/10 bg-[#0891B2]/[0.06] text-[#111827]/60",
  상해보험: "border-[#EA580C]/10 bg-[#EA580C]/[0.06] text-[#111827]/60",
  간병보험: "border-[#7C3AED]/10 bg-[#7C3AED]/[0.06] text-[#111827]/60",
  실손의료보험: "border-[#2563EB]/10 bg-[#2563EB]/[0.06] text-[#111827]/60",
  어린이보험: "border-[#DB2777]/10 bg-[#DB2777]/[0.06] text-[#111827]/60",
  자동차보험: "border-[#2563EB]/10 bg-[#2563EB]/[0.06] text-[#111827]/60",
  운전자보험: "border-[#1D4ED8]/10 bg-[#1D4ED8]/[0.06] text-[#111827]/60",
  여행자보험: "border-[#0F766E]/10 bg-[#0F766E]/[0.06] text-[#111827]/60",
  화재보험: "border-[#F97316]/10 bg-[#F97316]/[0.06] text-[#111827]/60",
  배상책임보험: "border-[#0F766E]/10 bg-[#0F766E]/[0.06] text-[#111827]/60",
  보증보험: "border-[#71717A]/10 bg-[#71717A]/[0.06] text-[#111827]/60",
};

const INSURER_LOGOS = insurerLogos;

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
    replaceDocumentSessionTokens,
    expireSession,
    clear,
  } = useInsuranceData();
  useBeforeUnloadGuard(hasData);
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<AnalysisTab>("insurance");
  const insuranceTabRef = useRef<HTMLButtonElement>(null);
  const analysisTabRef = useRef<HTMLButtonElement>(null);
  const chatTabRef = useRef<HTMLButtonElement>(null);
  const classificationHelpRef = useRef<HTMLDListElement>(null);
  const [openClassificationHelp, setOpenClassificationHelp] = useState<
    string | null
  >(null);
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

  useEffect(() => {
    if (!openClassificationHelp) return;

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpenClassificationHelp(null);
      }
    };
    const closeOnOutsidePointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (
        target instanceof Node &&
        classificationHelpRef.current?.contains(target)
      ) {
        return;
      }
      setOpenClassificationHelp(null);
    };

    document.addEventListener("keydown", closeOnEscape);
    document.addEventListener("pointerdown", closeOnOutsidePointerDown);
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      document.removeEventListener("pointerdown", closeOnOutsidePointerDown);
    };
  }, [openClassificationHelp]);

  const insuranceDocuments = useMemo(
    () => analysis?.insuranceDocuments ?? [],
    [analysis],
  );
  usePolicySessionRefresh({
    documents: insuranceDocuments,
    enabled: hasData && !sessionExpired,
    onTokensRefreshed: replaceDocumentSessionTokens,
    onExpired: expireSession,
  });
  const groupedInsuranceDocuments = useMemo(
    () => groupInsuranceDocuments(insuranceDocuments),
    [insuranceDocuments],
  );
  const classificationTypeCount = CLASSIFICATION_ORDER.length;
  const portfolioSummary = usePortfolioSummary(
    insuranceDocuments,
    deathBenefitContext,
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
        <CoverlyLogo className="absolute top-6 left-6" />
        <section className="w-full max-w-lg rounded-2xl border border-zinc-200 bg-white px-6 py-8 text-center shadow-[10px_10px_0_#e8edff]">
          <div className="mb-5 flex justify-center">
            <PixelEyebrow>분석 결과</PixelEyebrow>
          </div>
          <h1 className="text-2xl font-semibold tracking-[-0.04em]">
            분석할 보험증권이 없어요
          </h1>
          <p className="mt-3 text-sm leading-6 text-zinc-500">
            보험증권 PDF를 올리면 AI가 정리한 결과를 여기에서 볼 수 있어요.
          </p>
          <Link href="/upload" className={`mt-6 ${primaryButtonClassName}`}>
            보험증권 올리기
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="flex min-h-dvh flex-col bg-white px-5 py-6 text-zinc-950 sm:px-6">
      <header className="mx-auto flex w-full max-w-6xl items-center gap-4">
        <LeaveGuardLink
          href="/"
          enabled={hasData}
          onLeave={clear}
          className={coverlyLogoLinkClassName}
          ariaLabel="Coverly AI 홈"
        >
          <CoverlyMark />
        </LeaveGuardLink>
      </header>

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
                  <PixelEyebrow>나의 보장 지도</PixelEyebrow>
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
                <button
                  type="button"
                  onClick={openUploadModal}
                  className={primaryButtonClassName}
                >
                  보험증권 더 올리기
                </button>
                <p className="font-mono text-[10px] tracking-[0.04em] text-zinc-400">
                  정리한 시각 {formatDateTime(analysis.generatedAt)}
                </p>
              </div>
            </div>

            <dl
              ref={classificationHelpRef}
              className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
            >
              {CLASSIFICATION_ORDER.map((classification) => {
                const isHelpOpen = openClassificationHelp === classification;

                return (
                  <div
                    key={classification}
                    className="relative rounded-xl border border-zinc-200 bg-white px-4 py-4 shadow-[4px_4px_0_#f4f4f5]"
                  >
                    <dt className="flex items-start justify-between gap-3 text-xs font-medium text-zinc-500">
                      <span>{classification}</span>
                      <span className="relative inline-flex">
                        <button
                          type="button"
                          aria-label={`${classification} 설명 보기`}
                          aria-haspopup="dialog"
                          aria-controls={`classification-help-${classification}`}
                          aria-expanded={isHelpOpen}
                          onClick={() =>
                            setOpenClassificationHelp((current) =>
                              current === classification
                                ? null
                                : classification,
                            )
                          }
                          className="flex size-5 items-center justify-center rounded-full border border-zinc-200 text-[11px] font-semibold text-zinc-400 transition hover:border-blue-200 hover:bg-blue-50 hover:text-blue-600 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500"
                        >
                          ?
                        </button>
                        {isHelpOpen ? (
                          <span
                            id={`classification-help-${classification}`}
                            role="dialog"
                            aria-label={`${classification} 설명`}
                            className="absolute right-0 bottom-7 z-10 w-64 rounded-xl border border-zinc-200 bg-white p-3 text-left text-xs leading-5 font-normal text-zinc-600 shadow-lg"
                          >
                            {CLASSIFICATION_HELP[classification]}
                          </span>
                        ) : null}
                      </span>
                    </dt>
                    <dd className="mt-3 text-3xl font-semibold tracking-[-0.05em] text-blue-600">
                      {groupedInsuranceDocuments[classification]?.length ?? 0}
                    </dd>
                  </div>
                );
              })}
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
              {CLASSIFICATION_ORDER.map((classification) => {
                const classificationInsuranceDocuments =
                  groupedInsuranceDocuments[classification] ?? [];
                if (classificationInsuranceDocuments.length === 0) return null;

                return (
                  <section
                    key={classification}
                    className="overflow-hidden rounded-2xl border border-zinc-200 bg-white"
                  >
                    <div className="border-b border-zinc-100 bg-zinc-50/60 px-5 py-4">
                      <h2 className="flex flex-wrap items-center gap-2 text-lg font-semibold tracking-[-0.03em]">
                        <span>{classification}</span>
                        <span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium tracking-normal text-zinc-500 ring-1 ring-zinc-200">
                          {CLASSIFICATION_SUMMARY[classification]}
                        </span>
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
                                    insurerName={basicInfo?.보험사}
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
              <PixelEyebrow>내 보험 분석</PixelEyebrow>
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
              eligibleCount={insuranceDocuments.length}
              emptyReason={emptyReasonFor(insuranceDocuments)}
              onRetry={portfolioSummary.retry}
            />
          </div>
        ) : (
          <div>
            <div className="mb-7">
              <PixelEyebrow>근거 기반 Q&A</PixelEyebrow>
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
      <Link href="/upload" className={`mt-3 ${primaryButtonClassName}`}>
        보험증권 다시 올리기
      </Link>
    </div>
  );
}

function InsuranceDetail({
  insuranceDocument,
  isExpanded,
}: {
  insuranceDocument: AnalyzedInsurance;
  isExpanded: boolean;
}) {
  const basicInfo = insuranceDocument.result.기본정보;
  const detailItems = [
    ["보험사", basicInfo?.보험사],
    ["증권번호", basicInfo?.증권번호],
    ["계약자", basicInfo?.계약자],
    ["피보험자", basicInfo?.피보험자],
    ["보험기간", formatPeriod(basicInfo?.보험기간)],
    ["만기일", basicInfo?.만기일],
    ["납입기간", basicInfo?.납입기간],
    ["보험료", formatPremium(basicInfo?.보험료)],
    ["차량명", basicInfo?.차량정보?.차량명],
    ["차량번호", basicInfo?.차량정보?.차량번호],
    ["연식", basicInfo?.차량정보?.연식],
  ].filter((item): item is [string, string] => Boolean(item[1]));

  return (
    <div
      className={`border-t border-zinc-100 bg-zinc-50/70 px-5 py-5 transition-all duration-200 ease-out ${
        isExpanded ? "translate-y-0 opacity-100" : "-translate-y-1 opacity-0"
      }`}
    >
      <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {detailItems.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs font-medium text-zinc-500">{label}</dt>
            <dd className="mt-1 text-sm font-medium break-words text-zinc-800">
              {value}
            </dd>
          </div>
        ))}
      </dl>

      <div className="mt-6">
        <h3 className="text-xs font-medium text-zinc-500">보장 내용</h3>
        <div className="mt-2 rounded-xl border border-zinc-200 bg-white px-5 py-4">
          <InsuranceCoverageList
            coverages={insuranceDocument.result.보장목록}
            status={insuranceDocument.result.분석상태}
          />
        </div>
      </div>
    </div>
  );
}

function InsurerLogo({ insurerName }: { insurerName?: string }) {
  const logo = findInsurerLogo(insurerName);

  return (
    <span className="flex h-10 min-w-[4.75rem] shrink-0 items-center justify-center rounded-xl border border-zinc-200 bg-white px-2.5">
      {logo ? (
        <span className="relative flex h-7 w-full items-center justify-center overflow-hidden">
          <Image
            src={logo.src}
            alt=""
            aria-hidden="true"
            fill
            sizes="76px"
            className={`object-contain ${logo.imageClassName ?? ""}`}
          />
        </span>
      ) : (
        <span className="text-xs font-semibold text-zinc-400">
          {(insurerName ?? "?").slice(0, 1)}
        </span>
      )}
    </span>
  );
}

function findInsurerLogo(insurerName?: string) {
  if (!insurerName) return undefined;

  const normalizedName = normalizeInsurerName(insurerName);
  return INSURER_LOGOS.find(({ aliases }) =>
    aliases.some((alias) =>
      normalizedName.includes(normalizeInsurerName(alias)),
    ),
  );
}

function TagBadge({ tag }: { tag: string }) {
  return (
    <span
      className={`inline-flex h-6 items-center rounded-full border px-2 py-0 text-[11px] font-medium whitespace-nowrap ${TAG_STYLES[tag] ?? "border-[#111827]/10 bg-[#111827]/[0.04] text-[#111827]/60"}`}
    >
      {tag}
    </span>
  );
}

function groupInsuranceDocuments(insuranceDocuments: AnalyzedInsurance[]) {
  return insuranceDocuments.reduce<Record<string, AnalyzedInsurance[]>>(
    (groups, insuranceDocument) => {
      const classification = displayClassification(
        insuranceDocument.result.기본정보?.보험분류,
      );
      groups[classification] = [
        ...(groups[classification] ?? []),
        insuranceDocument,
      ];
      return groups;
    },
    {},
  );
}

function displayClassification(classification?: string) {
  if (classification && LIFE_CLASSIFICATIONS.has(classification)) {
    return "생명보험";
  }
  if (classification && THIRD_CLASSIFICATIONS.has(classification)) {
    return "제3보험";
  }
  if (classification && DAMAGE_CLASSIFICATIONS.has(classification)) {
    return "손해보험";
  }
  return "미분류";
}

function formatPeriod(
  period: InsurancePeriod | InsuranceBasicInfo["보험기간"],
) {
  if (!period?.시작일 || !period.종료일) return undefined;
  return `${period.시작일} - ${period.종료일}`;
}

function formatPremium(
  premium: InsurancePremium | InsuranceBasicInfo["보험료"],
) {
  if (premium?.금액 === undefined) return undefined;
  const cycle = premium.납입주기 ? `${premium.납입주기} ` : "";
  return `${cycle}${formatWon(premium.금액)}`;
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function UploadInsuranceModal({
  selectedName,
  existingDocuments,
  uploadInsurance,
  onClose,
  onAnalysisComplete,
}: {
  selectedName?: string;
  existingDocuments: AnalyzedInsurance[];
  uploadInsurance?: UploadInsurance;
  onClose: () => void;
  onAnalysisComplete: (analysis: InsuranceAnalysis) => void;
}) {
  const dialogRef = useDialogA11y<HTMLDivElement>({ open: true, onClose });

  return (
    <div
      ref={dialogRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/45 px-5 py-8 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="analysis-upload-modal-title"
      tabIndex={-1}
    >
      <div className="w-full max-w-2xl rounded-2xl border border-zinc-200 bg-white p-5 shadow-[12px_12px_0_rgba(232,237,255,0.45)] sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2
              id="analysis-upload-modal-title"
              className="text-xl font-semibold tracking-[-0.04em] text-zinc-950"
            >
              보험증권 더 올리기
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className={ghostButtonClassName}
          >
            닫기
          </button>
        </div>

        <div className="mt-6">
          <InsuranceUploadForm
            uploadInsurance={uploadInsurance}
            existingDocuments={existingDocuments}
            fixedSelectedName={selectedName}
            onAnalysisComplete={onAnalysisComplete}
            navigateToAnalysis={onClose}
            surface="modal"
          />
        </div>
      </div>
    </div>
  );
}
