"use client";

import { useState } from "react";
import { BellRing, Loader2, Send } from "lucide-react";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { zodResolver } from "@/lib/zod-resolver";

interface NotifyForm {
  feishu: string;
  wechat: string;
}

const schema = z.object({
  feishu: z
    .string()
    .refine((v) => v === "" || v.startsWith("https://"), "需以 https:// 开头"),
  wechat: z
    .string()
    .refine((v) => v === "" || v.startsWith("https://"), "需以 https:// 开头"),
});

function FieldError({ message }: { message?: string }) {
  if (!message) return null;
  return <p className="text-xs text-red-600 dark:text-red-400">{message}</p>;
}

/** 通知设置：每个登录用户配自己的飞书/企业微信 webhook（监控命中按用户推送）。 */
export function NotificationsSettingsClient({
  initialWebhooks,
}: {
  initialWebhooks: Record<string, string>;
}) {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<NotifyForm>({
    resolver: zodResolver(schema),
    defaultValues: {
      feishu: initialWebhooks.feishu ?? "",
      wechat: initialWebhooks.wechat ?? "",
    },
    mode: "onBlur",
  });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  const feishu = useWatch({ control, name: "feishu" });
  const wechat = useWatch({ control, name: "wechat" });

  async function onValidSubmit(form: NotifyForm) {
    setSaving(true);
    try {
      // 后端 /api/webhooks 是 JWT 鉴权，api() 会自动带上登录 token
      await api("/api/webhooks", {
        method: "PUT",
        body: JSON.stringify({ channel: "feishu", webhook_url: form.feishu.trim() }),
      });
      await api("/api/webhooks", {
        method: "PUT",
        body: JSON.stringify({ channel: "wechat", webhook_url: form.wechat.trim() }),
      });
      toast.success("通知渠道已保存");
    } catch (e) {
      toast.error((e as Error).message || "保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function sendTest() {
    setTesting(true);
    try {
      const res = await api<{ pushed: string[] }>("/api/webhooks/test", {
        method: "POST",
        body: "{}",
      });
      toast.success(`测试成功：${res.pushed.join("、")}`);
    } catch (e) {
      toast.error((e as Error).message || "测试失败");
    } finally {
      setTesting(false);
    }
  }

  return (
    <Card className="rounded-2xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <BellRing className="size-4 text-emerald-600 dark:text-emerald-400" />
          通知设置
        </CardTitle>
        <CardDescription>
          监控命中时推送到你自己的飞书/企业微信群；留空表示不启用该渠道
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onValidSubmit)} className="flex flex-col gap-4">
          <div className="grid gap-2">
            <Label htmlFor="feishu-webhook">飞书 Webhook</Label>
            <Input
              id="feishu-webhook"
              placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
              aria-invalid={Boolean(errors.feishu)}
              {...register("feishu")}
            />
            <FieldError message={errors.feishu?.message} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="wechat-webhook">企业微信 Webhook</Label>
            <Input
              id="wechat-webhook"
              placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."
              aria-invalid={Boolean(errors.wechat)}
              {...register("wechat")}
            />
            <FieldError message={errors.wechat?.message} />
          </div>
          <div className="flex gap-2">
            <Button type="submit" disabled={saving}>
              {saving && <Loader2 className="size-4 animate-spin" />}
              保存
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={sendTest}
              disabled={testing || (!feishu.trim() && !wechat.trim())}
            >
              {testing ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Send className="size-4" />
              )}
              发送测试通知
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
