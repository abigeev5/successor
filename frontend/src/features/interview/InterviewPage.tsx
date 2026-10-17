import {
  CheckCircle2,
  LoaderCircle,
  Mic,
  Pause,
  Play,
  Send,
  SkipForward,
  Square,
  Volume2,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { Link, useParams } from "react-router-dom";

import type { ApiError } from "@/api/client";
import { uploadAudio, useSession, useSessionActions } from "@/api/interviews";
import { ErrorNote } from "@/components/ErrorNote";
import { FullPageSpinner } from "@/components/Spinner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/select";
import { cn } from "@/lib/cn";
import { formatMinutes } from "@/lib/labels";

import { CandidatesPanel } from "./CandidatesPanel";
import { CoveragePanel } from "./CoveragePanel";
import { MAX_SECONDS, useVoiceRecorder } from "./useVoiceRecorder";

export function InterviewPage() {
  const { sessionId = "" } = useParams();
  const session = useSession(sessionId);
  const actions = useSessionActions(sessionId);
  const [text, setText] = useState("");
  const [audioId, setAudioId] = useState<string | null>(null);
  const [recognizing, setRecognizing] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [sentText, setSentText] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const onRecorded = useCallback(
    async (audio: Blob) => {
      setRecognizing(true);
      setVoiceError(null);
      try {
        const result = await uploadAudio(sessionId, audio);
        setText((current) => (current ? `${current} ${result.text}` : result.text));
        setAudioId(result.asset_id);
      } catch (error) {
        setVoiceError((error as ApiError).message);
      } finally {
        setRecognizing(false);
      }
    },
    [sessionId],
  );
  const recorder = useVoiceRecorder(onRecorded);

  const messagesCount = session.data?.messages.length ?? 0;
  useEffect(() => {
    bottom.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [messagesCount, sentText]);

  if (session.isPending) return <FullPageSpinner />;
  if (session.isError) return <ErrorNote error={session.error} />;
  const s = session.data;
  const finished = s.status === "finished";
  const paused = s.status === "paused";
  const busy = Object.values(actions).some((a) => a.isPending);
  const actionError = Object.values(actions).find((a) => a.error)?.error;

  function send(event?: FormEvent) {
    event?.preventDefault();
    const value = text.trim();
    if (!value || busy) return;
    setSentText(value);
    actions.send.mutate(
      { text: value, audio_asset_id: audioId },
      {
        onSuccess: () => {
          setText("");
          setAudioId(null);
        },
        onSettled: () => setSentText(null),
      },
    );
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) send();
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <section className="flex min-h-[70vh] flex-col">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <h1 className="mr-auto text-xl font-semibold">Интервью</h1>
          <span className="text-xs text-ink-muted">
            Активное время: {formatMinutes(s.active_seconds)}
          </span>
          {!finished && (
            <>
              {paused ? (
                <Button variant="secondary" onClick={() => actions.resume.mutate()} disabled={busy}>
                  <Play className="size-4" aria-hidden /> Продолжить
                </Button>
              ) : (
                <Button variant="secondary" onClick={() => actions.pause.mutate()} disabled={busy}>
                  <Pause className="size-4" aria-hidden /> Пауза
                </Button>
              )}
              <Button
                variant="secondary"
                onClick={() => actions.nextProcess.mutate()}
                disabled={busy}
              >
                <SkipForward className="size-4" aria-hidden /> Следующий процесс
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  if (
                    window.confirm("Завершить сессию? После этого появятся черновики карточек.")
                  ) {
                    actions.finish.mutate();
                  }
                }}
                disabled={busy}
              >
                <Square className="size-4" aria-hidden /> Завершить
              </Button>
            </>
          )}
        </div>

        <ol
          className="flex-1 space-y-3 overflow-y-auto rounded-lg bg-surface p-4"
          aria-live="polite"
        >
          {s.messages.map((m) => (
            <li
              key={m.id}
              className={cn(
                "max-w-[85%] whitespace-pre-line rounded-lg px-4 py-2.5 text-sm",
                m.role === "interviewer" ? "bg-white" : "ml-auto bg-primary text-white",
              )}
            >
              <span className="sr-only">{m.role === "interviewer" ? "Интервьюер: " : "Вы: "}</span>
              {m.content}
              {m.has_audio && (
                <Volume2 className="ml-1.5 inline size-3.5 opacity-70" aria-label="ответ голосом" />
              )}
            </li>
          ))}
          {sentText && (
            <>
              <li className="ml-auto max-w-[85%] whitespace-pre-line rounded-lg bg-primary/70 px-4 py-2.5 text-sm text-white">
                {sentText}
              </li>
              <li className="flex items-center gap-2 text-sm text-ink-muted" role="status">
                <LoaderCircle className="size-4 animate-spin" aria-hidden /> Интервьюер думает…
              </li>
            </>
          )}
          <div ref={bottom} />
        </ol>

        <ErrorNote error={actionError} />
        {finished ? (
          <div className="mt-3 flex flex-wrap items-center gap-3 rounded-lg bg-primary-light p-4 text-sm">
            <CheckCircle2 className="size-5 text-primary" aria-hidden />
            <span className="flex-1">
              Сессия завершена. Черновики карточек появятся на проверке через несколько минут.
            </span>
            <Link
              to={`/review?handover=${s.handover_id}`}
              className="font-medium text-primary hover:underline"
            >
              Перейти к проверке
            </Link>
          </div>
        ) : (
          <form onSubmit={send} className="mt-3 space-y-2">
            <Textarea
              rows={3}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder={
                recognizing ? "Распознаю речь…" : "Ваш ответ. Лучше на примере последнего случая."
              }
              aria-label="Ваш ответ"
              disabled={recognizing}
            />
            <div className="flex flex-wrap items-center gap-2">
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
                  title={
                    recorder.state === "unsupported" ? "Браузер не поддерживает запись" : undefined
                  }
                >
                  {recognizing ? (
                    <LoaderCircle className="size-4 animate-spin" aria-hidden />
                  ) : (
                    <Mic className="size-4" aria-hidden />
                  )}
                  {recognizing ? "Распознаю…" : "Ответить голосом"}
                </Button>
              )}
              <span className="mr-auto text-xs text-ink-muted">
                {audioId ? "Текст распознан — проверьте и поправьте перед отправкой. " : ""}
                Ctrl+Enter — отправить
              </span>
              <Button type="submit" disabled={!text.trim() || busy || recognizing}>
                <Send className="size-4" aria-hidden /> Отправить
              </Button>
            </div>
            {(recorder.error || voiceError) && (
              <p role="alert" className="text-sm text-danger">
                {recorder.error || voiceError}
              </p>
            )}
          </form>
        )}
      </section>

      <aside className="space-y-4 rounded-lg bg-surface p-4">
        {s.candidates.length > 0 && !finished && (
          <CandidatesPanel
            key={s.candidates.map((c) => c.name).join("|")}
            candidates={s.candidates}
            pending={actions.confirm.isPending}
            onConfirm={(items) => actions.confirm.mutate(items)}
          />
        )}
        <CoveragePanel coverage={s.coverage} currentProcessId={s.current_process_id} />
      </aside>
    </div>
  );
}
