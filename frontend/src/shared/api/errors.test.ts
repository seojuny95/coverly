import { describe, expect, it } from "vitest";
import {
  AppRequestError,
  safeErrorDiagnostics,
  userMessageForError,
} from "./errors";

describe("application request errors", () => {
  it("keeps developer and user messages separate", () => {
    const error = new AppRequestError({
      developerMessage: "Session store connection failed",
      userMessage: "요청을 처리하지 못했어요. 잠시 후 다시 시도해주세요.",
    });

    expect(error.message).toBe("Session store connection failed");
    expect(userMessageForError(error)).toBe(
      "요청을 처리하지 못했어요. 잠시 후 다시 시도해주세요.",
    );
  });

  it("never returns an unknown exception message to the UI", () => {
    expect(userMessageForError(new Error("database secret detail"))).toBe(
      "요청을 처리하지 못했어요. 잠시 후 다시 시도해주세요.",
    );
  });

  it("collects only allow-listed diagnostics", () => {
    const error = Object.assign(new Error("raw response body"), {
      code: "SERVICE_UNAVAILABLE",
      requestId: "request-1",
      status: 503,
      token: "must-not-be-logged",
    });

    expect(safeErrorDiagnostics(error)).toEqual({
      name: "Error",
      code: "SERVICE_UNAVAILABLE",
      requestId: "request-1",
      status: 503,
    });
  });

  it("includes only application-owned developer messages", () => {
    const safeError = new AppRequestError({
      developerMessage: "Backend readiness deadline exceeded",
      userMessage: "서버를 준비하지 못했어요.",
    });

    expect(safeErrorDiagnostics(safeError)).toEqual({
      name: "AppRequestError",
      developerMessage: "Backend readiness deadline exceeded",
    });
    expect(
      safeErrorDiagnostics(new Error("private provider response")),
    ).toEqual({ name: "Error" });
  });
});
