"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import { motion } from "motion/react";

/** 路由切换时主内容淡入 + 轻微上移（Motion 动效体系 P2）。 */
export function PageTransition({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <motion.div
      key={pathname}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}
