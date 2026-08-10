import test from "node:test";
import assert from "node:assert/strict";

async function load() {
  return import(new URL("../report-summary.ts", import.meta.url).href);
}

function result(module: string, outputs: Record<string, unknown> = {}) {
  return {
    module,
    status: "done" as const,
    score: 60,
    outputs,
    evidence: [] as string[],
    llm_explanation: null,
  };
}

test("空结果返回全 0", async () => {
  const { summarizeResults } = await load();
  assert.deepEqual(summarizeResults([]), { total: 0, risk: 0, veto: 0 });
});

test("统计总数与含风险模块数", async () => {
  const { summarizeResults } = await load();
  const out = summarizeResults([
    result("M2_financial_quality", { signals: [{ severity: "warn", message: "现金流背离" }] }),
    result("M4_valuation", { kill_switches: ["HIGH_LEVERAGE"] }),
    result("M8_safety_margin", {}),
  ]);
  assert.equal(out.total, 3);
  assert.equal(out.risk, 2);
  assert.equal(out.veto, 0);
});

test("一票否决单独计数（M9 vetoes / M10 blocked）", async () => {
  const { summarizeResults } = await load();
  const out = summarizeResults([
    result("M9_risk", { vetoes: [{ id: "LOSS_YEAR" }] }),
    result("M10_decision", { blocked_by_veto: true }),
    result("M5_moat", {}),
  ]);
  assert.equal(out.total, 3);
  assert.equal(out.veto, 2);
});
