"use client";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

/** 结果卡骨架：工作流运行中 / 页面加载时的占位。 */
export function ResultCardSkeleton() {
  return (
    <Card size="sm" className="flex flex-col gap-3 rounded-2xl">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-1">
        <div className="flex items-center gap-2.5">
          <Skeleton className="size-5 rounded-lg" />
          <div className="flex flex-col gap-1">
            <Skeleton className="h-3.5 w-20" />
            <Skeleton className="h-3 w-12" />
          </div>
        </div>
        <Skeleton className="h-5 w-14 rounded-md" />
      </CardHeader>
      <CardContent className="flex flex-col gap-2.5">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-2/3" />
      </CardContent>
    </Card>
  );
}
