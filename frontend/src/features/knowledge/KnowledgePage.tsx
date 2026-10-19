import { BookOpen, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useCards } from "@/api/cards";
import type { CardType, Handover } from "@/api/client";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { ErrorNote } from "@/components/ErrorNote";
import { HandoverGate } from "@/components/HandoverGate";
import { FullPageSpinner } from "@/components/Spinner";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/cn";
import { CARD_TYPE_LABELS } from "@/lib/labels";

import { CardView, SidePanel } from "./CardView";

export function KnowledgePage() {
  return (
    <HandoverGate
      icon={BookOpen}
      emptyTitle="Базы знаний пока нет"
      emptyText="Карточки появятся, когда у вас будет передача дел и эксперт подтвердит первые карточки."
    >
      {(handover, switcher) => (
        <Knowledge key={handover.id} handover={handover} switcher={switcher} />
      )}
    </HandoverGate>
  );
}

function normalize(text: string): string {
  return text.toLowerCase().replaceAll("ё", "е");
}

function Knowledge({ handover, switcher }: { handover: Handover; switcher: React.ReactNode }) {
  const cards = useCards(handover.id, "approved");
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const [processId, setProcessId] = useState("");
  const [type, setType] = useState<CardType | "">("");
  const selected = params.get("card");
  const processNames = useMemo(
    () => new Map(handover.processes.map((p) => [p.id, p.name])),
    [handover.processes],
  );

  function open(cardId: string | null) {
    const next = new URLSearchParams(params);
    if (cardId) next.set("card", cardId);
    else next.delete("card");
    setParams(next, { replace: true });
  }

  const words = normalize(query).split(/\s+/).filter(Boolean);
  const shown = (cards.data ?? []).filter(
    (c) =>
      (!processId || (c.process_id ?? "none") === processId) &&
      (!type || c.type === type) &&
      words.every((w) => normalize(`${c.title} ${c.summary}`).includes(w)),
  );
  const selectedCard = cards.data?.find((c) => c.id === selected);

  return (
    <section className="space-y-4">
      <PageHeader
        eyebrow="Проверено экспертом"
        title="База знаний"
        description="Только подтверждённые экспертом карточки. Ассистент отвечает по ним же."
        actions={switcher}
      />
      <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto]">
        <label className="relative">
          <span className="sr-only">Поиск</span>
          <Search
            className="pointer-events-none absolute top-2.5 left-3 size-4 text-ink-muted"
            aria-hidden
          />
          <Input
            withIcon
            placeholder="Поиск по названию и сути"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <Select
          aria-label="Процесс"
          value={processId}
          onChange={(e) => setProcessId(e.target.value)}
        >
          <option value="">Все процессы</option>
          {handover.processes.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
          <option value="none">Без процесса</option>
        </Select>
        <Select
          aria-label="Тип карточки"
          value={type}
          onChange={(e) => setType(e.target.value as CardType | "")}
        >
          <option value="">Все типы</option>
          {Object.entries(CARD_TYPE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </div>

      {cards.isPending ? (
        <FullPageSpinner />
      ) : cards.isError ? (
        <ErrorNote error={cards.error} />
      ) : cards.data.length === 0 ? (
        <EmptyState icon={BookOpen} title="Подтверждённых карточек пока нет">
          Они появятся, когда эксперт проверит черновики после интервью.
        </EmptyState>
      ) : (
        <div className={cn("grid gap-6", selectedCard && "lg:grid-cols-[1fr_420px]")}>
          <div>
            <p className="mb-2 text-xs text-ink-muted">
              Найдено: {shown.length} из {cards.data.length}
            </p>
            {shown.length === 0 ? (
              <p className="text-sm text-ink-muted">
                Ничего не нашлось. Попробуйте другие слова или сбросьте фильтры.
              </p>
            ) : (
              <ul className="grid gap-2 sm:grid-cols-2">
                {shown.map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => open(c.id)}
                      aria-current={c.id === selected}
                      className={cn(
                        "h-full w-full rounded-2xl p-4 text-left",
                        c.id === selected
                          ? "bg-primary-light ring-2 ring-primary"
                          : "bg-surface hover:bg-primary-light",
                      )}
                    >
                      <span className="block text-xs text-ink-muted">
                        {CARD_TYPE_LABELS[c.type]}
                        {c.process_id && ` · ${processNames.get(c.process_id) ?? ""}`}
                      </span>
                      <span className="mt-1 block font-medium">{c.title}</span>
                      <span className="mt-1 block text-sm text-ink-muted">{c.summary}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {selectedCard && (
            <SidePanel title="Карточка" onClose={() => open(null)}>
              <CardView
                cardId={selectedCard.id}
                processName={
                  selectedCard.process_id ? processNames.get(selectedCard.process_id) : undefined
                }
              />
            </SidePanel>
          )}
        </div>
      )}
    </section>
  );
}
