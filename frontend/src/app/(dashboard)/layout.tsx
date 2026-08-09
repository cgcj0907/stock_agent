import { redirect } from "next/navigation";

import { AppHeader } from "@/components/app-header";
import { CommandPalette } from "@/components/command-palette";
import { PageTransition } from "@/components/motion/page-transition";
import { AppSidebar } from "@/components/app-sidebar";
import { RightRailProvider } from "@/components/ui/right-rail";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { resolveProfileIdentity } from "@/lib/profile";
import { getProfile } from "@/lib/profile-store";
import { createClient } from "@/lib/supabase/server";

export default async function DashboardLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  let profile = null;
  try {
    profile = await getProfile(user.id);
  } catch {
    // profiles 表或新增字段尚未就绪时回退到 auth metadata
  }

  const identity = resolveProfileIdentity({
    email: user.email,
    authDisplayName: user.user_metadata?.display_name as string | undefined,
    authAvatarUrl: user.user_metadata?.avatar_url as string | undefined,
    profile,
  });

  return (
    <SidebarProvider>
      <RightRailProvider>
        <AppSidebar
          user={{
            name: identity.name,
            email: identity.email,
            avatarUrl: identity.avatarUrl,
          }}
        />
        <SidebarInset>
          <div className="flex min-w-0 flex-1 flex-col">
            <AppHeader />
            <main className="flex-1 p-4 md:p-6"><PageTransition>{children}</PageTransition></main>
          </div>
        </SidebarInset>
      </RightRailProvider>
      <CommandPalette />
    </SidebarProvider>
  );
}
