import Link from "next/link";
import { ArrowRight, Workflow } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export default function WorkflowsPlaceholderPage() {
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">工作流</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          可视化工作流分析（M4 里程碑开发中）
        </p>
      </div>
      <Card className="rounded-2xl border-dashed">
        <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
          <div className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
            <Workflow className="size-6" />
          </div>
          <div>
            <p className="text-sm font-medium">工作流分析即将上线</p>
            <p className="text-xs text-muted-foreground">
              下一步将实现 DAG 可视化、SSE 进度与结果/备忘录展示
            </p>
          </div>
          <Button asChild variant="outline" size="sm" className="rounded-lg">
            <Link href="/agents">
              先去逛逛智能体 <ArrowRight className="ml-1 size-3.5" />
            </Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
