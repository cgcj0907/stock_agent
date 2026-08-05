import { notFound } from "next/navigation";

import { WorkflowRunView } from "@/components/workflow/workflow-run-view";
import { getWorkflow } from "@/lib/workflows/catalog";

export default async function WorkflowDetailPage({
  params,
}: {
  params: Promise<{ workflowId: string }>;
}) {
  const { workflowId } = await params;
  const workflow = getWorkflow(workflowId);
  if (!workflow) notFound();

  return <WorkflowRunView workflow={workflow} />;
}
