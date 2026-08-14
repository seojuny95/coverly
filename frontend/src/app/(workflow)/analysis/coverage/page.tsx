import { AnalysisPageIntro } from "../_components/page-intro";
import { CoverageAnalysis } from "@/features/analysis/coverage/analysis";

export default function Page() {
  return (
    <>
      <AnalysisPageIntro
        label="내 보험 분석"
        title="가입한 보험을 한눈에 확인해요"
        description="전체 보험에서 사망·3대 진단비·실손의료비를 확인하고, 보험 종류별 보장도 함께 정리해요."
      />
      <CoverageAnalysis />
    </>
  );
}
