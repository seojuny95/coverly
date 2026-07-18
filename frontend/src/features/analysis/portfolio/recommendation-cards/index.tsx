import { Card } from "@/shared/components/ui/card";

import type { DeathBenefitGuideInput, EssentialCoverageItem } from "../api";
import { RecommendedDeathBenefitCard } from "./death-benefit-card";
import {
  RecommendedDiagnosisCard,
  recommendedDiagnosisItems,
} from "./diagnosis-card";
import { RecommendedMedicalIndemnityCard } from "./medical-indemnity-card";

export { recommendedDiagnosisItems };

export function RecommendedInsuranceCards({
  items,
  deathBenefitContext,
  onDeathBenefitContextChange,
  isDeathBenefitRefreshing,
}: {
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
    <Card className="analysis-overview-reveal analysis-overview-delay-1 p-5 sm:p-6">
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

        <RecommendedMedicalIndemnityCard item={medicalIndemnity} />
      </div>
    </Card>
  );
}
