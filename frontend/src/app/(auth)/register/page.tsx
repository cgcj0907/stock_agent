import Link from "next/link";
import { RegisterForm } from "@/components/auth/register-form";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function RegisterPage() {
  return (
    <Card className="rounded-2xl shadow-sm">
      <CardHeader>
        <CardTitle className="text-xl">创建账号</CardTitle>
        <CardDescription>注册后即可配置 LLM 并开始分析</CardDescription>
      </CardHeader>
      <CardContent>
        <RegisterForm />
      </CardContent>
      <CardFooter className="justify-center border-t pt-4 text-sm text-muted-foreground">
        已有账号？{" "}
        <Link
          href="/login"
          className="ml-1 font-medium text-emerald-600 underline-offset-4 hover:underline dark:text-emerald-400"
        >
          去登录
        </Link>
      </CardFooter>
    </Card>
  );
}
