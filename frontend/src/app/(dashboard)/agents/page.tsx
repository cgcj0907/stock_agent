import { AgentsClient } from "./agents-client";
import { fetchAgents } from "@/lib/agents/data";
import { getCurrentUser } from "@/lib/supabase/auth";
import { createClient } from "@/lib/supabase/server";

export default async function AgentsPage() {
  const agents = await fetchAgents();

  const user = await getCurrentUser();
  let favoriteIds: string[] = [];
  if (user) {
    try {
      const supabase = await createClient();
      const { data } = await supabase
        .from("agent_favorites")
        .select("agent_id")
        .eq("user_id", user.id);
      favoriteIds = (data ?? []).map((r) => r.agent_id);
    } catch {
      // agent_favorites 表未创建时忽略
    }
  }

  return (
    <AgentsClient agents={agents} initialFavorites={favoriteIds} />
  );
}
