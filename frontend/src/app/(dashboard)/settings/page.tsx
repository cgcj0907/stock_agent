import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowRight, UserRound } from "lucide-react";

import { LlmSettingsClient } from "./llm/llm-settings-client";
import { listLlmSettings } from "@/lib/llm/settings";
import { getCurrentUser } from "@/lib/supabase/auth";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default async function SettingsPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/login");

  let settings: Awaited<ReturnType<typeof listLlmSettings>> = [];
  try {
    settings = await listLlmSettings(user.id);
  } catch {
    // 表尚未创建时静默降级为空列表（页面会提示添加）
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">通用设置</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          管理账户与分析偏好
        </p>
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
        <LlmSettingsClient initialSettings={settings} embedded />
        <Card className="rounded-2xl">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <UserRound className="size-4 text-emerald-600 dark:text-emerald-400" />
              个人资料
            </CardTitle>
            <CardDescription>维护投资者画像、教育背景与资金档位</CardDescription>
          </CardHeader>
          <CardContent>
            <Link
              href="/settings/profile"
              className="group inline-flex items-center gap-1 text-sm font-medium text-emerald-600 underline-offset-4 hover:underline dark:text-emerald-400"
            >
              去填写
              <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
