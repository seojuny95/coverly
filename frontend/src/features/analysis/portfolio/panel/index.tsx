import { RetryButton } from "@/shared/components/retry-button";
import { ClaimGuide } from "../claim-guide";
import type { DeathBenefitGuideInput, PortfolioSummary } from "../api";
import { SpecialPolicySections } from "../special-policy-sections";
import { AnalysisLoading } from "./analysis-loading";
import { PortfolioOverview } from "./portfolio-overview";

export function PortfolioAnalysisPanel({
  status,
  summary,
  deathBenefitContext,
  onDeathBenefitContextChange,
  isDeathBenefitRefreshing = false,
  policyCount,
  onRetry,
  isRetrying = false,
  retryFailed = false,
  overviewRetryFailed = false,
}: {
  status: "loading" | "success" | "error";
  summary?: PortfolioSummary;
  deathBenefitContext: DeathBenefitGuideInput;
  onDeathBenefitContextChange: (context: DeathBenefitGuideInput) => void;
  isDeathBenefitRefreshing?: boolean;
  policyCount: number;
  onRetry: () => void;
  isRetrying?: boolean;
  retryFailed?: boolean;
  overviewRetryFailed?: boolean;
}) {
  if (status === "loading") return <AnalysisLoading />;

  if (status === "error") {
    return (
      <section className="rounded-2xl border border-zinc-200 p-8 text-center">
        <h2 className="text-xl font-semibold">
          보장 점검 결과를 불러오지 못했어요
        </h2>
        <p
          role={retryFailed ? "alert" : undefined}
          className="mt-2 text-sm text-zinc-500"
        >
          {retryFailed
            ? "다시 불러오지 못했어요. 업로드한 증권은 그대로 있으니 잠시 후 다시 시도해주세요."
            : "업로드한 증권은 그대로 있어요. 잠시 후 다시 확인해주세요."}
        </p>
        <RetryButton
          type="button"
          className="mt-5"
          onClick={onRetry}
          isPending={isRetrying}
          label="다시 확인하기"
          pendingLabel="다시 확인하는 중…"
        />
      </section>
    );
  }

  const items = summary?.essential_coverage_check?.items ?? [];
  const specialAnalyses = summary?.special_policy_analyses ?? [];

  return (
    <div className="space-y-8">
      <PortfolioOverview
        summary={summary}
        items={items}
        deathBenefitContext={deathBenefitContext}
        onDeathBenefitContextChange={onDeathBenefitContextChange}
        isDeathBenefitRefreshing={isDeathBenefitRefreshing}
        policyCount={policyCount}
        specialAnalyses={specialAnalyses}
        onRetry={onRetry}
        isRetrying={isRetrying}
        retryFailed={overviewRetryFailed}
      />

      {specialAnalyses.length > 0 ? (
        <SpecialPolicySections analyses={specialAnalyses} />
      ) : null}

      <ClaimGuide
        claimChannels={summary?.claim_channels ?? null}
        hasMedicalIndemnity={items.some(
          (item) =>
            item.kind === "medical_indemnity" && item.status !== "not_found",
        )}
      />
    </div>
  );
}
