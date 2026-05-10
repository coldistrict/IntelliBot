// @vitest-environment node

import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const testDir = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(testDir, "..");

describe("API contract generation", () => {
  it("matches the current backend OpenAPI schema", () => {
    expect(() => {
      execFileSync("node", ["./scripts/generate-api-types.mjs", "--check"], {
        cwd: frontendDir,
        stdio: "pipe",
      });
    }).not.toThrow();
  }, 15_000);
});
