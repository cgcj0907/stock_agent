"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import { Search } from "lucide-react";

import { Breadcrumb, BreadcrumbItem, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from "@/components/ui/breadcrumb";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import { Input } from "@/components/ui/input";
import { ThemeToggle } from "@/components/theme-toggle";

const TITLES: Record<string, string> = {
  "/": "仪表盘",
  "/agents": "智能体广场",
  "/workflows": "工作流",
  "/conversations": "对话记录",
  "/settings": "通用设置",
  "/settings/llm": "LLM 配置",
};

export function AppHeader() {
  const pathname = usePathname();
  // 二级页面（详情页）取父级标题，其余取完整匹配
  const keys = Object.keys(TITLES).sort((a, b) => b.length - a.length);
  const matched = keys.find(
    (k) => pathname === k || pathname.startsWith(`${k}/`)
  );
  const title = TITLES[matched ?? "/"];

  return (
    <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center gap-3 border-b bg-background/80 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="h-4" />
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbPage className="font-medium">{title}</BreadcrumbPage>
          </BreadcrumbItem>
          {matched && pathname !== matched && (
            <>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage className="text-muted-foreground">
                  {pathname.split("/").filter(Boolean).at(-1)}
                </BreadcrumbPage>
              </BreadcrumbItem>
            </>
          )}
        </BreadcrumbList>
      </Breadcrumb>
      <div className="ml-auto flex items-center gap-2">
        <div className="relative hidden md:block">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="搜索公司 / 会话…"
            className="h-8 w-56 rounded-lg bg-muted/50 pl-8 text-sm focus-visible:ring-ring/40"
          />
        </div>
        <ThemeToggle />
      </div>
    </header>
  );
}
