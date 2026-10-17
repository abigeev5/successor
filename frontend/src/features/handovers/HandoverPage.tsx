import {
  CalendarClock,
  ClipboardCheck,
  MessageSquareText,
  MonitorPlay,
  ShieldAlert,
} from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { useCards } from "@/api/cards";
import { useProgress } from "@/api/dashboard";
import { useHandover, useMyConsent } from "@/api/handovers";
import { useCoverage, useSessions, useStartInterview } from "@/api/interviews";
import { useRecordings } from "@/api/recordings";
import { ErrorNote } from "@/components/ErrorNote";
import { ProgressFacts } from "@/components/ProgressFacts";
import { FullPageSpinner } from "@/components/Spinner";
import { AspectBadge, ProgressBar } from "@/components/StatusBadges";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  CRITICALITY_LABELS,
  daysLeft,
  formatMinutes,
  REASON_LABELS,
  RECORDING_STATUS_LABELS,
  timecode,
} from "@/lib/labels";

const SESSION_STATUS: Record<string, string> = {
  active: "идёт",
  paused: "на паузе",
  finished: "завершена",
};

export function HandoverPage() {
  const { id } = useParams();
  const handover = useHandover(id);
  const role = handover.data?.my_role;
  const isExpert = role === "expert";
  const canSeeSessions = isExpert || role === "admin";
  const consent = useMyConsent(isExpert ? id : undefined);
  const coverage = useCoverage(id);
  const sessions = useSessions(id, canSeeSessions);
  const drafts = useCards(role && role !== "successor" ? id : undefined, "draft");
  const canSeeRecordings = canSeeSessions || role === "manager";
  const recordings = useRecordings(id, canSeeRecordings);
  const progress = useProgress(id, canSeeRecordings);
  const start = useStartInterview();
  const navigate = useNavigate();

  if (handover.isPending) return <FullPageSpinner />;
  if (handover.isError) return <ErrorNote error={handover.error} />;
  const h = handover.data;
  const unfinished = sessions.data?.find((s) => s.status !== "finished");

  return (
    <section className="space-y-6">
      <div>
        <p className="text-sm text-ink-muted">
          <Link to="/handovers" className="hover:underline">
            Передачи дел
          </Link>{" "}
          / {h.org_unit_name}
        </p>
        <h1 className="mt-1 text-xl font-semibold">
          Передача дел: {h.experts.map((e) => e.full_name).join(", ")}
        </h1>
        <p className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-muted">
          <span>{REASON_LABELS[h.reason]}</span>
          <span>Преемник: {h.successors.map((s) => s.full_name).join(", ") || "не назначен"}</span>
          <span>Руководитель: {h.manager.full_name}</span>
          {h.deadline && (
            <span className="flex items-center gap-1">
              <CalendarClock className="size-3.5" aria-hidden />
              Срок {new Date(h.deadline).toLocaleDateString("ru-RU")} ({daysLeft(h.deadline)})
            </span>
          )}
        </p>
      </div>

      {isExpert && consent.data === null && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg bg-warning-light p-6">
          <ShieldAlert className="size-5 text-amber-700" aria-hidden />
          <p className="flex-1 text-sm">
            Перед интервью нужно прочитать и принять согласие на запись и обработку рабочих бесед.
          </p>
          <Button onClick={() => navigate(`/consent/${h.id}`)}>Прочитать согласие</Button>
        </div>
      )}

      {isExpert && consent.data && (
        <div className="flex flex-wrap gap-3">
          <Button
            onClick={() => start.mutate(h.id, { onSuccess: (s) => navigate(`/interview/${s.id}`) })}
            disabled={start.isPending}
          >
            <MessageSquareText className="size-4" aria-hidden />
            {unfinished ? "Продолжить интервью" : "Начать интервью"}
          </Button>
          <Button variant="secondary" onClick={() => navigate(`/recordings/new?handover=${h.id}`)}>
            <MonitorPlay className="size-4" aria-hidden />
            Записать экран
          </Button>
          <Button variant="secondary" onClick={() => navigate(`/review?handover=${h.id}`)}>
            <ClipboardCheck className="size-4" aria-hidden />
            Проверить карточки
            {drafts.data && drafts.data.length > 0 && (
              <span className="rounded-full bg-primary px-2 text-xs text-white">
                {drafts.data.length}
              </span>
            )}
          </Button>
        </div>
      )}
      <ErrorNote error={start.error} />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-3 lg:col-span-2">
          <h2 className="text-lg font-semibold">Процессы и покрытие интервью</h2>
          {coverage.data?.length === 0 && (
            <p className="text-sm text-ink-muted">
              Процессы ещё не выбраны. Эксперт перечислит свои задачи в начале интервью.
            </p>
          )}
          {coverage.data?.map((p) => (
            <Card key={p.process_id} className="p-4">
              <details>
                <summary className="cursor-pointer list-none">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="font-medium">{p.name}</span>
                    <span className="text-xs text-ink-muted">
                      Важность: {CRITICALITY_LABELS[p.criticality].toLowerCase()}
                    </span>
                  </div>
                  <div className="mt-2">
                    <ProgressBar value={p.coverage} label={`Покрытие процесса «${p.name}»`} />
                  </div>
                </summary>
                <ul className="mt-3 grid gap-1 sm:grid-cols-2">
                  {p.aspects.map((a) => (
                    <AspectBadge
                      key={a.key}
                      label={a.label}
                      status={a.status}
                      notApplicable={a.not_applicable}
                    />
                  ))}
                </ul>
              </details>
            </Card>
          ))}
        </div>

        <div className="space-y-6">
          {progress.data && (
            <div className="space-y-3">
              <h2 className="text-lg font-semibold">Прогресс</h2>
              <Card className="p-4 text-sm">
                <ProgressFacts progress={progress.data} />
              </Card>
            </div>
          )}
          {canSeeSessions && (
            <div className="space-y-3">
              <h2 className="text-lg font-semibold">Сессии интервью</h2>
              {sessions.data?.length === 0 && (
                <p className="text-sm text-ink-muted">Интервью ещё не проводилось.</p>
              )}
              <ul className="space-y-2">
                {sessions.data?.map((s) => (
                  <li key={s.id}>
                    <Link to={`/interview/${s.id}`} className="block">
                      <Card className="p-3 text-sm hover:bg-primary-light/60">
                        <p className="font-medium">
                          {new Date(s.started_at).toLocaleDateString("ru-RU")} ·{" "}
                          {SESSION_STATUS[s.status]}
                        </p>
                        <p className="text-ink-muted">
                          {s.messages_count} реплик · {formatMinutes(s.active_seconds)}
                        </p>
                      </Card>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {canSeeRecordings && (
            <div className="space-y-3">
              <h2 className="text-lg font-semibold">Записи экрана</h2>
              {recordings.data?.length === 0 && (
                <p className="text-sm text-ink-muted">
                  Записей пока нет. Эксперт записывает экран, когда выполняет задачу и комментирует.
                </p>
              )}
              <ul className="space-y-2">
                {recordings.data?.map((r) => (
                  <li key={r.id}>
                    <Link to={`/recordings/${r.id}`} className="block">
                      <Card className="p-3 text-sm hover:bg-primary-light/60">
                        <p className="font-medium">{r.title}</p>
                        <p className="text-ink-muted">
                          {RECORDING_STATUS_LABELS[r.status]}
                          {r.duration_ms !== null && ` · ${timecode(r.duration_ms)}`}
                        </p>
                      </Card>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
