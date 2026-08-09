/**
 * 工作流编排器「连接提示」数据层（前端提示层，非强制约束）。
 *
 * 对齐 config/workflows/default.yaml 的默认依赖 + M0 可选画像（docs/13 §5/§7）：
 * - suggestedDeps：默认流里该模块依赖的上游（通常应接在这些模块后面）；
 * - suggestedDownstream：默认流里依赖该模块的下游（通常可接在这些模块前面）；
 * - optionalUpstream：不接也能跑、接了更强（如 M0 个性化画像）。
 *
 * 提示只做引导，不拦截——后端 validate 仍只拦硬错误（环/未注册/依赖缺失），
 * 语义自由度保留（与「自由编排」理念一致）。
 */

export interface ConnectionHint {
  /** 当前模块（agent id） */
  agent: string;
  /** 建议上游：默认流里它依赖的模块（接在它前面） */
  suggestedDeps: string[];
  /** 建议下游：默认流里依赖它的模块（接在它后面） */
  suggestedDownstream: string[];
  /** 可选上游：不接也能跑，接了个性化更强（如 M0 画像） */
  optionalUpstream: string[];
  /** 一句话说明 */
  note: string;
}

export const M0_AGENT = "M0_investor_profile";

/** M0 的可消费方：接在这些模块前面会注入个人可理解性/安全边际/风险/仓位 */
export const M0_CONSUMERS = [
  "M1_business_model",
  "M8_safety_margin",
  "M9_risk",
  "M10_decision",
] as const;

// 默认流依赖（agent id 级，与 config/workflows/default.yaml 对齐；short id 已映射为 agent id）
const DEFAULT_DEPS: Record<string, string[]> = {
  M1_business_model: [],
  M2_financial_quality: ["M1_business_model"],
  M3_growth: ["M1_business_model", "M2_financial_quality"],
  M4_valuation: [
    "M1_business_model",
    "M2_financial_quality",
    "M3_growth",
    "M5_moat",
    "M6_governance",
  ],
  M5_moat: ["M1_business_model"],
  M6_governance: [],
  M7_market: ["M1_business_model"],
  M8_safety_margin: [
    "M2_financial_quality",
    "M3_growth",
    "M4_valuation",
    "M5_moat",
    "M7_market",
  ],
  M9_risk: [
    "M2_financial_quality",
    "M3_growth",
    "M4_valuation",
    "M5_moat",
    "M6_governance",
    "M7_market",
    "M8_safety_margin",
  ],
  M10_decision: [
    "M1_business_model",
    "M2_financial_quality",
    "M3_growth",
    "M4_valuation",
    "M5_moat",
    "M6_governance",
    "M7_market",
    "M8_safety_margin",
    "M9_risk",
  ],
  M11_monitor: [
    "M2_financial_quality",
    "M3_growth",
    "M7_market",
    "M8_safety_margin",
    "M9_risk",
    "M10_decision",
  ],
};

const NOTES: Record<string, string> = {
  M1_business_model:
    "无依赖、最先产出生意类型与可理解性；M2/M3/M4/M5/M7 通常接在它后面。",
  M2_financial_quality:
    "通常接在 M1 之后（按生意类型分行业口径）；M4/M8/M9/M10/M11 消费它。",
  M3_growth:
    "通常接在 M1、M2 之后（周期/成长口径一致）；M4/M8/M9/M10/M11 消费它。",
  M4_valuation:
    "依赖 M1/M2/M3/M5/M6，是 M8 安全边际的前提——M8 缺它会降级「数据不足」。",
  M5_moat: "通常接在 M1 之后；M4/M8/M9/M10 消费它。",
  M6_governance: "无依赖、独立跑；M4/M9/M10 消费它。",
  M7_market: "通常接在 M1 之后（主指标路由）；M8/M9/M10/M11 消费它。",
  M8_safety_margin:
    "关键：必须接 M4（估值），否则降级「数据不足」；可选接 M0 个性化要求折扣。",
  M9_risk: "聚合 M2/M3/M4/M5/M6/M7/M8；可选接 M0 出个人风险提示。",
  M10_decision:
    "汇总 M1–M9 评分出结论与仓位；可选接 M0 收窄个人仓位上限。",
  M11_monitor: "通常接在 M10 之后，把决策转成持有监控规则。",
  M0_investor_profile:
    "可选画像：无依赖、可放任意位置；接在 M1/M8/M9/M10 前面会注入个性化分析。",
};

function build(): Record<string, ConnectionHint> {
  const hints: Record<string, ConnectionHint> = {};
  const all = [...Object.keys(DEFAULT_DEPS), M0_AGENT];

  for (const agent of all) {
    const suggestedDeps = [...(DEFAULT_DEPS[agent] ?? [])];
    const suggestedDownstream = Object.entries(DEFAULT_DEPS)
      .filter(([, deps]) => deps.includes(agent))
      .map(([a]) => a);
    const optionalUpstream =
      agent === M0_AGENT
        ? []
        : (M0_CONSUMERS as readonly string[]).includes(agent)
          ? [M0_AGENT]
          : [];
    // M0 的下游 = 默认流里依赖它的 + 可选消费者
    if (agent === M0_AGENT) {
      suggestedDownstream.push(...M0_CONSUMERS.filter((c) => !suggestedDownstream.includes(c)));
    }
    hints[agent] = {
      agent,
      suggestedDeps,
      suggestedDownstream: [...new Set(suggestedDownstream)],
      optionalUpstream,
      note: NOTES[agent] ?? "",
    };
  }
  return hints;
}

export const CONNECTION_HINTS: Record<string, ConnectionHint> = build();

/** source 接在 target 前面是否「推荐/可选」 */
export function isRecommended(source: string, target: string): boolean {
  const hint = CONNECTION_HINTS[target];
  if (!hint) return true; // 未知模块不拦
  return (
    hint.suggestedDeps.includes(source) || hint.optionalUpstream.includes(source)
  );
}

/** 非常规连接时给出一句提示文案；推荐/可选连接返回 null */
export function connectionWarning(source: string, target: string): string | null {
  if (isRecommended(source, target)) return null;
  const hint = CONNECTION_HINTS[target];
  const sugg = (hint?.suggestedDeps ?? []).join("、") || "无";
  return `${source} 通常不建议直接接在 ${target} 后面；${target} 一般接在 ${sugg} 之后`;
}
