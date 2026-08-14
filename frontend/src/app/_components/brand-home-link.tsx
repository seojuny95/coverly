"use client";

import { usePathname } from "next/navigation";

import { LeaveGuardLink } from "@/features/analysis/session/leave-guard-link";
import { useInsuranceData } from "@/features/analysis/session/store";
import { isAnalysisPath } from "@/features/analysis/routes";
import {
  BrandLink,
  BrandMark,
  brandLinkClassName,
} from "@/shared/components/brand";

const positionClassName = "absolute top-6 left-6 z-40 lg:left-8";

export function BrandHomeLink() {
  const pathname = usePathname();
  const { hasData } = useInsuranceData();

  if (isAnalysisPath(pathname) && hasData) {
    return (
      <LeaveGuardLink
        href="/"
        enabled
        className={`${brandLinkClassName} ${positionClassName}`}
        ariaLabel="Coverly AI 홈"
      >
        <BrandMark />
      </LeaveGuardLink>
    );
  }

  return <BrandLink className={positionClassName} />;
}
