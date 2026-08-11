import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

async function readSource(relativePath: string) {
  return readFile(new URL(relativePath, import.meta.url), "utf8");
}

test("running workflow rail uses divider sections instead of stacked cards", async () => {
  const source = await readSource("../../components/workflow/workflow-rail.tsx");

  assert.match(
    source,
    /const showRunningRail = !showResults && \(running \|\| Object\.keys\(statuses\)\.length > 0\);/,
  );
  assert.match(
    source,
    /<div className="flex flex-col divide-y divide-border\/60">/,
  );
  assert.match(
    source,
    /showRunningRail && \(\s*<>\s*<section className="py-4">/,
  );
  assert.doesNotMatch(source, /rounded-xl bg-card\/70/);
});

test("investment conclusion uses a single divider instead of boxed metric cards", async () => {
  const source = await readSource("../../components/workflow/workflow-rail.tsx");

  assert.match(
    source,
    /showResults && \(conclusion \|\| total != null \|\| ivMid != null\)[\s\S]*<section className="flex flex-col gap-3 py-4[^"]*">/,
  );
  assert.match(
    source,
    /<div className="border-t border-border\/60 pt-3">/,
  );
  assert.doesNotMatch(
    source,
    /grid grid-cols-2 gap-2[\s\S]*rounded-xl border bg-card/,
  );
});

test("risk list and memo navigation are plain sections without card containers", async () => {
  const source = await readSource("../../components/workflow/workflow-rail.tsx");

  assert.match(
    source,
    /showResults && riskItems\.length > 0 && \(\s*<section className="py-4">/,
  );
  assert.match(
    source,
    /hasResults && visibleAnchors\.length > 0 && \(\s*<section className="py-4">/,
  );
  assert.doesNotMatch(source, /<Card\b/);
});
