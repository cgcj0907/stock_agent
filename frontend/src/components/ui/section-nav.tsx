"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface SectionNavItem {
  id: string;
  label: string;
}

/** 页面内锚点导航：sticky 分段按钮，滚动时高亮当前区块。 */
export function StickySectionNav({ items }: { items: SectionNavItem[] }) {
  const [active, setActive] = React.useState<string | null>(items[0]?.id ?? null);
  // 用稳定 key 作为依赖，避免 items 每次渲染新引用导致 observer 反复重建
  const itemsKey = items.map((i) => i.id).join(",");

  React.useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActive(entry.target.id);
        }
      },
      { rootMargin: "-15% 0px -70% 0px", threshold: 0 },
    );
    for (const item of items) {
      const el = document.getElementById(item.id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [itemsKey]);

  function scrollTo(id: string) {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  if (items.length <= 1) return null;

  return (
    <nav
      aria-label="页面导航"
      className="sticky top-14 z-20 -mx-1 flex gap-1 overflow-x-auto rounded-xl border bg-background/80 p-1 backdrop-blur supports-[backdrop-filter]:bg-background/60"
    >
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          onClick={() => scrollTo(item.id)}
          aria-current={active === item.id ? "true" : undefined}
          className={cn(
            "flex-1 whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
            active === item.id
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:bg-muted hover:text-foreground",
          )}
        >
          {item.label}
        </button>
      ))}
    </nav>
  );
}
