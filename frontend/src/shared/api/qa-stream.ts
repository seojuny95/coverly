import type { QaErrorEvent, QaStreamEvent } from "./contracts";
import { AppRequestError } from "./errors";
import { QA_STREAM_JSON_SCHEMA } from "./generated-runtime";

export class QaStreamProtocolError extends AppRequestError {
  constructor() {
    super({
      developerMessage: "QA stream violated the generated SSE protocol",
      name: "QaStreamProtocolError",
      userMessage:
        "답변을 정상적으로 확인하지 못했어요. 잠시 후 다시 질문해주세요.",
    });
  }
}

export class QaStreamResponseError extends AppRequestError {
  readonly code: QaErrorEvent["code"];
  readonly requestId: string;
  readonly retryable: boolean;

  constructor(event: QaErrorEvent) {
    super({
      developerMessage: `QA stream failed (code=${event.code}, requestId=${event.request_id})`,
      name: "QaStreamResponseError",
      userMessage: event.message,
    });
    this.code = event.code;
    this.requestId = event.request_id;
    this.retryable = event.retryable;
  }
}

export function requireQaStreamEvent(value: unknown): QaStreamEvent {
  if (!matchesJsonSchema(value, QA_STREAM_JSON_SCHEMA.schema)) {
    throw new QaStreamProtocolError();
  }
  return value as QaStreamEvent;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function matchesJsonSchema(value: unknown, schema: unknown): boolean {
  if (!isRecord(schema)) return false;

  if (typeof schema.$ref === "string") {
    const resolved = resolveLocalReference(schema.$ref);
    return resolved !== undefined && matchesJsonSchema(value, resolved);
  }
  if (
    Array.isArray(schema.oneOf) &&
    schema.oneOf.filter((candidate) => matchesJsonSchema(value, candidate))
      .length !== 1
  ) {
    return false;
  }
  if (
    Array.isArray(schema.anyOf) &&
    !schema.anyOf.some((candidate) => matchesJsonSchema(value, candidate))
  ) {
    return false;
  }
  if (
    Array.isArray(schema.allOf) &&
    !schema.allOf.every((candidate) => matchesJsonSchema(value, candidate))
  ) {
    return false;
  }
  if ("const" in schema && !Object.is(value, schema.const)) return false;
  if (
    Array.isArray(schema.enum) &&
    !schema.enum.some((candidate) => Object.is(value, candidate))
  ) {
    return false;
  }

  if (schema.type === "null") return value === null;
  if (schema.type === "string") return typeof value === "string";
  if (schema.type === "boolean") return typeof value === "boolean";
  if (schema.type === "integer") {
    return (
      Number.isInteger(value) &&
      (typeof schema.minimum !== "number" || Number(value) >= schema.minimum) &&
      (typeof schema.maximum !== "number" || Number(value) <= schema.maximum)
    );
  }
  if (schema.type === "number") {
    return (
      typeof value === "number" &&
      Number.isFinite(value) &&
      (typeof schema.minimum !== "number" || value >= schema.minimum) &&
      (typeof schema.maximum !== "number" || value <= schema.maximum)
    );
  }
  if (schema.type === "array") {
    return (
      Array.isArray(value) &&
      (!("items" in schema) ||
        value.every((item) => matchesJsonSchema(item, schema.items)))
    );
  }
  if (schema.type === "object") {
    if (!isRecord(value) || Array.isArray(value)) return false;
    if (
      Array.isArray(schema.required) &&
      !schema.required.every((key) => typeof key === "string" && key in value)
    ) {
      return false;
    }
    if (isRecord(schema.properties)) {
      for (const [key, propertySchema] of Object.entries(schema.properties)) {
        if (key in value && !matchesJsonSchema(value[key], propertySchema)) {
          return false;
        }
      }
    }
  }

  return true;
}

function resolveLocalReference(reference: string): unknown {
  if (!reference.startsWith("#/")) return undefined;
  let current: unknown = QA_STREAM_JSON_SCHEMA;
  for (const encodedSegment of reference.slice(2).split("/")) {
    if (!isRecord(current)) return undefined;
    const segment = encodedSegment.replaceAll("~1", "/").replaceAll("~0", "~");
    current = current[segment];
  }
  return current;
}
