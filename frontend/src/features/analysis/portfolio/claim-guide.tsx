import { Alert, AlertDescription } from "@/shared/components/ui/alert";
import { Badge } from "@/shared/components/ui/badge";
import { Card } from "@/shared/components/ui/card";

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
      <Card variant="muted" className="rounded-[28px] p-5 sm:p-7">
        <p className="text-xs font-semibold tracking-[0.1em] text-blue-700 uppercase">
          보험금 청구 채널
        </p>
        <h2 id="claim-guide-title" className="mt-2 text-xl font-semibold">
          확인된 접수 채널을 모았어요
        </h2>
        <ClaimChannelOptions claimChannels={claimChannels} />
      </Card>
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
        <Alert variant="info" className="gap-0 px-3 py-2.5 text-xs leading-5">
          <AlertDescription className="text-xs text-zinc-600 [&_p:not(:last-child)]:mb-0">
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
          </AlertDescription>
        </Alert>
      ) : null}

      {claimChannels.insurers?.length ? (
        <details className="rounded-xl border border-zinc-200 bg-white px-3 py-2.5">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 marker:content-none [&::-webkit-details-marker]:hidden">
            <span>
              <span className="text-sm font-semibold text-zinc-900">
                보험사별 청구 채널
              </span>
            </span>
            <Badge
              variant="neutral"
              className="h-auto px-2.5 py-1 text-[11px] font-medium"
            >
              {claimChannels.insurers.length}곳
            </Badge>
          </summary>

          <ul className="mt-3 space-y-3 border-t border-zinc-100 pt-3 text-xs leading-5 text-zinc-600">
            {claimChannels.insurers.map((insurer) => (
              <li key={insurer.name}>
                <Card variant="muted" className="rounded-lg border-none p-3">
                  <p className="font-semibold text-zinc-900">{insurer.name}</p>
                  {insurer.customer_center ? (
                    <p className="mt-1 text-zinc-500">
                      고객센터 {insurer.customer_center}
                    </p>
                  ) : null}
                  {insurer.note ? (
                    <p className="mt-1 text-zinc-500">{insurer.note}</p>
                  ) : null}
                  <ChannelLinkList
                    links={insurer.links ?? []}
                    className="mt-2"
                  />
                </Card>
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
              <Badge
                key={`${link.label}-${link.url}`}
                variant="neutral"
                className="h-auto px-2.5 py-1 text-[11px] font-medium text-zinc-500"
              >
                {link.label}
              </Badge>
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
