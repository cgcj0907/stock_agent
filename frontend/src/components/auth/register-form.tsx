"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Loader2, MailCheck } from "lucide-react";
import { toast } from "sonner";

import { createClient } from "@/lib/supabase/client";
import { GoogleLoginButton } from "@/components/auth/google-login-button";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";

export function RegisterForm() {
  const router = useRouter();
  const [name, setName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [submitted, setSubmitted] = React.useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    const supabase = createClient();
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: { display_name: name },
        emailRedirectTo: `${window.location.origin}/auth/callback?next=/`,
      },
    });
    if (error) {
      toast.error(error.message || "注册失败");
      setLoading(false);
      return;
    }
    if (data.session) {
      // 项目关闭了邮箱确认：直接登录成功
      toast.success("注册成功");
      router.push("/");
      router.refresh();
      return;
    }
    // 需要邮箱确认
    setSubmitted(true);
    setLoading(false);
  }

  if (submitted) {
    return (
      <div className="flex flex-col items-center gap-3 py-6 text-center">
        <div className="flex size-12 items-center justify-center rounded-full bg-emerald-50 text-emerald-600 dark:bg-emerald-950/60 dark:text-emerald-400">
          <MailCheck className="size-6" />
        </div>
        <p className="text-sm font-medium">确认邮件已发送</p>
        <p className="text-sm text-muted-foreground">
          请前往 {email} 查收邮件并点击确认链接完成注册。
        </p>
        <Button
          variant="outline"
          size="sm"
          className="rounded-lg"
          onClick={() => setSubmitted(false)}
        >
          返回修改
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <GoogleLoginButton redirectTo="/" label="使用 Google 注册" />

      <div className="flex items-center gap-3">
        <Separator className="flex-1" />
        <span className="text-xs text-muted-foreground">或使用邮箱注册</span>
        <Separator className="flex-1" />
      </div>

      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <Label htmlFor="name">昵称</Label>
          <Input
            id="name"
            type="text"
            placeholder="如何称呼你"
            autoComplete="nickname"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="email">邮箱</Label>
          <Input
            id="email"
            type="email"
            placeholder="you@example.com"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="password">密码</Label>
          <Input
            id="password"
            type="password"
            placeholder="至少 6 位"
            autoComplete="new-password"
            required
            minLength={6}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <Button type="submit" disabled={loading} className="rounded-xl">
          {loading && <Loader2 className="size-4 animate-spin" />}
          注册
        </Button>
      </form>
    </div>
  );
}
