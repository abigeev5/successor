import { EyeOff, LoaderCircle, Play, RotateCcw, TriangleAlert } from "lucide-react";
import { useRef } from "react";
import { Link, useParams } from "react-router-dom";

import type { Recording, RecordingStep } from "@/api/client";
import { useRecording, useRetryRecording } from "@/api/recordings";
import { ErrorNote } from "@/components/ErrorNote";
import { FullPageSpinner } from "@/components/Spinner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { RECORDING_STAGE_LABELS, RECORDING_STATUS_LABELS, timecode } from "@/lib/labels";

export function RecordingPage() {
  const { id } = useParams();
  const recording = useRecording(id);
  const retry = useRetryRecording();
  const player = useRef<HTMLVideoElement>(null);

  if (recording.isPending) return <FullPageSpinner />;
  if (recording.isError) return <ErrorNote error={recording.error} />;
  const r = recording.data;

  function seek(ms: number) {
    const video = player.current;
    if (!video) return;
    video.currentTime = ms / 1000;
    video.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
    void video.play?.()?.catch(() => undefined);
  }

  return (
    <section className="space-y-5">
      <div>
        <p className="text-sm text-ink-muted">
          <Link to={`/handovers/${r.handover_id}`} className="hover:underline">
            Передача дел
          </Link>{" "}
          / Запись экрана
        </p>
        <h1 className="mt-1 text-xl font-semibold">{r.title}</h1>
        <p className="mt-1 text-sm text-ink-muted">
          {RECORDING_STATUS_LABELS[r.status]}
          {r.duration_ms !== null && ` · ${timecode(r.duration_ms)}`}
          {r.status === "ready" && ` · шагов: ${r.steps.length}`}
        </p>
      </div>

      <Status recording={r} onRetry={() => retry.mutate(r.id)} retrying={retry.isPending} />
      <ErrorNote error={retry.error} />

      <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        <div className="space-y-3 lg:sticky lg:top-4 lg:self-start">
          <video
            ref={player}
            src={`/api/assets/${r.video_asset_id}`}
            controls
            preload="metadata"
            className="w-full rounded-lg bg-black"
          />
          {r.card_id && (
            <p className="text-sm">
              {r.card_status === "draft" ? (
                <>
                  Из записи получился черновик инструкции.{" "}
                  <Link
                    className="font-medium text-primary hover:underline"
                    to={`/review?handover=${r.handover_id}`}
                  >
                    Проверить и подтвердить
                  </Link>
                </>
              ) : (
                <Link
                  className="font-medium text-primary hover:underline"
                  to={`/knowledge?handover=${r.handover_id}&card=${r.card_id}`}
                >
                  Инструкция в базе знаний
                </Link>
              )}
            </p>
          )}
        </div>
        {r.steps.length > 0 && (
          <ol className="space-y-3" aria-label="Шаги">
            {r.steps.map((s) => (
              <li key={s.id}>
                <StepCard step={s} onSeek={seek} />
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}

function Status({
  recording: r,
  onRetry,
  retrying,
}: {
  recording: Recording;
  onRetry: () => void;
  retrying: boolean;
}) {
  if (r.status === "uploaded" || r.status === "processing") {
    return (
      <Card className="flex items-center gap-3 p-4 text-sm" role="status">
        <LoaderCircle className="size-5 animate-spin text-primary" aria-hidden />
        <span>
          {r.stage ? RECORDING_STAGE_LABELS[r.stage] : "Запись ждёт обработки"}… Страницу можно
          закрыть: обработка идёт на сервере.
        </span>
      </Card>
    );
  }
  if (r.status === "failed") {
    return (
      <div
        className="flex flex-wrap items-center gap-3 rounded-lg bg-danger-light p-4 text-sm"
        role="alert"
      >
        <TriangleAlert className="size-5 text-danger" aria-hidden />
        <span className="flex-1">{r.error ?? "Запись не удалось обработать."}</span>
        <Button variant="secondary" onClick={onRetry} disabled={retrying}>
          <RotateCcw className="size-4" aria-hidden /> Обработать заново
        </Button>
      </div>
    );
  }
  return null;
}

function StepCard({ step: s, onSeek }: { step: RecordingStep; onSeek: (ms: number) => void }) {
  return (
    <Card className="space-y-2 p-4">
      <div className="flex items-baseline gap-2">
        <span className="font-semibold text-primary-dark">{s.idx}.</span>
        <h3 className="flex-1 font-medium">{s.title}</h3>
        <Button
          variant="ghost"
          className="px-2 py-1 text-xs"
          onClick={() => onSeek(s.start_ms)}
          title="Показать этот шаг в видео"
        >
          <Play className="size-3.5" aria-hidden />
          {timecode(s.start_ms)}–{timecode(s.end_ms)}
        </Button>
      </div>
      {s.action && s.action !== s.title && <p className="text-sm">{s.action}</p>}
      {s.rationale && (
        <p className="text-sm text-ink-muted">
          <span className="font-medium text-ink">Почему так:</span> {s.rationale}
        </p>
      )}
      {s.screenshot_asset_id ? (
        <a href={`/api/assets/${s.screenshot_asset_id}`} target="_blank" rel="noreferrer">
          <img
            src={`/api/assets/${s.screenshot_asset_id}`}
            alt={`Скриншот шага ${s.idx}`}
            loading="lazy"
            className="w-full rounded-md border border-black/10"
          />
        </a>
      ) : (
        <p className="text-xs text-ink-muted">
          Скриншота нет: кадр не удалось проверить на персональные данные, поэтому он не сохранён.
        </p>
      )}
      {s.screenshot_blurred && (
        <p className="flex items-center gap-1.5 text-xs text-ink-muted">
          <EyeOff className="size-3.5" aria-hidden /> Персональные данные скрыты автоматически
        </p>
      )}
    </Card>
  );
}
