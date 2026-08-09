import { backendAuthHeaders } from "@/lib/backend-auth";
import {
  LOCAL_AGENTS,
  mergeBackendAgents,
  type AgentInfo,
  type BackendAgentSpec,
} from "@/lib/agents/catalog";

/** 从后端拉取智能体元数据；后端不可用时回退本地目录 */
export async function fetchAgents(): Promise<AgentInfo[]> {
  const base =
    process.env.API_BASE_SERVER || process.env.NEXT_PUBLIC_API_BASE || "";
  if (!base) return LOCAL_AGENTS;

  try {
    const res = await fetch(`${base.replace(/\/+$/, "")}/api/agents`, {
      headers: await backendAuthHeaders(),
      cache: "no-store",
      signal: AbortSignal.timeout(6000),
    });
    if (!res.ok) throw new Error(`backend ${res.status}`);
    const data = (await res.json()) as { agents?: BackendAgentSpec[] };
    if (!data.agents?.length) throw new Error("empty");
    return mergeBackendAgents(data.agents);
  } catch {
    return LOCAL_AGENTS;
  }
}
