import {
  CircleCheck,
  Clock,
  LoaderCircle,
  MessageCircleQuestion,
  Mic,
  MinusCircle,
  Square,
} from "lucide-react";
import { useCallback, useState } from "react";
import { Link } from "react-router-dom";

import type { ApiError, Gap, GapStatus, Handover } from "@/api/client";
import { uploadGapAudio, useGapActions, useGaps } from "@/api/gaps";
import { useUsers } from "@/api/handovers";
import { EmptyState } from "@/components/EmptyState";
import { ErrorNote } from "@/components/ErrorNote";
import { HandoverGate } from "@/components/HandoverGate";
import { FullPageSpinner } from "@/components/Spinner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select, Textarea } from "@/components/ui/select";
import { MAX_SECONDS, useVoiceRecorder } from "@/features/interview/useVoiceRecorder";
import { cn } from "@/lib/cn";
import { GAP_STATUS_LABELS } from "@/lib/labels";

const TABS: { status: GapStatus | undefined; label: string }[] = [
  { status: "open", label: "Открытые" },
  { status: "answered", label: "С ответом" },
  { status: "dismissed", label: "Закрытые" },
  { status: undefined, label: "Все" },
];

export function GapsPage() {
  return (
    <HandoverGate
      icon={MessageCircleQuestion}
      emptyTitle="Пробелов нет"
      emptyText="Здесь будут вопросы преемника, на которые в базе знаний пока нет ответа."
    >
      {(handover, switcher) => <Gaps key={handover.id} handover={handover} switcher={switcher} />}
    </HandoverGate>
  );
}

