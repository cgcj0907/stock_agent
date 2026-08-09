import Link from "next/link";
import { AlertCircle } from "lucide-react";

import { LoginForm } from "@/components/auth/login-form";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ redirectTo?: string; error?: string }>;
}) {
  const { redirectTo, error } = await searchParams;

  const errorMessage =
    error === "access_denied"
      ? "未获得 Google 授权，已取消登录"
      : error
        ? "登录失败，请重试"
        : null;

  return (
    <Card className="rounded-2xl shadow-sm">
      <CardHeader>
        <CardTitle className="text-xl">欢迎回来</CardTitle>
        <CardDescription>登录后继续你的价值投资分析</CardDescription>
      </CardHeader>
      <CardContent>
        {errorMessage && (
          <div className="mb-4 flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            <span>{errorMessage}</span>
          </div>
        )}
        <LoginForm redirectTo={redirectTo} />
      </CardContent>
      <CardFooter className="justify-center border-t pt-4 text-sm text-muted-foreground">
        还没有账号？{" "}
        <Link
          href="/register"
          className="ml-1 font-medium text-emerald-600 underline-offset-4 hover:underline dark:text-emerald-400"
        >
          立即注册
        </Link>
      </CardFooter>
    </Card>
  );
}
