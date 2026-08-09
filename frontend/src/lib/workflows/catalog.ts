import { findAgent } from "@/lib/agents/catalog";

export interface WorkflowStep {
  id: string; // 步骤 id（如 M1）
  agent: string; // 智能体 id（如 M1_business_model）
  deps: string[]; // 依赖的步骤 id
}

export interface WorkflowInfo {
  id: string;
  name: string;
  description: string;
  steps: WorkflowStep[];
  accent: string;
}

export const WORKFLOWS: WorkflowInfo[] = [
  {
    id: "default",
    name: "标准价值投资分析",
    description:
      "M1→M11 全链路：商业模式、财务质量、成长、估值、护城河、治理、市场、安全边际、风险与监控，产出完整投资备忘录。",
    accent: "from-emerald-500 to-teal-600",
    steps: [
      { id: "M1", agent: "M1_business_model", deps: [] },
      { id: "M2", agent: "M2_financial_quality", deps: [] },
      { id: "M3", agent: "M3_growth", deps: ["M1", "M2"] },
      { id: "M4", agent: "M4_valuation", deps: ["M1", "M2", "M3", "M5", "M6"] },
      { id: "M5", agent: "M5_moat", deps: ["M1"] },
      { id: "M6", agent: "M6_governance", deps: [] },
      { id: "M7", agent: "M7_market", deps: ["M1"] },
      { id: "M8", agent: "M8_safety_margin", deps: ["M2", "M3", "M4", "M5", "M7"] },
      { id: "M9", agent: "M9_risk", deps: ["M2", "M3", "M4", "M5", "M6", "M7", "M8"] },
      { id: "M10", agent: "M10_decision", deps: ["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9"] },
      { id: "M11", agent: "M11_monitor", deps: ["M2", "M3", "M7", "M8", "M9", "M10"] },
    ],
  },
  {
    id: "quick",
    name: "快速估值流",
    description:
      "只跑硬核三件套：财务质量 → 估值 → 安全边际，用于快速筛查。",
    accent: "from-amber-500 to-orange-600",
    steps: [
      { id: "M2", agent: "M2_financial_quality", deps: [] },
      { id: "M4", agent: "M4_valuation", deps: ["M2"] },
      { id: "M8", agent: "M8_safety_margin", deps: ["M4"] },
    ],
  },
];

export function getWorkflow(id: string): WorkflowInfo | undefined {
  return WORKFLOWS.find((w) => w.id === id);
}

export type StepStatus = "pending" | "running" | "done" | "failed" | "skipped";

/** 按依赖深度分层布局（列 = 拓扑深度） */
export function computeStepDepths(
  steps: WorkflowStep[]
): Record<string, number> {
  const depth: Record<string, number> = {};
  let changed = true;
  let guard = 0;
  while (changed && guard++ < 30) {
    changed = false;
    for (const s of steps) {
      const d =
        s.deps.length === 0
          ? 0
          : Math.max(...s.deps.map((x) => depth[x] ?? 0)) + 1;
      if (depth[s.id] !== d) {
        depth[s.id] = d;
        changed = true;
      }
    }
  }
  return depth;
}

export function stepAgent(step: WorkflowStep) {
  return findAgent(step.agent);
}
