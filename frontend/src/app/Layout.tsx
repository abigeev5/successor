import { LogOut } from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useLogout } from "@/api/auth";
import type { User } from "@/api/client";
import { DemoBanner } from "@/components/DemoBanner";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { NAV, ROLE_LABELS } from "@/lib/roles";

export function Layout({ user }: { user: User }) {
  const logout = useLogout();
  const navigate = useNavigate();

  return (
    <div className="flex min-h-full flex-col">
      <DemoBanner />
      <header className="border-b border-black/10">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <NavLink to="/" className="text-lg font-semibold text-ink">
            Преемник
          </NavLink>
          <nav
            aria-label="Разделы"
            className="order-last flex w-full flex-wrap gap-1 sm:order-none sm:w-auto sm:flex-1"
          >
            {NAV[user.role].map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "rounded-md px-3 py-1.5 text-sm",
                    isActive
                      ? "bg-primary-light font-medium text-primary-dark"
                      : "text-ink-muted hover:bg-surface hover:text-ink",
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 sm:ml-0">
            <div className="text-right text-sm leading-tight">
              <div className="font-medium">{user.full_name}</div>
              <div className="text-xs text-ink-muted">{ROLE_LABELS[user.role]}</div>
            </div>
            <Button
              variant="ghost"
              className="px-2"
              onClick={() => logout.mutate(undefined, { onSuccess: () => navigate("/login") })}
              disabled={logout.isPending}
              title="Выйти"
            >
              <LogOut className="size-4" aria-hidden />
              <span className="sr-only sm:not-sr-only">Выйти</span>
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
