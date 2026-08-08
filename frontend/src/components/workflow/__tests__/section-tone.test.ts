import test from "node:test";
import assert from "node:assert/strict";

async function loadSectionTone() {
  return import(new URL("../section-tone.ts", import.meta.url).href);
}

test("generic signal title uses neutral color even when caller passes rose", async () => {
  const { getSectionTitleClass } = await loadSectionTone();
  assert.equal(getSectionTitleClass("信号", "rose"), "text-primary/70");
});

test("explicit risk signal titles keep rose color", async () => {
  const { getSectionTitleClass } = await loadSectionTone();
  assert.equal(
    getSectionTitleClass("风险信号", "rose"),
    "text-rose-600/80 dark:text-rose-400/80",
  );
  assert.equal(
    getSectionTitleClass("治理风险信号", "rose"),
    "text-rose-600/80 dark:text-rose-400/80",
  );
});

test("non-rose tones are preserved", async () => {
  const { getSectionTitleClass } = await loadSectionTone();
  assert.equal(
    getSectionTitleClass("LLM 定性", "violet"),
    "text-violet-600/80 dark:text-violet-300/80",
  );
});
