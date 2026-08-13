import { SectionLabel } from "@/shared/components/section-label";

const dontDoItems = [
  {
    title: "보험을 팔지 않아요",
    description: "보험사에서 수수료를 받지 않아요. 분석만 해요.",
  },
  {
    title: "추측하지 않아요",
    description:
      "AI가 약관에서 확인한 내용만 말해요. 확인이 안 되면 모른다고 해요.",
  },
  {
    title: "개인정보를 남기지 않아요",
    description: "이름, 증권번호 같은 정보는 가려서 처리해요.",
  },
];

export function TrustPrinciples() {
  return (
    <section
      aria-label="Coverly가 하지 않는 것"
      className="mx-auto w-full max-w-6xl px-6 pb-24 lg:px-8"
    >
      <div className="flex justify-center">
        <SectionLabel>WHAT WE DON&apos;T DO</SectionLabel>
      </div>
      <div className="mx-auto mt-6 grid max-w-4xl gap-3 sm:grid-cols-3">
        {dontDoItems.map((item) => (
          <div
            key={item.title}
            className="rounded-2xl border border-zinc-200 bg-white px-5 py-5 text-left shadow-[5px_5px_0_#f4f4f5]"
          >
            <p className="text-sm font-semibold tracking-[-0.02em] text-zinc-950">
              {item.title}
            </p>
            <p className="mt-2 text-sm leading-6 [word-break:keep-all] text-zinc-500">
              {item.description}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
