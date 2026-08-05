import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

/**
 * 邮箱确认 / 密码重置回调：
 * Supabase 通过 code 跳回本页，交换 code 为会话后跳转到 next。
 */
export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next") ?? "/";

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      return NextResponse.redirect(`${origin}${next}`);
    }
  }

  return NextResponse.redirect(`${origin}/login?error=auth`);
}
