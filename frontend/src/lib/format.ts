/**
 * 数字 / 百分比统一展示口径（UI 优化 P0）。
 * 约定：金额（元）→ formatPrice / formatNumber；比例（0~1）→ formatPct / formatPct1；
 * 带方向 → formatSignedPct；大数（财务指标）→ formatBigNumber。
 */

const zh = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });

/** 千分位数字；null / undefined / 非有限数 → "—"。 */
export function formatNumber(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return zh.format(v);
}

/** 价格（元）：千分位 + 最多 2 位小数；≥1 万用「万」，≥1 亿用「亿」。 */
export function formatPrice(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  if (abs >= 1e8) return `${(v / 1e8).toFixed(2)} 亿`;
  if (abs >= 1e4) return `${(v / 1e4).toFixed(1)} 万`;
  return zh.format(v);
}

/** 大数单位化：≥1 亿 → "x.xx 亿"；≥1 万 → "x.x 万"；否则千分位。 */
export function formatBigNumber(
  v: number | null | undefined,
  decimals = 2
): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  if (abs >= 1e8) return `${(v / 1e8).toFixed(decimals)} 亿`;
  if (abs >= 1e4) return `${(v / 1e4).toFixed(1)} 万`;
  return zh.format(v);
}

/** 小数比例 → 整数百分比（0.123 → "12%"）。 */
export function formatPct(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${Math.round(v * 100)}%`;
}

/** 小数比例 → 1 位小数百分比（0.1234 → "12.3%"）。 */
export function formatPct1(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

/** 带符号百分比（0.123 → "+12.3%"；-0.05 → "-5.0%"）。 */
export function formatSignedPct(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const sign = v >= 0 ? "+" : "-";
  return `${sign}${Math.abs(v * 100).toFixed(1)}%`;
}
