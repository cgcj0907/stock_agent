"use client";

import * as React from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";

function GoogleIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={className}>
      <path
        fill="#4285F4"
        d="M23.49 12.27c0-.79-.07-1.54-.19-2.27H12v4.51h6.47c-.29 1.48-1.14 2.73-2.4 3.58v3h3.86c2.26-2.09 3.56-5.17 3.56-8.82Z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.86-3c-1.08.72-2.45 1.16-4.07 1.16-3.13 0-5.78-2.11-6.73-4.96H1.29v3.09C3.26 21.3 7.31 24 12 24Z"
      />
      <path
        fill="#FBBC05"
        d="M5.27 14.29c-.25-.72-.38-1.49-.38-2.29s.14-1.57.38-2.29V6.62H1.29A11.86 11.86 0 0 0 0 12c0 1.94.47 3.76 1.29 5.38l3.98-3.09Z"
      />
      <path
        fill="#EA4335"
        d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.31 0 3.26 2.7 1.29 6.62l3.98 3.09c.95-2.85 3.6-4.96 6.73-4.96Z"
      />
    </svg>
  );
}

/**
 * Google OAuth 登录按钮：调用 Supabase signInWithOAuth（PKCE），
 * 回跳 /auth/callback 兑换会话。首次登录会自动创建账号（注册与登录共用）。
 */
export function GoogleLoginButton({
  redirectTo,
  label = "使用 Google 登录",
}: {
  redirectTo?: string;
  label?: string;
}) {
  const [loading, setLoading] = React.useState(false);

  async function handleGoogleLogin() {
    setLoading(true);
    const supabase = createClient();
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/auth/callback?next=${
          encodeURIComponent(redirectTo || "/")
        }`,
      },
    });
    if (error) {
      toast.error(error.message || "Google 登录失败，请稍后重试");
      setLoading(false);
    }
    // 成功时浏览器会自动跳转到 Google 授权页，无需手动处理
  }

  return (
    <Button
      type="button"
      variant="outline"
      onClick={handleGoogleLogin}
      disabled={loading}
      className="w-full rounded-xl"
    >
      {loading ? (
        <Loader2 className="size-4 animate-spin" />
      ) : (
        <GoogleIcon className="size-4" />
      )}
      {label}
    </Button>
  );
}
