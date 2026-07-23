import Image from "next/image";

import { Alert } from "@/shared/components/ui/alert";
import { Badge } from "@/shared/components/ui/badge";
import { Card } from "@/shared/components/ui/card";
import type {
  InsuranceBasicInfo,
  InsurancePeriod,
  InsurancePremium,
} from "../upload/api";
import { formatWon } from "./portfolio/money-format";
import type { AnalyzedInsurance } from "./store";
import { InsuranceCoverageList } from "./coverage-list";
import insurerLogos from "./insurer-logos.json";
import { normalizeInsurerName } from "./policy-identity";

const INSURER_LOGOS = insurerLogos;

const TAG_STYLES: Record<string, string> = {
  사망보험: "border-[#4F46E5]/10 bg-[#4F46E5]/[0.06] text-[#111827]/60",
  종신보험: "border-[#4F46E5]/10 bg-[#4F46E5]/[0.06] text-[#111827]/60",
  정기보험: "border-[#6366F1]/10 bg-[#6366F1]/[0.06] text-[#111827]/60",
  연금보험: "border-[#0284C7]/10 bg-[#0284C7]/[0.06] text-[#111827]/60",
  양로보험: "border-[#0D9488]/10 bg-[#0D9488]/[0.06] text-[#111827]/60",
  저축보험: "border-[#65A30D]/10 bg-[#65A30D]/[0.06] text-[#111827]/60",
  질병보험: "border-[#0891B2]/10 bg-[#0891B2]/[0.06] text-[#111827]/60",
  상해보험: "border-[#EA580C]/10 bg-[#EA580C]/[0.06] text-[#111827]/60",
  간병보험: "border-[#7C3AED]/10 bg-[#7C3AED]/[0.06] text-[#111827]/60",
  실손의료보험: "border-[#2563EB]/10 bg-[#2563EB]/[0.06] text-[#111827]/60",
  어린이보험: "border-[#DB2777]/10 bg-[#DB2777]/[0.06] text-[#111827]/60",
  자동차보험: "border-[#2563EB]/10 bg-[#2563EB]/[0.06] text-[#111827]/60",
  운전자보험: "border-[#1D4ED8]/10 bg-[#1D4ED8]/[0.06] text-[#111827]/60",
  여행자보험: "border-[#0F766E]/10 bg-[#0F766E]/[0.06] text-[#111827]/60",
  화재보험: "border-[#F97316]/10 bg-[#F97316]/[0.06] text-[#111827]/60",
  배상책임보험: "border-[#0F766E]/10 bg-[#0F766E]/[0.06] text-[#111827]/60",
  보증보험: "border-[#71717A]/10 bg-[#71717A]/[0.06] text-[#111827]/60",
};

export function InsuranceDetail({
  insuranceDocument,
  isExpanded,
}: {
  insuranceDocument: AnalyzedInsurance;
  isExpanded: boolean;
}) {
  const basicInfo = insuranceDocument.result.기본정보;
  const detailItems = [
    ["보험사", basicInfo?.보험사],
    ["증권번호", basicInfo?.증권번호],
    ["계약자", basicInfo?.계약자],
    ["피보험자", basicInfo?.피보험자],
    ["보험기간", formatPeriod(basicInfo?.보험기간)],
    ["만기일", basicInfo?.만기일],
    ["납입기간", basicInfo?.납입기간],
    ["보험료", formatPremium(basicInfo?.보험료)],
    ["차량명", basicInfo?.차량정보?.차량명],
    ["차량번호", basicInfo?.차량정보?.차량번호],
    ["연식", basicInfo?.차량정보?.연식],
  ].filter((item): item is [string, string] => Boolean(item[1]));

  return (
    <div
      className={`border-t border-zinc-100 bg-zinc-50/70 px-5 py-5 transition-all duration-200 ease-out ${
        isExpanded ? "translate-y-0 opacity-100" : "-translate-y-1 opacity-0"
      }`}
    >
      {insuranceDocument.result.policy_terms_status === "unavailable" ? (
        <Alert
          variant="warning"
          role="note"
          className="mb-5 px-4 py-3 text-sm leading-6"
        >
          약관 질문에 필요한 자료를 준비하지 못했어요. 이 증권의 보장 분석은
          그대로 확인할 수 있어요.
        </Alert>
      ) : null}

      <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {detailItems.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs font-medium text-zinc-500">{label}</dt>
            <dd className="mt-1 text-sm font-medium break-words text-zinc-800">
              {value}
            </dd>
          </div>
        ))}
      </dl>

      <div className="mt-6">
        <h3 className="text-xs font-medium text-zinc-500">보장 내용</h3>
        <Card className="mt-2 rounded-xl px-5 py-4">
          <InsuranceCoverageList
            coverages={insuranceDocument.result.보장목록}
            status={insuranceDocument.result.분석상태}
          />
        </Card>
      </div>
    </div>
  );
}

export function InsurerLogo({ insurerName }: { insurerName?: string }) {
  const logo = findInsurerLogo(insurerName);

  return (
    <Card className="flex h-10 min-w-[4.75rem] shrink-0 items-center justify-center rounded-xl px-2.5">
      {logo ? (
        <span className="relative flex h-7 w-full items-center justify-center overflow-hidden">
          <Image
            src={logo.src}
            alt=""
            aria-hidden="true"
            fill
            sizes="76px"
            className={`object-contain ${logo.imageClassName ?? ""}`}
          />
        </span>
      ) : (
        <span className="text-xs font-semibold text-zinc-400">
          {(insurerName ?? "?").slice(0, 1)}
        </span>
      )}
    </Card>
  );
}

export function TagBadge({ tag }: { tag: string }) {
  return (
    <Badge
      className={`h-6 rounded-full px-2 py-0 text-[11px] ${TAG_STYLES[tag] ?? "border-[#111827]/10 bg-[#111827]/[0.04] text-[#111827]/60"}`}
    >
      {tag}
    </Badge>
  );
}

function findInsurerLogo(insurerName?: string) {
  if (!insurerName) return undefined;

  const normalizedName = normalizeInsurerName(insurerName);
  return INSURER_LOGOS.find(({ aliases }) =>
    aliases.some((alias) =>
      normalizedName.includes(normalizeInsurerName(alias)),
    ),
  );
}

function formatPeriod(
  period: InsurancePeriod | InsuranceBasicInfo["보험기간"],
) {
  if (!period?.시작일 || !period.종료일) return undefined;
  return `${period.시작일} - ${period.종료일}`;
}

function formatPremium(
  premium: InsurancePremium | InsuranceBasicInfo["보험료"],
) {
  if (premium?.금액 === undefined) return undefined;
  const cycle = premium.납입주기 ? `${premium.납입주기} ` : "";
  return `${cycle}${formatWon(premium.금액)}`;
}
