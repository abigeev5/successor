import { Check, Eye, GitMerge, Pencil, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";

import { useCard, useCardActions } from "@/api/cards";
import type { CardDetail, CardEdit, CardListItem, CardType, Source } from "@/api/client";
import { ErrorNote } from "@/components/ErrorNote";
import { FullPageSpinner } from "@/components/Spinner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { Select, Textarea } from "@/components/ui/select";
import { CARD_TYPE_LABELS } from "@/lib/labels";

type Form = {
  title: string;
  summary: string;
  body_md: string;
  type: CardType;
  process_id: string;
  applies_when: string;
};

function toForm(card: CardDetail): Form {
  return {
    title: card.title,
    summary: card.summary,
    body_md: card.body_md,
    type: card.type,
    process_id: card.process_id ?? "",
    applies_when: card.applies_when ?? "",
  };
}

/** Only changed fields are sent: an unchanged card is approved as is (no new version). */
function diff(card: CardDetail, form: Form): CardEdit | null {
  const before = toForm(card);
  const edits: CardEdit = {};
  if (form.title !== before.title) edits.title = form.title;
  if (form.summary !== before.summary) edits.summary = form.summary;
  if (form.body_md !== before.body_md) edits.body_md = form.body_md;
  if (form.type !== before.type) edits.type = form.type;
  if (form.process_id !== before.process_id) edits.process_id = form.process_id || null;
  if (form.applies_when !== before.applies_when) edits.applies_when = form.applies_when || null;
  return Object.keys(edits).length ? edits : null;
}

/** Seconds the card was open while the tab was visible (SPEC 7.7, review_seconds). */
function useVisibleSeconds() {
  const seconds = useRef(0);
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") seconds.current += 1;
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);
  return seconds;
}

