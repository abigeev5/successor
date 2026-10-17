import { LogIn } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useLogin, useMe, useMeta } from "@/api/auth";
import type { UserRole } from "@/api/client";
import { DemoBanner } from "@/components/DemoBanner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { homePath, ROLE_LABELS } from "@/lib/roles";

/** Demo accounts from seed/data/demo.json, shown only on a demo stand. */
export const DEMO_ACCOUNTS: { email: string; name?: string; role: UserRole }[] = [
  { email: "manager@demo.local", name: "Ольга Викторовна", role: "manager" },
  { email: "expert@demo.local", name: "Ирина Сергеевна", role: "expert" },
  { email: "successor@demo.local", name: "Дмитрий", role: "successor" },
  { email: "admin@demo.local", role: "admin" },
];
export const DEMO_PASSWORD = "demo1234";

export function LoginPage() {
  const me = useMe();
  const meta = useMeta();
  const login = useLogin();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const from = (location.state as { from?: string } | null)?.from;

  if (me.data) return <Navigate to={from ?? homePath(me.data.role)} replace />;

  function submit(event: FormEvent) {
    event.preventDefault();
    login.mutate(
      { email, password },
      { onSuccess: (user) => navigate(from ?? homePath(user.role), { replace: true }) },
    );
  }

  function fillDemo(demoEmail: string) {
    setEmail(demoEmail);
    setPassword(DEMO_PASSWORD);
  }

  return (
    <div className="flex min-h-full flex-col">
      <DemoBanner />
      <main className="flex flex-1 items-center justify-center px-4 py-10">
        <div className="w-full max-w-sm">
          <div className="mb-8 text-center">
            <h1 className="text-2xl font-semibold">Преемник</h1>
            <p className="mt-1 text-sm text-ink-muted">Передача дел без потери знаний</p>
          </div>

          <form onSubmit={submit} className="space-y-4" noValidate>
            <div>
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div>
              <Label htmlFor="password">Пароль</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {login.error && (
              <p role="alert" className="rounded-md bg-danger-light px-3 py-2 text-sm text-danger">
                {login.error.message}
              </p>
            )}
            <Button
              type="submit"
              className="w-full"
              disabled={login.isPending || !email || !password}
            >
              <LogIn className="size-4" aria-hidden />
              {login.isPending ? "Входим…" : "Войти"}
            </Button>
          </form>

          {meta.data?.demo_mode && (
            <Card className="mt-8 p-4">
              <p className="text-sm font-medium">Демо-учётки</p>
              <p className="mt-0.5 text-xs text-ink-muted">
                Пароль для всех: <code>{DEMO_PASSWORD}</code>. Нажмите, чтобы подставить.
              </p>
              <ul className="mt-3 space-y-1">
                {DEMO_ACCOUNTS.map((account) => (
                  <li key={account.email}>
                    <button
                      type="button"
                      onClick={() => fillDemo(account.email)}
                      className="w-full rounded-md px-2 py-1.5 text-left text-sm hover:bg-primary-light"
                    >
                      <span className="font-medium">{ROLE_LABELS[account.role]}</span>
                      {account.name && <span className="text-ink-muted"> · {account.name}</span>}
                      <span className="block text-xs text-ink-muted">{account.email}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </main>
    </div>
  );
}
