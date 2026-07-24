import type {
  QaMetaEvent,
  QaRequest,
  QaStreamEvent,
} from "../../../shared/api/contracts";
import {
  QaStreamProtocolError,
  QaStreamResponseError,
  requireQaStreamEvent,
} from "../../../shared/api/qa-stream";
import type { ChatHistoryItem } from "./types";
import { consumeQaStream } from "./qa-stream-transport";

type QaStreamHandlers = {
  onMeta?: (meta: QaMetaEvent) => void;
  onDelta: (text: string) => void | Promise<void>;
  onEnd: () => void;
};

export async function streamPortfolioQuestion(
  question: string,
  history: ChatHistoryItem[],
  handlers: QaStreamHandlers,
  portfolioSessionToken: string,
  signal?: AbortSignal,
): Promise<void> {
  const body = {
    question,
    session_id: portfolioSessionToken,
    history,
  } satisfies QaRequest;
  await consumeQaStream(body, signal, async (reader) => {
    const decoder = new TextDecoder();
    let buffer = "";
    const protocol: { phase: "meta" | "answer" | "end" } = { phase: "meta" };

    const dispatch = async (frame: string) => {
      const data = frame
        .split(/\r?\n/)
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (!data) return;

      let payload: unknown;
      try {
        payload = JSON.parse(data);
      } catch {
        throw new QaStreamProtocolError();
      }
      const event: QaStreamEvent = requireQaStreamEvent(payload);

      if (event.type === "meta") {
        if (protocol.phase !== "meta") throw new QaStreamProtocolError();
        protocol.phase = "answer";
        handlers.onMeta?.(event);
      } else if (event.type === "delta") {
        if (protocol.phase !== "answer") throw new QaStreamProtocolError();
        await handlers.onDelta(event.text);
      } else if (event.type === "end") {
        if (protocol.phase !== "answer") throw new QaStreamProtocolError();
        protocol.phase = "end";
        handlers.onEnd();
      } else if (event.type === "error") {
        if (protocol.phase !== "answer") throw new QaStreamProtocolError();
        protocol.phase = "end";
        throw new QaStreamResponseError(event);
      }
    };

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary = nextSseBoundary(buffer);
      while (boundary) {
        await dispatch(buffer.slice(0, boundary.index));
        buffer = buffer.slice(boundary.index + boundary.length);
        if (protocol.phase === "end") {
          await reader.cancel();
          return;
        }
        boundary = nextSseBoundary(buffer);
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) await dispatch(buffer);
    if (protocol.phase !== "end") throw new QaStreamProtocolError();
  });
}

function nextSseBoundary(
  buffer: string,
): { index: number; length: number } | null {
  const match = /\r?\n\r?\n/.exec(buffer);
  return match ? { index: match.index, length: match[0].length } : null;
}
