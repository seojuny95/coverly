import { primaryButtonClassName } from "../../components/coverly-brand";
import type { EmptyReason } from "./analysis-eligibility";
import { AnalysisLoading, InfoState } from "./portfolio-analysis-states";
import { ClaimGuide } from "./portfolio-claim-guide";
import { PortfolioOverview } from "./portfolio-overview";
import { SpecialPolicySections } from "./special-policy-sections";
import type { PortfolioSummary } from "./portfolio-api";

const EMPTY_COPY: Record<EmptyReason, { title: string; description: string }> =
  {
    "auto-only": {
      title: "확인할 보험 정보가 없어요",
      description:
        "담보 내용이 있는 보험증권을 올리면 전체 보험을 확인할 수 있어요.",
    },
    "no-coverage": {
      title: "확인할 담보가 없어요",
      description:
        "담보 내용이 있는 보험증권을 올리면 전체 보험을 확인할 수 있어요.",
    },
    mixed: {
      title: "확인할 담보가 없어요",
      description:
        "담보 내용이 있는 보험증권을 올리면 전체 보험을 확인할 수 있어요.",
    },
  };

export function PortfolioAnalysisPanel({
  status,
  summary,
  eligibleCount,
  emptyReason,
  onRetry,
}: {
  status: "loading" | "success" | "error";
  summary?: PortfolioSummary;
  eligibleCount: number;
  emptyReason: EmptyReason;
  onRetry: () => void;
}) {
  if (eligibleCount === 0) return <InfoState {...EMPTY_COPY[emptyReason]} />;
  if (status === "loading") return <AnalysisLoading />;

  if (status === "error") {
    return (
      <section className="rounded-2xl border border-zinc-200 p-8 text-center">
        <h2 className="text-xl font-semibold">
          보장 점검 결과를 불러오지 못했어요
        </h2>
        <p className="mt-2 text-sm text-zinc-500">
          업로드한 증권은 그대로 있어요. 잠시 후 다시 확인해주세요.
        </p>
        <button
          type="button"
          className={`mt-5 ${primaryButtonClassName}`}
          onClick={onRetry}
        >
          다시 확인하기
        </button>
      </section>
    );
  }

  const items = summary?.essential_coverage_check?.items ?? [];
  const specialAnalyses = summary?.special_policy_analyses ?? [];
  const missingItems = items.filter((item) => item.status === "not_found");
  const reviewItems = items.filter((item) => item.status === "needs_review");

  return (
    <div className="space-y-8">
      <PortfolioOverview
        summary={summary}
        items={items}
        policyCount={eligibleCount}
        missingItems={missingItems}
        reviewItems={reviewItems}
        specialAnalyses={specialAnalyses}
      />

      {specialAnalyses.length > 0 ? (
        <SpecialPolicySections analyses={specialAnalyses} />
      ) : null}

      <ClaimGuide claimChannels={summary?.claim_channels ?? null} />
    </div>
  );
}
