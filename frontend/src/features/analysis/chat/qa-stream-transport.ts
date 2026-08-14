import { apiResponseError, apiUrl } from "@/shared/api/client";
import type { QaRequest } from "@/shared/api/contracts";
import { AppRequestError } from "@/shared/api/errors";
import { QaStreamProtocolError } from "@/shared/api/qa-stream";

const QA_CONNECTION_TIMEOUT_MS = 30 * 1000;
const QA_IDLE_TIMEOUT_MS = 45 * 1000;

export type TimedQaStreamReader = {
  cancel: () => Promise<void>;
  read: () => Promise<ReadableStreamReadResult<Uint8Array>>;
};

class QaStreamTimeoutError extends AppRequestError {
  constructor(phase: "connection" | "idle") {
    super({
      developerMessage: `QA stream ${phase} deadline exceeded`,
      name: "QaStreamTimeoutError",
      userMessage:
        "답변을 기다리는 시간이 길어지고 있어요. 잠시 후 다시 질문해주세요.",
    });
  }
}

export async function consumeQaStream<T>(
  body: QaRequest,
  signal: AbortSignal | undefined,
  consume: (reader: TimedQaStreamReader) => Promise<T>,
): Promise<T> {
  const controller = new AbortController();
  let connectionTimeoutError: QaStreamTimeoutError | undefined;
  const abortFromCaller = () => controller.abort(signal?.reason);
  if (signal?.aborted) throw abortReason(signal);
  signal?.addEventListener("abort", abortFromCaller, { once: true });

  const connectionTimeout = window.setTimeout(() => {
    connectionTimeoutError = new QaStreamTimeoutError("connection");
    controller.abort(connectionTimeoutError);
  }, QA_CONNECTION_TIMEOUT_MS);

  try {
    const response = await openStream(
      body,
      controller,
      () => connectionTimeoutError,
    );
    window.clearTimeout(connectionTimeout);

    const reader = response.body!.getReader();
    const timedReader: TimedQaStreamReader = {
      cancel: async () => {
        await reader.cancel();
      },
      read: () => readWithIdleTimeout(reader, controller),
    };
    try {
      return await consume(timedReader);
    } catch (error) {
      await reader.cancel().catch(() => undefined);
      throw error;
    }
  } finally {
    window.clearTimeout(connectionTimeout);
    signal?.removeEventListener("abort", abortFromCaller);
  }
}

async function openStream(
  body: QaRequest,
  controller: AbortController,
  connectionTimeoutError: () => QaStreamTimeoutError | undefined,
): Promise<Response & { body: ReadableStream<Uint8Array> }> {
  let response: Response;
  try {
    response = await fetch(apiUrl("/qa/stream"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (error) {
    throw connectionTimeoutError() ?? error;
  }
  if (!response.ok || !response.body) {
    throw await apiResponseError(response, "상담 요청에 실패했어요.");
  }
  if (!response.headers.get("content-type")?.includes("text/event-stream")) {
    throw new QaStreamProtocolError();
  }
  return response as Response & { body: ReadableStream<Uint8Array> };
}

async function readWithIdleTimeout(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  controller: AbortController,
): Promise<ReadableStreamReadResult<Uint8Array>> {
  let timeout: number | undefined;
  const deadline = new Promise<never>((_resolve, reject) => {
    timeout = window.setTimeout(() => {
      const error = new QaStreamTimeoutError("idle");
      controller.abort(error);
      reject(error);
    }, QA_IDLE_TIMEOUT_MS);
  });
  try {
    return await Promise.race([reader.read(), deadline]);
  } finally {
    if (timeout !== undefined) window.clearTimeout(timeout);
  }
}

function abortReason(signal?: AbortSignal): unknown {
  return signal?.reason ?? new DOMException("Aborted", "AbortError");
}
