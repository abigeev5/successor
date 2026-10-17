import { BellRing, LoaderCircle, MessagesSquare, Send, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { useAsk, useHistory } from "@/api/assistant";
import { useCards } from "@/api/cards";
import type { Gap, Handover } from "@/api/client";
import { useGaps } from "@/api/gaps";
import { ErrorNote } from "@/components/ErrorNote";
import { HandoverGate } from "@/components/HandoverGate";
import { FullPageSpinner } from "@/components/Spinner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/select";
import { CardView, SidePanel } from "@/features/knowledge/CardView";

import { AnswerView } from "./AnswerView";
import { MyQuestions } from "./MyQuestions";

const EXAMPLES = 4;
const SEEN_KEY = "preemnik:seen-answered-gaps";

/** Answered gaps the user has not dismissed yet (per browser; losing it only re-shows a notice). */
function useUnseenAnswers(gaps: Gap[] | undefined) {
  const [seen, setSeen] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(SEEN_KEY) ?? "[]") as string[];
    } catch {
      return [];
    }
  });
  const unseen = (gaps ?? []).filter((g) => g.status === "answered" && !seen.includes(g.id));
  function dismiss() {
    const next = [...seen, ...unseen.map((g) => g.id)];
    setSeen(next);
    try {
      localStorage.setItem(SEEN_KEY, JSON.stringify(next));
    } catch {
      // storage is a convenience here
    }
  }
  return { unseen, dismiss };
}

export function AssistantPage() {
  return (
    <HandoverGate
      icon={MessagesSquare}
      emptyTitle="Ассистент пока недоступен"
      emptyText="Он заработает, когда вас добавят преемником в передачу дел."
    >
      {(handover, switcher) => (
        <Assistant key={handover.id} handover={handover} switcher={switcher} />
      )}
    </HandoverGate>
  );
}

function Assistant({ handover, switcher }: { handover: Handover; switcher: React.ReactNode }) {
  const history = useHistory(handover.id);
  const ask = useAsk(handover.id);
  const cards = useCards(handover.id, "approved");
  const gaps = useGaps(handover.id);
  const notices = useUnseenAnswers(gaps.data);
  const [text, setText] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [cardId, setCardId] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);

  const processNames = useMemo(
    () => new Map(handover.processes.map((p) => [p.id, p.name])),
    [handover.processes],
  );
  const examples = useMemo(() => (cards.data ?? []).slice(0, EXAMPLES), [cards.data]);
  const count = history.data?.length ?? 0;
  useEffect(() => {
    bottom.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [count, pending]);

  function send() {
    const question = text.trim();
    if (question.length < 2 || ask.isPending) return;
    setPending(question);
    setText("");
    ask.mutate(question, {
      onSettled: () => setPending(null),
      onError: () => setText(question),
    });
  }

  const card = cards.data?.find((c) => c.id === cardId);
  const panel = cardId ? (
    <SidePanel title="Источник" onClose={() => setCardId(null)}>
      <CardView
        cardId={cardId}
        processName={card?.process_id ? processNames.get(card.process_id) : undefined}
      />
    </SidePanel>
  ) : (
    <MyQuestions gaps={gaps.data} onOpen={setCardId} />
  );

  return (
    <section className="grid gap-6 lg:grid-cols-[1fr_380px]">
      <div className="flex min-h-[60vh] flex-col gap-4">
        <div className="flex flex-wrap items-baseline gap-3">
          <h1 className="text-xl font-semibold">Ассистент</h1>
          {switcher}
        </div>

        {notices.unseen.length > 0 && (
          <div
            role="status"
            className="flex items-start gap-2 rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-900"
          >
            <BellRing className="mt-0.5 size-4 shrink-0" aria-hidden />
            <p className="flex-1">
              Эксперт ответил на {notices.unseen.length === 1 ? "ваш вопрос" : "ваши вопросы"}:{" "}
              {notices.unseen.map((g) => `«${g.question}»`).join(", ")}. Ответ уже в базе знаний —
              спросите ещё раз или откройте его в «Мои вопросы эксперту».
            </p>
            <Button variant="ghost" className="px-1 py-0" onClick={notices.dismiss} title="Скрыть">
              <X className="size-4" aria-hidden />
              <span className="sr-only">Скрыть</span>
            </Button>
          </div>
        )}

        <div className="flex-1 space-y-6" aria-live="polite">
          {history.isPending && <FullPageSpinner />}
          <ErrorNote error={history.error} />
          {count === 0 && !pending && !history.isPending && (
            <div className="space-y-3 py-6 text-center">
              <p className="text-sm text-ink-muted">
                Спросите о работе — я отвечу только по проверенным экспертом карточкам и покажу
                источники. Если ответа нет, передам вопрос эксперту.
              </p>
              {examples.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs text-ink-muted">Например, о чём есть карточки:</p>
                  <ul className="flex flex-wrap justify-center gap-2">
                    {examples.map((c) => (
                      <li key={c.id}>
                        <button
                          type="button"
                          className="rounded-full bg-surface px-3 py-1.5 text-sm hover:bg-primary-light"
                          onClick={() => {
                            setText(c.title);
                            input.current?.focus();
                          }}
                        >
                          {c.title}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
          {history.data?.map((a) => (
            <div key={a.qa_id} className="space-y-2">
              <Question text={a.question} />
              <AnswerView answer={a} handoverId={handover.id} onOpen={setCardId} />
            </div>
          ))}
          {pending && (
            <div className="space-y-2">
              <Question text={pending} />
              <p className="flex items-center gap-2 text-sm text-ink-muted" role="status">
                <LoaderCircle className="size-4 animate-spin" aria-hidden />
                Ищу ответ в базе знаний и проверяю его по источникам…
              </p>
            </div>
          )}
          <div ref={bottom} />
        </div>

        <form
          className="sticky bottom-0 space-y-2 bg-white pt-2 pb-1"
          onSubmit={(event) => {
            event.preventDefault();
            send();
          }}
        >
          <ErrorNote error={ask.error} />
          <div className="flex items-end gap-2">
            <Textarea
              ref={input}
              rows={2}
              aria-label="Ваш вопрос"
              placeholder="Например: до какого числа сдавать отчёт о контингенте?"
              value={text}
              maxLength={2000}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  send();
                }
              }}
            />
            <Button type="submit" disabled={text.trim().length < 2 || ask.isPending}>
              <Send className="size-4" aria-hidden />
              <span className="sr-only sm:not-sr-only">Спросить</span>
            </Button>
          </div>
          <p className="text-xs text-ink-muted">Enter — отправить, Shift+Enter — новая строка</p>
        </form>
      </div>
      <div>{panel}</div>
    </section>
  );
}

function Question({ text }: { text: string }) {
  return (
    <p className="ml-auto w-fit max-w-[85%] rounded-lg bg-primary px-4 py-2 text-sm whitespace-pre-line text-white">
      {text}
    </p>
  );
}
