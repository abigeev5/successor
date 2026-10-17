import type { UserRole } from "@/api/client";

export const ROLE_LABELS: Record<UserRole, string> = {
  admin: "Администратор",
  manager: "Руководитель",
  expert: "Эксперт",
  successor: "Преемник",
};

export type NavItem = { to: string; label: string };

/** Sections per role (SPEC 9.1). */
export const NAV: Record<UserRole, NavItem[]> = {
  manager: [
    { to: "/dashboard", label: "Панель" },
    { to: "/handovers", label: "Передачи дел" },
    { to: "/gaps", label: "Пробелы" },
    { to: "/knowledge", label: "База знаний" },
  ],
  expert: [
    { to: "/handovers", label: "Передачи дел" },
    { to: "/review", label: "Проверка карточек" },
    { to: "/gaps", label: "Пробелы" },
    { to: "/knowledge", label: "База знаний" },
    { to: "/privacy", label: "Мои данные" },
  ],
  successor: [
    { to: "/assistant", label: "Ассистент" },
    { to: "/knowledge", label: "База знаний" },
  ],
  admin: [
    { to: "/handovers", label: "Передачи дел" },
    { to: "/admin", label: "Администрирование" },
  ],
};

/** Where "/" leads after login (SPEC 9.1). Experts get /handovers/:id once handovers exist (M1). */
export function homePath(role: UserRole): string {
  return NAV[role][0].to;
}
