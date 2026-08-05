import Link from "next/link";
import {
  ArrowRight,
  Bot,
  CircleDollarSign,
  Cpu,
  FileSearch,
  History,
  LineChart,
  ShieldCheck,
  Workflow,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const STATS = [
  { label: "智能体", value: 11, icon: Bot },
  { label: "工作流", value: 2, icon: Workflow },
  { label: "对话记录", value: 0, icon: History },
  { label: "LLM 服务商", value: 0, icon: Cpu },
];

const FEATURED_AGENTS = [
  {
    id: "M2_financial_quality",
    code: "M2",
    name: "财务质量",
    emoji: "🧮",
    desc: "盈利能力、现金流、造假信号",
    color: "from-emerald-500 to-teal-600",
  },
  {
    id: "M4_valuation",
    code: "M4",
    name: "现金流估值",
    emoji: "💹",
    desc: "多模型 DCF 估值与区间",
    color: "from-sky-500 to-blue-600",
  },
  {
    id: "M8_safety_margin",
    code: "M8",
    name: "安全边际",
    emoji: "🛡️",
    desc: "估值与价格的缓冲测算",
    color: "from-amber-500 to-orange-600",
  },
];

export default function DashboardPage() {
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      {/* Hero */}
      <section className="relative overflow-hidden rounded-2xl border bg-gradient-to-br from-emerald-50 via-white to-teal-50 px-6 py-10 dark:from-emerald-950/40 dark:via-card dark:to-teal-950/30">
        <div className="pointer-events-none absolute inset-0 bg-grid-faint [mask-image:radial-gradient(ellipse_at_top,black,transparent_65%)]" />
        <div className="relative flex flex-col items-start gap-4">
          <Badge
            variant="outline"
            className="border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300"
          >
            <LineChart className="mr-1 size-3.5" />
            A 股价值投资分析平台
          </Badge>
          <h1 className="max-w-2xl text-3xl font-semibold tracking-tight md:text-4xl">
            用可验证的智能体工作流，
            <span className="text-emerald-600 dark:text-emerald-400">
              审视每一笔投资
            </span>
          </h1>
          <p className="max-w-xl text-sm leading-6 text-muted-foreground md:text-base">
            输入公司代码，自动产出财务质量、估值、安全边际与风险清单完整备忘录。
            11 个专业智能体，自由编排工作流，支持自定义 LLM 服务商。
          </p>
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Button asChild size="lg" className="rounded-xl">
              <Link href="/workflows">
                发起分析 <ArrowRight className="size-4" />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline" className="rounded-xl">
              <Link href="/agents">浏览智能体</Link>
            </Button>
            <Button asChild variant="ghost" size="lg" className="rounded-xl">
              <Link href="/settings/llm">配置 LLM</Link>
            </Button>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4">
        {STATS.map((stat) => (
          <Card key={stat.label} className="rounded-xl">
            <CardContent className="flex items-center gap-3 p-4 md:p-5">
              <div className="flex size-10 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600 dark:bg-emerald-950/60 dark:text-emerald-400">
                <stat.icon className="size-5" />
              </div>
              <div>
                <div className="text-2xl font-semibold tabular-nums">
                  {stat.value}
                </div>
                <div className="text-xs text-muted-foreground">
                  {stat.label}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </section>

      {/* Quick actions + recent */}
      <section className="grid gap-4 md:grid-cols-2">
        <Card className="rounded-xl">
          <CardHeader>
            <CardTitle className="text-base">快捷分析</CardTitle>
            <CardDescription>选择一个工作流开始新的分析会话</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <Link
              href="/workflows/default"
              className="group flex items-center justify-between rounded-xl border p-4 transition-colors hover:border-emerald-300 hover:bg-emerald-50/50 dark:hover:border-emerald-700 dark:hover:bg-emerald-950/30"
            >
              <div className="flex items-center gap-3">
                <div className="flex size-10 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600 dark:bg-emerald-950/60 dark:text-emerald-400">
                  <FileSearch className="size-5" />
                </div>
                <div>
                  <div className="text-sm font-medium">标准价值投资分析</div>
                  <div className="text-xs text-muted-foreground">
                    M1 → M11 全链路
                  </div>
                </div>
              </div>
              <ArrowRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-emerald-600" />
            </Link>
            <Link
              href="/workflows/quick"
              className="group flex items-center justify-between rounded-xl border p-4 transition-colors hover:border-emerald-300 hover:bg-emerald-50/50 dark:hover:border-emerald-700 dark:hover:bg-emerald-950/30"
            >
              <div className="flex items-center gap-3">
                <div className="flex size-10 items-center justify-center rounded-lg bg-amber-50 text-amber-600 dark:bg-amber-950/60 dark:text-amber-400">
                  <ShieldCheck className="size-5" />
                </div>
                <div>
                  <div className="text-sm font-medium">快速估值流</div>
                  <div className="text-xs text-muted-foreground">
                    M2 → M4 → M8 快速筛查
                  </div>
                </div>
              </div>
              <ArrowRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-emerald-600" />
            </Link>
          </CardContent>
        </Card>

        <Card className="rounded-xl">
          <CardHeader>
            <CardTitle className="text-base">最近会话</CardTitle>
            <CardDescription>继续上次的分析或查看历史记录</CardDescription>
          </CardHeader>
          <CardContent className="flex min-h-40 flex-col items-center justify-center gap-3 rounded-xl border border-dashed text-center">
            <div className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
              <History className="size-6" />
            </div>
            <div>
              <p className="text-sm font-medium">还没有对话记录</p>
              <p className="text-xs text-muted-foreground">
                完成一次分析后，会话会出现在这里
              </p>
            </div>
            <Button asChild variant="outline" size="sm" className="rounded-lg">
              <Link href="/conversations">查看全部</Link>
            </Button>
          </CardContent>
        </Card>
      </section>

      {/* Featured agents */}
      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">常用智能体</h2>
          <Button asChild variant="ghost" size="sm" className="rounded-lg">
            <Link href="/agents">
              全部智能体 <ArrowRight className="ml-1 size-3.5" />
            </Link>
          </Button>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          {FEATURED_AGENTS.map((agent) => (
            <Card
              key={agent.id}
              className="group cursor-pointer rounded-xl transition-all hover:-translate-y-0.5 hover:shadow-md"
            >
              <CardContent className="flex items-start gap-3 p-4">
                <div
                  className={`flex size-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br text-lg text-white shadow-sm ${agent.color}`}
                >
                  {agent.emoji}
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium">
                      {agent.name}
                    </span>
                    <Badge
                      variant="secondary"
                      className="rounded-md px-1.5 py-0 text-[10px]"
                    >
                      {agent.code}
                    </Badge>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {agent.desc}
                  </p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Footer note */}
      <p className="flex items-center justify-center gap-1.5 pb-4 text-xs text-muted-foreground">
        <CircleDollarSign className="size-3.5" />
        Value Agent · 数据源 BaoStock / AkShare · 免费额度内运行
      </p>
    </div>
  );
}
