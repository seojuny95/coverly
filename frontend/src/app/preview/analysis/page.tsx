import { notFound } from "next/navigation";

import { PortfolioAnalysisPreview } from "@/features/portfolio/portfolio-analysis-preview";

export default function Page() {
  if (process.env.NODE_ENV !== "development") notFound();
  return <PortfolioAnalysisPreview />;
}