function Gaps({ handover, switcher }: { handover: Handover; switcher: React.ReactNode }) {
  const [tab, setTab] = useState(0);
  const gaps = useGaps(handover.id, TABS[tab].status);
  const canAnswer = handover.my_role === "expert" || handover.my_role === "admin";
  const canReassign = handover.my_role === "manager" || handover.my_role === "admin";

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-3">
        <h1 className="text-xl font-semibold">Пробелы</h1>
        {switcher}
      </div>
      <p className="text-sm text-ink-muted">
        Вопросы преемника, на которые ассистент не нашёл ответа. Ответ эксперта станет черновиком
        карточки и попадёт в базу после проверки.
      </p>
      <div role="tablist" aria-label="Статус" className="flex flex-wrap gap-1">
        {TABS.map((t, i) => (
          <button
            key={t.label}
            type="button"
            role="tab"
            aria-selected={i === tab}
            onClick={() => setTab(i)}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm",
              i === tab
                ? "bg-primary-light font-medium text-primary-dark"
                : "text-ink-muted hover:bg-surface",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      {gaps.isPending ? (
        <FullPageSpinner />
      ) : gaps.isError ? (
        <ErrorNote error={gaps.error} />
      ) : gaps.data.length === 0 ? (
        <EmptyState icon={MessageCircleQuestion} title="Здесь пусто">
          {TABS[tab].status === "open"
            ? "Открытых вопросов нет: ассистент находит ответы в базе знаний."
            : "Вопросов с таким статусом нет."}
        </EmptyState>
      ) : (
        <ul className="space-y-3">
          {gaps.data.map((gap) => (
            <li key={gap.id}>
              <GapItem
                gap={gap}
                handoverId={handover.id}
                canAnswer={canAnswer}
                canReassign={canReassign}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function StatusLine({ gap }: { gap: Gap }) {
  const view =
    gap.status === "answered"
      ? { icon: CircleCheck, className: "text-emerald-700" }
      : gap.status === "dismissed"
        ? { icon: MinusCircle, className: "text-ink-muted" }
        : { icon: Clock, className: "text-amber-700" };
  const Icon = view.icon;
  return (
    <span className={cn("inline-flex items-center gap-1.5", view.className)}>
      <Icon className="size-3.5" aria-hidden />
      {gap.status === "open" && gap.answer_on_review
        ? "Ответ на проверке"
        : GAP_STATUS_LABELS[gap.status]}
    </span>
  );
}

function GapItem({
  gap,
  handoverId,
  canAnswer,
  canReassign,
}: {
  gap: Gap;
  handoverId: string;
  canAnswer: boolean;
  canReassign: boolean;
}) {
  const open = gap.status === "open";
  return (
    <Card className="space-y-3 p-4">
      <div className="space-y-1">
        <p className="font-medium">{gap.question}</p>
        <p className="flex flex-wrap gap-x-3 text-xs text-ink-muted">
          <StatusLine gap={gap} />
          {gap.asked_by_name && <span>Спросил(а): {gap.asked_by_name}</span>}
          <span>{new Date(gap.created_at).toLocaleDateString("ru-RU")}</span>
          {gap.assignee_name && <span>Отвечает: {gap.assignee_name}</span>}
        </p>
      </div>
      {gap.answer_text && (
        <blockquote className="border-l-2 border-primary pl-3 text-sm whitespace-pre-line">
          {gap.answer_text}
        </blockquote>
      )}
      {open && gap.answer_on_review && (
        <p className="text-sm">
          Ответ ждёт проверки:{" "}
          <Link
            className="font-medium text-primary hover:underline"
            to={`/review?handover=${handoverId}`}
          >
            открыть «Проверку карточек»
          </Link>
        </p>
      )}
      {gap.status === "answered" && gap.answered_card_id && (
        <Link
          className="text-sm font-medium text-primary hover:underline"
          to={`/knowledge?handover=${handoverId}&card=${gap.answered_card_id}`}
        >
          Открыть карточку в базе знаний
        </Link>
      )}
      {open && !gap.answer_on_review && (canAnswer || canReassign) && (
        <GapActions gap={gap} canAnswer={canAnswer} canReassign={canReassign} />
      )}
    </Card>
  );
}

function GapActions({
  gap,
  canAnswer,
  canReassign,
}: {
  gap: Gap;
  canAnswer: boolean;
  canReassign: boolean;
}) {
  const actions = useGapActions();
  const experts = useUsers("expert", canReassign);
  const [text, setText] = useState("");
  const [assignee, setAssignee] = useState("");
  const [recognizing, setRecognizing] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);

  const onRecorded = useCallback(
    async (audio: Blob) => {
      setRecognizing(true);
      setVoiceError(null);
      try {
        const result = await uploadGapAudio(gap.id, audio);
        setText((current) => (current ? `${current} ${result.text}` : result.text));
      } catch (error) {
        setVoiceError((error as ApiError).message);
      } finally {
        setRecognizing(false);
      }
    },
    [gap.id],
  );
  const recorder = useVoiceRecorder(onRecorded);
  const busy = Object.values(actions).some((a) => a.isPending);
  const error = Object.values(actions).find((a) => a.error)?.error;

  return (
    <div className="space-y-2">
      {canAnswer && (
        <form
          className="space-y-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (text.trim()) actions.answer.mutate({ id: gap.id, text: text.trim() });
          }}
        >
          <Textarea
            rows={3}
            aria-label="Ваш ответ"
            placeholder="Ответьте так, как объяснили бы новому сотруднику."
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" disabled={!text.trim() || busy || recognizing}>
              Ответить
            </Button>
            {recorder.state === "recording" ? (
              <Button type="button" variant="secondary" onClick={recorder.stop}>
                <Square className="size-4 text-danger" aria-hidden />
                Остановить · {recorder.seconds} / {MAX_SECONDS} с
              </Button>
            ) : (
              <Button
                type="button"
                variant="secondary"
                onClick={recorder.start}
                disabled={recorder.state === "unsupported" || recognizing || busy}
              >
                {recognizing ? (
                  <LoaderCircle className="size-4 animate-spin" aria-hidden />
                ) : (
                  <Mic className="size-4" aria-hidden />
                )}
                {recognizing ? "Распознаю…" : "Голосом"}
              </Button>
            )}
          </div>
        </form>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {canReassign && (
          <>
            <Select
              aria-label="Назначить другого эксперта"
              className="w-auto"
              value={assignee}
              onChange={(e) => setAssignee(e.target.value)}
            >
              <option value="">Назначить другого эксперта…</option>
              {(experts.data ?? [])
                .filter((u) => u.id !== gap.assignee_id)
                .map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name}
                  </option>
                ))}
            </Select>
            <Button
              variant="secondary"
              disabled={!assignee || busy}
              onClick={() => actions.reassign.mutate({ id: gap.id, assigneeId: assignee })}
            >
              Назначить
            </Button>
          </>
        )}
        <Button variant="ghost" disabled={busy} onClick={() => actions.dismiss.mutate(gap.id)}>
          Закрыть без ответа
        </Button>
      </div>
      {(recorder.error || voiceError) && (
        <p role="alert" className="text-sm text-danger">
          {recorder.error || voiceError}
        </p>
      )}
      <ErrorNote error={error} />
    </div>
  );
}
