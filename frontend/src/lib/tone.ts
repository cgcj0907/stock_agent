/**
 * 语义配色统一口径（展示层）：结果卡 / 模块输出 / 备忘录共用，
 * 避免各组件各自定义色表导致色值漂移（如 info 一处 sky 一处 amber）。
 * 约定：中性/信息=sky，警告=amber，高风险/负面=orange→red，正向/低估=emerald。
 */

export const POSITION_TONE: Record<string, string> = {
  极低估: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
  低估: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
  合理: "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-950/60 dark:text-sky-300",
  合理偏下: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
  合理偏上: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  高估: "border-orange-200 bg-orange-50 text-orange-700 dark:border-orange-800 dark:bg-orange-950/60 dark:text-orange-300",
  泡沫: "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/60 dark:text-red-300",
  样本不足: "border-border bg-muted/50 text-muted-foreground",
};

export const SEVERITY_TONE: Record<string, string> = {
  info: "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-950/60 dark:text-sky-300",
  low: "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-950/60 dark:text-sky-300",
  medium: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  warn: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  high: "border-orange-200 bg-orange-50 text-orange-700 dark:border-orange-800 dark:bg-orange-950/60 dark:text-orange-300",
  critical: "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/60 dark:text-red-300",
};

export const MOS_TONE: Record<string, string> = {
  attractive: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
  fair: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  expensive: "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/60 dark:text-red-300",
  unavailable: "border-border bg-muted/50 text-muted-foreground",
};

export const MOS_LABEL: Record<string, string> = {
  attractive: "安全边际充足",
  fair: "边际一般",
  expensive: "安全边际为负",
  unavailable: "数据不足",
};

export const WIDTH_TEXT_TONE: Record<string, string> = {
  宽: "text-emerald-700 dark:text-emerald-300",
  较宽: "text-emerald-700 dark:text-emerald-300",
  中: "text-amber-700 dark:text-amber-300",
  较窄: "text-orange-700 dark:text-orange-300",
  窄: "text-red-700 dark:text-red-300",
  无: "text-red-700 dark:text-red-300",
};

export const CONCLUSION_TONE: Record<string, string> = {
  强烈关注: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
  关注: "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-950/60 dark:text-sky-300",
  中性: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  回避: "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/60 dark:text-red-300",
};

export const VERDICT_TONE: Record<string, string> = {
  positive:
    "border-emerald-200/70 bg-emerald-50/60 text-emerald-800 dark:border-emerald-800/50 dark:bg-emerald-950/30 dark:text-emerald-300",
  neutral: "border-border/60 bg-muted/40 text-foreground",
  negative:
    "border-rose-200/70 bg-rose-50/60 text-rose-800 dark:border-rose-800/50 dark:bg-rose-950/30 dark:text-rose-300",
  muted: "border-border/60 bg-muted/30 text-muted-foreground",
};

/** 枚举/中文键 → 配色类；未知键回退中性灰。 */
export function toneOf(map: Record<string, string>, key: unknown): string {
  const k = typeof key === "string" ? key : String(key ?? "");
  return map[k] ?? "border-border bg-muted/50 text-muted-foreground";
}

/** 枚举 → 中文标签；未知键原样返回。 */
export function labelOf(map: Record<string, string>, v: unknown): string {
  const k = typeof v === "string" ? v : String(v ?? "");
  return map[k] ?? k;
}
