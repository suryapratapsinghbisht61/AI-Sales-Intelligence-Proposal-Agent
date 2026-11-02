"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import {
  BarChart3, BookOpen, Building2, CheckSquare, FileText, LayoutDashboard, LogOut, Menu, MessageSquare,
  Moon, Plug, Search, Settings, Sun, User, Users, X,
} from "lucide-react";
import { useTheme } from "next-themes";
import { api, useApi, type Me } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/workspace", label: "AI Workspace", icon: MessageSquare },
  { href: "/knowledge", label: "Knowledge Base", icon: BookOpen },
  { href: "/prospects", label: "Prospects", icon: Building2 },
  { href: "/proposals", label: "Proposal Studio", icon: FileText },
  { href: "/research", label: "Research", icon: Search },
  { href: "/approvals", label: "Approvals", icon: CheckSquare },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/integrations", label: "Integrations", icon: Plug },
  { href: "/team", label: "Team", icon: Users },
  { href: "/settings", label: "Settings", icon: Settings },
];

const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext)!;
export const can = (me: Me, perm: string) => me.permissions.includes(perm);

export function AppShell({ children }: { children: React.ReactNode }) {
  const { data: me, error, mutate } = useApi<Me>("/me");
  const router = useRouter();
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const { resolvedTheme, setTheme } = useTheme();

  useEffect(() => {
    if ((error as any)?.status === 401) router.replace(`/login?next=${encodeURIComponent(path)}`);
    else if (me && !me.active_organization) router.replace("/onboarding");
  }, [error, me, router, path]);
  useEffect(() => setOpen(false), [path]);

  if (!me?.active_organization) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        {error && (error as any).status !== 401 ? (
          <div className="text-center text-sm">
            <p className="font-medium">Could not reach the SalesPilot API.</p>
            <p className="mt-1 text-muted-foreground">{(error as Error).message}</p>
            <Button className="mt-4" variant="outline" onClick={() => mutate()}>Retry</Button>
          </div>
        ) : <Skeleton className="h-8 w-48" />}
      </div>
    );
  }

  const switchOrg = async (id: string) => {
    await api("/session/organization", { json: { organization_id: id } });
    window.location.href = "/dashboard"; // full reload drops every cached tenant query
  };
  const logout = async () => {
    await api("/auth/logout", { method: "POST" });
    window.location.href = "/login";
  };

  return (
    <MeContext.Provider value={me}>
      <div className="flex min-h-screen">
        <aside className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r bg-sidebar transition-transform md:sticky md:top-0 md:h-screen md:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}>
          <div className="flex h-14 items-center justify-between px-4">
            <Link href="/dashboard" className="flex items-center gap-2 font-semibold">
              <span className="grid size-6 place-items-center rounded-md bg-primary text-xs text-primary-foreground">SP</span>
              SalesPilot
            </Link>
            <Button variant="ghost" size="icon" className="md:hidden" aria-label="Close menu" onClick={() => setOpen(false)}><X /></Button>
          </div>
          <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-2" aria-label="Main">
            {NAV.map(({ href, label, icon: Icon }) => {
              const active = path === href || path.startsWith(href + "/");
              return (
                <Link key={href} href={href} aria-current={active ? "page" : undefined}
                  className={cn("flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-foreground",
                    active && "bg-sidebar-accent font-medium text-sidebar-foreground")}>
                  <Icon className="size-4" aria-hidden />{label}
                </Link>
              );
            })}
          </nav>
          <div className="border-t p-3 text-xs">
            <label htmlFor="org-switch" className="mb-1 block text-muted-foreground">Organization</label>
            <select id="org-switch" value={me.active_organization.id} onChange={(e) => switchOrg(e.target.value)}
              className="w-full rounded-md border bg-background px-2 py-1 text-sm">
              {me.organizations.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
            <Link href="/onboarding?new=1" className="mt-1.5 block text-muted-foreground hover:text-foreground">+ New organization</Link>
          </div>
        </aside>
        {open && <div className="fixed inset-0 z-30 bg-black/30 md:hidden" onClick={() => setOpen(false)} aria-hidden />}
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b bg-background/95 px-4 backdrop-blur">
            <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open menu" onClick={() => setOpen(true)}><Menu /></Button>
            <span className="truncate text-sm text-muted-foreground">
              {me.active_organization.name} · <span className="capitalize">{me.active_organization.role.replace("_", " ")}</span>
            </span>
            <div className="ml-auto flex items-center gap-1">
              <Button variant="ghost" size="icon" aria-label="Toggle theme" onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}>
                {resolvedTheme === "dark" ? <Sun /> : <Moon />}
              </Button>
              <Link href="/account" className="flex items-center gap-1.5 rounded-md px-2 py-1 text-sm hover:bg-muted">
                <User className="size-4" aria-hidden /><span className="hidden sm:inline">{me.user.name || me.user.email}</span>
              </Link>
              <Button variant="ghost" size="icon" aria-label="Sign out" onClick={logout}><LogOut /></Button>
            </div>
          </header>
          <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 md:px-8">{children}</main>
        </div>
      </div>
    </MeContext.Provider>
  );
}
