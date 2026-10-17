import { CircleCheck, Clock, MinusCircle } from "lucide-react";

import type { Gap } from "@/api/client";
import { GAP_STATUS_LABELS } from "@/lib/labels";

function status(gap: Gap) {
  if (gap.status === "answered") return { icon: CircleCheck, className: "text-emerald-700" };
  if (gap.status === "dismissed") return { icon: MinusCircle, className: "text-ink-muted" };
  return { icon: Clock, className: "text-amber-700" };
}

/** The successor's questions that went to the expert (SPEC 7.8), answered ones first. */
export function MyQuestions({
  gaps,
  onOpen,
}: {
  gaps: Gap[] | undefined;
  onOpen: (cardId: string) => void;
}) {
  const order = { answered: 0, open: 1, dismissed: 2 };
  const sorted = [...(gaps ?? [])].sort((a, b) => order[a.status] - order[b.status]);
  return (
    <aside className="space-y-3 rounded-lg bg-surface p-4">
      <h2 className="text-sm font-semibold">Мои вопросы эксперту</h2>
      {sorted.length === 0 ? (
        <p className="text-sm text-ink-muted">
          Пока нет. Если ассистент не найдёт ответа, вопрос попадёт сюда и к эксперту.
        </p>
      ) : (
        <ul className="space-y-3">
          {sorted.map((gap) => {
            const view = status(gap);
            const Icon = view.icon;
            return (
              <li key={gap.id} className="space-y-1 text-sm">
                <p className="font-medium">{gap.question}</p>
                <p className={`flex items-center gap-1.5 text-xs ${view.className}`}>
                  <Icon className="size-3.5 shrink-0" aria-hidden />
                  {gap.status === "open" && gap.answer_on_review
                    ? "Эксперт ответил, ответ на проверке"
                    : GAP_STATUS_LABELS[gap.status]}
                  {gap.status === "open" && !gap.answer_on_review && gap.assignee_name
                    ? ` · ${gap.assignee_name}`
                    : ""}
                </p>
                {gap.status === "answered" && gap.answered_card_id && (
                  <button
                    type="button"
                    className="text-xs font-medium text-primary hover:underline"
                    onClick={() => onOpen(gap.answered_card_id!)}
                  >
                    Открыть ответ в базе знаний
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
