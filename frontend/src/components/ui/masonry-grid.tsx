"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

/** 客户端挂载检测：服务端/水合首帧返回 false，水合完成后返回 true。 */
function useIsClient(): boolean {
  return React.useSyncExternalStore(
    () => () => {},
    () => true,
    () => false
  );
}

/**
 * 瀑布流网格：按每张卡片的实际高度把子项分配到当前最短的列，
 * 保持从左到右的阅读顺序，卡片高度变化（展开/收起、数据加载、窗口缩放）时自动重新平衡。
 *
 * - 列数根据容器宽度自动计算（`minColumnWidth` 决定换列阈值，`maxColumns` 封顶）
 * - 挂载前回退为普通纵向排列，避免服务端渲染时绝对定位导致卡片重叠
 */
export function MasonryGrid({
  children,
  className,
  gap = 16,
  minColumnWidth = 340,
  maxColumns = 3,
}: {
  children: React.ReactNode;
  className?: string;
  gap?: number;
  minColumnWidth?: number;
  maxColumns?: number;
}) {
  const items = React.Children.toArray(children);
  const containerRef = React.useRef<HTMLDivElement>(null);
  const itemRefs = React.useRef<Array<HTMLDivElement | null>>([]);
  const isClient = useIsClient();

  const [width, setWidth] = React.useState(0);
  const [heights, setHeights] = React.useState<number[]>(() =>
    items.map(() => 0)
  );

  // 监听容器宽度，决定列数
  React.useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => setWidth(el.clientWidth);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const columns = React.useMemo(() => {
    if (!isClient || width <= 0) return 1;
    const n = Math.floor((width + gap) / (minColumnWidth + gap));
    return Math.max(1, Math.min(n, maxColumns));
  }, [isClient, width, gap, minColumnWidth, maxColumns]);

  // 监听每张卡片的高度，高度变化时重新平衡
  React.useLayoutEffect(() => {
    const els = itemRefs.current.filter(
      (el): el is HTMLDivElement => el !== null
    );
    if (!isClient || els.length === 0) return;
    const observer = new ResizeObserver((entries) => {
      setHeights((prev) => {
        let next: number[] | null = null;
        for (const entry of entries) {
          const index = Number((entry.target as HTMLElement).dataset.index);
          if (!Number.isFinite(index)) continue;
          const height = entry.contentRect.height;
          if (!next) next = [...prev];
          if (next[index] !== height) next[index] = height;
        }
        return next ?? prev;
      });
    });
    els.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [isClient, items.length]);

  const itemWidth =
    isClient && width > 0 ? (width - gap * (columns - 1)) / columns : 0;

  // 贪心分配：依次把卡片放进当前最短的列，保持阅读顺序
  const { positions, totalHeight } = React.useMemo(() => {
    const columnTops = new Array<number>(columns).fill(0);
    const positions = Array.from({ length: items.length }, (_, i) => {
      const col = columnTops.indexOf(Math.min(...columnTops));
      const top = columnTops[col];
      columnTops[col] = top + (heights[i] ?? 0) + gap;
      return { col, top };
    });
    const totalHeight =
      Math.max(0, ...columnTops) - (items.length > 0 ? gap : 0);
    return { positions, totalHeight };
  }, [items.length, columns, heights, gap]);

  return (
    <div
      ref={containerRef}
      className={cn("relative", !isClient && "flex flex-col", className)}
      style={isClient ? { height: totalHeight, gap } : { gap }}
    >
      {items.map((child, i) => {
        const key =
          React.isValidElement(child) && child.key != null ? child.key : i;
        const pos = positions[i];
        return (
          <div
            key={key}
            ref={(el) => {
              itemRefs.current[i] = el;
            }}
            data-index={i}
            className={cn("min-w-0", isClient && "absolute top-0 left-0")}
            style={
              isClient
                ? {
                    width: itemWidth,
                    transform: `translate(${pos.col * (itemWidth + gap)}px, ${pos.top}px)`,
                  }
                : undefined
            }
          >
            {child}
          </div>
        );
      })}
    </div>
  );
}
