export type ProfileOption = {
  value: string;
  label: string;
};

export type ProfileInput = {
  display_name?: string;
  avatar_url?: string;
  education_level?: string;
  education_major?: string;
  education_note?: string;
  career_stage?: string;
  annual_income_range?: string;
  investable_assets_range?: string;
  loss_tolerance_range?: string;
  capital_availability?: string;
  income_dependency_level?: string;
  investment_goal?: string;
  holding_period?: string;
  risk_tolerance?: string;
  investment_style?: string;
  circle_of_competence?: string[];
  decision_preference?: string;
};

export type ProfileRecord = Required<ProfileInput> & {
  id: string;
  created_at: string;
  updated_at: string;
};

export const EDUCATION_LEVEL_OPTIONS = [
  { value: "high_school", label: "高中及以下" },
  { value: "associate", label: "专科" },
  { value: "bachelor", label: "本科" },
  { value: "master", label: "硕士" },
  { value: "doctor", label: "博士" },
  { value: "other", label: "其他" },
] as const satisfies readonly ProfileOption[];

export const EDUCATION_MAJOR_OPTIONS = [
  { value: "science_engineering", label: "理工科" },
  { value: "economics", label: "经管金融" },
  { value: "law", label: "法律" },
  { value: "medicine", label: "医学" },
  { value: "humanities", label: "文史哲" },
  { value: "arts", label: "艺术设计" },
  { value: "other", label: "其他" },
] as const satisfies readonly ProfileOption[];

export const CAREER_STAGE_OPTIONS = [
  { value: "student", label: "学生" },
  { value: "early_career", label: "职场早期" },
  { value: "mid_career", label: "职场中期" },
  { value: "senior", label: "资深阶段" },
  { value: "retired", label: "退休" },
  { value: "freelancer", label: "自由职业" },
] as const satisfies readonly ProfileOption[];

export const ANNUAL_INCOME_RANGE_OPTIONS = [
  { value: "income_lt_20", label: "20 万以下" },
  { value: "income_20_50", label: "20-50 万" },
  { value: "income_50_100", label: "50-100 万" },
  { value: "income_100_300", label: "100-300 万" },
  { value: "income_300_500", label: "300-500 万" },
  { value: "income_gt_500", label: "500 万以上" },
] as const satisfies readonly ProfileOption[];

export const INVESTABLE_ASSETS_RANGE_OPTIONS = [
  { value: "assets_lt_30", label: "30 万以下" },
  { value: "assets_30_100", label: "30-100 万" },
  { value: "assets_100_300", label: "100-300 万" },
  { value: "assets_300_1000", label: "300-1000 万" },
  { value: "assets_1000_3000", label: "1000-3000 万" },
  { value: "assets_gt_3000", label: "3000 万以上" },
] as const satisfies readonly ProfileOption[];

export const LOSS_TOLERANCE_RANGE_OPTIONS = [
  { value: "loss_lt_5", label: "5% 以内" },
  { value: "loss_5_10", label: "5%-10%" },
  { value: "loss_10_20", label: "10%-20%" },
  { value: "loss_20_30", label: "20%-30%" },
  { value: "loss_gt_30", label: "30% 以上" },
] as const satisfies readonly ProfileOption[];

export const CAPITAL_AVAILABILITY_OPTIONS = [
  { value: "long_term_idle", label: "长期闲钱" },
  { value: "mid_term_idle", label: "阶段性闲钱" },
  { value: "may_need_1_3y", label: "1-3 年可能要用" },
] as const satisfies readonly ProfileOption[];

export const INCOME_DEPENDENCY_LEVEL_OPTIONS = [
  { value: "low", label: "低" },
  { value: "medium", label: "中" },
  { value: "high", label: "高" },
] as const satisfies readonly ProfileOption[];

export const INVESTMENT_GOAL_OPTIONS = [
  { value: "capital_preservation", label: "保值" },
  { value: "steady_growth", label: "稳健增值" },
  { value: "long_term_compounding", label: "长期复利" },
  { value: "aggressive_return", label: "进攻收益" },
] as const satisfies readonly ProfileOption[];

export const HOLDING_PERIOD_OPTIONS = [
  { value: "short_term", label: "短期" },
  { value: "mid_term", label: "中期" },
  { value: "long_term", label: "长期" },
] as const satisfies readonly ProfileOption[];

export const RISK_TOLERANCE_OPTIONS = [
  { value: "low", label: "低" },
  { value: "medium", label: "中" },
  { value: "high", label: "高" },
] as const satisfies readonly ProfileOption[];

export const INVESTMENT_STYLE_OPTIONS = [
  { value: "value", label: "价值" },
  { value: "growth", label: "成长" },
  { value: "dividend", label: "红利" },
  { value: "balanced", label: "均衡" },
  { value: "contrarian", label: "逆向" },
  { value: "event_driven", label: "事件驱动" },
] as const satisfies readonly ProfileOption[];

export const CIRCLE_OF_COMPETENCE_OPTIONS = [
  { value: "consumer", label: "消费" },
  { value: "finance", label: "金融" },
  { value: "technology", label: "科技" },
  { value: "healthcare", label: "医药医疗" },
  { value: "manufacturing", label: "制造业" },
  { value: "energy", label: "能源材料" },
  { value: "internet", label: "互联网平台" },
  { value: "utilities", label: "公用事业" },
  { value: "real_estate", label: "地产链" },
  { value: "overseas", label: "海外市场" },
] as const satisfies readonly ProfileOption[];

