import Link from "next/link";
import { ArrowLeft, Workflow } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export default async function WorkflowDetailPlaceholder({
  params,
}: {
  params: Promise<{ workflowId: string }>;
}) {
  const { workflowId } = await params;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <Button asChild variant="ghost" size="sm" className="w-fit rounded-lg">
        <Link href="/workflows">
          <ArrowLeft className="size-4" />
          返回工作流
        </Link>
      </Button>
      <Card className="rounded-2xl border-dashed">
        <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
          <div className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
            <Workflow className="size-6" />
          </div>
          <div>
            <p className="text-sm font-medium">
              工作流「{workflowId}」分析页开发中
            </p>
            <p className="text-xs text-muted-foreground">
              M4 将实现 DAG 可视化与 SSE 实时进度
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
