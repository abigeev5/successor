import {
  BookOpen,
  LayoutDashboard,
  MessageCircleQuestion,
  MessagesSquare,
  Settings,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

import { EmptyState } from "@/components/EmptyState";

/** Placeholder sections of M0. Each one is replaced by a real page in its milestone (docs/plan.md). */
export const SECTIONS: Record<string, { title: string; icon: LucideIcon; text: string }> = {
  dashboard: {
    title: "Панель руководителя",
    icon: LayoutDashboard,
    text: "Здесь будет карта рисков: какие процессы держатся на одном человеке и сколько знаний уже сохранено.",
  },
  gaps: {
    title: "Пробелы",
    icon: MessageCircleQuestion,
    text: "Здесь будут вопросы преемника, на которые в базе знаний пока нет ответа.",
  },
  knowledge: {
    title: "База знаний",
    icon: BookOpen,
    text: "Подтверждённых карточек пока нет. Они появятся после проверки экспертом.",
  },
  assistant: {
    title: "Ассистент",
    icon: MessagesSquare,
    text: "Здесь можно будет задать вопрос о работе и получить ответ со ссылками на проверенные карточки.",
  },
  privacy: {
    title: "Мои данные",
    icon: ShieldCheck,
    text: "Здесь будут ваши согласия и записи. Любые свои данные можно будет удалить.",
  },
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