function isTyping(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

type Props = {
  cardId: string;
  processes: { id: string; name: string }[];
  allCards: CardListItem[];
  onNext: () => void;
  onPrev: () => void;
};

export function CardReview(props: Props) {
  const card = useCard(props.cardId);
  if (card.isPending) return <FullPageSpinner />;
  if (card.isError) return <ErrorNote error={card.error} />;
  return <CardEditor {...props} card={card.data} />;
}

function CardEditor({
  cardId,
  card: c,
  processes,
  allCards,
  onNext,
  onPrev,
}: Props & { card: CardDetail }) {
  const actions = useCardActions();
  const seconds = useVisibleSeconds();
  // The editor is remounted for every card (key in ReviewPage), so the form starts from the card.
  const [form, setForm] = useState<Form>(() => toForm(c));
  const [preview, setPreview] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [mergeInto, setMergeInto] = useState("");

  const edits = diff(c, form);
  const busy = actions.approve.isPending || actions.reject.isPending || actions.merge.isPending;
  const error = actions.approve.error ?? actions.reject.error ?? actions.merge.error;

  function approve() {
    if (busy) return;
    actions.approve.mutate(
      { id: cardId, edits, review_seconds: seconds.current },
      { onSuccess: onNext },
    );
  }

  function reject() {
    if (busy) return;
    actions.reject.mutate(
      { id: cardId, reason: reason.trim() || null, review_seconds: seconds.current },
      { onSuccess: onNext },
    );
  }

  // Hotkeys A / R / J / K (not while typing in a field). The ref always holds the latest handlers.
  const handlers = useRef({ approve, onNext, onPrev, openReject: () => setRejecting(true) });
  useEffect(() => {
    handlers.current = { approve, onNext, onPrev, openReject: () => setRejecting(true) };
  });
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (isTyping(event.target) || event.ctrlKey || event.metaKey || event.altKey) return;
      const key = event.key.toLowerCase();
      if (key === "a" || key === "ф") handlers.current.approve();
      else if (key === "r" || key === "к") handlers.current.openReject();
      else if (key === "j" || key === "о") handlers.current.onNext();
      else if (key === "k" || key === "л") handlers.current.onPrev();
      else return;
      event.preventDefault();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const duplicate = c.duplicate_of ? allCards.find((x) => x.id === c.duplicate_of) : undefined;
  const mergeTargets = allCards.filter(
    (x) => x.id !== c.id && (x.status === "approved" || x.status === "draft"),
  );

  function set<K extends keyof Form>(key: K, value: Form[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
      <Card className="space-y-4">
        {duplicate && (
          <p className="rounded-md bg-warning-light px-3 py-2 text-sm">
            Возможный дубль карточки «{duplicate.title}». Если это одно и то же — объедините их.
          </p>
        )}
        <div>
          <Label htmlFor="title">Заголовок</Label>
          <Input id="title" value={form.title} onChange={(e) => set("title", e.target.value)} />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="type">Тип</Label>
            <Select
              id="type"
              value={form.type}
              onChange={(e) => set("type", e.target.value as CardType)}
            >
              {Object.entries(CARD_TYPE_LABELS).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="process">Процесс</Label>
            <Select
              id="process"
              value={form.process_id}
              onChange={(e) => set("process_id", e.target.value)}
            >
              <option value="">Без процесса</option>
              {processes.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
          </div>
        </div>
        <div>
          <Label htmlFor="summary">Суть</Label>
          <Textarea
            id="summary"
            rows={2}
            value={form.summary}
            onChange={(e) => set("summary", e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="applies">Когда применять</Label>
          <Input
            id="applies"
            value={form.applies_when}
            placeholder="Например, «каждый месяц, до 5-го числа»"
            onChange={(e) => set("applies_when", e.target.value)}
          />
        </div>
        <div>
          <div className="mb-1 flex items-center justify-between">
            <Label htmlFor="body">Содержание</Label>
            <button
              type="button"
              className="flex items-center gap-1 text-xs text-primary hover:underline"
              onClick={() => setPreview((p) => !p)}
            >
              {preview ? (
                <Pencil className="size-3" aria-hidden />
              ) : (
                <Eye className="size-3" aria-hidden />
              )}
              {preview ? "Редактировать" : "Предпросмотр"}
            </button>
          </div>
          {preview ? (
            <div className="min-h-32 rounded-md border border-black/10 bg-white px-3 py-2 text-sm [&_ol]:list-decimal [&_ol]:pl-5 [&_ul]:list-disc [&_ul]:pl-5">
              <Markdown>{form.body_md}</Markdown>
            </div>
          ) : (
            <Textarea
              id="body"
              rows={8}
              value={form.body_md}
              onChange={(e) => set("body_md", e.target.value)}
            />
          )}
        </div>

        <ErrorNote error={error} />
        {rejecting ? (
          <div className="space-y-2 rounded-md bg-danger-light p-3">
            <Label htmlFor="reason">Почему отклоняете? (необязательно)</Label>
            <Input
              id="reason"
              autoFocus
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && reject()}
            />
            <div className="flex gap-2">
              <Button onClick={reject} disabled={busy} className="bg-danger hover:bg-danger/90">
                Отклонить
              </Button>
              <Button variant="ghost" onClick={() => setRejecting(false)}>
                Отмена
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button onClick={approve} disabled={busy}>
              <Check className="size-4" aria-hidden />
              {edits ? "Подтвердить с правками" : "Подтвердить"}
            </Button>
            <Button variant="secondary" onClick={() => setRejecting(true)} disabled={busy}>
              <X className="size-4" aria-hidden /> Отклонить
            </Button>
            <div className="flex items-center gap-2">
              <Select
                aria-label="Объединить с карточкой"
                className="w-auto max-w-56"
                value={mergeInto}
                onChange={(e) => setMergeInto(e.target.value)}
              >
                <option value="">Объединить с…</option>
                {mergeTargets.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.title}
                  </option>
                ))}
              </Select>
              {mergeInto && (
                <Button
                  variant="secondary"
                  disabled={busy}
                  onClick={() =>
                    actions.merge.mutate({ id: cardId, into: mergeInto }, { onSuccess: onNext })
                  }
                >
                  <GitMerge className="size-4" aria-hidden /> Объединить
                </Button>
              )}
            </div>
          </div>
        )}
      </Card>

      <aside className="space-y-3">
        <h2 className="text-sm font-semibold">Источники</h2>
        {c.sources.length === 0 && (
          <p className="text-sm text-ink-muted">Карточка создана вручную, источников нет.</p>
        )}
        {c.sources.map((source) => (
          <SourceView key={source.id} source={source} />
        ))}
      </aside>
    </div>
  );
}

/** The quote highlighted inside the expert's full answer (SPEC 7.7). */
function SourceView({ source }: { source: Source }) {
  const context = source.context ?? "";
  const at = context.indexOf(source.quote);
  return (
    <Card className="space-y-1 p-3 text-sm">
      <p className="text-xs text-ink-muted">{source.label}</p>
      {at >= 0 ? (
        <p className="whitespace-pre-line">
          {context.slice(0, at)}
          <mark className="rounded bg-primary-light px-0.5">{source.quote}</mark>
          {context.slice(at + source.quote.length)}
        </p>
      ) : (
        <blockquote className="border-l-2 border-primary pl-2">«{source.quote}»</blockquote>
      )}
    </Card>
  );
}
