import { ClipboardCheck, Info } from "lucide-react";
import { useMemo, useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";

import { useCards } from "@/api/cards";
import type { CardListItem } from "@/api/client";
import { useHandover, useHandovers } from "@/api/handovers";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { ErrorNote } from "@/components/ErrorNote";
import { FullPageSpinner } from "@/components/Spinner";
import { cn } from "@/lib/cn";
import { CARD_TYPE_LABELS } from "@/lib/labels";

import { CardReview } from "./CardReview";

export function ReviewPage() {
  const [params] = useSearchParams();
  const handoverId = params.get("handover") ?? undefined;
  const handovers = useHandovers();

  if (!handoverId) {
    if (handovers.isPending) return <FullPageSpinner />;
    const mine = handovers.data?.find((h) => h.my_role === "expert") ?? handovers.data?.[0];
    if (mine) return <Navigate to={`/review?handover=${mine.id}`} replace />;
    return (
      <EmptyState icon={ClipboardCheck} title="Проверять пока нечего">
        Карточки появятся, когда у вас будет передача дел и пройдёт первая сессия интервью.
      </EmptyState>
    );
  }
  return <ReviewQueue handoverId={handoverId} />;
}

function ReviewQueue({ handoverId }: { handoverId: string }) {
  const handover = useHandover(handoverId);
  const drafts = useCards(handoverId, "draft");
  const all = useCards(handoverId);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const processNames = useMemo(
    () => new Map(handover.data?.processes.map((p) => [p.id, p.name]) ?? []),
    [handover.data],
  );
  // Group drafts by process, in the order of the handover's processes; «без процесса» last.
  const ordered = useMemo(() => {
    const order = [...(handover.data?.processes.map((p) => p.id) ?? []), null];
    return [...(drafts.data ?? [])].sort(
      (a, b) => order.indexOf(a.process_id ?? null) - order.indexOf(b.process_id ?? null),
    );
  }, [drafts.data, handover.data]);

  if (drafts.isPending || handover.isPending) return <FullPageSpinner />;
  if (drafts.isError) return <ErrorNote error={drafts.error} />;
  // The selection falls back to the first draft (e.g. after the selected one was approved).
  const currentId = ordered.some((c) => c.id === selectedId)
    ? selectedId
    : (ordered[0]?.id ?? null);
  const index = ordered.findIndex((c) => c.id === currentId);

  function go(step: number) {
    if (!ordered.length) return;
    const next = (Math.max(index, 0) + step + ordered.length) % ordered.length;
    setSelectedId(ordered[next].id);
  }

  const groups: { title: string; cards: CardListItem[] }[] = [];
  for (const card of ordered) {
    const title = card.process_id
      ? (processNames.get(card.process_id) ?? "Процесс")
      : "Без процесса";
    const last = groups.at(-1);
    if (last?.title === title) last.cards.push(card);
    else groups.push({ title, cards: [card] });
  }

  return (
    <section className="space-y-4">
      <PageHeader eyebrow={`На проверке: ${ordered.length}`} title="Проверка карточек" />
      <p className="flex items-center gap-2 rounded-xl bg-primary-faint px-4 py-3 text-sm text-primary-deep">
        <Info className="size-4 shrink-0 text-primary" aria-hidden />В базу знаний попадёт только
        то, что вы подтвердите. Горячие клавиши: A — подтвердить, R — отклонить, J / K — следующая /
        предыдущая.
      </p>

      {ordered.length === 0 ? (
        <EmptyState icon={ClipboardCheck} title="Черновиков нет">
          Новые черновики появятся после следующей сессии интервью.
        </EmptyState>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
          <nav aria-label="Очередь черновиков" className="space-y-4">
            {groups.map((group) => (
              <div key={group.title}>
                <h2 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                  {group.title}
                </h2>
                <ul className="space-y-1">
                  {group.cards.map((card) => (
                    <li key={card.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedId(card.id)}
                        aria-current={card.id === currentId}
                        className={cn(
                          "w-full rounded-xl px-3 py-2 text-left text-sm",
                          card.id === currentId
                            ? "bg-primary text-white"
                            : "bg-surface hover:bg-primary-light",
                        )}
                      >
                        <span className="block font-medium">{card.title}</span>
                        <span
                          className={cn(
                            "text-xs",
                            card.id === currentId ? "text-white/80" : "text-ink-muted",
                          )}
                        >
                          {CARD_TYPE_LABELS[card.type]}
                          {card.duplicate_of && " · возможный дубль"}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>
          {currentId && (
            <CardReview
              key={currentId}
              cardId={currentId}
              processes={handover.data?.processes ?? []}
              allCards={all.data ?? []}
              onNext={() => go(1)}
              onPrev={() => go(-1)}
            />
          )}
        </div>
      )}
    </section>
  );
}
