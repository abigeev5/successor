import { Settings, type LucideIcon } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";

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
      <PageHeader title={title} />
      <EmptyState icon={icon}>{text}</EmptyState>
    </section>
  );
}
