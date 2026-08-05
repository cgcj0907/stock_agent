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
              className="group overflow-hidden rounded-2xl transition-all hover:-translate-y-0.5 hover:shadow-md"
            >
              <div className="h-1.5 bg-gradient-to-r from-violet-500 to-purple-600" />
              <CardHeader>
                <div className="flex items-center gap-2">
                  <CardTitle className="text-base">{cwf.name}</CardTitle>
                  <Badge variant="secondary" className="rounded-md text-[10px]">
                    自定义
                  </Badge>
                </div>
                {cwf.description && (
                  <CardDescription className="line-clamp-1 text-xs">
                    {cwf.description}
                  </CardDescription>
                )}
              </CardHeader>
              <CardContent className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <GitBranch className="size-3.5" />
                  {cwf.steps.length} 步 ·{" "}
                  {cwf.steps.map((s) => s.id).join(" → ")}
                </div>
                <div className="flex items-center gap-1">
                  <Button asChild variant="ghost" size="sm" className="rounded-lg text-xs">
                    <Link href={`/workflows/builder?id=${cwf.id}`}>
                      <Pencil className="size-3.5" />
                      编辑
                    </Link>
                  </Button>
                  <Button asChild size="sm" className="rounded-full">
                    <Link href={`/workflows/custom/${cwf.id}`}>
                      <Play className="size-3.5" />
                      运行
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
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </section>
  );
}
