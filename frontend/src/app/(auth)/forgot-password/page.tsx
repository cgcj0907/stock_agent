import Link from "next/link";
import { ForgotPasswordForm } from "@/components/auth/forgot-password-form";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function ForgotPasswordPage() {
  return (
    <Card className="rounded-2xl shadow-sm">
      <CardHeader>
        <CardTitle className="text-xl">重置密码</CardTitle>
        <CardDescription>
          输入注册邮箱，我们将发送重置链接
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ForgotPasswordForm />
      </CardContent>
      <CardFooter className="justify-center border-t pt-4 text-sm text-muted-foreground">
        想起密码了？{" "}
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
