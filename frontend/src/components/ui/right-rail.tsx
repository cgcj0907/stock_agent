"use client";

import * as React from "react";
import { ChevronsLeft, ChevronsRight } from "lucide-react";
import { motion } from "motion/react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const RIGHT_RAIL_STORAGE_KEY = "right_rail_state";

type RightRailContextValue = {
  open: boolean;
  setOpen: (open: boolean) => void;
  toggle: () => void;
};

const RightRailContext = React.createContext<RightRailContextValue | null>(null);

/** 折叠偏好外部存储：localStorage + 跨标签页同步。 */
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
}

/** 读取用户折叠偏好；服务端（SSR）恒返回 true，保证首帧与服务器 HTML 一致。 */
function readStoredOpen(): boolean {
  if (typeof window === "undefined") return true;
  try {
    return window.localStorage.getItem(RIGHT_RAIL_STORAGE_KEY) !== "collapsed";
  } catch {
    return true;
  }
}

function subscribe(callback: () => void) {
  listeners.add(callback);
  window.addEventListener("storage", callback);
  return () => {
    listeners.delete(callback);
    window.removeEventListener("storage", callback);
  };
}

export function RightRailProvider({ children }: { children: React.ReactNode }) {
  // useSyncExternalStore：水合期间使用服务端快照（展开），水合后再同步 localStorage，
  // 避免「服务端展开 / 客户端折叠」导致的 hydration mismatch。
  const open = React.useSyncExternalStore(subscribe, readStoredOpen, () => true);

  const setOpen = React.useCallback((nextOpen: boolean) => {
    try {
      window.localStorage.setItem(
        RIGHT_RAIL_STORAGE_KEY,
        nextOpen ? "expanded" : "collapsed",
      );
    } catch {
      // 隐私模式等写入失败时忽略
    }
    emit();
  }, []);

  const toggle = React.useCallback(() => {
    setOpen(!readStoredOpen());
  }, [setOpen]);

  const value = React.useMemo(
    () => ({ open, setOpen, toggle }),
    [open, setOpen, toggle],
  );

  return (
    <RightRailContext.Provider value={value}>{children}</RightRailContext.Provider>
  );
}

export function useRightRail() {
  const context = React.useContext(RightRailContext);
  if (!context) {
    throw new Error("useRightRail must be used within RightRailProvider.");
  }
  return context;
}

export function RightRailShell({
  children,
  className,
  contentClassName,
  collapsedContent,
}: {
  children: React.ReactNode;
  className?: string;
  contentClassName?: string;
  /** 折叠态展示的迷你信息（如状态点 + 总分） */
  collapsedContent?: React.ReactNode;
}) {
  const { open, toggle } = useRightRail();

  // sticky 必须放在作为 flex 子项的 <aside> 上（相对整行高度固定），
  // 放在内层 div 时父容器高度只有内容高，sticky 无可移动空间，滚动时右栏会随页面滚走。
  return (
    <aside
      className={cn(
        "hidden w-full lg:flex lg:shrink-0 lg:flex-col lg:sticky lg:top-20 lg:max-h-[calc(100vh_-_5rem)] lg:overscroll-contain",
        open ? "lg:w-80" : "lg:w-12",
        className,
      )}
    >
      {/* 顶部分割线 + 折叠按钮（固定在顶部，不随内容滚动） */}
      <div
        className={cn(
          "flex border-t border-border/60 pt-3 lg:border-t-0 lg:border-l lg:pl-4",
          open ? "mb-3 justify-start lg:pr-1" : "justify-center",
        )}
      >
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="size-8 rounded-full"
          onClick={toggle}
          aria-label={open ? "收起右侧栏" : "展开右侧栏"}
          title={open ? "收起右侧栏" : "展开右侧栏"}
        >
          {open ? <ChevronsRight className="size-4" /> : <ChevronsLeft className="size-4" />}
        </Button>
      </div>

      {open ? (
        <motion.div
          initial={{ opacity: 0, x: 6 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.18, ease: "easeOut" }}
          className={cn(
            "min-h-0 flex-1 overflow-y-auto overscroll-contain pb-3 lg:border-l lg:pl-4 lg:pr-1",
            contentClassName,
          )}
        >
          {children}
        </motion.div>
      ) : collapsedContent ? (
        <div className="flex flex-col items-center gap-1 lg:border-l lg:pl-4">
          {collapsedContent}
        </div>
      ) : null}
    </aside>
  );
}
