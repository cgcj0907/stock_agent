"use client";

import * as React from "react";

/**
 * ECharts 主题色：从 CSS 变量（globals.css --chart-* / --border / --muted-foreground …）
 * 读取，随亮/暗主题切换自动更新，替代硬编码色（UI 优化 P0）。
 */

export interface ChartTheme {
  axisLabel: string;
  splitLine: string;
  splitArea: [string, string];
  bar: string;
  barLabel: string;
  markLine: string;
  markLabel: string;
  radarName: string;
  radarLine: string;
  radarArea: string;
  radarItem: string;
}

export const FALLBACK_CHART_THEME: ChartTheme = {
  axisLabel: "#8a8a92",
  splitLine: "#e7e8ea",
  splitArea: ["#ffffff", "#fafafa"],
  bar: "#7c3edc",
  barLabel: "#232329",
  markLine: "#a78bfa",
  markLabel: "#8b5cf6",
  radarName: "#8a8a92",
  radarLine: "#059669",
  radarArea: "rgba(5,150,105,0.22)",
  radarItem: "#059669",
};

function readCssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const raw = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return raw || fallback;
}

export function readChartTheme(): ChartTheme {
  const chart1 = readCssVar("--chart-1", FALLBACK_CHART_THEME.radarLine);
  const chart2 = readCssVar("--chart-2", FALLBACK_CHART_THEME.markLine);
  const chart3 = readCssVar("--chart-3", FALLBACK_CHART_THEME.bar);
  return {
    axisLabel: readCssVar("--muted-foreground", FALLBACK_CHART_THEME.axisLabel),
    splitLine: readCssVar("--border", FALLBACK_CHART_THEME.splitLine),
    splitArea: [
      readCssVar("--card", FALLBACK_CHART_THEME.splitArea[0]),
      readCssVar("--muted", FALLBACK_CHART_THEME.splitArea[1]),
    ],
    bar: chart3,
    barLabel: readCssVar("--foreground", FALLBACK_CHART_THEME.barLabel),
    markLine: chart2,
    markLabel: chart2,
    radarName: readCssVar("--muted-foreground", FALLBACK_CHART_THEME.radarName),
    radarLine: chart1,
    radarArea: `color-mix(in oklab, ${chart1} 22%, transparent)`,
    radarItem: chart1,
  };
}

/** 监听 <html> class（亮/暗切换）变化，返回最新主题色。 */
export function useChartTheme(): ChartTheme {
  const [theme, setTheme] = React.useState<ChartTheme>(readChartTheme);

  React.useEffect(() => {
    const update = () => setTheme(readChartTheme());
    update();
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    window.addEventListener("resize", update);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", update);
    };
  }, []);

  return theme;
}
