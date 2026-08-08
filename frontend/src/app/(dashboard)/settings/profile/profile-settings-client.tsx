"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  BriefcaseBusiness,
  GraduationCap,
  Save,
  Target,
  UserRound,
  Wallet,
} from "lucide-react";
import { toast } from "sonner";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  ANNUAL_INCOME_RANGE_OPTIONS,
  CAPITAL_AVAILABILITY_OPTIONS,
  CAREER_STAGE_OPTIONS,
  CIRCLE_OF_COMPETENCE_OPTIONS,
  DECISION_PREFERENCE_OPTIONS,
  EDUCATION_LEVEL_OPTIONS,
  EDUCATION_MAJOR_OPTIONS,
  HOLDING_PERIOD_OPTIONS,
  INCOME_DEPENDENCY_LEVEL_OPTIONS,
  INVESTABLE_ASSETS_RANGE_OPTIONS,
  INVESTMENT_GOAL_OPTIONS,
  INVESTMENT_STYLE_OPTIONS,
  LOSS_TOLERANCE_RANGE_OPTIONS,
  RISK_TOLERANCE_OPTIONS,
  type ProfileInput,
} from "@/lib/profile";

function SectionTitle({
  icon: Icon,
  title,
  description,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
}) {
  return (
    <div className="flex items-start gap-3">
      <div className="flex size-10 items-center justify-center rounded-xl border bg-muted/30 text-foreground">
        <Icon className="size-4" />
      </div>
      <div>
        <CardTitle className="text-base">{title}</CardTitle>
        <CardDescription className="mt-1">{description}</CardDescription>
      </div>
    </div>
  );
}

function FieldShell({
  label,
  description,
  children,
}: {
  label: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2">
      <Label>{label}</Label>
      {children}
      {description ? (
        <p className="text-xs text-muted-foreground">{description}</p>
      ) : null}
    </div>
  );
}

