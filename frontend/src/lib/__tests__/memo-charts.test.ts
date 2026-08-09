import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

async function readSource(relativePath: string) {
  return readFile(new URL(relativePath, import.meta.url), "utf8");
}

test("ValueBandChart uses the same static band style as M4 outputs", async () => {
  const source = await readSource("../../components/workflow/memo-charts.tsx");

  assert.match(
    source,
    /function ValueBandChart[\s\S]*rounded-xl border p-3\.5[\s\S]*bg-gradient-to-r from-emerald-200 via-emerald-300 to-amber-300/,
  );
  assert.doesNotMatch(
    source,
    /function ValueBandChart[\s\S]*return <EChart option=\{option\} className="h-14 w-full" \/>/,
  );
});
