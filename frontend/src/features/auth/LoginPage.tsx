import { LogIn } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useLogin, useMe, useMeta } from "@/api/auth";
import type { UserRole } from "@/api/client";
import { BrandMark } from "@/components/BrandMark";
import { DemoBanner } from "@/components/DemoBanner";
import { ErrorNote } from "@/components/ErrorNote";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { homePath, ROLE_LABELS } from "@/lib/roles";

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
      <main className="grid flex-1 lg:grid-cols-[1.1fr_1fr]">
        <section className="bg-sky relative flex flex-col justify-between overflow-hidden px-6 py-10 text-white sm:px-12 lg:py-14">
          <div className="flex items-center gap-2.5">
            <BrandMark inverted />
            <span className="text-[17px] font-semibold tracking-tight">Преемник</span>
          </div>
          <div className="my-12 max-w-xl lg:my-0">
            <h1 className="text-5xl font-bold tracking-tight uppercase drop-shadow-sm sm:text-6xl">
              Преемник
            </h1>
            <p className="mt-6 inline-block rounded-full bg-white px-5 py-2.5 text-sm font-medium text-ink shadow-sm sm:text-base">
              Сохраняем знания опытного сотрудника до того, как он уйдёт
            </p>
          </div>
          <ul className="grid max-w-xl gap-3 text-sm sm:grid-cols-3">
            {[
              ["Интервью", "ИИ-интервьюер разбирает реальные случаи"],
              ["Проверка", "эксперт подтверждает каждую карточку"],
              ["Ассистент", "ответ только со ссылкой на источник"],
            ].map(([title, text]) => (
              <li key={title} className="rounded-2xl bg-white/85 p-4 text-ink backdrop-blur">
                <p className="font-semibold">{title}</p>
                <p className="mt-1 text-xs text-ink-muted">{text}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="flex items-center justify-center px-4 py-12 sm:px-10">
          <div className="w-full max-w-sm">
            <p className="eyebrow">Вход</p>
            <h2 className="mt-1.5 text-[28px] font-semibold tracking-tight">Добро пожаловать</h2>
            <p className="mt-1 text-sm text-ink-muted">Передача дел без потери знаний</p>

            <form onSubmit={submit} className="mt-8 space-y-4" noValidate>
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
              <ErrorNote error={login.error} />
              <Button
                type="submit"
                size="lg"
                className="w-full"
                disabled={login.isPending || !email || !password}
              >
                <LogIn className="size-4" aria-hidden />
                {login.isPending ? "Входим…" : "Войти"}
              </Button>
            </form>

            {meta.data?.demo_mode && (
              <Card padding="sm" className="mt-8">
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
                        className="w-full rounded-xl px-3 py-2 text-left text-sm transition-colors hover:bg-white"
                      >
                        <span className="font-medium">{ROLE_LABELS[account.role]}</span>
                        {account.name && <span className="text-ink-muted"> · {account.name}</span>}
                        <span className="block text-xs text-ink-soft">{account.email}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
