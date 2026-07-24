export const GENERIC_REQUEST_ERROR_MESSAGE =
  "요청을 처리하지 못했어요. 잠시 후 다시 시도해주세요.";

export class AppRequestError extends Error {
  readonly userMessage: string;

  constructor({
    cause,
    developerMessage,
    name = "AppRequestError",
    userMessage,
  }: {
    cause?: unknown;
    developerMessage: string;
    name?: string;
    userMessage: string;
  }) {
    super(developerMessage, { cause });
    this.name = name;
    this.userMessage = userMessage;
  }
}

export function userMessageForError(
  error: unknown,
  fallback = GENERIC_REQUEST_ERROR_MESSAGE,
): string {
  return error instanceof AppRequestError ? error.userMessage : fallback;
}

export function safeErrorDiagnostics(error: unknown): {
  name: string;
  developerMessage?: string;
  code?: string;
  requestId?: string;
  status?: number;
} {
  if (!(error instanceof Error)) return { name: "UnknownError" };

  return {
    name: error.name,
    ...(error instanceof AppRequestError
      ? { developerMessage: error.message }
      : {}),
    ...readStringField(error, "code"),
    ...readStringField(error, "requestId"),
    ...readNumberField(error, "status"),
  };
}

export function reportClientOperationFailure(
  operation: string,
  error: unknown,
): void {
  if (process.env.NODE_ENV === "test") return;
  console.error("client_operation_failed", {
    operation,
    ...safeErrorDiagnostics(error),
  });
}

function readStringField(
  error: Error,
  key: "code" | "requestId",
): Partial<Record<typeof key, string>> {
  const value = (error as unknown as Record<string, unknown>)[key];
  return typeof value === "string" ? { [key]: value } : {};
}

function readNumberField(
  error: Error,
  key: "status",
): Partial<Record<typeof key, number>> {
  const value = (error as unknown as Record<string, unknown>)[key];
  return typeof value === "number" ? { [key]: value } : {};
}
