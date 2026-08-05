"use client";

import * as React from "react";
import { Star } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

export function FavoriteButton({
  agentId,
  initial,
}: {
  agentId: string;
  initial: boolean;
}) {
  const [favorite, setFavorite] = React.useState(initial);
  const [busy, setBusy] = React.useState(false);

  async function toggle(e?: React.MouseEvent) {
    e?.preventDefault();
    e?.stopPropagation();
    setBusy(true);
    try {
      const res = await fetch("/api/agent-favorites", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_id: agentId, favorite: !favorite }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "操作失败");
      setFavorite(!favorite);
      toast.success(!favorite ? "已收藏" : "已取消收藏");
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className="size-8 rounded-lg"
      onClick={toggle}
      disabled={busy}
      aria-label={favorite ? "取消收藏" : "收藏"}
    >
      <Star
        className={`size-4 ${
          favorite
            ? "fill-amber-400 text-amber-400"
            : "text-muted-foreground"
        }`}
      />
    </Button>
  );
}
