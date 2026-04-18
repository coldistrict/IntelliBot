import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(scriptDir, "..", "..");
const frontendDir = resolve(repoRoot, "frontend");
const outputPath = resolve(frontendDir, "lib", "generated", "api-types.ts");
const checkOnly = process.argv.includes("--check");
const tempDir = mkdtempSync(resolve(tmpdir(), "intellibot-openapi-"));
const openapiPath = resolve(tempDir, "openapi.json");
const tempTypesPath = resolve(tempDir, "api-types.ts");

try {
  execFileSync("uv", ["run", "--project", "backend", "python", "backend/scripts/export_openapi.py", openapiPath], {
    cwd: repoRoot,
    stdio: "inherit",
  });
  execFileSync("pnpm", ["exec", "openapi-typescript", openapiPath, "-o", tempTypesPath], {
    cwd: frontendDir,
    stdio: "inherit",
  });

  const generated = readFileSync(tempTypesPath, "utf8");
  if (checkOnly) {
    const existing = readFileSync(outputPath, "utf8");
    if (existing !== generated) {
      throw new Error("Generated API types are out of date. Run `pnpm --filter frontend generate:api-types`.");
    }
  } else {
    mkdirSync(dirname(outputPath), { recursive: true });
    writeFileSync(outputPath, generated, "utf8");
  }
} finally {
  rmSync(tempDir, { recursive: true, force: true });
}
