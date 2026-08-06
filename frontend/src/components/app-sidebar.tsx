"use client";

import * as React from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bot,
  Cpu,
  History,
  LayoutDashboard,
  Settings,
  Sparkles,
  Workflow,
} from "lucide-react";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";
import { NavUser } from "@/components/nav-user";

const NAV_GROUPS = [
  {
    label: "总览",
    items: [{ title: "仪表盘", href: "/", icon: LayoutDashboard }],
  },
  {
    label: "智能体",
    items: [
      { title: "智能体广场", href: "/agents", icon: Bot },
      { title: "工作流", href: "/workflows", icon: Workflow },
    ],
  },
  {
    label: "记录",
    items: [{ title: "对话记录", href: "/conversations", icon: History }],
  },
  {
    label: "设置",
    items: [
      { title: "LLM 配置", href: "/settings/llm", icon: Cpu },
      { title: "通用设置", href: "/settings", icon: Settings },
    ],
  },
];

function BrandMark() {
  return (
    <Image
      src="/logo.png"
      alt="Value Agent"
      width={96}
      height={96}
      priority
      className="size-8 shrink-0 rounded-lg object-cover shadow-sm"
    />
  );
}

export function AppSidebar({
  user,
  ...props
}: React.ComponentProps<typeof Sidebar> & {
  user: { name: string; email: string };
}) {
  const pathname = usePathname();

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <Link href="/">
                <BrandMark />
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-semibold">Value Agent</span>
                  <span className="truncate text-xs text-muted-foreground">
                    价值投资智能体
                  </span>
                </div>
                <Sparkles className="ml-auto size-4 text-emerald-600 dark:text-emerald-400" />
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        {NAV_GROUPS.map((group) => (
          <SidebarGroup key={group.label}>
            <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => {
                  const active =
                    item.href === "/"
                      ? pathname === "/"
                      : pathname.startsWith(item.href);
                  return (
                    <SidebarMenuItem key={item.title}>
                      <SidebarMenuButton
                        asChild
                        isActive={active}
                        tooltip={item.title}
                      >
                        <Link href={item.href}>
                          <item.icon />
                          <span>{item.title}</span>
                        </Link>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  );
                })}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>

      <SidebarFooter>
        <NavUser user={user} />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
