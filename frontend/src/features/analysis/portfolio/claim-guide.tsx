import type { ClaimChannelBlock } from "./api";
import { safeHref } from "./safe-href";

export function ClaimGuide({
  claimChannels,
}: {
  claimChannels: ClaimChannelBlock | null;
}) {
  const steps = [
    {
      title: "보장 대상인지 먼저 확인",
      description:
        "사고·진단 일자와 내용을 정리하고, 증권과 약관에서 해당 위험이 보장되는지 살펴봐요.",
    },
    {
      title: "청구 서류 준비",
      description:
        "공통으로 청구서와 신분증을 준비해요. 진단비는 진단서, 실손의료비는 진료비 계산서·영수증과 세부내역서가 기본이에요.",
    },
    {
      title: "청구 채널 선택",
      description:
        "실손의료비는 실손24와 보험사 채널 중에서 고를 수 있어요. 그 외 보험금은 보험사 앱·홈페이지·우편·방문 중 가능한 방법으로 접수해요.",
    },
    {
      title: "접수와 심사 결과 확인",
      description:
        "접수번호와 담당자를 확인하고, 추가 서류 요청이나 지급 결과를 살펴봐요. 청구권은 일반적으로 사고 발생 후 3년 안에 행사해야 해요.",
    },
  ];

  return (
    <section aria-labelledby="claim-guide-title">
      <div className="rounded-[28px] border border-zinc-200 bg-zinc-50 p-5 sm:p-7">
        <p className="text-xs font-semibold tracking-[0.1em] text-blue-700 uppercase">
          보험금 청구 방법
        </p>
        <h2 id="claim-guide-title" className="mt-2 text-xl font-semibold">
          접수까지 네 단계로 준비해요
        </h2>
        <ol className="mt-6 space-y-3">
          {steps.map((step, index) => (
            <li
              key={step.title}
              className="rounded-2xl border border-zinc-200 bg-white p-4"
            >
              <div className="flex gap-3">
                <span className="grid size-8 shrink-0 place-items-center rounded-full bg-blue-600 font-mono text-sm font-semibold text-white">
                  {index + 1}
                </span>
                <div>
                  <h3 className="text-sm font-semibold">{step.title}</h3>
                  <p className="mt-1 text-sm leading-6 text-zinc-600">
                    {step.description}
                  </p>
                  {index === 2 &&
                  (claimChannels?.medical_indemnity ||
                    claimChannels?.insurers.length) ? (
                    <ClaimChannelOptions claimChannels={claimChannels} />
                  ) : null}
                </div>
              </div>
            </li>
          ))}
        </ol>

        <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3">
          <p className="text-sm font-semibold text-amber-950">
            가입 당시 알린 내용도 확인해두세요
          </p>
          <p className="mt-1 text-xs leading-5 text-amber-900/80">
            청구 심사에서는 가입 당시 청약서에 답한 내용과 약관을 확인할 수
            있어요. 고지 대상과 질문 기간은 계약마다 다르므로, 기억에만 의존하지
            말고 청약서 원문을 기준으로 살펴보세요.
          </p>
        </div>
      </div>
    </section>
  );
}

function ClaimChannelOptions({
  claimChannels,
}: {
  claimChannels: ClaimChannelBlock;
}) {
  return (
    <div className="mt-3 space-y-3">
      {claimChannels.medical_indemnity ? (
        <div className="rounded-xl border border-blue-100 bg-blue-50 px-3 py-2.5 text-xs leading-5 text-zinc-600">
          <p className="font-semibold text-zinc-900">
            {claimChannels.medical_indemnity.name}
          </p>
          {claimChannels.medical_indemnity.description ? (
            <p className="mt-1">
              {claimChannels.medical_indemnity.description}
            </p>
          ) : null}
          <p className="mt-1">
            참여 병원이라면 진료비 서류를 전자 전송할 수 있어요. 먼저 연계
            병원인지 확인해요.
          </p>
          {claimChannels.medical_indemnity.call_center ? (
            <p className="mt-1 text-zinc-500">
              콜센터 {claimChannels.medical_indemnity.call_center}
            </p>
          ) : null}
          <ChannelLinkList
            links={claimChannels.medical_indemnity.links}
            className="mt-2"
          />
        </div>
      ) : null}

      {claimChannels.insurers.length ? (
        <details className="rounded-xl border border-zinc-200 bg-white px-3 py-2.5">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 marker:content-none [&::-webkit-details-marker]:hidden">
            <span>
              <span className="text-sm font-semibold text-zinc-900">
                가입한 보험사 청구 채널 보기
              </span>
              <span className="mt-1 block text-xs text-zinc-500">
                가입한 보험사의 앱이나 홈페이지에서 직접 청구할 수 있어요.
              </span>
            </span>
            <span className="rounded-full bg-zinc-100 px-2.5 py-1 text-[11px] font-medium text-zinc-600">
              {claimChannels.insurers.length}곳
            </span>
          </summary>

          <ul className="mt-3 space-y-3 border-t border-zinc-100 pt-3 text-xs leading-5 text-zinc-600">
            {claimChannels.insurers.map((insurer) => (
              <li key={insurer.name} className="rounded-lg bg-zinc-50 p-3">
                <p className="font-semibold text-zinc-900">{insurer.name}</p>
                {insurer.customer_center ? (
                  <p className="mt-1 text-zinc-500">
                    고객센터 {insurer.customer_center}
                  </p>
                ) : null}
                {insurer.note ? (
                  <p className="mt-1 text-zinc-500">{insurer.note}</p>
                ) : null}
                <ChannelLinkList links={insurer.links} className="mt-2" />
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

function ChannelLinkList({
  links,
  className,
}: {
  links: ClaimChannelBlock["insurers"][number]["links"];
  className?: string;
}) {
  if (!links.length) return null;

  return (
    <div className={className}>
      <div className="flex flex-wrap gap-2">
        {links.map((link) => {
          const href = safeHref(link.url);
          if (!href) {
            return (
              <span
                key={`${link.label}-${link.url}`}
                className="rounded-full bg-zinc-100 px-2.5 py-1 text-[11px] font-medium text-zinc-500"
              >
                {link.label}
              </span>
            );
          }

          return (
            <a
              key={`${link.label}-${link.url}`}
              href={href}
              target="_blank"
              rel="noreferrer"
              className="rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-blue-700 ring-1 ring-blue-200"
            >
              {link.label}
            </a>
          );
        })}
      </div>
    </div>
  );
}
