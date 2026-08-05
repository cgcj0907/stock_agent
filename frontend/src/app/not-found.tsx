import Link from "next/link";
import { TrendingUp } from "lucide-react";

import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-gradient-to-br from-emerald-50 via-background to-teal-50 p-6 text-center dark:from-emerald-950/30 dark:via-background dark:to-teal-950/20">
      <div className="flex size-12 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 text-white shadow-sm">
        <TrendingUp className="size-6" />
      </div>
      <h1 className="text-3xl font-semibold tracking-tight">404</h1>
      <p className="text-sm text-muted-foreground">
        页面不存在或已被移除
      </p>
      <Button asChild className="rounded-full">
        <Link href="/">返回首页</Link>
      </Button>
    </div>
  );
}
