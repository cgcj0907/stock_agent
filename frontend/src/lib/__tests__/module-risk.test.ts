import test from "node:test";
import assert from "node:assert/strict";

async function load() {
  return import(new URL("../module-risk.ts", import.meta.url).href);
}

const base = {
  module: "M9_risk",
  status: "done",
  score: null,
  outputs: {},
  evidence: [],
  llm_explanation: null,
};

test("risk_items / risks 字段判为有风险", async () => {
  const { hasRiskContent } = await load();
  assert.equal(hasRiskContent({ ...base, outputs: { risk_items: [] } }), true);
  assert.equal(hasRiskContent({ ...base, outputs: { risks: [{ severity: "high" }] } }), true);
});

test("kill_switches / vetoed / monitor_rules 判为有风险", async () => {
  const { hasRiskContent } = await load();
  assert.equal(hasRiskContent({ ...base, outputs: { kill_switches: ["HIGH_LEVERAGE"] } }), true);
  assert.equal(hasRiskContent({ ...base, outputs: { vetoed: ["M9"] } }), true);
  assert.equal(hasRiskContent({ ...base, outputs: { monitor_rules: [] } }), true);
});

test("signals 含风险信号时判为有风险", async () => {
  const { hasRiskContent } = await load();
  assert.equal(
    hasRiskContent({
      ...base,
      outputs: { signals: ["护城河侵蚀风险：毛利率下滑"] },
    }),
    true,
  );
});

test("仅正向/中性信号与普通字段判为无风险", async () => {
  const { hasRiskContent } = await load();
  assert.equal(
    hasRiskContent({ ...base, outputs: { signals: ["ROE 稳定", "现金流健康"], score: 85 } }),
    false,
  );
  assert.equal(hasRiskContent({ ...base, outputs: { intrinsic_value: { mid: 50 } } }), false);
});
