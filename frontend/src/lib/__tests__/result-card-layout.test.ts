import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

async function readSource(relativePath: string) {
  return readFile(new URL(relativePath, import.meta.url), "utf8");
}

test("result card header keeps status at top-right in a single row", async () => {
  const source = await readSource("../../components/workflow/result-card.tsx");

  // 头部单行：display:flex（覆盖 CardHeader 基础 grid，避免上下排布），状态组靠右
  assert.match(
    source,
    /<CardHeader className="flex items-center justify-between[^"]*pb-1">/,
  );
  // 状态点位于独立的右上角状态组（shrink-0）
  assert.match(
    source,
    /<div className="flex shrink-0 items-center gap-1\.5">[\s\S]*?title="已完成"/,
  );
  // 不得再退回 flex-row（只设 flex-direction 不设 display，会被 CardHeader 基础 grid 排成上下两行）
  assert.doesNotMatch(source, /<CardHeader className="flex-row/);
});
