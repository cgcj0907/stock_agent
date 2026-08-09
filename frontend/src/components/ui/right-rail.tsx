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

export function RightRailProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpenState] = React.useState(() => {
    if (typeof window === "undefined") return true;
    return window.localStorage.getItem(RIGHT_RAIL_STORAGE_KEY) !== "collapsed";
  });

  const setOpen = React.useCallback((nextOpen: boolean) => {
    setOpenState(nextOpen);
    window.localStorage.setItem(
      RIGHT_RAIL_STORAGE_KEY,
      nextOpen ? "expanded" : "collapsed",
    );
  }, []);

  const toggle = React.useCallback(() => {
    setOpen(!open);
  }, [open, setOpen]);

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

  return (
    <aside
      className={cn(
        "hidden w-full lg:block lg:shrink-0",
        open ? "lg:w-80" : "lg:w-12",
        className,
      )}
    >
      <div
        className={cn(
          "border-t border-border/60 pt-3 lg:border-t-0 lg:border-l lg:pl-4",
          open && "lg:pr-1",
        )}
      >
        <div className={cn("flex", open ? "mb-3 justify-start" : "justify-center")}>
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
              "lg:sticky lg:top-20 lg:max-h-[calc(100vh_-_5rem)] lg:overflow-y-auto lg:overscroll-contain lg:pb-3",
              contentClassName,
            )}
          >
            {children}
          </motion.div>
        ) : collapsedContent ? (
          <div className="flex flex-col items-center gap-1">{collapsedContent}</div>
        ) : null}
      </div>
    </aside>
  );
}
