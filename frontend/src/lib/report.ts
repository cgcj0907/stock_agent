/**
 * 分析报告（PDF 导出）纯函数：模块结果排序等展示层派生逻辑，独立成纯函数便于回归测试。
 */
import type { ModuleResultView } from "@/hooks/use-workflow-run";
import type { WorkflowInfo } from "@/lib/workflows/catalog";

export interface OrderedModuleResult {
  agent: string;
  result: ModuleResultView;
}

/**
 * 按工作流步骤顺序输出模块结果（与对话详情页一致）；
 * 工作流未知时回退按 agent id 字典序，保证导出页在任何情况下都有稳定顺序。
 */
export function orderedModuleResults(
  workflow: WorkflowInfo | undefined,
  moduleResults: Record<string, ModuleResultView>
): OrderedModuleResult[] {
  if (workflow) {
    return workflow.steps
      .map((s) => ({ agent: s.agent, result: moduleResults[s.agent] }))
      .filter(
        (x): x is { agent: string; result: ModuleResultView } => !!x.result
      );
  }
  return Object.entries(moduleResults)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([agent, result]) => ({ agent, result }));
}
