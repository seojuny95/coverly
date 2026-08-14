import type { FormEventHandler, RefObject } from "react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";

export function ChatComposer({
  question,
  suggestions,
  streaming,
  sessionExpired,
  turnsRemaining,
  inputRef,
  onQuestionChange,
  onSuggestion,
  onSubmit,
}: {
  question: string;
  suggestions: string[];
  streaming: boolean;
  sessionExpired: boolean;
  turnsRemaining: number;
  inputRef: RefObject<HTMLInputElement | null>;
  onQuestionChange: (question: string) => void;
  onSuggestion: (suggestion: string) => void;
  onSubmit: FormEventHandler<HTMLFormElement>;
}) {
  const outOfTurns = turnsRemaining <= 0;
  const inputDisabled = sessionExpired || outOfTurns;

  return (
    <div className="border-t border-zinc-100 bg-white p-4">
      {sessionExpired ? <ExpiredSessionNotice /> : null}
      {!sessionExpired && outOfTurns ? <TurnLimitNotice /> : null}

      {suggestions.length > 0 ? (
        <div className="mb-3 flex gap-2 overflow-x-auto pb-1">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              disabled={streaming || inputDisabled}
              onClick={() => onSuggestion(suggestion)}
              className="shrink-0 rounded-full border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-50"
            >
              {suggestion}
            </button>
          ))}
        </div>
      ) : null}

      <form onSubmit={onSubmit}>
        <div className="mb-2 flex items-baseline justify-between gap-2">
          <label htmlFor="insurance-question" className="sr-only">
            보험 질문
          </label>
          <p
            aria-live="polite"
            className={`ml-auto text-xs tabular-nums transition-colors ${
              outOfTurns
                ? "text-zinc-400"
                : turnsRemaining <= 3
                  ? "font-medium text-amber-700"
                  : "text-zinc-500"
            }`}
          >
            질문 {turnsRemaining}번 남음
          </p>
        </div>
        <div className="flex gap-2">
          <Input
            ref={inputRef}
            id="insurance-question"
            value={question}
            onChange={(event) => onQuestionChange(event.target.value)}
            disabled={inputDisabled}
            autoComplete="off"
            autoCorrect="off"
            spellCheck={false}
            placeholder={
              outOfTurns
                ? "질문 횟수를 모두 사용했어요"
                : "예: 겹치는 보장이 있나요?"
            }
            className="h-auto min-w-0 flex-1 rounded-xl border border-zinc-300 px-4 py-3 text-sm outline-none focus:border-blue-600 focus-visible:ring-0 disabled:bg-zinc-100 disabled:text-zinc-500"
          />
          <Button
            type="submit"
            disabled={!question.trim() || streaming || inputDisabled}
          >
            질문하기
          </Button>
        </div>
      </form>
    </div>
  );
}

function ExpiredSessionNotice() {
  return (
    <div
      role="status"
      className="mb-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-950"
    >
      분석 세션이 만료됐어요. 다시 분석하려면 보험증권을 다시 올려주세요.
    </div>
  );
}

function TurnLimitNotice() {
  return (
    <div
      role="status"
      className="motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-2 mb-3 flex items-start gap-3 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm leading-6 text-blue-950 motion-safe:duration-300"
    >
      <span aria-hidden className="mt-0.5 text-base">
        💬
      </span>
      <span>
        이 분석에서 할 수 있는 질문을 모두 사용했어요. 보험증권을 다시 올려 새로
        분석하면 이어서 물어볼 수 있어요.
      </span>
    </div>
  );
}
