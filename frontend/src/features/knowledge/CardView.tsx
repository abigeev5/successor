import { X } from "lucide-react";
import type { ReactNode } from "react";
import Markdown from "react-markdown";

import { useCard } from "@/api/cards";
import { ErrorNote } from "@/components/ErrorNote";
import { SourceView } from "@/components/SourceView";
import { FullPageSpinner } from "@/components/Spinner";
import { Button } from "@/components/ui/button";
import { CARD_TYPE_LABELS } from "@/lib/labels";

/** Full screen on a phone: the assistant must work there too. */
export function SidePanel({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <aside
      aria-label={title}
      className="fixed inset-0 z-20 overflow-y-auto bg-white p-4 lg:sticky lg:top-4 lg:z-auto lg:max-h-[calc(100vh-2rem)] lg:rounded-2xl lg:bg-surface"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-ink-muted">{title}</h2>
        <Button variant="ghost" size="icon" onClick={onClose} title="Закрыть">
          <X className="size-4" aria-hidden />
          <span className="sr-only">Закрыть</span>
        </Button>
      </div>
      {children}
    </aside>
  );
}

export function CardView({ cardId, processName }: { cardId: string; processName?: string }) {
  const card = useCard(cardId);
  if (card.isPending) return <FullPageSpinner />;
  if (card.isError) return <ErrorNote error={card.error} />;
  const c = card.data;
  return (
    <article className="space-y-4">
      <header className="space-y-1">
        <p className="text-xs text-ink-muted">
          {CARD_TYPE_LABELS[c.type]}
          {processName && ` · ${processName}`}
          {c.version > 1 && ` · версия ${c.version}`}
        </p>
        <h3 className="text-lg font-semibold leading-snug">{c.title}</h3>
        <p className="text-sm">{c.summary}</p>
        {c.applies_when && (
          <p className="text-sm text-ink-muted">
            <span className="font-medium text-ink">Когда применять:</span> {c.applies_when}
          </p>
        )}
      </header>
      {c.body_md && (
        <div className="space-y-2 text-sm [&_ol]:list-decimal [&_ol]:pl-5 [&_ul]:list-disc [&_ul]:pl-5">
          <Markdown>{c.body_md}</Markdown>
        </div>
      )}
      <section className="space-y-2">
        <h4 className="text-sm font-semibold">Первоисточники</h4>
        {c.sources.length === 0 ? (
          <p className="text-sm text-ink-muted">Карточка создана экспертом вручную.</p>
        ) : (
          c.sources.map((source) => <SourceView key={source.id} source={source} />)
        )}
      </section>
    </article>
  );
}
