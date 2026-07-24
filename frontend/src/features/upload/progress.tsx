"use client";

import { useEffect, useState } from "react";
import { BrandMark } from "../../shared/components/brand";

const ANALYSIS_STEP_MESSAGES = [
  "증권에서 보장 내용을 찾고 있어요",
  "보장마다 확인한 근거를 붙이고 있어요",
];

const LONG_WAIT_MESSAGE = "파일이 길수록 조금 더 걸려요. 지금도 읽고 있어요.";
const ALMOST_DONE_MESSAGE = "거의 다 왔어요. 조금만 더 기다려주세요.";
// States only that reading finished — must not assert anything about the
// analysis results, which haven't been shown yet.
const COMPLETE_MESSAGE = "다 읽었어요. 결과를 보여드릴게요.";

// Full-screen (page) / inline (modal) progress view shown while uploads are in
// flight. Owns its own trickle/message/elapsed timers; the caller only feeds it
// milestone progress and the per-file done/reading state.
export function AnalysisProgress({
  progress,
  files,
  surface,
  isCompleting = false,
  isPreparingServer = false,
}: {
  progress: { completed: number; total: number };
  files: Array<{ name: string; status: "done" | "reading" | "waiting" }>;
  surface: "page" | "modal";
  isCompleting?: boolean;
  isPreparingServer?: boolean;
}) {
  const milestonePercent =
    progress.total > 0 ? (progress.completed / progress.total) * 100 : 0;
  // Trickle only fills up to 90% of the in-flight file's share; real
  // completions move the milestone, so the bar never fakes a finish.
  const trickleCapPercent = isPreparingServer
    ? 0
    : progress.total > 0
      ? Math.min(((progress.completed + 0.9) / progress.total) * 100, 100)
      : 90;
  const [displayPercent, setDisplayPercent] = useState(0);
  const [messageIndex, setMessageIndex] = useState(0);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setDisplayPercent(
        (current) => current + (trickleCapPercent - current) * 0.04,
      );
    }, 250);
    return () => clearInterval(timer);
  }, [trickleCapPercent]);

  useEffect(() => {
    const timer = setInterval(() => {
      setMessageIndex((current) => current + 1);
    }, 4000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const timer = setInterval(() => {
      setElapsedSeconds((current) => current + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const statusMessages = [
    ...ANALYSIS_STEP_MESSAGES,
    ...(elapsedSeconds >= 90
      ? [ALMOST_DONE_MESSAGE]
      : elapsedSeconds >= 30
        ? [LONG_WAIT_MESSAGE]
        : []),
  ];
  const statusMessage = isCompleting
    ? COMPLETE_MESSAGE
    : isPreparingServer
      ? "서버가 준비되면 증권을 바로 읽기 시작해요."
      : statusMessages[messageIndex % statusMessages.length];
  // Real milestones floor the trickle so completed files always show through.
  const percent = isCompleting
    ? 100
    : isPreparingServer
      ? 0
      : Math.round(Math.max(displayPercent, milestonePercent));
  const fileListClassName =
    files.length === 1
      ? "mt-5 grid w-full max-w-md grid-cols-1 gap-1.5 text-left"
      : "mt-5 grid w-full grid-cols-1 gap-1.5 text-left sm:grid-cols-2";

  return (
    <section
      role="status"
      className={`${
        surface === "modal"
          ? "flex w-full max-w-none flex-col items-center py-8 text-center"
          : "animate-enter-overlay fixed inset-0 z-50 flex items-center justify-center bg-white px-6 py-10 text-center"
      }`}
    >
      {surface === "page" ? (
        <span className="absolute top-6 left-5 flex items-center gap-1.5 sm:left-6">
          <BrandMark />
        </span>
      ) : null}
      <div className="animate-enter flex w-full max-w-[760px] flex-col items-center delay-150">
        <div className="analysis-pixel-loader grid size-16 grid-cols-3 gap-1.5 rounded-2xl border border-zinc-200 bg-white p-3 shadow-[7px_7px_0_#e8edff]">
          {Array.from({ length: 9 }).map((_, index) => (
            <span key={index} />
          ))}
        </div>
        <h1 className="mt-8 text-2xl font-semibold tracking-[-0.04em] text-zinc-950">
          {isPreparingServer
            ? "분석 서버를 준비하고 있어요"
            : "증권을 한 장씩 읽고 있어요"}
        </h1>
        <p className="mt-2 text-sm leading-6 text-zinc-500">
          {isPreparingServer
            ? "처음 연결할 때는 최대 1분 정도 걸릴 수 있어요"
            : "보통 1~2분 정도 걸려요"}
        </p>
        <div
          role="progressbar"
          aria-label="보험 분석 진행률"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          className="mt-7 h-1.5 w-full overflow-hidden rounded-sm bg-zinc-100"
        >
          <div
            className="h-full bg-blue-600 transition-all duration-300"
            style={{
              width: isPreparingServer ? "0%" : `${Math.max(percent, 4)}%`,
            }}
          />
        </div>
        {files.length > 0 ? (
          <ul aria-label="파일별 진행 상태" className={fileListClassName}>
            {files.map((file, index) => (
              <li
                key={`${file.name}-${index}`}
                className="flex min-w-0 items-center justify-between gap-3 rounded-lg border border-zinc-100 bg-white px-3 py-2 text-xs text-zinc-600"
              >
                <span className="truncate">{file.name}</span>
                {file.status === "done" ? (
                  <span className="shrink-0 font-medium text-blue-600">
                    완료
                  </span>
                ) : file.status === "waiting" ? (
                  <span className="shrink-0 text-zinc-400">대기 중</span>
                ) : (
                  <span className="shrink-0 animate-pulse text-zinc-400">
                    읽는 중
                  </span>
                )}
              </li>
            ))}
          </ul>
        ) : null}
        <p
          key={statusMessage}
          className="animate-enter mt-6 text-sm leading-6 text-zinc-500"
        >
          {statusMessage}
        </p>
        <p className="mt-1 text-xs text-zinc-400">
          확인이 안 되는 내용은 추측하지 않아요.
        </p>
      </div>
    </section>
  );
}
