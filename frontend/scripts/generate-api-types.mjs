import { execFileSync } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import openapiTS, { astToString, COMMENT_HEADER } from "openapi-typescript";
import { format } from "prettier";

const frontendDirectory = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const backendDirectory = path.resolve(frontendDirectory, "../backend");
const outputPath = path.resolve(
  frontendDirectory,
  "src/shared/api/generated.ts",
);
const runtimeOutputPath = path.resolve(
  frontendDirectory,
  "src/shared/api/generated-runtime.ts",
);

const schema = JSON.parse(
  execFileSync(
    "uv",
    [
      "run",
      "python",
      "-c",
      "import json; from app.main import app; print(json.dumps(app.openapi(), ensure_ascii=False))",
    ],
    { cwd: backendDirectory, encoding: "utf8" },
  ),
);
const nodes = await openapiTS(schema);
const generated = await format(`${COMMENT_HEADER}${astToString(nodes)}`, {
  filepath: outputPath,
});

function enumValues(value, label) {
  if (
    !Array.isArray(value) ||
    !value.every((item) => typeof item === "string")
  ) {
    throw new Error(`OpenAPI ${label} must be a string enum.`);
  }
  return value;
}

const schemas = schema.components?.schemas;
const apiErrorCodes = enumValues(schemas?.ApiErrorCode?.enum, "ApiErrorCode");
const policyClassifications = enumValues(
  schemas?.PolicySummary?.properties?.["보험분류"]?.enum,
  "PolicySummary.보험분류",
);
const portfolioMaxDocuments =
  schemas?.PortfolioSessionResponse?.["x-maxDocuments"];
if (
  typeof portfolioMaxDocuments !== "number" ||
  !Number.isInteger(portfolioMaxDocuments) ||
  portfolioMaxDocuments < 1
) {
  throw new Error(
    "OpenAPI PortfolioSessionResponse.x-maxDocuments must be a positive integer.",
  );
}
const parseRequestSchemaReference =
  schema.paths?.["/policies/parse"]?.post?.requestBody?.content?.[
    "multipart/form-data"
  ]?.schema?.$ref;
const parseRequestSchemaName =
  typeof parseRequestSchemaReference === "string"
    ? parseRequestSchemaReference.split("/").at(-1)
    : undefined;
const pdfMaxBytes = parseRequestSchemaName
  ? schemas?.[parseRequestSchemaName]?.properties?.file?.["x-maxBytes"]
  : undefined;
if (
  typeof pdfMaxBytes !== "number" ||
  !Number.isInteger(pdfMaxBytes) ||
  pdfMaxBytes < 1
) {
  throw new Error(
    "OpenAPI /policies/parse file.x-maxBytes must be a positive integer.",
  );
}
const qaStreamSchema =
  schema.paths?.["/qa/stream"]?.post?.responses?.["200"]?.content?.[
    "text/event-stream"
  ]?.schema;
if (!qaStreamSchema || typeof qaStreamSchema !== "object") {
  throw new Error("OpenAPI /qa/stream response schema is missing.");
}

function referencedComponentSchemas(rootSchema) {
  const referenced = new Set();

  function visit(value) {
    if (Array.isArray(value)) {
      value.forEach(visit);
      return;
    }
    if (!value || typeof value !== "object") return;

    if (typeof value.$ref === "string") {
      const prefix = "#/components/schemas/";
      if (!value.$ref.startsWith(prefix)) {
        throw new Error(`Unsupported OpenAPI schema reference: ${value.$ref}`);
      }
      const name = value.$ref.slice(prefix.length);
      if (!referenced.has(name)) {
        const component = schemas?.[name];
        if (!component) {
          throw new Error(`Missing OpenAPI component schema: ${name}`);
        }
        referenced.add(name);
        visit(component);
      }
    }

    Object.values(value).forEach(visit);
  }

  visit(rootSchema);
  return Object.fromEntries(
    [...referenced].sort().map((name) => [name, schemas[name]]),
  );
}

const qaStreamComponentSchemas = referencedComponentSchemas(qaStreamSchema);
const runtimeGenerated = await format(
  `${COMMENT_HEADER}
import type { components } from "./generated";

type ApiErrorCode = components["schemas"]["ApiErrorCode"];
type PolicyClassification = components["schemas"]["PolicySummary"]["보험분류"];

export const API_ERROR_CODES = ${JSON.stringify(apiErrorCodes)} as const satisfies readonly ApiErrorCode[];
export const POLICY_CLASSIFICATIONS = ${JSON.stringify(policyClassifications)} as const satisfies readonly PolicyClassification[];
export const PORTFOLIO_MAX_DOCUMENTS = ${portfolioMaxDocuments} as const;
export const PDF_MAX_BYTES = ${pdfMaxBytes} as const;

export const QA_STREAM_JSON_SCHEMA = ${JSON.stringify({
    schema: qaStreamSchema,
    components: { schemas: qaStreamComponentSchemas },
  })} as const;

const apiErrorCodeSet: ReadonlySet<string> = new Set(API_ERROR_CODES);

export function isApiErrorCode(value: unknown): value is ApiErrorCode {
  return typeof value === "string" && apiErrorCodeSet.has(value);
}
`,
  { filepath: runtimeOutputPath },
);

if (process.argv.includes("--check")) {
  const current = await readFile(outputPath, "utf8").catch(() => "");
  const currentRuntime = await readFile(runtimeOutputPath, "utf8").catch(
    () => "",
  );
  if (current !== generated || currentRuntime !== runtimeGenerated) {
    throw new Error("API types are stale. Run `pnpm api:generate`.");
  }
} else {
  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, generated);
  await writeFile(runtimeOutputPath, runtimeGenerated);
}
