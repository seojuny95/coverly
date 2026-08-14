import { SectionLabel } from "@/shared/components/section-label";
import { Button } from "@/shared/components/ui/button";
import {
  POLICY_CLASSIFICATIONS,
  PORTFOLIO_MAX_DOCUMENTS,
} from "@/shared/api/generated-runtime";

export function PolicyOverviewHeader({
  selectedName,
  generatedAt,
  uploadLimitReached,
  onOpenUploadModal,
}: {
  selectedName?: string | null;
  generatedAt: string;
  uploadLimitReached: boolean;
  onOpenUploadModal: () => void;
}) {
  const classificationCount = POLICY_CLASSIFICATIONS.length;

  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <div className="mb-4">
          <SectionLabel>나의 보장 지도</SectionLabel>
        </div>
        <h1 className="text-3xl font-semibold tracking-[-0.05em] text-zinc-950 sm:text-4xl">
          내 보험을 종류별로 정리했어요
        </h1>
        <p className="mt-3 text-sm leading-6 text-zinc-500">
          {selectedName
            ? `${selectedName}님의 보험을 ${classificationCount}가지 종류로 보기 쉽게 정리했어요.`
            : `보험을 ${classificationCount}가지 종류로 보기 쉽게 정리했어요.`}
        </p>
      </div>
      <div className="flex flex-col items-start gap-3 sm:items-end">
        <Button
          type="button"
          onClick={onOpenUploadModal}
          disabled={uploadLimitReached}
          aria-describedby={
            uploadLimitReached ? "portfolio-upload-limit-notice" : undefined
          }
        >
          보험증권 더 올리기
        </Button>
        {uploadLimitReached ? (
          <p
            id="portfolio-upload-limit-notice"
            role="status"
            className="max-w-xs text-xs leading-5 text-zinc-500 sm:text-right"
          >
            보험증권은 최대 {PORTFOLIO_MAX_DOCUMENTS}개까지 분석할 수 있어요.
            현재 분석에는 보험증권을 더 추가할 수 없어요.
          </p>
        ) : null}
        <p className="font-mono text-[10px] tracking-[0.04em] text-zinc-400">
          정리한 시각 {formatDateTime(generatedAt)}
        </p>
      </div>
    </div>
  );
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
