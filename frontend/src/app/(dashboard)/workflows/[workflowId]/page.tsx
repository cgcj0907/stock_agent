import { notFound } from "next/navigation";

import { WorkflowRunView } from "@/components/workflow/workflow-run-view";
import { getWorkflow } from "@/lib/workflows/catalog";

export default async function WorkflowDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ workflowId: string }>;
  searchParams: Promise<{ code?: string; name?: string }>;
}) {
  const { workflowId } = await params;
  const { code, name } = await searchParams;
  const workflow = getWorkflow(workflowId);
  if (!workflow) notFound();

  return (
    <WorkflowRunView
      workflow={workflow}
      initialCode={code}
      initialName={name}
    />
  );
}
