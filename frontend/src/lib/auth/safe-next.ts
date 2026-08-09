/**
 * 认证回调回跳地址白名单：只允许站内相对路径，
 * 拒绝外部 URL 与协议相对地址（如 `//evil.com`），避免异常回跳。
 */
export function safeNext(next: string | null | undefined): string {
  if (!next) return "/";
  if (!next.startsWith("/") || next.startsWith("//")) return "/";
  return next;
}
