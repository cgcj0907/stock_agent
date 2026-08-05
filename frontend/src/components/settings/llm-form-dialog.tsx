"use client";

import * as React from "react";
import { Loader2, PlugZap } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { LLM_PROVIDERS, getProvider } from "@/lib/llm/providers";
import type { LlmSetting, LlmSettingInput } from "@/types/llm";

interface Props {
  open: boolean;
  editing: LlmSetting | null;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}

/** 表单主体：通过 key 重挂载初始化，避免 effect 内 setState */
function LlmFormFields({
  editing,
  onCancel,
  onSaved,
}: {
  editing: LlmSetting | null;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = React.useState<LlmSettingInput>(() => {
    if (editing) {
      return {
        provider: editing.provider,
        name: editing.name,
        base_url: editing.base_url,
        model: editing.model,
        api_key: "",
        is_default: editing.is_default,
      };
    }
    const preset = getProvider("deepseek");
    return {
      provider: preset.id,
      name: "",
      base_url: preset.baseUrl,
      model: preset.models[0] ?? "",
      api_key: "",
      is_default: false,
    };
  });
  const [saving, setSaving] = React.useState(false);
  const [testing, setTesting] = React.useState(false);
  const [testResult, setTestResult] = React.useState<{
    ok: boolean;
    message: string;
    latencyMs?: number;
  } | null>(null);

  const preset = getProvider(form.provider);

  function handleProviderChange(provider: string) {
    const next = getProvider(provider);
    setForm((prev) => ({
      ...prev,
      provider,
      base_url: next.baseUrl,
      model:
        prev.provider === provider && prev.model
          ? prev.model
          : (next.models[0] ?? prev.model),
    }));
  }

  async function handleTest() {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch("/api/llm-settings/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: form.provider,
          base_url: form.base_url,
          model: form.model,
          api_key: form.api_key || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "测试失败");
      setTestResult(data);
    } catch (e) {
      setTestResult({ ok: false, message: (e as Error).message });
    } finally {
      setTesting(false);
    }
  }

  async function handleSave() {
    if (!form.base_url.trim() || !form.model.trim()) {
      toast.error("Base URL 与模型为必填");
      return;
    }
    if (!editing && !form.api_key.trim() && form.provider !== "ollama") {
      toast.error("请填写 API Key");
      return;
    }
    setSaving(true);
    try {
      const url = editing
        ? `/api/llm-settings/${editing.id}`
        : "/api/llm-settings";
      const method = editing ? "PATCH" : "POST";
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "保存失败");
      toast.success(editing ? "配置已更新" : "配置已添加");
      onSaved();
      onCancel();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>{editing ? "编辑服务商" : "新增服务商"}</DialogTitle>
        <DialogDescription>
          配置 LLM 服务商，Key 将加密存储在服务端
        </DialogDescription>
      </DialogHeader>

      <div className="flex flex-col gap-4 py-1">
        <div className="flex flex-col gap-2">
          <Label>服务商</Label>
          <Select value={form.provider} onValueChange={handleProviderChange}>
            <SelectTrigger>
              <SelectValue placeholder="选择服务商" />
            </SelectTrigger>
            <SelectContent>
              {LLM_PROVIDERS.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {preset.note && (
            <p className="text-xs text-muted-foreground">{preset.note}</p>
          )}
        </div>

        <div className="flex flex-col gap-2">
          <Label htmlFor="llm-name">名称（可选）</Label>
          <Input
            id="llm-name"
            placeholder={preset.label}
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </div>

        <div className="flex flex-col gap-2">
          <Label htmlFor="llm-base-url">Base URL</Label>
          <Input
            id="llm-base-url"
            placeholder="https://api.example.com/v1"
            value={form.base_url}
            onChange={(e) => setForm({ ...form, base_url: e.target.value })}
          />
        </div>

        <div className="flex flex-col gap-2">
          <Label htmlFor="llm-model">模型</Label>
          <Input
            id="llm-model"
            list="llm-model-suggestions"
            placeholder="deepseek-chat"
            value={form.model}
            onChange={(e) => setForm({ ...form, model: e.target.value })}
          />
          <datalist id="llm-model-suggestions">
            {preset.models.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
        </div>

        <div className="flex flex-col gap-2">
          <Label htmlFor="llm-api-key">
            API Key{editing ? "（已保存，留空保持不变）" : ""}
          </Label>
          <Input
            id="llm-api-key"
            type="password"
            autoComplete="off"
            placeholder={
              editing
                ? (editing.api_key_masked ?? "••••••••")
                : preset.keyPlaceholder
            }
            value={form.api_key}
            onChange={(e) => setForm({ ...form, api_key: e.target.value })}
          />
        </div>

        <div className="flex items-center justify-between rounded-lg border p-3">
          <div>
            <Label htmlFor="llm-default" className="cursor-pointer">
              设为默认服务商
            </Label>
            <p className="text-xs text-muted-foreground">发起分析时优先使用</p>
          </div>
          <Switch
            id="llm-default"
            checked={form.is_default}
            onCheckedChange={(v) => setForm({ ...form, is_default: v })}
          />
        </div>

        {testResult && (
          <div
            className={`rounded-lg border px-3 py-2 text-sm ${
              testResult.ok
                ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300"
                : "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/60 dark:text-red-300"
            }`}
          >
            {testResult.ok ? "✅" : "❌"} {testResult.message}
            {testResult.latencyMs != null && `（${testResult.latencyMs}ms）`}
          </div>
        )}
      </div>

      <DialogFooter className="gap-2 sm:justify-between">
        <Button
          type="button"
          variant="outline"
          onClick={handleTest}
          disabled={testing || saving}
        >
          {testing ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <PlugZap className="size-4" />
          )}
          测试连通
        </Button>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={onCancel}
            disabled={saving}
          >
            取消
          </Button>
          <Button type="button" onClick={handleSave} disabled={saving}>
            {saving && <Loader2 className="size-4 animate-spin" />}
            保存
          </Button>
        </div>
      </DialogFooter>
    </>
  );
}

export function LlmFormDialog({ open, editing, onOpenChange, onSaved }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        {open && (
          <LlmFormFields
            key={editing?.id ?? "new"}
            editing={editing}
            onCancel={() => onOpenChange(false)}
            onSaved={onSaved}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
