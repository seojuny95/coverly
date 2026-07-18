import { InsuranceUploadForm } from "@/features/upload/form";
import { SectionLabel } from "@/shared/components/section-label";
import { BrandLink } from "@/shared/components/brand";

export default function UploadPage() {
  return (
    <main className="flex min-h-screen flex-col bg-white px-5 py-6 text-zinc-950 sm:px-6">
      <header className="mx-auto flex w-full max-w-5xl items-center justify-between">
        <BrandLink />
        <p className="font-mono text-[10px] tracking-[0.08em] text-zinc-400">
          CONNECT INSURANCE
        </p>
      </header>

      <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col justify-center py-12 sm:py-16">
        <section className="mx-auto w-full max-w-2xl text-center">
          <div className="mb-5 flex justify-center">
            <SectionLabel>보험증권 연결</SectionLabel>
          </div>
          <h1 className="text-4xl leading-[1.08] font-semibold tracking-[-0.055em] text-zinc-950 sm:text-5xl">
            내 보험을 한눈에 정리해요
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-base leading-7 text-zinc-500">
            보험증권 PDF만 올리면 돼요. 어려운 약관은 AI가 대신 읽고
            정리해드려요.
          </p>
        </section>

        <div className="mx-auto mt-10 w-full max-w-2xl">
          <InsuranceUploadForm />
        </div>
      </div>
    </main>
  );
}
