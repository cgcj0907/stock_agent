import test from "node:test";
import assert from "node:assert/strict";

import type { ModuleResultView } from "@/hooks/use-workflow-run";

async function load() {
  return import(new URL("../module-verdict.ts", import.meta.url).href);
}

function result(partial: Partial<ModuleResultView>) {
  return {
    module: "M2_financial_quality",
    status: "done",
    score: 80,
    outputs: {},
    evidence: [],
    llm_explanation: null,
    ...partial,
  };
}

test("非 done 状态不产出结论", async () => {
  const { verdictFor } = await load();
  assert.equal(verdictFor(result({ status: "running" })), null);
});

test("M5 宽 → 正向", async () => {
  const { verdictFor } = await load();
  const v = verdictFor(result({ module: "M5_moat", outputs: { width: "较宽" } }));
  assert.equal(v.tone, "positive");
});

test("M5 窄 → 负面", async () => {
  const { verdictFor } = await load();
  const v = verdictFor(result({ module: "M5_moat", outputs: { width: "窄" } }));
  assert.equal(v.tone, "negative");
});

test("M7 泡沫 → 负面", async () => {
  const { verdictFor } = await load();
  const v = verdictFor(result({ module: "M7_market", outputs: { position: "泡沫" } }));
  assert.equal(v.tone, "negative");
});

test("M8 attractive → 正向", async () => {
  const { verdictFor } = await load();
  const v = verdictFor(result({ module: "M8_safety_margin", outputs: { mos_state: "attractive" } }));
  assert.equal(v.tone, "positive");
});

test("M9 有否决 → 负面", async () => {
  const { verdictFor } = await load();
  const v = verdictFor(result({ module: "M9_risk", outputs: { vetoes: [{ id: "V1" }] } }));
  assert.equal(v.tone, "negative");
  assert.match(v.text, /一票否决/);
});

test("M9 无风险项 → 正向", async () => {
  const { verdictFor } = await load();
  const v = verdictFor(result({ module: "M9_risk", outputs: { risk_items: [] } }));
  assert.equal(v.tone, "positive");
});

test("M9 中危多项 → 中性", async () => {
  const { verdictFor } = await load();
  const v = verdictFor(result({
    module: "M9_risk",
    outputs: { risk_items: [{ severity: "medium" }, { severity: "low" }] },
  }));
  assert.equal(v.tone, "neutral");
});

test("M10 回避 → 负面", async () => {
  const { verdictFor } = await load();
  const v = verdictFor(result({ module: "M10_decision", outputs: { conclusion: "回避" } }));
  assert.equal(v.tone, "negative");
});

test("M10 被否决 → 负面", async () => {
  const { verdictFor } = await load();
  const v = verdictFor(result({ module: "M10_decision", outputs: { blocked_by_veto: true } }));
  assert.equal(v.tone, "negative");
});

test("M4 风险开关 → 负面", async () => {
  const { verdictFor } = await load();
  const v = verdictFor(result({ module: "M4_valuation", outputs: { kill_switches: ["KS1"] } }));
  assert.equal(v.tone, "negative");
});

test("无专属结论字段时退回 score 分档", async () => {
  const { verdictFor } = await load();
  assert.equal(verdictFor(result({ score: 85 })).tone, "positive");
  assert.equal(verdictFor(result({ score: 50 })).tone, "neutral");
  assert.equal(verdictFor(result({ score: 20 })).tone, "negative");
});
