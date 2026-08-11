"use client";

import { ArrowLeft, Copy, Download, Printer } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

/**
 * 分析报告操作栏（打印时隐藏）：
 * 返回对话 + 复制 Markdown / 导出 .md（备忘录有 Markdown 时）+ 导出 PDF / 打印。
 * 统一作为「导出报告」的唯一入口，避免与备忘录页按钮重复。
 */
export function ReportActions({
  conversationId,
  markdown = "",
  fileName = "分析报告",
}: {
  conversationId: string;
  markdown?: string;
  fileName?: string;
}) {
  async function copy() {
    try {
      await navigator.clipboard.writeText(markdown);
      toast.success("已复制 Markdown");
    } catch {
      toast.error("复制失败，请手动选择复制");
    }
  }

  function download() {
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${fileName}.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex flex-wrap items-center gap-2 print:hidden">
      <Button variant="ghost" size="sm" asChild className="rounded-lg">
        <Link href={`/conversations/${conversationId}`}>
          <ArrowLeft className="size-3.5" />
          返回对话
        </Link>
      </Button>
      {markdown && (
        <>
          <Button variant="outline" size="sm" onClick={copy} className="rounded-lg">
            <Copy className="size-3.5" />
            复制 Markdown
          </Button>
          <Button variant="outline" size="sm" onClick={download} className="rounded-lg">
            <Download className="size-3.5" />
            导出 .md
          </Button>
        </>
      )}
      <Button size="sm" onClick={() => window.print()} className="rounded-lg">
        <Printer className="size-3.5" />
        导出 PDF / 打印
      </Button>
    </div>
  );
}
