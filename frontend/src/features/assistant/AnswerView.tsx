import {
  CircleAlert,
  CircleCheck,
  MessageCircleQuestion,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { useState } from "react";
import Markdown from "react-markdown";

import { useFeedback } from "@/api/assistant";
import type { Answer, AnswerSource } from "@/api/client";
import { useGapActions } from "@/api/gaps";
import { ErrorNote } from "@/components/ErrorNote";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/select";
import { cn } from "@/lib/cn";
import { CARD_TYPE_LABELS, VERIFICATION_NOTES } from "@/lib/labels";

const SOURCE_LINK = "#source-";

/** «…до 5-го числа [1].» → a markdown link per citation, rendered as a chip by `Citation`. */
export function linkCitations(text: string): string {
  return text.replace(/\[(\d+)\](?!\()/g, (_, n: string) => `[${n}](${SOURCE_LINK}${n})`);
}

function Citation({ source, onOpen }: { source: AnswerSource | undefined; onOpen: () => void }) {
  if (!source) return null;
  return (
    <button
      type="button"
      onClick={onOpen}
      title={source.title}
      className="mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded bg-primary-light px-1 align-baseline text-xs font-semibold text-primary-dark hover:bg-primary hover:text-white"
    >
      {source.n}
    </button>
  );
}

export function AnswerText({
  answer,
  sources,
  onOpen,
}: {
  answer: string;
  sources: AnswerSource[];
  onOpen: (cardId: string) => void;
}) {
  const byN = new Map(sources.map((s) => [s.n, s]));
  return (
    <div className="space-y-2 text-sm leading-relaxed [&_ol]:list-decimal [&_ol]:space-y-1 [&_ol]:pl-5 [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-5">
      <Markdown
        components={{
          a: ({ href, children }) => {
            if (href?.startsWith(SOURCE_LINK)) {
              const source = byN.get(Number(href.slice(SOURCE_LINK.length)));
              return <Citation source={source} onOpen={() => source && onOpen(source.card_id)} />;
            }
            return <a href={href}>{children}</a>;
          },
        }}
      >
        {linkCitations(answer)}
      </Markdown>
    </div>
  );
}

export function SourceChips({
  sources,
  onOpen,
}: {
  sources: AnswerSource[];
  onOpen: (cardId: string) => void;
}) {
  if (sources.length === 0) return null;
  return (
    <ul aria-label="Источники" className="flex flex-wrap gap-2">
      {sources.map((s) => (
        <li key={s.n}>
          <button
            type="button"
            onClick={() => onOpen(s.card_id)}
            className="rounded-full bg-white px-3 py-1 text-left text-xs ring-1 ring-black/10 hover:ring-primary"
          >
            <span className="font-semibold text-primary-dark">[{s.n}]</span> {s.title}
            <span className="text-ink-muted"> · {CARD_TYPE_LABELS[s.type]}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function VerificationNote({ answer }: { answer: Answer }) {
  const note = VERIFICATION_NOTES[answer.verification];
  if (!note) return null;
  const ok = answer.verification === "verified";
  const Icon = ok ? CircleCheck : CircleAlert;
  return (
    <p className={cn("flex items-center gap-1.5 text-xs", ok ? "text-primary" : "text-amber-700")}>
      <Icon className="size-3.5 shrink-0" aria-hidden />
      {note}
    </p>
  );
}

function Feedback({ answer, handoverId }: { answer: Answer; handoverId: string }) {
  const feedback = useFeedback(handoverId);
  const gaps = useGapActions();
  const [open, setOpen] = useState(false);
  const [comment, setComment] = useState("");
  const [asked, setAsked] = useState(false);

  if (asked) {
    return (
      <p className="text-xs text-ink-muted">
        Вопрос передан эксперту. Ответ появится в «Мои вопросы эксперту».
      </p>
    );
  }
  if (answer.feedback !== null && !open) {
    return (
      <p className="text-xs text-ink-muted">
        {answer.feedback > 0 ? "Спасибо, отмечено: помогло." : "Спасибо за отзыв."}
      </p>
    );
  }
  if (open) {
    return (
      <div className="space-y-2">
        <Textarea
          rows={2}
          aria-label="Что не так с ответом"
          placeholder="Что не так? Необязательно, но поможет улучшить ответы."
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            disabled={feedback.isPending}
            onClick={() =>
              feedback.mutate(
                { qaId: answer.qa_id, helpful: false, comment },
                { onSuccess: () => setOpen(false) },
              )
            }
          >
            Отправить отзыв
          </Button>
          <Button
            variant="secondary"
            disabled={gaps.create.isPending}
            onClick={() => {
              if (answer.feedback === null) {
                feedback.mutate({ qaId: answer.qa_id, helpful: false, comment });
              }
              gaps.create.mutate(
                { handoverId, question: answer.question, qaId: answer.qa_id },
                { onSuccess: () => setAsked(true) },
              );
            }}
          >
            <MessageCircleQuestion className="size-4" aria-hidden />
            Спросить эксперта
          </Button>
        </div>
        <ErrorNote error={feedback.error ?? gaps.create.error} />
      </div>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        variant="ghost"
        size="sm"
        disabled={feedback.isPending}
        onClick={() => feedback.mutate({ qaId: answer.qa_id, helpful: true })}
      >
        <ThumbsUp className="size-3.5" aria-hidden /> Помогло
      </Button>
      <Button variant="ghost" size="sm" onClick={() => setOpen(true)}>
        <ThumbsDown className="size-3.5" aria-hidden /> Не помогло
      </Button>
    </div>
  );
}

export function AnswerView({
  answer,
  handoverId,
  onOpen,
}: {
  answer: Answer;
  handoverId: string;
  onOpen: (cardId: string) => void;
}) {
  if (answer.status === "refused" || !answer.answer) {
    return (
      <div className="space-y-1 rounded-2xl bg-surface p-4 text-sm">
        <p className="flex items-start gap-2">
          <MessageCircleQuestion className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
          <span>
            В базе знаний нет ответа на этот вопрос.{" "}
            {answer.forwarded_to
              ? `Я передал его: ${answer.forwarded_to}.`
              : "Вопрос передан эксперту."}
          </span>
        </p>
        <p className="pl-6 text-xs text-ink-muted">Ответ появится в «Мои вопросы эксперту».</p>
      </div>
    );
  }
  return (
    <div className="space-y-3 rounded-2xl bg-surface p-4">
      <AnswerText answer={answer.answer} sources={answer.sources} onOpen={onOpen} />
      <SourceChips sources={answer.sources} onOpen={onOpen} />
      <VerificationNote answer={answer} />
      <Feedback answer={answer} handoverId={handoverId} />
    </div>
  );
}
