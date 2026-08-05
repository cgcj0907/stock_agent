import Link from "next/link";
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
  const { redirectTo } = await searchParams;

  return (
    <Card className="rounded-2xl shadow-sm">
      <CardHeader>
        <CardTitle className="text-xl">欢迎回来</CardTitle>
        <CardDescription>登录后继续你的价值投资分析</CardDescription>
      </CardHeader>
      <CardContent>
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
