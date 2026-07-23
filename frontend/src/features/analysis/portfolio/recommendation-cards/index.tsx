import { cardVariants } from "@/shared/components/ui/card";
import { cn } from "@/shared/lib/utils";

import type {
  DeathBenefitGuideInput,
  EssentialCoverageItem,
  PortfolioSummary,
} from "../api";
import { RecommendedDeathBenefitCard } from "./death-benefit-card";
import {
  RecommendedDiagnosisCard,
  recommendedDiagnosisItems,
} from "./diagnosis-card";
import { RecommendedMedicalIndemnityCard } from "./medical-indemnity-card";

export { recommendedDiagnosisItems };

export function RecommendedInsuranceCards({
  actualLossCoverages,
  items,
  deathBenefitContext,
  onDeathBenefitContextChange,
  isDeathBenefitRefreshing,
}: {
  actualLossCoverages: PortfolioSummary["actual_loss_coverages"];
  items: EssentialCoverageItem[];
  deathBenefitContext: DeathBenefitGuideInput;
  onDeathBenefitContextChange: (context: DeathBenefitGuideInput) => void;
  isDeathBenefitRefreshing: boolean;
}) {
  const death = items.find((item) => item.kind === "death");
  const diagnosisItems = recommendedDiagnosisItems(items);
  const medicalIndemnity = items.find(
    (item) => item.kind === "medical_indemnity",
  );
  const diagnosisConfirmedCount = diagnosisItems.filter(
    (item) => item.status !== "not_found",
  ).length;

  return (
    <article
      className={cn(cardVariants(), "animate-enter p-5 delay-100 sm:p-6")}
    >
      <div>
        <p className="text-xs font-semibold tracking-[0.1em] text-blue-700 uppercase">
          핵심 보장 확인
        </p>
      </div>

      <div className="mt-4 space-y-4">
        <RecommendedDeathBenefitCard
          item={death}
          deathBenefitContext={deathBenefitContext}
          onDeathBenefitContextChange={onDeathBenefitContextChange}
          isRefreshing={isDeathBenefitRefreshing}
        />

        <RecommendedDiagnosisCard
          items={diagnosisItems}
          confirmedCount={diagnosisConfirmedCount}
        />

        <RecommendedMedicalIndemnityCard
          actualLossCoverages={actualLossCoverages}
          item={medicalIndemnity}
        />
      </div>
    </article>
  );
}
