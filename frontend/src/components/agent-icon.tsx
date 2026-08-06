"use client";

import { Bot, type LucideIcon } from "lucide-react";

import { AGENT_ICONS } from "@/lib/agents/catalog";

/** 智能体图标：icon 为 AGENT_ICONS 的 key，缺失时回退 Bot。 */
export function AgentIcon({
  icon,
  className,
}: {
  icon?: string;
  className?: string;
}) {
  const Icon: LucideIcon = (icon ? AGENT_ICONS[icon] : undefined) ?? Bot;
  return <Icon className={className} aria-hidden />;
}
