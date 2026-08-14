import { SectionLabel } from "@/shared/components/section-label";

export function AnalysisPageIntro({
  label,
  title,
  description,
}: {
  label: string;
  title: string;
  description: string;
}) {
  return (
    <div className="mb-7">
      <SectionLabel>{label}</SectionLabel>
      <h1 className="mt-4 text-3xl font-semibold tracking-[-0.05em] sm:text-4xl">
        {title}
      </h1>
      <p className="mt-3 text-sm leading-6 text-zinc-500">{description}</p>
    </div>
  );
}
