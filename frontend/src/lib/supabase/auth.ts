import { createClient } from "@/lib/supabase/server";

/** 服务端获取当前登录用户；未登录返回 null */
export async function getCurrentUser() {
  const supabase = await createClient();
  const {
    data: { user },
    error,
  } = await supabase.auth.getUser();
  if (error || !user) return null;
  return user;
}
