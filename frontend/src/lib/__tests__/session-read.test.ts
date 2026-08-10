import test from "node:test";
import assert from "node:assert/strict";

async function load() {
  return import(new URL("../session-read.ts", import.meta.url).href);
}

const FALLBACK = {
  id: "sess_1",
  company_code: "600519",
  company_name: "贵州茅台",
  status: "completed",
  workflow_id: "default",
};

test("payload → SessionView（module_results/status/assumptions/memo_versions/monitor_hits）", async () => {
  const { sessionFromPayload } = await load();
  const sv = sessionFromPayload(
    {
      payload: {
        module_results: {
          M2_financial_quality: {
            module: "M2_financial_quality",
            status: "done",
            score: 80,
            outputs: {},
            evidence: [],
            llm_explanation: null,
          },
        },
        status: "completed",
        assumptions: { growth: 0.1 },
        memo_versions: ["# 备忘录"],
        monitor_hits: [{ company_code: "600519" }],
      },
    },
    FALLBACK
  );
  assert.ok(sv);
  assert.equal(sv!.module_results.M2_financial_quality.score, 80);
  assert.equal(sv!.status, "completed");
  assert.equal(sv!.assumptions?.growth, 0.1);
  assert.deepEqual(sv!.memo_versions, ["# 备忘录"]);
  assert.equal((sv!.monitor_hits as unknown[]).length, 1);
});

test("payload 无 module_results → null", async () => {
  const { sessionFromPayload } = await load();
  assert.equal(
    sessionFromPayload({ payload: { status: "created" } }, FALLBACK),
    null
  );
  assert.equal(sessionFromPayload(null, FALLBACK), null);
});

test("payload 状态缺失时回退 conversation.status", async () => {
  const { sessionFromPayload } = await load();
  const sv = sessionFromPayload(
    {
      payload: {
        module_results: {
          M4_valuation: {
            module: "M4_valuation",
            status: "done",
            score: 60,
            outputs: {},
            evidence: [],
            llm_explanation: null,
          },
        },
      },
    },
    FALLBACK
  );
  assert.ok(sv);
  assert.equal(sv!.status, "completed");
});
