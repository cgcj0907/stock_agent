"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { WorkflowInfo } from "@/lib/workflows/catalog";
import type { CustomWorkflow } from "@/types/custom-workflow";

interface QuickStartOption {
  id: string;
  label: string;
  desc: string;
  href: string;
}

export function QuickStart({
  workflows,
  custom,
}: {
  workflows: WorkflowInfo[];
  custom: CustomWorkflow[];
}) {
  const router = useRouter();
  const [code, setCode] = React.useState("");
  const [name, setName] = React.useState("");

  const builtinOptions: QuickStartOption[] = workflows.map((w) => ({
    id: w.id,
    label: w.name,
    desc: `${w.steps.length} 个智能体`,
    href: `/workflows/${w.id}`,
  }));
  const customOptions: QuickStartOption[] = custom.map((c) => ({
    id: `custom:${c.id}`,
    label: c.name,
    desc: `${c.steps.length} 个智能体 · 自定义`,
    href: `/workflows/custom/${c.id}`,
  }));
  const options = [...builtinOptions, ...customOptions];
  const [workflowId, setWorkflowId] = React.useState<string>(
    options[0]?.id ?? ""
  );
  const selected = options.find((o) => o.id === workflowId);

  function start(e: React.FormEvent) {
    e.preventDefault();
    const c = code.trim();
    if (!c || !selected) return;
    const qs = new URLSearchParams();
    qs.set("code", c);
    if (name.trim()) qs.set("name", name.trim());
    router.push(`${selected.href}?${qs.toString()}`);
  }

  return (
    <Card className="overflow-hidden rounded-2xl border">
      <div className="h-0.5 bg-primary/70" />
      <CardContent className="p-4 md:p-5">
        <form
          onSubmit={start}
          className="flex flex-col gap-3 lg:flex-row lg:items-center"
        >
          <div className="grid flex-1 gap-3 sm:grid-cols-[minmax(0,1fr)_14rem]">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="输入 A 股代码，如 600519"
                autoFocus
                className="h-10 rounded-xl pl-9"
              />
            </div>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="公司名称（可选）"
              className="h-10 rounded-xl"
            />
          </div>
          <div className="flex items-center gap-2">
            <Select value={workflowId} onValueChange={setWorkflowId}>
              <SelectTrigger className="h-10 w-full rounded-xl lg:w-52">
                <SelectValue placeholder="选择工作流" />
              </SelectTrigger>
              <SelectContent align="end">
                <SelectGroup>
                  <SelectLabel>内置工作流</SelectLabel>
                  {builtinOptions.map((o) => (
                    <SelectItem key={o.id} value={o.id}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectGroup>
                {customOptions.length > 0 && (
                  <SelectGroup>
                    <SelectLabel>自定义工作流</SelectLabel>
                    {customOptions.map((o) => (
                      <SelectItem key={o.id} value={o.id}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                )}
              </SelectContent>
            </Select>
            <Button
              type="submit"
              disabled={!code.trim() || !selected}
              className="h-10 rounded-xl px-5"
            >
              开始分析 <ArrowRight className="size-4" />
            </Button>
          </div>
        </form>
        <p className="mt-3 text-xs text-muted-foreground">
          {selected
            ? `${selected.label} · ${selected.desc}，完整分析约 1–2 分钟`
            : "请选择工作流"}
        </p>
      </CardContent>
    </Card>
  );
}
