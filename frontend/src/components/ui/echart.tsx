"use client";

import * as React from "react";
import * as echarts from "echarts/core";
import { BarChart, RadarChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  RadarComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  BarChart,
  RadarChart,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  RadarComponent,
  TooltipComponent,
  CanvasRenderer,
]);

export type EChartOption = echarts.EChartsCoreOption;

/**
 * 轻量 echarts 容器：自动初始化 / 更新 / 随容器缩放。
 * 固定挂 `echarts-container` 类：打印 / 导出 PDF 时经 globals.css 隐藏画布
 * （画布打印易空白或受深色主题影响，数值表格/摘要仍在报告里）。
 */
export function EChart({
  option,
  className,
}: {
  option: EChartOption;
  className?: string;
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  const chartRef = React.useRef<echarts.ECharts | null>(null);

  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const chart = echarts.init(el);
    chartRef.current = chart;
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  React.useEffect(() => {
    chartRef.current?.setOption(option, { notMerge: true });
  }, [option]);

  return (
    <div
      ref={ref}
      className={className ? `echarts-container ${className}` : "echarts-container"}
    />
  );
}
