"use client";

import * as React from "react";
import { motion } from "motion/react";

/** 结果卡入场：逐个淡入 + 上移，卡片高度由子内容决定（适合瀑布流测量）。 */
export function CardEntrance({
  children,
  index = 0,
}: {
  children: React.ReactNode;
  index?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut", delay: Math.min(index * 0.04, 0.3) }}
    >
      {children}
    </motion.div>
  );
}
