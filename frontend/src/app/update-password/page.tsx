import { UpdatePasswordForm } from "@/components/auth/update-password-form";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function UpdatePasswordPage() {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-gradient-to-br from-emerald-50 via-background to-teal-50 p-6 dark:from-emerald-950/30 dark:via-background dark:to-teal-950/20">
      <div className="pointer-events-none absolute inset-0 bg-grid-faint [mask-image:radial-gradient(ellipse_at_top,black,transparent_70%)]" />
      <Card className="relative w-full max-w-sm rounded-2xl shadow-sm">
        <CardHeader>
          <CardTitle className="text-xl">设置新密码</CardTitle>
          <CardDescription>密码至少 6 位</CardDescription>
        </CardHeader>
        <CardContent>
          <UpdatePasswordForm />
        </CardContent>
      </Card>
    </div>
  );
}
