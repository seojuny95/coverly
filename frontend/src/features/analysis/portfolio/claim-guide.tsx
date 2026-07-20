"use client";

import { ExternalLink } from "lucide-react";

import { Alert, AlertDescription } from "@/shared/components/ui/alert";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card } from "@/shared/components/ui/card";
import { CollapseRegion, useDisclosure } from "@/shared/components/disclosure";

import type { ClaimChannelBlock } from "./api";
import { safeHref } from "./safe-href";

const CLAIM_STEPS = [
  {
    title: "보장 내용 확인",
    description:
      "사고나 진단 일자와 내용을 정리하고, 증권과 약관에서 청구할 보장을 확인해요.",
  },
  {
    title: "필요 서류 준비",
    description:
      "보험사 안내에서 필요한 서류를 확인해요. 청구 사유와 보장에 따라 준비할 서류가 달라질 수 있어요.",
  },
  {
    title: "청구 접수",
    description:
      "실손24 또는 가입한 보험사의 앱, 홈페이지, 고객센터 중 편한 채널을 선택해 접수해요.",
  },
  {
    title: "진행 상황 확인",
    description:
      "접수번호를 보관하고 추가 서류 요청과 보험사의 심사 결과를 확인해요.",
  },
] as const;

export function ClaimGuide({
  claimChannels,
  hasMedicalIndemnity,
}: {
  claimChannels: ClaimChannelBlock | null;
  hasMedicalIndemnity: boolean;
}) {
  return (
    // Continues the panel's enter stagger (0/100/200ms) as the last section in render order.
    <section
      aria-labelledby="claim-guide-title"
      className="animate-enter delay-300"
    >
      <Card variant="muted" className="rounded-[28px] p-5 sm:p-7">
        <p className="text-xs font-semibold tracking-[0.1em] text-blue-700 uppercase">
          보험금 청구 방법
        </p>
        <h2 id="claim-guide-title" className="mt-2 text-xl font-semibold">
          청구 순서와 접수 채널을 확인해요
        </h2>
        <p className="mt-2 text-sm leading-6 text-zinc-600">
          필요한 서류는 청구하려는 보장과 보험사에 따라 달라질 수 있어요.
        </p>

        <ol className="mt-6 space-y-5">
          {CLAIM_STEPS.map((step, index) => (
            <li key={step.title} className="flex gap-3">
              <span className="grid size-7 shrink-0 place-items-center rounded-full bg-blue-600 font-mono text-xs font-semibold text-white">
                {index + 1}
              </span>
              <div>
                <h3 className="text-sm font-semibold text-zinc-950">
                  {step.title}
                </h3>
                <p className="mt-1 text-sm leading-6 text-zinc-600">
                  {step.description}
                </p>
                {index === 2 && claimChannels?.medical_indemnity ? (
                  <ChannelLinkList
                    links={claimChannels.medical_indemnity.links ?? []}
                    className="mt-2"
                    prominent
                  />
                ) : null}
              </div>
            </li>
          ))}
        </ol>

        {(hasMedicalIndemnity && claimChannels?.medical_indemnity) ||
        claimChannels?.insurers?.length ? (
          <ClaimChannelOptions
            claimChannels={claimChannels}
            hasMedicalIndemnity={hasMedicalIndemnity}
          />
        ) : null}
      </Card>
    </section>
  );
}

function ClaimChannelOptions({
  claimChannels,
  hasMedicalIndemnity,
}: {
  claimChannels: ClaimChannelBlock;
  hasMedicalIndemnity: boolean;
}) {
  return (
    <div className="mt-6 space-y-4 border-t border-zinc-200 pt-5">
      {hasMedicalIndemnity && claimChannels.medical_indemnity ? (
        <Alert
          variant="info"
          role="note"
          className="gap-0 rounded-xl px-4 py-3 text-xs leading-5"
        >
          <AlertDescription className="text-xs text-zinc-600 [&_p:not(:last-child)]:mb-0">
            <p className="text-sm font-semibold text-zinc-900">
              실손의료보험은 {claimChannels.medical_indemnity.name}로 청구할 수
              있어요
            </p>
            {claimChannels.medical_indemnity.description ? (
              <p className="mt-1">
                {claimChannels.medical_indemnity.description}
              </p>
            ) : null}
            <p className="mt-2 font-medium text-zinc-700">
              본인확인 → 보험사 선택 → 진료·처방 내역 선택 → 청구서 작성·전송
              순서로 진행해요.
            </p>
            <p className="mt-1 text-zinc-500">
              실손24와 연계된 병원·약국인지 먼저 확인하고, 필요한 추가 서류가
              있다면 함께 첨부해요.
            </p>
            {claimChannels.medical_indemnity.call_center ? (
              <p className="mt-1 text-zinc-500">
                콜센터 {claimChannels.medical_indemnity.call_center}
              </p>
            ) : null}
          </AlertDescription>
        </Alert>
      ) : null}

      {claimChannels.insurers?.length ? (
        <InsurerChannelList insurers={claimChannels.insurers} />
      ) : null}
    </div>
  );
}

function InsurerChannelList({
  insurers,
}: {
  insurers: NonNullable<ClaimChannelBlock["insurers"]>;
}) {
  const { expanded, toggle, panelId } = useDisclosure();

  return (
    <div className="rounded-xl border border-zinc-200 bg-white px-3 py-2.5">
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={toggle}
        className="flex w-full cursor-pointer items-center justify-between gap-3 rounded-lg text-left focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:outline-none"
      >
        <span>
          <span className="text-sm font-semibold text-zinc-900">
            가입한 보험사별 청구 채널
          </span>
          <span className="mt-1 block text-xs text-zinc-500">
            가입한 보험사의 접수 링크와 고객센터만 모았어요.
          </span>
        </span>
        <Badge
          variant="neutral"
          className="h-auto px-2.5 py-1 text-[11px] font-medium"
        >
          {insurers.length}곳
        </Badge>
      </button>

      <CollapseRegion expanded={expanded} id={panelId}>
        <ul className="mt-3 divide-y divide-zinc-100 border-t border-zinc-100 text-xs leading-5 text-zinc-600">
          {insurers.map((insurer) => (
            <li key={insurer.name} className="py-3 first:pt-3 last:pb-0">
              <div className="px-1">
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
              </div>
            </li>
          ))}
        </ul>
      </CollapseRegion>
    </div>
  );
}

function ChannelLinkList({
  links,
  className,
  prominent = false,
}: {
  links: NonNullable<
    NonNullable<ClaimChannelBlock["insurers"]>[number]["links"]
  >;
  className?: string;
  prominent?: boolean;
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
            <Button
              key={`${link.label}-${link.url}`}
              asChild
              variant="outline"
              size={prominent ? "sm" : "xs"}
              className="border-blue-200 text-blue-700 hover:border-blue-300 hover:bg-blue-50"
            >
              <a href={href} target="_blank" rel="noreferrer">
                <ExternalLink data-icon="inline-start" />
                {link.label}
              </a>
            </Button>
          );
        })}
      </div>
    </div>
  );
}
