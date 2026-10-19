import { Circle, MonitorPlay, ShieldAlert, Square, Upload } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import type { ApiError } from "@/api/client";
import { useHandover, useMyConsent } from "@/api/handovers";
import { uploadRecording } from "@/api/recordings";
import { ErrorNote } from "@/components/ErrorNote";
import { PageHeader } from "@/components/PageHeader";
import { FullPageSpinner } from "@/components/Spinner";
import { ProgressBar } from "@/components/StatusBadges";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { timecode } from "@/lib/labels";

import { MAX_MINUTES, useScreenRecorder } from "./useScreenRecorder";

const MAX_FILE_BYTES = 1024 * 1024 * 1024;

export function NewRecordingPage() {
  const [params] = useSearchParams();
  const handoverId = params.get("handover") ?? undefined;
  const handover = useHandover(handoverId);
  const consent = useMyConsent(handoverId);
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [processId, setProcessId] = useState("");
  const [video, setVideo] = useState<Blob | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const onRecorded = useCallback((blob: Blob) => setVideo(blob), []);
  const recorder = useScreenRecorder(onRecorded);

  const preview = useMemo(() => (video ? URL.createObjectURL(video) : null), [video]);
  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview);
    },
    [preview],
  );

  if (!handoverId) return <ErrorNote error={new Error("Не выбрана передача дел")} />;
  if (handover.isPending || consent.isPending) return <FullPageSpinner />;
  if (handover.isError) return <ErrorNote error={handover.error} />;
  const h = handover.data;

  if (consent.data === null) {
    return (
      <Card className="mx-auto flex max-w-xl flex-col items-start gap-3">
        <ShieldAlert className="size-6 text-amber-700" aria-hidden />
        <p className="text-sm">
          Перед записью экрана нужно прочитать и принять согласие на запись и обработку.
        </p>
        <Button onClick={() => navigate(`/consent/${h.id}`)}>Прочитать согласие</Button>
      </Card>
    );
  }

  function pickFile(file: File | undefined) {
    setError(null);
    if (!file) return;
    if (file.size > MAX_FILE_BYTES) {
      setError("Файл больше 1 ГБ. Сократите запись или разбейте её на части.");
      return;
    }
    setVideo(file);
    if (!title) setTitle(file.name.replace(/\.[^.]+$/, ""));
  }

  async function send() {
    if (!video) return;
    setError(null);
    setProgress(0);
    try {
      const recording = await uploadRecording(
        { handoverId: h.id, title: title.trim(), processId, video },
        setProgress,
      );
      navigate(`/recordings/${recording.id}`);
    } catch (e) {
      setError((e as ApiError).message);
      setProgress(null);
    }
  }

  const recording = recorder.state === "recording";
  const uploading = progress !== null;
  return (
    <section className="mx-auto max-w-3xl space-y-5">
      <PageHeader
        eyebrow={
          <Link to={`/handovers/${h.id}`} className="hover:underline">
            Передача дел · новая запись
          </Link>
        }
        title="Запись экрана с комментарием"
        description="Выполните задачу как обычно и рассказывайте вслух, что и зачем делаете. Из записи получится пошаговая инструкция со скриншотами — её вы проверите перед публикацией."
      />

      <Card className="space-y-3">
        <div>
          <Label htmlFor="title">Название</Label>
          <Input
            id="title"
            value={title}
            maxLength={300}
            placeholder="Например: Оформление направления на пересдачу"
            onChange={(e) => setTitle(e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="process">Процесс</Label>
          <Select id="process" value={processId} onChange={(e) => setProcessId(e.target.value)}>
            <option value="">Не выбран</option>
            {h.processes.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
        </div>
      </Card>

      {!video && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Card className="space-y-3">
            <h2 className="flex items-center gap-2 font-semibold">
              <MonitorPlay className="size-5 text-primary" aria-hidden /> Записать экран
            </h2>
            <p className="rounded-xl bg-warning-light px-3 py-2 text-sm">
              Перед началом закройте вкладки и окна с личной информацией: почту, мессенджеры, банк.
              Телефоны, email и ФИО на скриншотах размываются автоматически, но видео сохраняется
              как есть.
            </p>
            {recording ? (
              <Button variant="secondary" onClick={recorder.stop}>
                <Square className="size-4 text-danger" aria-hidden />
                Остановить · {timecode(recorder.seconds * 1000)} / {MAX_MINUTES}:00
              </Button>
            ) : (
              <Button
                onClick={recorder.start}
                disabled={recorder.state === "unsupported"}
                title={
                  recorder.state === "unsupported" ? "Браузер не умеет записывать экран" : undefined
                }
              >
                <Circle className="size-4 fill-current" aria-hidden /> Начать запись
              </Button>
            )}
            {recorder.state === "unsupported" && (
              <p className="text-xs text-ink-muted">
                Этот браузер не записывает экран. Откройте страницу в Chrome, Edge или Firefox на
                компьютере или загрузите готовый файл.
              </p>
            )}
            {recorder.error && (
              <p role="alert" className="text-sm text-danger">
                {recorder.error}
              </p>
            )}
          </Card>
          <Card className="space-y-3">
            <h2 className="flex items-center gap-2 font-semibold">
              <Upload className="size-5 text-primary" aria-hidden /> Загрузить файл
            </h2>
            <p className="text-sm text-ink-muted">MP4, WebM или MOV до 1 ГБ, со звуком.</p>
            <label className="block">
              <span className="sr-only">Видеофайл</span>
              <input
                type="file"
                accept="video/mp4,video/webm,video/quicktime"
                disabled={recording}
                onChange={(e) => pickFile(e.target.files?.[0])}
                className="text-sm"
              />
            </label>
          </Card>
        </div>
      )}

      {video && preview && (
        <Card className="space-y-3">
          <video src={preview} controls className="w-full rounded-xl bg-black" />
          {uploading ? (
            <ProgressBar value={progress} label="Загрузка записи" />
          ) : (
            <div className="flex flex-wrap gap-2">
              <Button onClick={send} disabled={!title.trim()}>
                <Upload className="size-4" aria-hidden /> Загрузить и обработать
              </Button>
              <Button variant="ghost" onClick={() => setVideo(null)}>
                Отменить
              </Button>
              {!title.trim() && (
                <span className="self-center text-xs text-ink-muted">Сначала назовите запись</span>
              )}
            </div>
          )}
        </Card>
      )}
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </section>
  );
}
