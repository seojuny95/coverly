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

if (process.argv.includes("--check")) {
  const current = await readFile(outputPath, "utf8").catch(() => "");
  if (current !== generated) {
    throw new Error("API types are stale. Run `pnpm api:generate`.");
  }
} else {
  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, generated);
}
