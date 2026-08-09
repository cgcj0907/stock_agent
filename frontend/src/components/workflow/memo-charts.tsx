"use client";

import { EChart, type EChartOption } from "@/components/ui/echart";
import { useChartTheme } from "@/lib/chart-theme";

const METHOD_LABELS: Record<string, string> = {
  dcf: "DCF",
  tang: "唐朝法",
  graham_number: "格雷厄姆数",
  graham_formula: "格雷厄姆公式",
  ddm: "股利贴现",
  relative_median_pe: "相对中位 PE",
};

const DIMS: { key: string; label: string }[] = [
  { key: "business_moat", label: "护城河" },
  { key: "financial_quality", label: "财务质量" },
  { key: "growth_prosperity", label: "成长景气" },
  { key: "valuation_margin", label: "估值边际" },
  { key: "governance_risk", label: "治理风险" },
];

interface MethodView {
  method?: string;
  applicable?: boolean;
  value?: number | null;
}

/** 内在价值区间带：低/中/高 + 当前价标记线 */
export function ValueBandChart({
  low,
  mid,
  high,
  currentPrice,
}: {
  low: number;
  mid: number;
  high: number;
  currentPrice?: number | null;
}) {
  const bandPct =
    currentPrice != null
      ? Math.max(0, Math.min(100, ((currentPrice - low) / (high - low)) * 100))
      : null;

  const fmt = (value: number | null | undefined) =>
    value == null ? "—" : String(Math.round(value * 100) / 100);

  return (
    <div className="rounded-xl px-1 py-2">
      <div className="relative mx-1 h-2 rounded-full bg-gradient-to-r from-emerald-200 via-emerald-300 to-amber-300">
        {bandPct != null && (
          <span
            className="absolute -top-[5px] h-[18px] w-[3px] rounded bg-sky-500 shadow-[0_0_0_3px_#e0f2fe]"
            style={{ left: `calc(${bandPct}% - 1px)` }}
            title={`现价 ${fmt(currentPrice)}`}
          />
        )}
      </div>
      <div className="mt-2 flex justify-between text-xs text-muted-foreground tabular-nums">
        <span>低 {fmt(low)}</span>
        <span className="font-bold text-foreground">中 {fmt(mid)}</span>
        <span>高 {fmt(high)}</span>
      </div>
    </div>
  );
}

/** 估值方法对比：横向柱状 + 中值参考线 */
export function MethodCompareChart({ methods }: { methods: MethodView[] }) {
  const theme = useChartTheme();
  const items = methods
    .filter((m) => m.applicable !== false && m.value != null)
    .map((m) => ({
      name: METHOD_LABELS[m.method ?? ""] ?? m.method ?? "—",
      value: m.value as number,
    }));
  if (items.length === 0) return null;

  const avg = items.reduce((s, x) => s + x.value, 0) / items.length;

  const option: EChartOption = {
    grid: { left: 4, right: 36, top: 12, bottom: 4, containLabel: true },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, confine: true },
    xAxis: {
      type: "value",
      splitLine: { show: false },
      axisLabel: { show: false },
    },
    yAxis: {
      type: "category",
      inverse: true,
      data: items.map((i) => i.name),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { fontSize: 11, color: theme.axisLabel },
    },
    series: [
      {
        type: "bar",
        data: items.map((i) => i.value),
        barWidth: 11,
        itemStyle: { color: theme.bar, borderRadius: [0, 4, 4, 0] },
        label: {
          show: true,
          position: "right",
          fontSize: 10,
          fontWeight: 600,
          color: theme.barLabel,
          formatter: "{c}",
        },
        markLine: {
          symbol: "none",
          lineStyle: { color: theme.markLine, type: "dashed", width: 1.5 },
          label: {
            formatter: `中值 ${avg.toFixed(0)}`,
            color: theme.markLabel,
            fontSize: 10,
            position: "insideEndTop",
          },
          data: [{ xAxis: avg }],
        },
      },
    ],
  };
  return <EChart option={option} className="h-32 w-full" />;
}

/** 五维评分雷达图 */
export function RadarScoreChart({ dims }: { dims: Record<string, number> }) {
  const theme = useChartTheme();
  const values = DIMS.map((d) => dims[d.key]);
  if (values.every((v) => v == null)) return null;

  const option: EChartOption = {
    tooltip: { trigger: "item", confine: true },
    radar: {
      indicator: DIMS.map((d) => ({ name: d.label, max: 100 })),
      radius: "68%",
      splitNumber: 4,
      axisName: { color: theme.radarName, fontSize: 10 },
      splitLine: { lineStyle: { color: theme.splitLine } },
      splitArea: { areaStyle: { color: theme.splitArea } },
      axisLine: { lineStyle: { color: theme.splitLine } },
    },
    series: [
      {
        type: "radar",
        data: [
          {
            value: values.map((v) => (v == null ? 0 : v)),
            name: "五维评分",
            areaStyle: { color: theme.radarArea },
            lineStyle: { color: theme.radarLine, width: 2 },
            itemStyle: { color: theme.radarItem },
            symbolSize: 4,
          },
        ],
      },
    ],
  };
  return <EChart option={option} className="h-44 w-full" />;
}
