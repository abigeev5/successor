import { Settings, type LucideIcon } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";

/** Placeholder sections of M0. Each one is replaced by a real page in its milestone (docs/plan.md). */
export const SECTIONS: Record<string, { title: string; icon: LucideIcon; text: string }> = {
  admin: {
    title: "Администрирование",
    icon: Settings,
    text: "Пользователи и подразделения.",
  },
};

export function SectionPage({ section }: { section: keyof typeof SECTIONS }) {
  const { title, icon, text } = SECTIONS[section];
  return (
    <section>
      <h1 className="text-xl font-semibold">{title}</h1>
      <EmptyState icon={icon}>{text}</EmptyState>
    </section>
  );
}
