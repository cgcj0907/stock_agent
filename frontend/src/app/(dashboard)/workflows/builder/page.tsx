import { WorkflowBuilder } from "@/components/workflow/workflow-builder";
import { createClient } from "@/lib/supabase/server";
import { getCurrentUser } from "@/lib/supabase/auth";
import type { CustomWorkflow } from "@/types/custom-workflow";

export default async function BuilderPage({
  searchParams,
}: {
  searchParams: Promise<{ id?: string }>;
}) {
  const { id } = await searchParams;
  const user = await getCurrentUser();
  let initial: CustomWorkflow | null = null;

  if (id && user) {
    try {
      const supabase = await createClient();
      const { data } = await supabase
        .from("custom_workflows")
        .select("*")
        .eq("id", id)
        .eq("user_id", user.id)
        .maybeSingle();
      initial = (data as CustomWorkflow) ?? null;
    } catch {
      initial = null;
    }
  }

  return <WorkflowBuilder initial={initial} />;
}
