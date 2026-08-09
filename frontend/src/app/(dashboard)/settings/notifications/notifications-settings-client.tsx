"use client";

import { useState } from "react";
import { BellRing, Loader2, Send } from "lucide-react";
import { toast } from "sonner";

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

/** 通知设置：每个登录用户配自己的飞书/企业微信 webhook（监控命中按用户推送）。 */
export function NotificationsSettingsClient({
  initialWebhooks,
}: {
  initialWebhooks: Record<string, string>;
}) {
  const [feishu, setFeishu] = useState(initialWebhooks.feishu ?? "");
  const [wechat, setWechat] = useState(initialWebhooks.wechat ?? "");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  async function save() {
    setSaving(true);
    try {
      // 后端 /api/webhooks 是 JWT 鉴权，api() 会自动带上登录 token
      await api("/api/webhooks", {
        method: "PUT",
        body: JSON.stringify({ channel: "feishu", webhook_url: feishu.trim() }),
      });
      await api("/api/webhooks", {
        method: "PUT",
        body: JSON.stringify({ channel: "wechat", webhook_url: wechat.trim() }),
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
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-2">
          <Label htmlFor="feishu-webhook">飞书 Webhook</Label>
          <Input
            id="feishu-webhook"
            placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
            value={feishu}
            onChange={(e) => setFeishu(e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="wechat-webhook">企业微信 Webhook</Label>
          <Input
            id="wechat-webhook"
            placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."
            value={wechat}
            onChange={(e) => setWechat(e.target.value)}
          />
        </div>
        <div className="flex gap-2">
          <Button onClick={save} disabled={saving}>
            {saving && <Loader2 className="size-4 animate-spin" />}
            保存
          </Button>
          <Button
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
      </CardContent>
    </Card>
  );
}
