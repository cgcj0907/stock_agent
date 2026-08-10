import test from "node:test";
import assert from "node:assert/strict";

async function load() {
  return import(new URL("../report.ts", import.meta.url).href);
}

function result(module: string, score = 60) {
  return {
    module,
    status: "done" as const,
    score,
    outputs: {},
    evidence: [] as string[],
    llm_explanation: null,
  };
}

const WORKFLOW = {
  id: "quick",
  name: "快速估值流",
  description: "",
  accent: "",
  steps: [
    { id: "M2", agent: "M2_financial_quality", deps: [] },
    { id: "M4", agent: "M4_valuation", deps: ["M2"] },
    { id: "M8", agent: "M8_safety_margin", deps: ["M4"] },
  ],
};

test("按工作流步骤顺序输出模块结果", async () => {
  const { orderedModuleResults } = await load();
  const out = orderedModuleResults(WORKFLOW, {
    M8_safety_margin: result("M8_safety_margin"),
    M2_financial_quality: result("M2_financial_quality"),
    M4_valuation: result("M4_valuation"),
  });
  assert.deepEqual(
    out.map((x: { agent: string }) => x.agent),
    ["M2_financial_quality", "M4_valuation", "M8_safety_margin"]
  );
});

test("工作流步骤中缺失的结果被过滤", async () => {
  const { orderedModuleResults } = await load();
  const out = orderedModuleResults(WORKFLOW, {
    M2_financial_quality: result("M2_financial_quality"),
  });
  assert.deepEqual(out.map((x: { agent: string }) => x.agent), ["M2_financial_quality"]);
});

test("工作流未知时回退按 agent id 字典序", async () => {
  const { orderedModuleResults } = await load();
  const out = orderedModuleResults(undefined, {
    M10_decision: result("M10_decision"),
    M1_business_model: result("M1_business_model"),
  });
  assert.deepEqual(
    out.map((x: { agent: string }) => x.agent),
    ["M1_business_model", "M10_decision"]
  );
});
