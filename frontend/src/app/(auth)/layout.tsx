import Link from "next/link";
import { TrendingUp } from "lucide-react";

export default function AuthLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-gradient-to-br from-emerald-50 via-background to-teal-50 p-6 dark:from-emerald-950/30 dark:via-background dark:to-teal-950/20">
      <div className="pointer-events-none absolute inset-0 bg-grid-faint [mask-image:radial-gradient(ellipse_at_top,black,transparent_70%)]" />
      <Link href="/" className="relative mb-8 flex items-center gap-2.5">
        <div className="flex size-9 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 text-white shadow-sm">
          <TrendingUp className="size-5" />
        </div>
        <div>
          <div className="text-base font-semibold leading-tight">
            Value Agent
          </div>
          <div className="text-xs text-muted-foreground">价值投资智能体</div>
        </div>
      </Link>
      <div className="relative w-full max-w-sm">{children}</div>
      <p className="relative mt-8 text-xs text-muted-foreground">
        A 股价值投资分析平台 · 免费额度内运行
      </p>
    </div>
  );
}
