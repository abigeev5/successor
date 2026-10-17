import { ShieldCheck, Trash2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import type { Erased, Handover } from "@/api/client";
import { useMyData, useDeleteRecording, useEraseMyData, useRevokeConsent } from "@/api/privacy";
import { useRecordings } from "@/api/recordings";
import { ErrorNote } from "@/components/ErrorNote";
import { HandoverGate } from "@/components/HandoverGate";
import { FullPageSpinner } from "@/components/Spinner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { formatBytes, MY_DATA_LABELS, RECORDING_STATUS_LABELS, timecode } from "@/lib/labels";

/** «Мои данные» (SPEC 7.3, 9.1): consent, what is stored, deleting a recording or everything. */
export function PrivacyPage() {
  return (
    <HandoverGate
      icon={ShieldCheck}
      emptyTitle="Данных нет"
      emptyText="Здесь появятся ваши согласия и записи, когда вас добавят в передачу дел."
    >
      {(handover, switcher) => <MyData key={handover.id} handover={handover} switcher={switcher} />}
    </HandoverGate>
  );
}

/** A destructive action asks once more, in place, instead of a browser dialog. */
function Confirm({
  label,
  question,
  confirmLabel,
  pending,
  onConfirm,
}: {
  label: ReactNode;
  question: string;
  confirmLabel: string;
  pending: boolean;
  onConfirm: () => void;
}) {
  const [open, setOpen] = useState(false);
  if (!open) {
    return (
      <Button variant="secondary" onClick={() => setOpen(true)}>
        {label}
      </Button>
    );
  }
  return (
    <div
      className="space-y-3 rounded-lg bg-danger-light p-4"
      role="alertdialog"
      aria-label={question}
    >
      <p className="text-sm">{question}</p>
      <div className="flex flex-wrap gap-2">
        <Button variant="danger" onClick={onConfirm} disabled={pending}>
          {confirmLabel}
        </Button>
        <Button variant="ghost" onClick={() => setOpen(false)} disabled={pending}>
          Отмена
        </Button>
      </div>
    </div>
  );
}

function erasedSummary(erased: Erased): string {
  const parts = Object.entries(erased.counts)
    .filter(([, n]) => n > 0)
    .map(([key, n]) => `${MY_DATA_LABELS[key] ?? key}: ${n}`);
  if (erased.files > 0) parts.push(`файлов: ${erased.files}`);
  return parts.length > 0 ? `Удалено — ${parts.join(", ")}.` : "Удалять было нечего.";
}

function MyData({ handover, switcher }: { handover: Handover; switcher: ReactNode }) {
  const data = useMyData(handover.id);
  const recordings = useRecordings(handover.id);
  const revoke = useRevokeConsent();
  const erase = useEraseMyData(handover.id);
  const deleteRecording = useDeleteRecording();

  if (data.isPending) return <FullPageSpinner />;
  if (data.isError) return <ErrorNote error={data.error} />;
  const { consent, counts } = data.data;

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-baseline gap-3">
        <h1 className="text-xl font-semibold">Мои данные</h1>
        {switcher}
      </div>

      <Card className="space-y-3">
        <h2 className="font-semibold">Согласие на запись и обработку</h2>
        {consent ? (
          <>
            <p className="text-sm">
              Принято {new Date(consent.accepted_at).toLocaleDateString("ru-RU")} (версия текста{" "}
              {consent.text_version}).
            </p>
            <Confirm
              label="Отозвать согласие"
              question="После отзыва нельзя будет проходить интервью и записывать экран. Уже собранные данные останутся, пока вы их не удалите ниже."
              confirmLabel="Да, отозвать"
              pending={revoke.isPending}
              onConfirm={() => revoke.mutate(consent.id)}
            />
          </>
        ) : (
          <p className="text-sm">
            Согласие не принято или отозвано: новые интервью и записи недоступны.{" "}
            <Link to={`/consent/${handover.id}`} className="text-primary hover:underline">
              Прочитать согласие
            </Link>
          </p>
        )}
        <ErrorNote error={revoke.error} />
      </Card>

      <Card className="space-y-3">
        <h2 className="font-semibold">Что хранится</h2>
        <dl className="grid max-w-md grid-cols-[1fr_auto] gap-x-6 gap-y-1 text-sm">
          {Object.entries(MY_DATA_LABELS).map(([key, label]) => (
            <div key={key} className="contents">
              <dt className="text-ink-muted">{label}</dt>
              <dd className="tabular-nums">
                {counts[key] ?? 0}
                {key === "files" && counts.files > 0 && ` (${formatBytes(counts.files_bytes)})`}
              </dd>
            </div>
          ))}
        </dl>
        <p className="text-xs text-ink-muted">
          Всё хранится в контуре организации. Видео и голос удаляются автоматически по истечении
          срока хранения; скриншоты с размытыми персональными данными и карточки остаются.
        </p>
      </Card>

      <Card className="space-y-3">
        <h2 className="font-semibold">Мои записи экрана</h2>
        {recordings.data?.length === 0 && <p className="text-sm text-ink-muted">Записей нет.</p>}
        <ul className="space-y-3">
          {recordings.data?.map((r) => (
            <li key={r.id} className="flex flex-wrap items-start justify-between gap-3">
              <div className="text-sm">
                <Link to={`/recordings/${r.id}`} className="font-medium hover:underline">
                  {r.title}
                </Link>
                <p className="text-ink-muted">
                  {new Date(r.created_at).toLocaleDateString("ru-RU")} ·{" "}
                  {RECORDING_STATUS_LABELS[r.status]}
                  {r.duration_ms !== null && ` · ${timecode(r.duration_ms)}`}
                </p>
              </div>
              <Confirm
                label={
                  <>
                    <Trash2 className="size-4" aria-hidden />
                    Удалить запись
                  </>
                }
                question={`Удалить «${r.title}»? Видео, скриншоты и шаги будут удалены. Карточки, у которых не останется других источников, уйдут в архив.`}
                confirmLabel="Да, удалить запись"
                pending={deleteRecording.isPending}
                onConfirm={() => deleteRecording.mutate(r.id)}
              />
            </li>
          ))}
        </ul>
        <ErrorNote error={deleteRecording.error} />
      </Card>

      <Card className="space-y-3">
        <h2 className="font-semibold">Удалить всё</h2>
        <p className="text-sm text-ink-muted">
          Будут удалены интервью, голосовые ответы, записи экрана и ваши ответы на вопросы преемника
          по этой передаче дел. Карточки, у которых не останется источников, уйдут в архив и
          пропадут из ассистента. Отменить удаление нельзя.
        </p>
        {erase.data ? (
          <p role="status" className="text-sm font-medium">
            {erasedSummary(erase.data)}
          </p>
        ) : (
          <Confirm
            label={
              <>
                <Trash2 className="size-4" aria-hidden />
                Удалить мои данные
              </>
            }
            question="Удалить все ваши данные по этой передаче дел? Это нельзя отменить."
            confirmLabel="Да, удалить всё"
            pending={erase.isPending}
            onConfirm={() => erase.mutate()}
          />
        )}
        <ErrorNote error={erase.error} />
      </Card>
    </section>
  );
}
