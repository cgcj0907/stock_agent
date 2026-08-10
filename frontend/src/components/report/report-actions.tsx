"use client";

import { ArrowLeft, Printer } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

/** 分析报告操作栏：返回对话 + 导出 PDF / 打印（打印时隐藏）。 */
export function ReportActions({ conversationId }: { conversationId: string }) {
  return (
    <div className="flex flex-wrap items-center gap-2 print:hidden">
      <Button variant="ghost" size="sm" asChild className="rounded-lg">
        <Link href={`/conversations/${conversationId}`}>
          <ArrowLeft className="size-3.5" />
          返回对话
        </Link>
      </Button>
      <Button size="sm" onClick={() => window.print()} className="rounded-lg">
        <Printer className="size-3.5" />
        导出 PDF / 打印
      </Button>
    </div>
  );
}
