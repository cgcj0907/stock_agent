import Link from "next/link";
import { ArrowRight, Cpu, UserRound } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function SettingsPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">通用设置</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          管理账户与分析偏好
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card className="rounded-2xl">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Cpu className="size-4 text-emerald-600 dark:text-emerald-400" />
              LLM 服务商
            </CardTitle>
            <CardDescription>配置分析所用的大模型服务商与 Key</CardDescription>
          </CardHeader>
          <CardContent>
            <Link
              href="/settings/llm"
              className="group inline-flex items-center gap-1 text-sm font-medium text-emerald-600 underline-offset-4 hover:underline dark:text-emerald-400"
            >
              去配置
              <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
          </CardContent>
        </Card>

        <Card className="rounded-2xl opacity-60">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <UserRound className="size-4 text-emerald-600 dark:text-emerald-400" />
              个人资料
            </CardTitle>
            <CardDescription>昵称与头像（M2 后续迭代）</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">即将上线</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
