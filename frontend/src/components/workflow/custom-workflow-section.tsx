"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { GitBranch, Pencil, Play, Plus, Trash2, Workflow } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { CustomWorkflow } from "@/types/custom-workflow";

export function CustomWorkflowSection({
  initial,
}: {
  initial: CustomWorkflow[];
}) {
  const [items, setItems] = React.useState<CustomWorkflow[]>(initial);
  const router = useRouter();

  async function handleDelete(cwf: CustomWorkflow) {
    if (!window.confirm(`删除自定义工作流「${cwf.name}」？`)) return;
    const res = await fetch(`/api/custom-workflows/${cwf.id}`, {
      method: "DELETE",
    });
    const data = await res.json();
    if (!res.ok) {
      toast.error(data.error || "删除失败");
      return;
    }
    setItems((prev) => prev.filter((x) => x.id !== cwf.id));
    toast.success("已删除");
    router.refresh();
  }

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">我的自定义工作流</h2>
        <Button asChild variant="outline" size="sm" className="rounded-full">
          <Link href="/workflows/builder">
            <Plus className="size-3.5" />
            新建
          </Link>
        </Button>
      </div>

      {items.length === 0 ? (
        <Card className="rounded-2xl border-dashed opacity-80">
          <CardContent className="flex h-full min-h-32 flex-col items-center justify-center gap-2 p-6 text-center">
            <Workflow className="size-6 text-muted-foreground" />
            <div>
              <p className="text-sm font-medium">还没有自定义工作流</p>
              <p className="text-xs text-muted-foreground">
                用编排器拖拽组合智能体，保存后即可运行
              </p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {items.map((cwf) => (
            <Card
              key={cwf.id}
              className="group rounded-2xl border-foreground/10 bg-background transition-all duration-200 hover:-translate-y-0.5 hover:border-foreground/20 hover:shadow-[0_18px_40px_-32px_rgba(0,0,0,0.8)]"
            >
              <CardHeader className="gap-4 pb-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <div className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-foreground/10 bg-muted/35 text-foreground">
                      <Workflow className="size-4" />
                    </div>
                    <div className="space-y-1.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <CardTitle className="text-base tracking-[-0.01em]">
                          {cwf.name}
                        </CardTitle>
                        <Badge
                          variant="secondary"
                          className="rounded-full border border-foreground/10 bg-background px-2 py-0 text-[10px] text-muted-foreground"
                        >
                          自定义
                        </Badge>
                      </div>
                      <p className="text-[11px] text-muted-foreground">
                        自由编排的个性化分析流程
                      </p>
                    </div>
                  </div>
                  <div className="hidden rounded-full border border-dashed border-foreground/10 px-2.5 py-1 text-[10px] text-muted-foreground md:block">
                    {cwf.steps.length} 步
                  </div>
                </div>
                {cwf.description && (
                  <CardDescription className="text-xs leading-5">
                    {cwf.description}
                  </CardDescription>
                )}
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <div className="rounded-xl border border-foreground/10 bg-muted/25 p-3">
                  <div className="mb-2 flex items-center gap-2 text-[11px] font-medium text-foreground/80">
                    <GitBranch className="size-3.5 text-muted-foreground" />
                    分析路径
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {cwf.steps.map((step) => (
                      <span
                        key={step.id}
                        className="rounded-md border border-foreground/10 bg-background px-2 py-1 font-mono text-[10px] text-foreground/80"
                      >
                        {step.id}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-foreground/10 pt-1">
                  <div className="text-xs text-muted-foreground">
                    {cwf.steps.length} 步工作流，可编辑后再运行
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      asChild
                      variant="ghost"
                      size="sm"
                      className="rounded-lg text-xs"
                    >
                      <Link href={`/workflows/builder?id=${cwf.id}`}>
                        <Pencil className="size-3.5" />
                        编辑
                      </Link>
                    </Button>
                    <Button
                      asChild
                      size="sm"
                      variant="outline"
                      className="rounded-full border-foreground/15 bg-background px-3"
                    >
                      <Link href={`/workflows/custom/${cwf.id}`}>
                        开始分析 <Play className="size-3.5" />
                      </Link>
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-8 rounded-lg text-muted-foreground hover:text-destructive"
                      onClick={() => handleDelete(cwf)}
                      aria-label="删除"
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </section>
  );
}