function OptionSelect({
  value,
  onChange,
  options,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  options: readonly { value: string; label: string }[];
  placeholder: string;
}) {
  return (
    <Select
      value={value || "__unset"}
      onValueChange={(next) => onChange(next === "__unset" ? "" : next)}
    >
      <SelectTrigger className="h-10 w-full rounded-xl">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="__unset">暂不填写</SelectItem>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function ProfileSettingsClient({
  initialProfile,
  email,
}: {
  initialProfile: Required<ProfileInput> & { id?: string };
  email: string;
}) {
  const router = useRouter();
  const [profile, setProfile] = React.useState(initialProfile);
  const [saving, setSaving] = React.useState(false);

  const displayName = profile.display_name || email.split("@")[0] || "用户";
  const avatarInitial = displayName.charAt(0) || "用";

  function updateField<K extends keyof ProfileInput>(key: K, value: Required<ProfileInput>[K]) {
    setProfile((current) => ({ ...current, [key]: value }));
  }

  function toggleCircle(value: string) {
    setProfile((current) => {
      const exists = current.circle_of_competence.includes(value);
      if (exists) {
        return {
          ...current,
          circle_of_competence: current.circle_of_competence.filter(
            (item) => item !== value,
          ),
        };
      }
      if (current.circle_of_competence.length >= 5) {
        toast.error("能力圈最多选择 5 个行业");
        return current;
      }
      return {
        ...current,
        circle_of_competence: [...current.circle_of_competence, value],
      };
    });
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);

    try {
      const res = await fetch("/api/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(profile),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "保存失败");

      setProfile((current) => ({ ...current, ...(data.profile ?? {}) }));
      toast.success("个人资料已保存");
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mx-auto flex max-w-5xl flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">个人资料</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            维护你的基础资料与投资者画像，当前仅保存到资料库，不参与分析模块。
          </p>
        </div>
        <Button type="submit" className="rounded-xl" disabled={saving}>
          <Save className="size-4" />
          {saving ? "保存中..." : "保存资料"}
        </Button>
      </div>

      <Card className="rounded-2xl">
        <CardContent className="flex flex-col gap-5 p-5 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-4">
            <Avatar size="lg" className="size-14 rounded-2xl">
              <AvatarImage src={profile.avatar_url || undefined} alt={displayName} />
              <AvatarFallback className="rounded-2xl bg-muted text-base text-foreground">
                {avatarInitial}
              </AvatarFallback>
            </Avatar>
            <div>
              <p className="text-base font-semibold">{displayName}</p>
              <p className="text-sm text-muted-foreground">{email || "未绑定邮箱"}</p>
            </div>
          </div>
          <div className="grid gap-3 md:w-[28rem] md:grid-cols-2">
            <FieldShell label="昵称">
              <Input
                value={profile.display_name}
                placeholder="填写你的称呼"
                className="h-10 rounded-xl"
                onChange={(event) => updateField("display_name", event.target.value)}
              />
            </FieldShell>
            <FieldShell label="头像 URL">
              <Input
                value={profile.avatar_url}
                placeholder="https://..."
                className="h-10 rounded-xl"
                onChange={(event) => updateField("avatar_url", event.target.value)}
              />
            </FieldShell>
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-2xl">
        <CardHeader>
          <SectionTitle
            icon={GraduationCap}
            title="基础身份"
            description="记录教育和职业背景，作为个人资料的基础信息。"
          />
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <FieldShell label="学历层级">
            <OptionSelect
              value={profile.education_level}
              onChange={(value) => updateField("education_level", value)}
              options={EDUCATION_LEVEL_OPTIONS}
              placeholder="选择学历层级"
            />
          </FieldShell>
          <FieldShell label="专业背景">
            <OptionSelect
              value={profile.education_major}
              onChange={(value) => updateField("education_major", value)}
              options={EDUCATION_MAJOR_OPTIONS}
              placeholder="选择专业背景"
            />
          </FieldShell>
          <FieldShell label="职业阶段">
            <OptionSelect
              value={profile.career_stage}
              onChange={(value) => updateField("career_stage", value)}
              options={CAREER_STAGE_OPTIONS}
              placeholder="选择职业阶段"
            />
          </FieldShell>
          <FieldShell
            label="教育经历补充"
            description="可填写学校、证书或研究方向，最多 120 字。"
          >
            <Textarea
              value={profile.education_note}
              placeholder="例如：金融工程背景，CFA 二级"
              className="min-h-24 rounded-xl"
              onChange={(event) => updateField("education_note", event.target.value)}
            />
          </FieldShell>
        </CardContent>
      </Card>

      <Card className="rounded-2xl">
        <CardHeader>
          <SectionTitle
            icon={Wallet}
            title="财务画像"
            description="采用区间档位存储，不要求填写精确金额。"
          />
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <FieldShell label="年收入区间">
            <OptionSelect
              value={profile.annual_income_range}
              onChange={(value) => updateField("annual_income_range", value)}
              options={ANNUAL_INCOME_RANGE_OPTIONS}
              placeholder="选择年收入区间"
            />
          </FieldShell>
          <FieldShell label="可投资资产区间">
            <OptionSelect
              value={profile.investable_assets_range}
              onChange={(value) => updateField("investable_assets_range", value)}
              options={INVESTABLE_ASSETS_RANGE_OPTIONS}
              placeholder="选择可投资资产区间"
            />
          </FieldShell>
          <FieldShell label="单一标的可承受亏损">
            <OptionSelect
              value={profile.loss_tolerance_range}
              onChange={(value) => updateField("loss_tolerance_range", value)}
              options={LOSS_TOLERANCE_RANGE_OPTIONS}
              placeholder="选择亏损承受区间"
            />
          </FieldShell>
          <FieldShell label="资金属性">
            <OptionSelect
              value={profile.capital_availability}
              onChange={(value) => updateField("capital_availability", value)}
              options={CAPITAL_AVAILABILITY_OPTIONS}
              placeholder="选择资金属性"
            />
          </FieldShell>
          <FieldShell label="是否依赖投资收益改善现金流">
            <OptionSelect
              value={profile.income_dependency_level}
              onChange={(value) => updateField("income_dependency_level", value)}
              options={INCOME_DEPENDENCY_LEVEL_OPTIONS}
              placeholder="选择依赖程度"
            />
          </FieldShell>
        </CardContent>
      </Card>

      <Card className="rounded-2xl">
        <CardHeader>
          <SectionTitle
            icon={Target}
            title="投资画像"
            description="聚焦你的目标、风格和能力圈，便于后续继续扩展。"
          />
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <FieldShell label="投资目标">
            <OptionSelect
              value={profile.investment_goal}
              onChange={(value) => updateField("investment_goal", value)}
              options={INVESTMENT_GOAL_OPTIONS}
              placeholder="选择投资目标"
            />
          </FieldShell>
          <FieldShell label="持有周期">
            <OptionSelect
              value={profile.holding_period}
              onChange={(value) => updateField("holding_period", value)}
              options={HOLDING_PERIOD_OPTIONS}
              placeholder="选择持有周期"
            />
          </FieldShell>
          <FieldShell label="风险承受度">
            <OptionSelect
              value={profile.risk_tolerance}
              onChange={(value) => updateField("risk_tolerance", value)}
              options={RISK_TOLERANCE_OPTIONS}
              placeholder="选择风险承受度"
            />
          </FieldShell>
          <FieldShell label="投资风格">
            <OptionSelect
              value={profile.investment_style}
              onChange={(value) => updateField("investment_style", value)}
              options={INVESTMENT_STYLE_OPTIONS}
              placeholder="选择投资风格"
            />
          </FieldShell>
          <FieldShell label="决策偏好">
            <OptionSelect
              value={profile.decision_preference}
              onChange={(value) => updateField("decision_preference", value)}
              options={DECISION_PREFERENCE_OPTIONS}
              placeholder="选择决策偏好"
            />
          </FieldShell>
          <FieldShell
            label="能力圈行业"
            description={`最多选择 5 个，目前已选 ${profile.circle_of_competence.length} 个。`}
          >
            <div className="flex flex-wrap gap-2">
              {CIRCLE_OF_COMPETENCE_OPTIONS.map((option) => {
                const active = profile.circle_of_competence.includes(option.value);
                const disabled =
                  !active && profile.circle_of_competence.length >= 5;
                return (
                  <Button
                    key={option.value}
                    type="button"
                    variant={active ? "default" : "outline"}
                    size="sm"
                    className="rounded-full"
                    disabled={disabled}
                    onClick={() => toggleCircle(option.value)}
                  >
                    {option.label}
                  </Button>
                );
              })}
            </div>
          </FieldShell>
        </CardContent>
      </Card>

      <Card className="rounded-2xl border-dashed">
        <CardContent className="flex flex-col gap-2 p-5 text-sm text-muted-foreground md:flex-row md:items-center md:justify-between">
          <div className="flex items-start gap-2">
            <UserRound className="mt-0.5 size-4 shrink-0" />
            <p>
              这一版资料页只做存储与维护，不会改动当前分析模块的输入逻辑。
            </p>
          </div>
          <Button type="submit" className="rounded-xl" disabled={saving}>
            <BriefcaseBusiness className="size-4" />
            {saving ? "保存中..." : "保存本页资料"}
          </Button>
        </CardContent>
      </Card>
    </form>
  );
}