export const DECISION_PREFERENCE_OPTIONS = [
  { value: "margin_of_safety", label: "更看重安全边际" },
  { value: "growth_upside", label: "更看重成长弹性" },
  { value: "balanced", label: "两者平衡" },
] as const satisfies readonly ProfileOption[];

type EnumFields = Omit<ProfileInput, "display_name" | "avatar_url" | "education_note" | "circle_of_competence">;

const ENUM_OPTIONS: Record<keyof EnumFields, readonly ProfileOption[]> = {
  education_level: EDUCATION_LEVEL_OPTIONS,
  education_major: EDUCATION_MAJOR_OPTIONS,
  career_stage: CAREER_STAGE_OPTIONS,
  annual_income_range: ANNUAL_INCOME_RANGE_OPTIONS,
  investable_assets_range: INVESTABLE_ASSETS_RANGE_OPTIONS,
  loss_tolerance_range: LOSS_TOLERANCE_RANGE_OPTIONS,
  capital_availability: CAPITAL_AVAILABILITY_OPTIONS,
  income_dependency_level: INCOME_DEPENDENCY_LEVEL_OPTIONS,
  investment_goal: INVESTMENT_GOAL_OPTIONS,
  holding_period: HOLDING_PERIOD_OPTIONS,
  risk_tolerance: RISK_TOLERANCE_OPTIONS,
  investment_style: INVESTMENT_STYLE_OPTIONS,
  decision_preference: DECISION_PREFERENCE_OPTIONS,
};

export const EMPTY_PROFILE: Required<ProfileInput> = {
  display_name: "",
  avatar_url: "",
  education_level: "",
  education_major: "",
  education_note: "",
  career_stage: "",
  annual_income_range: "",
  investable_assets_range: "",
  loss_tolerance_range: "",
  capital_availability: "",
  income_dependency_level: "",
  investment_goal: "",
  holding_period: "",
  risk_tolerance: "",
  investment_style: "",
  circle_of_competence: [],
  decision_preference: "",
};

function cleanText(value: unknown, maxLength: number) {
  return String(value ?? "").trim().slice(0, maxLength);
}

function assertEnumField(
  field: keyof EnumFields,
  value: string,
): string {
  if (!value) return "";
  const allowed = new Set(ENUM_OPTIONS[field].map((option) => option.value));
  if (!allowed.has(value)) {
    throw new Error(`Invalid ${field}: ${value}`);
  }
  return value;
}

export function normalizeProfileInput(input: ProfileInput): Required<ProfileInput> {
  const display_name = cleanText(input.display_name, 32);
  const avatar_url = cleanText(input.avatar_url, 2048);
  const education_note = cleanText(input.education_note, 120);

  if (avatar_url && !/^https?:\/\//i.test(avatar_url)) {
    throw new Error(`Invalid avatar_url: ${avatar_url}`);
  }

  const circle_of_competence = Array.from(
    new Set(
      Array.isArray(input.circle_of_competence)
        ? input.circle_of_competence
            .map((value) => String(value).trim())
            .filter(Boolean)
        : [],
    ),
  );

  const allowedCircles = new Set<string>(
    CIRCLE_OF_COMPETENCE_OPTIONS.map((option) => option.value),
  );
  for (const value of circle_of_competence) {
    if (!allowedCircles.has(value)) {
      throw new Error(`Invalid circle_of_competence: ${value}`);
    }
  }
  if (circle_of_competence.length > 5) {
    throw new Error("Invalid circle_of_competence: max 5 items");
  }

  return {
    display_name,
    avatar_url,
    education_note,
    circle_of_competence,
    education_level: assertEnumField(
      "education_level",
      cleanText(input.education_level, 32),
    ),
    education_major: assertEnumField(
      "education_major",
      cleanText(input.education_major, 32),
    ),
    career_stage: assertEnumField("career_stage", cleanText(input.career_stage, 32)),
    annual_income_range: assertEnumField(
      "annual_income_range",
      cleanText(input.annual_income_range, 32),
    ),
    investable_assets_range: assertEnumField(
      "investable_assets_range",
      cleanText(input.investable_assets_range, 32),
    ),
    loss_tolerance_range: assertEnumField(
      "loss_tolerance_range",
      cleanText(input.loss_tolerance_range, 32),
    ),
    capital_availability: assertEnumField(
      "capital_availability",
      cleanText(input.capital_availability, 32),
    ),
    income_dependency_level: assertEnumField(
      "income_dependency_level",
      cleanText(input.income_dependency_level, 32),
    ),
    investment_goal: assertEnumField(
      "investment_goal",
      cleanText(input.investment_goal, 32),
    ),
    holding_period: assertEnumField(
      "holding_period",
      cleanText(input.holding_period, 32),
    ),
    risk_tolerance: assertEnumField(
      "risk_tolerance",
      cleanText(input.risk_tolerance, 32),
    ),
    investment_style: assertEnumField(
      "investment_style",
      cleanText(input.investment_style, 32),
    ),
    decision_preference: assertEnumField(
      "decision_preference",
      cleanText(input.decision_preference, 32),
    ),
  };
}

export function mergeProfileRecord(row: Partial<ProfileRecord> | null | undefined) {
  return {
    ...EMPTY_PROFILE,
    ...row,
    circle_of_competence: Array.isArray(row?.circle_of_competence)
      ? row.circle_of_competence
      : [],
  };
}
