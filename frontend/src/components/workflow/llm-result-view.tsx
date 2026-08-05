"use client";

import * as React from "react";
import { ValueView } from "@/components/workflow/value-view";
import { tryParseJson } from "@/lib/json";

/** LLM 结构化 JSON 字段 → 中文标签（提示词中定义的稳定键名）。 */
const LLM_KEY_LABELS: Record<string, string> = {
  business_model: "商业模式",
  understandability: "可理解性",
  reasons: "判断理由",
  moat_sources: "护城河来源",
  width: "宽度评级",
  evidence: "证据链",
  governance_assessment: "治理评估",
  capital_allocation: "资本配置",
  risks: "主要风险点",
  conclusion: "结论",
  key_assumptions: "关键假设",
  permanent_loss_paths: "永久损失路径",
  verdict: "反方结论",
};

/**
 * 把 LLM 结构化输出（dict 或 JSON 文本）渲染成「字段名 + 值」的整齐列表。
 * 非对象 / 解析失败时回退到 ValueView 原样展示。
 */
export function LlmResultView({ value }: { value: unknown }) {
  let data: Record<string, unknown> | null = null;
  if (value && typeof value === "object" && !Array.isArray(value)) {
    data = value as Record<string, unknown>;
  } else if (typeof value === "string") {
    const parsed = tryParseJson(value);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      data = parsed as Record<string, unknown>;
    }
  }

  if (!data || Object.keys(data).length === 0) {
    return <ValueView value={value} />;
  }

  return (
    <div className="flex flex-col gap-1.5">
      {Object.entries(data).map(([k, v]) => (
        <div key={k} className="flex flex-col gap-0.5">
          <span className="text-[10px] font-semibold text-muted-foreground">
            {LLM_KEY_LABELS[k] ?? k}
          </span>
          <div className="text-xs leading-5">
            <ValueView value={v} label={LLM_KEY_LABELS[k] ?? k} />
          </div>
        </div>
      ))}
    </div>
  );
}
