import test from "node:test";
import assert from "node:assert/strict";

async function loadHints() {
  return import(new URL("../workflows/connection-hints.ts", import.meta.url).href);
}

test("M8 建议上游包含 M4 估值（缺它降级）", async () => {
  const { CONNECTION_HINTS } = await loadHints();
  assert.ok(CONNECTION_HINTS.M8_safety_margin.suggestedDeps.includes("M4_valuation"));
});

test("M0 不进默认流，但建议下游覆盖 M1/M8/M9/M10", async () => {
  const { CONNECTION_HINTS, M0_AGENT } = await loadHints();
  const hint = CONNECTION_HINTS[M0_AGENT];
  assert.equal(hint.suggestedDeps.length, 0);
  assert.deepEqual(
    [...hint.suggestedDownstream].sort(),
    ["M1_business_model", "M10_decision", "M8_safety_margin", "M9_risk"].sort()
  );
});

test("M1/M8/M9/M10 把 M0 列为可选上游", async () => {
  const { CONNECTION_HINTS, M0_AGENT } = await loadHints();
  for (const agent of ["M1_business_model", "M8_safety_margin", "M9_risk", "M10_decision"]) {
    assert.ok(CONNECTION_HINTS[agent].optionalUpstream.includes(M0_AGENT), agent);
  }
  assert.ok(!CONNECTION_HINTS.M2_financial_quality.optionalUpstream.includes(M0_AGENT));
});

test("isRecommended：M4→M8 推荐；M0→M8 可选；M6→M8 非常规", async () => {
  const { isRecommended } = await loadHints();
  assert.equal(isRecommended("M4_valuation", "M8_safety_margin"), true);
  assert.equal(isRecommended("M0_investor_profile", "M8_safety_margin"), true);
  assert.equal(isRecommended("M6_governance", "M8_safety_margin"), false);
});

test("connectionWarning 只对非常规连接出文案", async () => {
  const { connectionWarning } = await loadHints();
  assert.equal(connectionWarning("M4_valuation", "M8_safety_margin"), null);
  assert.match(connectionWarning("M6_governance", "M8_safety_margin") ?? "", /通常不建议直接接/);
});
