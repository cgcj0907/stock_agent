import { ConversationsClient } from "./conversations-client";
import { createClient } from "@/lib/supabase/server";
import { getCurrentUser } from "@/lib/supabase/auth";
import type { Conversation } from "@/types/conversation";

export default async function ConversationsPage() {
  const user = await getCurrentUser();
  let conversations: Conversation[] = [];

  if (user) {
    try {
      const supabase = await createClient();
      const { data } = await supabase
        .from("conversations")
        .select("*")
        .eq("user_id", user.id)
        .order("updated_at", { ascending: false });
      conversations = (data ?? []) as Conversation[];
    } catch {
      // conversations 表未创建时显示空态
    }
  }

  return <ConversationsClient initial={conversations} />;
}
