"use client";

import { Copy, Download, Printer } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

/** 备忘录分享/打印操作：复制 Markdown、导出 .md、打印 / 导出 PDF。 */
export function MemoShareActions({
  markdown,
  fileName,
}: {
  markdown: string;
  fileName: string;
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
      <Button variant="outline" size="sm" onClick={copy} className="rounded-lg">
        <Copy className="size-3.5" />
        复制 Markdown
      </Button>
      <Button variant="outline" size="sm" onClick={download} className="rounded-lg">
        <Download className="size-3.5" />
        导出 .md
      </Button>
      <Button variant="outline" size="sm" onClick={() => window.print()} className="rounded-lg">
        <Printer className="size-3.5" />
        打印 / PDF
      </Button>
    </div>
  );
}
