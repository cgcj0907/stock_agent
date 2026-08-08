import test from "node:test";
import assert from "node:assert/strict";

async function load() {
  return import(new URL("../signal-polarity.ts", import.meta.url).href);
}

test("M5 正向信号（字符串）判为 positive", async () => {
  const { classifySignal } = await load();
  assert.equal(classifySignal("ROE 稳定（变异系数 ≤0.15）"), "positive");
  assert.equal(classifySignal("ROE 波动可控"), "positive");
});

test("M5 风险信号（字符串）判为 risk", async () => {
  const { classifySignal } = await load();
  assert.equal(classifySignal("护城河侵蚀风险：毛利率下滑"), "risk");
});

test("结构化 RiskSignal 按契约视为风险，即使文案中性", async () => {
  const { classifySignal } = await load();
  assert.equal(
    classifySignal({ code: "OCF_NP_DIVERGENCE", severity: "medium", message: "经营现金流/净利润背离" }),
    "risk",
  );
});

test("明确无风险文案判为 positive，避免被风险词误伤", async () => {
  const { classifySignal } = await load();
  assert.equal(classifySignal("未发现明显风险"), "positive");
});

test("中性文案判为 neutral", async () => {
  const { classifySignal } = await load();
  assert.equal(classifySignal("数据源：财报"), "neutral");
});

test("groupSignals 保持组内顺序", async () => {
  const { groupSignals } = await load();
  const groups = groupSignals(["护城河侵蚀", "ROE 稳定", "中性提示"]);
  assert.deepEqual(groups.positive, ["ROE 稳定"]);
  assert.deepEqual(groups.risk, ["护城河侵蚀"]);
  assert.deepEqual(groups.neutral, ["中性提示"]);
});
