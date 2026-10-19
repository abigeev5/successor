import { LogOut } from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useLogout } from "@/api/auth";
import type { User } from "@/api/client";
import { BrandMark } from "@/components/BrandMark";
import { DemoBanner } from "@/components/DemoBanner";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { NAV, ROLE_LABELS } from "@/lib/roles";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0] ?? "")
    .join("")
    .toUpperCase();
}

export function Layout({ user }: { user: User }) {
  const logout = useLogout();
  const navigate = useNavigate();

  return (
    <div className="flex min-h-full flex-col">
      <DemoBanner />
      <header className="sticky top-0 z-20 border-b border-line bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-8 gap-y-2 px-4 py-3 sm:px-6">
          <NavLink to="/" className="flex items-center gap-2.5">
            <BrandMark />
            <span className="text-[17px] font-semibold tracking-tight text-ink">Преемник</span>
          </NavLink>
          <nav
            aria-label="Разделы"
            className="order-last -mx-1 flex w-full gap-1 overflow-x-auto [scrollbar-width:none] sm:order-none sm:w-auto sm:flex-1"
          >
            {NAV[user.role].map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "rounded-full px-3.5 py-1.5 text-sm whitespace-nowrap transition-colors",
                    isActive
                      ? "bg-primary-light font-medium text-primary-deep"
                      : "text-ink-muted hover:bg-surface hover:text-ink",
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 sm:ml-0">
            <div className="hidden text-right text-sm leading-tight sm:block">
              <div className="font-medium">{user.full_name}</div>
              <div className="text-xs text-ink-soft">{ROLE_LABELS[user.role]}</div>
            </div>
            <span
              aria-hidden
              className="grid size-9 place-items-center rounded-full bg-primary-faint text-xs font-semibold text-primary-dark"
            >
              {initials(user.full_name)}
            </span>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => logout.mutate(undefined, { onSuccess: () => navigate("/login") })}
              disabled={logout.isPending}
              title="Выйти"
            >
              <LogOut className="size-4" aria-hidden />
              <span className="sr-only">Выйти</span>
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6 sm:py-10">
        <Outlet />
      </main>
      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap justify-between gap-2 px-4 py-5 text-xs text-ink-soft sm:px-6">
          <span>Преемник — передача дел без потери знаний</span>
          <span>Данные хранятся в контуре организации</span>
        </div>
      </footer>
    </div>
  );
}
