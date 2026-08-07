/** 智能体目录：本地富元数据 + 后端 /api/agents 元数据合并 */
import {
  Calculator,
  Castle,
  ChartLine,
  Factory,
  Landmark,
  RadioTower,
  ShieldCheck,
  Target,
  TrendingDown,
  TrendingUp,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";

/** 图标 key → lucide 图标组件（客户端渲染用，避免函数跨 Server/Client 边界） */
export const AGENT_ICONS: Record<string, LucideIcon> = {
  factory: Factory,
  calculator: Calculator,
  "trending-up": TrendingUp,
  "chart-line": ChartLine,
  castle: Castle,
  landmark: Landmark,
  "trending-down": TrendingDown,
  "shield-check": ShieldCheck,
  "triangle-alert": TriangleAlert,
  target: Target,
  "radio-tower": RadioTower,
};

export interface AgentInfo {
  id: string;
  code: string; // M1..M11
  name: string;
  tagline: string;
  description: string;
  inputs: string[];
  requires_llm: boolean;
  version: string;
  icon: string; // 图标 key（见 AGENT_ICONS）
  gradient: string;
  category: string;
}

export interface BackendAgentSpec {
  id: string;
  name: string;
  description: string;
  inputs: string[];
  requires_llm: boolean;
  version: string;
}

const RAW: Array<Omit<AgentInfo, "inputs" | "requires_llm" | "version">> = [
  {
    id: "M1_business_model",
    code: "M1",
    name: "商业模式认知",
    tagline: "生意类型标签 + 能力圈评级",
    description:
      "识别公司生意类型（消费/制造/金融/周期…）与商业模式核心，评估能力圈匹配度与可理解性，为后续估值方法选择提供基础。",
    icon: "factory",
    gradient: "from-slate-500 to-zinc-700",
    category: "基础",
  },
  {
    id: "M2_financial_quality",
    code: "M2",
    name: "财务质量",
    tagline: "盈利能力 / 现金流 / 造假信号",
    description:
      "基于 ROE 杜邦分解、现金流匹配、资产负债结构与财务操纵信号，评估盈利质量与报表可信度，输出财务质量评分。",
    icon: "calculator",
    gradient: "from-emerald-500 to-teal-600",
    category: "财务",
  },
  {
    id: "M3_growth",
    code: "M3",
    name: "成长与再投资",
    tagline: "行业景气 + 增速假设",
    description:
      "结合行业景气度、全球趋势与公司再投资回报率，建立未来 3-5 年营收与利润增速假设，判断成长可持续性。",
    icon: "trending-up",
    gradient: "from-sky-500 to-blue-600",
    category: "成长",
  },
  {
    id: "M4_valuation",
    code: "M4",
    name: "估值引擎",
    tagline: "方法路由 + 多模型交叉",
    description:
      "按生意类型路由估值方法（DCF / PE / PB / 股息），多模型交叉验证，输出估值中枢与合理区间。",
    icon: "chart-line",
    gradient: "from-violet-500 to-purple-600",
    category: "估值",
  },
  {
    id: "M5_moat",
    code: "M5",
    name: "护城河",
    tagline: "财务代理评级 + LLM 定性两层合成",
    description:
      "规则层按相对行业基准的 ROE/利润率/杠杆做财务代理评级并识别来源信号，LLM 定性补充品牌/网络/转换成本等来源与侵蚀风险，两层合成最终宽度。",
    icon: "castle",
    gradient: "from-amber-500 to-orange-600",
    category: "质地",
  },
  {
    id: "M6_governance",
    code: "M6",
    name: "治理与资本配置",
    tagline: "管理层 + 分红回购",
    description:
      "评估管理层诚信与能力、股权结构、分红回购与再融资历史，判断资本配置是否有利于股东。",
    icon: "landmark",
    gradient: "from-rose-500 to-pink-600",
    category: "治理",
  },
  {
    id: "M7_market",
    code: "M7",
    name: "价格与情绪",
    tagline: "估值分位 + 股债性价比",
    description:
      "结合估值历史分位、股债性价比与市场情绪指标，判断当前价格隐含的预期与安全程度。",
    icon: "trending-down",
    gradient: "from-cyan-500 to-teal-600",
    category: "市场",
  },
  {
    id: "M8_safety_margin",
    code: "M8",
    name: "安全边际",
    tagline: "折扣率 + 买卖区间",
    description:
      "对比内在价值与当前价格，计算折扣率，给出买入区间、卖出区间与仓位建议。",
    icon: "shield-check",
    gradient: "from-lime-500 to-green-600",
    category: "决策",
  },
  {
    id: "M9_risk",
    code: "M9",
    name: "风险与否决",
    tagline: "风险清单 + 一票否决",
    description:
      "系统性梳理经营 / 财务 / 估值 / 治理风险，维护一票否决清单，对重大风险给出红灯预警。",
    icon: "triangle-alert",
    gradient: "from-red-500 to-rose-600",
    category: "风险",
  },
  {
    id: "M10_decision",
    code: "M10",
    name: "决策输出",
    tagline: "评分卡 + 结论 + 备忘录",
    description:
      "汇总全部模块评分，生成加权评分卡、投资结论与可验证的投资备忘录。",
    icon: "target",
    gradient: "from-indigo-500 to-blue-700",
    category: "决策",
  },
  {
    id: "M11_monitor",
    code: "M11",
    name: "跟踪监控",
    tagline: "持有逻辑验证 + 卖出触发",
    description:
      "定义持有逻辑的验证指标与卖出触发条件，支持定期监控与异动提醒。",
    icon: "radio-tower",
    gradient: "from-fuchsia-500 to-purple-700",
    category: "监控",
  },
];

export const LOCAL_AGENTS: AgentInfo[] = RAW.map((a) => ({
  ...a,
  inputs: [],
  requires_llm: false,
  version: "0.1.0",
}));

export function findAgent(id: string): AgentInfo | undefined {
  return LOCAL_AGENTS.find((a) => a.id === id);
}

export function mergeBackendAgents(
  specs: BackendAgentSpec[]
): AgentInfo[] {
  const map = new Map<string, BackendAgentSpec>();
  for (const s of specs) map.set(s.id, s);

  return LOCAL_AGENTS.map((local) => {
    const remote = map.get(local.id);
    if (!remote) return local;
    return {
      ...local,
      name: remote.name || local.name,
      description: remote.description || local.description,
      inputs: remote.inputs ?? local.inputs,
      requires_llm: remote.requires_llm ?? local.requires_llm,
      version: remote.version || local.version,
    };
  });
}
