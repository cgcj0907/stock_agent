"use client";

import { EChart, type EChartOption } from "@/components/ui/echart";

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
  const option: EChartOption = {
    grid: { left: 4, right: 64, top: 10, bottom: 2, containLabel: true },
    tooltip: { trigger: "item", confine: true },
    xAxis: {
      type: "value",
      splitLine: { show: false },
      axisLabel: { show: false },
    },
    yAxis: {
      type: "category",
      data: [""],
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { show: false },
    },
    series: [
      {
        type: "bar",
        stack: "band",
        data: [{ value: low, itemStyle: { color: "transparent" } }],
        barWidth: 12,
        silent: true,
      },
      {
        type: "bar",
        stack: "band",
        data: [
          {
            value: Math.max(0, mid - low),
            itemStyle: { color: "#6ee7b7" },
          },
        ],
        barWidth: 12,
        silent: true,
      },
      {
        type: "bar",
        stack: "band",
        data: [
          {
            value: Math.max(0, high - mid),
            itemStyle: { color: "#fde68a", borderRadius: [0, 6, 6, 0] },
          },
        ],
        barWidth: 12,
        silent: true,
      },
      {
        type: "bar",
        stack: "band",
        data: [{ value: 0, itemStyle: { color: "transparent" } }],
        barWidth: 12,
        markLine:
          currentPrice != null
            ? {
                symbol: "none",
                lineStyle: { color: "#0ea5e9", width: 1.5, type: "dashed" },
                label: {
                  formatter: `现价 ${currentPrice}`,
                  color: "#0369a1",
                  fontSize: 10,
                  position: "insideEndTop",
                },
                data: [{ xAxis: currentPrice }],
              }
            : undefined,
      },
    ],
  };
  return <EChart option={option} className="h-14 w-full" />;
}

/** 估值方法对比：横向柱状 + 中值参考线 */
export function MethodCompareChart({ methods }: { methods: MethodView[] }) {
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
      axisLabel: { fontSize: 11, color: "#8a8a92" },
    },
    series: [
      {
        type: "bar",
        data: items.map((i) => i.value),
        barWidth: 11,
        itemStyle: { color: "#7c3aed", borderRadius: [0, 4, 4, 0] },
        label: {
          show: true,
          position: "right",
          fontSize: 10,
          fontWeight: 600,
          color: "#232329",
          formatter: "{c}",
        },
        markLine: {
          symbol: "none",
          lineStyle: { color: "#a78bfa", type: "dashed", width: 1.5 },
          label: {
            formatter: `中值 ${avg.toFixed(0)}`,
            color: "#8b5cf6",
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
  const values = DIMS.map((d) => dims[d.key]);
  if (values.every((v) => v == null)) return null;

  const option: EChartOption = {
    tooltip: { trigger: "item", confine: true },
    radar: {
      indicator: DIMS.map((d) => ({ name: d.label, max: 100 })),
      radius: "68%",
      splitNumber: 4,
      axisName: { color: "#8a8a92", fontSize: 10 },
      splitLine: { lineStyle: { color: "#e7e8ea" } },
      splitArea: { areaStyle: { color: ["#ffffff", "#fafafa"] } },
      axisLine: { lineStyle: { color: "#e7e8ea" } },
    },
    series: [
      {
        type: "radar",
        data: [
          {
            value: values.map((v) => (v == null ? 0 : v)),
            name: "五维评分",
            areaStyle: { color: "rgba(5,150,105,0.22)" },
            lineStyle: { color: "#059669", width: 2 },
            itemStyle: { color: "#059669" },
            symbolSize: 4,
          },
        ],
      },
    ],
  };
  return <EChart option={option} className="h-44 w-full" />;
}
