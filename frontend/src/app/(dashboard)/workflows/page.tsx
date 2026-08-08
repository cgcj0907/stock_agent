import Link from "next/link";
import { ArrowRight, GitBranch, Workflow } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { CustomWorkflowSection } from "@/components/workflow/custom-workflow-section";
import { createClient } from "@/lib/supabase/server";
import { getCurrentUser } from "@/lib/supabase/auth";
import { WORKFLOWS } from "@/lib/workflows/catalog";
import type { CustomWorkflow } from "@/types/custom-workflow";

function getWorkflowSummary(id: string) {
  return id === "default" ? "完整链路" : "快速筛查";
}

export default async function WorkflowsPage() {
  let custom: CustomWorkflow[] = [];
  try {
    const user = await getCurrentUser();
    if (user) {
      const supabase = await createClient();
      const { data } = await supabase
        .from("custom_workflows")
        .select("*")
        .eq("user_id", user.id)
        .order("updated_at", { ascending: false });
      custom = (data ?? []) as CustomWorkflow[];
    }
  } catch {
    // 表未创建时忽略
  }
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">工作流</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          选择分析流程，输入公司后运行；也可在智能体广场中组合自己的流程
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {WORKFLOWS.map((wf) => (
          <Card
            key={wf.id}
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
                        {wf.name}
                      </CardTitle>
                      <Badge
                        variant="secondary"
                        className="rounded-full border border-foreground/10 bg-background px-2 py-0 font-mono text-[10px] text-muted-foreground"
                      >
                        {wf.id}
                      </Badge>
                    </div>
                    <p className="text-[11px] text-muted-foreground">
                      {getWorkflowSummary(wf.id)}
                    </p>
                  </div>
                </div>
                <div className="hidden rounded-full border border-dashed border-foreground/10 px-2.5 py-1 text-[10px] text-muted-foreground md:block">
                  {wf.steps.length} 步
                </div>
              </div>
              <CardDescription className="text-xs leading-5">
                {wf.description}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="rounded-xl border border-foreground/10 bg-muted/25 p-3">
                <div className="mb-2 flex items-center gap-2 text-[11px] font-medium text-foreground/80">
                  <GitBranch className="size-3.5 text-muted-foreground" />
                  分析路径
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {wf.steps.map((step) => (
                    <span
                      key={step.id}
                      className="rounded-md border border-foreground/10 bg-background px-2 py-1 font-mono text-[10px] text-foreground/80"
                    >
                      {step.id}
                    </span>
                  ))}
                </div>
              </div>

              <div className="flex items-center justify-between gap-3 border-t border-foreground/10 pt-1">
                <div className="text-xs text-muted-foreground">
                  {wf.steps.length} 步工作流，按既定顺序推进
                </div>
                <Button
                  asChild
                  size="sm"
                  variant="outline"
                  className="rounded-full border-foreground/15 bg-background px-3"
                >
                  <Link href={`/workflows/${wf.id}`}>
                    开始分析 <ArrowRight className="size-3.5" />
                  </Link>
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <CustomWorkflowSection initial={custom} />
    </div>
  );
}
