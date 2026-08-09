"use client";

import * as React from "react";
import {
  Box,
  Bot,
  CloudSun,
  Crown,
  Loader2,
  Pencil,
  PlugZap,
  Plus,
  Settings2,
  Sparkles,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { LlmFormDialog } from "@/components/settings/llm-form-dialog";
import { getProvider } from "@/lib/llm/providers";
import type { LlmSetting } from "@/types/llm";

const PROVIDER_VISUAL: Record<
  string,
  { icon: React.ComponentType<{ className?: string }>; gradient: string }
> = {
  deepseek: { icon: Bot, gradient: "from-blue-500 to-indigo-600" },
  openai: { icon: Sparkles, gradient: "from-emerald-500 to-teal-600" },
  qwen: { icon: CloudSun, gradient: "from-violet-500 to-purple-600" },
  ollama: { icon: Box, gradient: "from-orange-500 to-amber-600" },
  custom: { icon: Settings2, gradient: "from-slate-500 to-slate-700" },
};

export function LlmSettingsClient({
  initialSettings,
  embedded = false,
}: {
  initialSettings: LlmSetting[];
  embedded?: boolean;
}) {
  const [settings, setSettings] = React.useState<LlmSetting[]>(initialSettings);
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<LlmSetting | null>(null);
  const [testingId, setTestingId] = React.useState<string | null>(null);

  async function refresh() {
    const res = await fetch("/api/llm-settings");
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "加载失败");
    setSettings(data.settings ?? []);
  }

  async function handleSetDefault(item: LlmSetting) {
    const res = await fetch(`/api/llm-settings/${item.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_default: true }),
    });
    const data = await res.json();
    if (!res.ok) {
      toast.error(data.error || "设置失败");
      return;
    }
    toast.success(
      `已将 ${item.name || getProvider(item.provider).label} 设为默认`
    );
    await refresh();
  }

  async function handleDelete(item: LlmSetting) {
    if (
      !window.confirm(
        `确定删除「${item.name || getProvider(item.provider).label}」？`
      )
    ) {
      return;
    }
    const res = await fetch(`/api/llm-settings/${item.id}`, {
      method: "DELETE",
    });
    const data = await res.json();
    if (!res.ok) {
      toast.error(data.error || "删除失败");
      return;
    }
    toast.success("已删除");
    await refresh();
  }

  async function handleTest(item: LlmSetting) {
    setTestingId(item.id);
    try {
      const res = await fetch("/api/llm-settings/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: item.id }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "测试失败");
      if (data.ok) {
        toast.success(
          `${item.name || getProvider(item.provider).label} 连接成功（${data.latencyMs}ms）`
        );
      } else {
        toast.error(
          `${item.name || getProvider(item.provider).label}：${data.message}`
        );
      }
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setTestingId(null);
    }
  }

  async function handleSaved() {
    await refresh();
  }

  return (
    <div
      className={
        embedded
          ? "flex flex-col gap-6"
          : "mx-auto flex max-w-5xl flex-col gap-6"
      }
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {embedded ? "LLM 服务商" : "LLM 配置"}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            管理分析所用的 LLM 服务商，Key 加密存储在服务端
          </p>
        </div>
        <Button
          onClick={() => {
            setEditing(null);
            setDialogOpen(true);
          }}
          className="rounded-xl"
        >
          <Plus className="size-4" />
          新增服务商
        </Button>
      </div>

      {settings.length === 0 ? (
        <Card className="rounded-2xl border-dashed">
          <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
            <div className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
              <Settings2 className="size-6" />
            </div>
            <div>
              <p className="text-sm font-medium">还没有配置 LLM 服务商</p>
              <p className="text-xs text-muted-foreground">
                添加 DeepSeek / OpenAI / Qwen 等服务商后即可发起分析
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="rounded-lg"
              onClick={() => {
                setEditing(null);
                setDialogOpen(true);
              }}
            >
              添加第一个服务商
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {settings.map((item) => {
            const preset = getProvider(item.provider);
            const visual =
              PROVIDER_VISUAL[item.provider] ?? PROVIDER_VISUAL.custom;
            const Icon = visual.icon;
            const label = item.name || preset.label;
            return (
              <Card
                key={item.id}
                className="rounded-2xl transition-shadow hover:shadow-md"
              >
                <CardHeader className="flex-row items-start justify-between space-y-0 pb-2">
                  <div className="flex items-center gap-3">
                    <div
                      className={`flex size-10 items-center justify-center rounded-xl bg-gradient-to-br text-white shadow-sm ${visual.gradient}`}
                    >
                      <Icon className="size-5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <CardTitle className="text-base">{label}</CardTitle>
                        {item.is_default && (
                          <Badge className="gap-1 rounded-md bg-emerald-600 text-white">
                            <Crown className="size-3" />
                            默认
                          </Badge>
                        )}
                      </div>
                      <CardDescription className="text-xs">
                        {preset.label}
                      </CardDescription>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <Badge
                      variant="secondary"
                      className="rounded-md font-mono"
                    >
                      {item.model}
                    </Badge>
                    <span className="max-w-[180px] truncate text-muted-foreground">
                      {item.base_url}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span className="font-mono">
                      {item.api_key_masked ?? "未配置 Key"}
                    </span>
                    {item.provider === "ollama" && (
                      <span className="text-emerald-600 dark:text-emerald-400">
                        本地模式
                      </span>
                    )}
                  </div>
                  <div className="mt-1 flex items-center gap-1">
                    {!item.is_default && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="rounded-lg text-xs"
                        onClick={() => handleSetDefault(item)}
                      >
                        <Crown className="size-3.5" />
                        设为默认
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      className="rounded-lg text-xs"
                      onClick={() => handleTest(item)}
                      disabled={testingId === item.id}
                    >
                      {testingId === item.id ? (
                        <Loader2 className="size-3.5 animate-spin" />
                      ) : (
                        <PlugZap className="size-3.5" />
                      )}
                      测试
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="rounded-lg text-xs"
                      onClick={() => {
                        setEditing(item);
                        setDialogOpen(true);
                      }}
                    >
                      <Pencil className="size-3.5" />
                      编辑
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="ml-auto rounded-lg text-xs text-destructive hover:text-destructive"
                      onClick={() => handleDelete(item)}
                    >
                      <Trash2 className="size-3.5" />
                      删除
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <LlmFormDialog
        open={dialogOpen}
        editing={editing}
        onOpenChange={setDialogOpen}
        onSaved={handleSaved}
      />
    </div>
  );
}
