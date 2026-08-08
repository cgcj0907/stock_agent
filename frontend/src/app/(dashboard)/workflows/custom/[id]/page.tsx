import { notFound } from "next/navigation";

import { WorkflowRunView } from "@/components/workflow/workflow-run-view";
import { createClient } from "@/lib/supabase/server";
import { getCurrentUser } from "@/lib/supabase/auth";
import type { WorkflowInfo } from "@/lib/workflows/catalog";
import type { CustomWorkflow } from "@/types/custom-workflow";

export default async function CustomWorkflowRunPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ code?: string; name?: string }>;
}) {
  const { id } = await params;
  const { code, name } = await searchParams;
  const user = await getCurrentUser();
  if (!user) notFound();
  let cwf: CustomWorkflow | null = null;

  try {
    const supabase = await createClient();
    const { data } = await supabase
      .from("custom_workflows")
      .select("*")
      .eq("id", id)
      .eq("user_id", user.id)
      .maybeSingle();
    cwf = (data as CustomWorkflow) ?? null;
  } catch {
    cwf = null;
  }
  if (!cwf) notFound();

  const workflow: WorkflowInfo = {
    id: "custom",
    name: cwf.name,
    description: cwf.description || "自定义工作流",
    accent: "from-violet-500 to-purple-600",
    steps: cwf.steps.map((s) => ({
      id: s.id,
      agent: s.agent,
      deps: s.deps ?? [],
    })),
  };

  return (
    <WorkflowRunView
      workflow={workflow}
      initialCode={code}
      initialName={name}
    />
  );
}
