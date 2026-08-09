"use client";

import { createBrowserClient } from "@supabase/ssr";

/**
 * 浏览器端 Supabase 客户端。
 * 使用 PKCE flow：OAuth（Google 登录）与邮箱确认回调都以 `?code=`
 * 形式回跳，由 /auth/callback 统一兑换会话，避免 token 暴露在 URL hash。
 */
export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
    { auth: { flowType: "pkce" } }
  );
}
