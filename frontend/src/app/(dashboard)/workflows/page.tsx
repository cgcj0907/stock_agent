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
            className="group overflow-hidden rounded-2xl transition-all hover:-translate-y-0.5 hover:shadow-md"
          >
            <div className={`h-1.5 bg-gradient-to-r ${wf.accent}`} />
            <CardHeader>
              <div className="flex items-center gap-2">
                <CardTitle className="text-base">{wf.name}</CardTitle>
                <Badge variant="secondary" className="rounded-md font-mono text-[10px]">
                  {wf.id}
                </Badge>
              </div>
              <CardDescription className="text-xs leading-5">
                {wf.description}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <GitBranch className="size-3.5" />
                {wf.steps.length} 步 · {wf.steps.map((s) => s.id).join(" → ")}
              </div>
              <Button asChild size="sm" className="rounded-full">
                <Link href={`/workflows/${wf.id}`}>
                  开始分析 <ArrowRight className="size-3.5" />
                </Link>
              </Button>
            </CardContent>
          </Card>
        ))}

        <Card className="rounded-2xl border-dashed opacity-70">
          <CardContent className="flex h-full min-h-32 flex-col items-center justify-center gap-2 p-6 text-center">
            <Workflow className="size-6 text-muted-foreground" />
            <div>
              <p className="text-sm font-medium">自定义工作流</p>
              <p className="text-xs text-muted-foreground">
                M4.5 里程碑：拖拽编排你自己的分析流
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      <CustomWorkflowSection initial={custom} />
    </div>
  );
}
