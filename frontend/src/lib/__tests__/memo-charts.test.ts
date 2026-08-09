import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

async function readSource(relativePath: string) {
  return readFile(new URL(relativePath, import.meta.url), "utf8");
}

test("ValueBandChart keeps the static band but without nested border chrome", async () => {
  const source = await readSource("../../components/workflow/memo-charts.tsx");

  assert.match(
    source,
    /function ValueBandChart[\s\S]*rounded-xl px-1 py-2[\s\S]*bg-gradient-to-r from-emerald-200 via-emerald-300 to-amber-300/,
  );
  assert.doesNotMatch(
    source,
    /function ValueBandChart[\s\S]*rounded-xl border p-3\.5/,
  );
  assert.doesNotMatch(
    source,
    /function ValueBandChart[\s\S]*return <EChart option=\{option\} className="h-14 w-full" \/>/,
  );
});

test("memo valuation summary removes secondary parameter rows and bordered tiles", async () => {
  const source = await readSource("../../components/workflow/memo-card.tsx");

  assert.doesNotMatch(source, /置信度/);
  assert.doesNotMatch(source, /质量乘数/);
  assert.doesNotMatch(source, /风险折扣/);
  assert.doesNotMatch(source, /安全边际：/);
  assert.doesNotMatch(source, /rounded-xl border border-emerald-200/);
  assert.doesNotMatch(source, /rounded-xl border border-amber-200/);
  assert.match(source, /rounded-xl bg-emerald-50\/80/);
  assert.match(source, /rounded-xl bg-amber-50\/80/);
});
