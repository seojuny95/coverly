import type { ClaimChannelBlock } from "./api";
import { safeHref } from "./safe-href";

export function ClaimGuide({
  claimChannels,
}: {
  claimChannels: ClaimChannelBlock | null;
}) {
  if (!claimChannels?.medical_indemnity && !claimChannels?.insurers?.length) {
    return null;
  }

  return (
    <section aria-labelledby="claim-guide-title">
      <div className="rounded-[28px] border border-zinc-200 bg-zinc-50 p-5 sm:p-7">
        <p className="text-xs font-semibold tracking-[0.1em] text-blue-700 uppercase">
          보험금 청구 채널
        </p>
        <h2 id="claim-guide-title" className="mt-2 text-xl font-semibold">
          확인된 접수 채널을 모았어요
        </h2>
        <ClaimChannelOptions claimChannels={claimChannels} />
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
          {claimChannels.medical_indemnity.call_center ? (
            <p className="mt-1 text-zinc-500">
              콜센터 {claimChannels.medical_indemnity.call_center}
            </p>
          ) : null}
          <ChannelLinkList
            links={claimChannels.medical_indemnity.links ?? []}
            className="mt-2"
          />
        </div>
      ) : null}

      {claimChannels.insurers?.length ? (
        <details className="rounded-xl border border-zinc-200 bg-white px-3 py-2.5">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 marker:content-none [&::-webkit-details-marker]:hidden">
            <span>
              <span className="text-sm font-semibold text-zinc-900">
                보험사별 청구 채널
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
                <ChannelLinkList links={insurer.links ?? []} className="mt-2" />
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
  links: NonNullable<
    NonNullable<ClaimChannelBlock["insurers"]>[number]["links"]
  >;
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
