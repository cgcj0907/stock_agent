import { NextResponse, type NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/middleware";

/** 公开路径：无需登录即可访问（认证相关页面） */
const PUBLIC_PATHS = ["/login", "/register", "/forgot-password", "/auth"];

export async function proxy(request: NextRequest) {
  const { supabaseResponse, user } = await updateSession(request);
  const { pathname } = request.nextUrl;
  const url = request.nextUrl.clone();

  const isPublic = PUBLIC_PATHS.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`)
  );
  // API 路由不重定向：由 Route Handler 自行返回 401 JSON
  const isApi = pathname.startsWith("/api");

  // 未登录 → 跳转登录页（带回跳地址）
  if (!user && !isPublic && !isApi) {
    url.pathname = "/login";
    url.searchParams.set("redirectTo", pathname);
    return NextResponse.redirect(url);
  }

  // 已登录访问认证页 → 回首页
  if (user && isPublic) {
    url.pathname = "/";
    url.search = "";
    return NextResponse.redirect(url);
  }

  return supabaseResponse;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};
