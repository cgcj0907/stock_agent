export interface Conversation {
  id: string;
  user_id: string;
  session_id: string;
  company_code: string;
  company_name: string;
  workflow_id: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export const CONVERSATION_STATUS: Record<
  string,
  { label: string; className: string }
> = {
  created: {
    label: "已创建",
    className:
      "border-border bg-muted/50 text-muted-foreground",
  },
  in_progress: {
    label: "进行中",
    className:
      "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-950/60 dark:text-sky-300",
  },
  completed: {
    label: "已完成",
    className:
      "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
  },
  failed: {
    label: "失败",
    className:
      "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/60 dark:text-red-300",
  },
  archived: {
    label: "已归档",
    className: "border-border bg-muted/50 text-muted-foreground",
  },
};
