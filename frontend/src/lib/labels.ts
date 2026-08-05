/**
 * 各模块输出字段 → 中文标签（仅用于展示，无匹配时保留原键名）。
 * 覆盖结果卡片顶层字段与嵌套指标（metrics / intrinsic_value / methods / params / dimensions 等）。
 */
export const FIELD_LABELS: Record<string, string> = {
  // M1 商业模式
  business_type: "生意类型",
  one_liner: "一句话描述",
  understandability: "可理解性",
  industry: "行业",
  // M2 财务质量
  metrics: "核心指标",
  signals: "风险信号",
  summary: "摘要",
  years: "年报期数",
  roe_latest: "ROE 最新",
  roe_mean: "ROE 均值",
  net_margin: "净利率",
  grossprofit_margin: "毛利率",
  equity_multiplier: "权益乘数",
  implied_asset_turnover: "隐含周转",
  ocf_to_np_min: "现金流/净利最低",
  debt_to_assets_latest: "资产负债率",
  // M3 成长
  growth_estimate: "增速估计",
  prosperity: "景气度",
  // M4 估值
  methods: "估值方法",
  intrinsic_value: "内在价值区间",
  current_price: "现价",
  params: "估值参数",
  note: "备注",
  low: "低",
  mid: "中",
  high: "高",
  value: "估值",
  growth_rate: "增长率",
  discount_rate: "折现率",
  terminal_growth: "永续增速",
  risk_free_rate: "无风险利率",
  dcf: "DCF 现金流折现",
  tang: "唐朝法",
  graham_number: "格雷厄姆数",
  graham_formula: "格雷厄姆公式",
  ddm: "股利贴现",
  relative_median_pe: "相对中位 PE",
  // M5 护城河
  width: "护城河宽度",
  // M6 治理
  dividend_years: "连续分红年数",
  payout_latest: "最新分红率",
  // M7 市场
  pe_percentile: "PE 分位",
  pb_percentile: "PB 分位",
  position: "估值位置",
  // M8 安全边际
  price: "现价",
  discount: "折扣率",
  required_discount: "要求折扣",
  buy_price: "买入价",
  sell_price: "卖出价",
  status: "状态",
  // M9 风险
  schema_version: "契约版本",
  module_type: "模块类型",
  core_facts: "核心事实",
  qualitative: "定性分析",
  handoff: "下游契约",
  meta: "质量元数据",
  reason_codes: "降级原因",
  risk_items: "风险清单",
  veto: "否决项",
  // M10 决策
  dimensions: "五维评分",
  total: "加权总分",
  conclusion: "结论",
  vetoed: "否决项",
  // M11 监控
  monitor_rules: "监控规则",
  rule_count: "规则数",
  trigger: "触发条件",
  description: "说明",
  severity: "级别",
  // 五维评分
  business_moat: "护城河",
  financial_quality: "财务质量",
  growth_prosperity: "成长景气",
  valuation_margin: "估值边际",
  governance_risk: "治理风险",
  // LLM 定性
  llm_qualitative: "LLM 定性分析",
  llm_red_team: "LLM 红队批判",
  llm_explanation: "LLM 解释",
  // LLM 结构化字段
  business_model: "商业模式",
  reasons: "判断理由",
  moat_sources: "护城河来源",
  evidence: "证据链",
  governance_assessment: "治理评估",
  capital_allocation: "资本配置",
  risks: "主要风险点",
  key_assumptions: "关键假设",
  permanent_loss_paths: "永久损失路径",
  verdict: "反方结论",
  references: "参考文章",
};

export function fieldLabel(key: string): string {
  return FIELD_LABELS[key] ?? key;
}
