import { createClient } from "@/lib/supabase/server";

/**
 * 服务端调用 FC 后端时附加 Supabase 登录 token（后端 /api/* 全局鉴权）。
 * 未登录 / 取不到会话时返回空头（后端会 401，由调用方处理）。
 */
export async function backendAuthHeaders(): Promise<Record<string, string>> {
  try {
    const supabase = await createClient();
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    return {};
  }
}
