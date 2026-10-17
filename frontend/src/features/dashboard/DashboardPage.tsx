import { CalendarClock, Download, LayoutDashboard } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import type { Handover, Metrics, ProcessRisk } from "@/api/client";
import {
  metricsCsvUrl,
  useMetrics,
  useProgress,
  useRiskMap,
  type MetricsFilter,
} from "@/api/dashboard";
import { useHandovers } from "@/api/handovers";
import { EmptyState } from "@/components/EmptyState";
import { ErrorNote } from "@/components/ErrorNote";
import { handoverLabel } from "@/components/HandoverGate";
import { ProgressFacts } from "@/components/ProgressFacts";
import { FullPageSpinner } from "@/components/Spinner";
import { AspectCellIcon, CELL_LEGEND, ProgressBar, RiskBadge } from "@/components/StatusBadges";
import { Card } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/cn";
import { CRITICALITY_LABELS, daysLeft } from "@/lib/labels";

/** Manager dashboard (SPEC 7.9): risk map, the «processes × aspects» matrix, handovers, metrics. */
export function DashboardPage() {
  const risk = useRiskMap();
  const handovers = useHandovers();

  if (risk.isPending) return <FullPageSpinner />;
  if (risk.isError) return <ErrorNote error={risk.error} />;
  const processes = risk.data.processes;

  return (
    <section className="space-y-8">
      <div>
        <h1 className="text-xl font-semibold">Панель руководителя</h1>
        <p className="mt-1 text-sm text-ink-muted">{risk.data.org_unit_name}</p>
      </div>

      {processes.length === 0 ? (
        <EmptyState icon={LayoutDashboard} title="Процессов пока нет">
          Добавьте процессы подразделения при создании передачи дел — здесь появится карта рисков:
          какие из них держатся на одном человеке и сколько знаний уже сохранено.
        </EmptyState>
      ) : (
        <>
          <RiskTable processes={processes} />
          <AspectMatrix processes={processes} />
        </>
      )}

      {handovers.data && handovers.data.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Передачи дел</h2>
          <div className="grid gap-3 md:grid-cols-2">
            {handovers.data.map((h) => (
              <HandoverProgressCard key={h.id} handover={h} />
            ))}
          </div>
        </div>
      )}

      <MetricsBlock handovers={handovers.data ?? []} />
    </section>
  );
}

function RiskTable({ processes }: { processes: ProcessRisk[] }) {
  return (
    <div className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold">Карта рисков</h2>
        <p className="text-sm text-ink-muted">
          Риск выше, если процесс важный, его больше никто не знает, срок близко, а подтверждённых
          карточек мало.
        </p>
      </div>
      <div className="overflow-x-auto rounded-lg border border-black/10">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="bg-surface text-xs text-ink-muted">
            <tr>
              <th className="px-3 py-2 font-medium">Процесс</th>
              <th className="px-3 py-2 font-medium">Важность</th>
              <th className="px-3 py-2 font-medium">Кто ещё знает</th>
              <th className="w-40 px-3 py-2 font-medium">Покрытие карточками</th>
              <th className="px-3 py-2 font-medium">Пробелы</th>
              <th className="px-3 py-2 font-medium">Срок</th>
              <th className="px-3 py-2 font-medium">Риск</th>
            </tr>
          </thead>
          <tbody>
            {processes.map((p) => (
              <tr key={p.process_id} className="border-t border-black/10 align-top">
                <td className="px-3 py-2 font-medium">{p.name}</td>
                <td className="px-3 py-2">{CRITICALITY_LABELS[p.criticality]}</td>
                <td className="px-3 py-2">
                  {p.holders.length > 0 ? (
                    p.holders.map((h) => h.full_name).join(", ")
                  ) : (
                    <span className="text-danger">никто</span>
                  )}
                </td>
                <td className="px-3 py-2">
                  <ProgressBar value={p.coverage} label={`Покрытие процесса «${p.name}»`} />
                </td>
                <td className="px-3 py-2 tabular-nums">{p.open_gaps}</td>
                <td className="px-3 py-2">
                  {p.deadline ? (
                    <span className="flex items-center gap-1 whitespace-nowrap">
                      <CalendarClock className="size-3.5 shrink-0" aria-hidden />
                      {daysLeft(p.deadline)}
                    </span>
                  ) : (
                    <span className="text-ink-muted">нет</span>
                  )}
                </td>
                <td className="px-3 py-2" title={`Оценка риска: ${p.risk.toFixed(2)}`}>
                  <RiskBadge level={p.level} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AspectMatrix({ processes }: { processes: ProcessRisk[] }) {
  const aspects = processes[0].aspects;
  return (
    <div className="space-y-3">
      <h2 className="text-lg font-semibold">Что уже передано: процессы × аспекты</h2>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-muted">
        {CELL_LEGEND.map(({ status, icon: Icon, text, className }) => (
          <li key={status} className="flex items-center gap-1">
            <Icon className={cn("size-3.5", className)} aria-hidden />
            {text}
          </li>
        ))}
      </ul>
      <div className="overflow-x-auto rounded-lg border border-black/10">
        <table className="w-full min-w-[900px] text-sm">
          <thead className="bg-surface text-xs text-ink-muted">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Процесс</th>
              {aspects.map((a) => (
                <th key={a.key} className="px-1 py-2 text-center align-bottom font-medium">
                  {a.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {processes.map((p) => (
              <tr key={p.process_id} className="border-t border-black/10">
                <td className="px-3 py-2 font-medium">{p.name}</td>
                {p.aspects.map((cell) => (
                  <td key={cell.key} className="px-1 py-2 text-center">
                    <AspectCellIcon cell={cell} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function HandoverProgressCard({ handover }: { handover: Handover }) {
  const progress = useProgress(handover.id);
  const p = progress.data;
  return (
    <Link to={`/handovers/${handover.id}`} className="block">
      <Card className="space-y-2 p-4 text-sm hover:bg-primary-light/60">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <span className="font-medium">{handoverLabel(handover)}</span>
          {handover.deadline && (
            <span className="text-xs text-ink-muted">срок {daysLeft(handover.deadline)}</span>
          )}
        </div>
        {p ? <ProgressFacts progress={p} /> : <ErrorNote error={progress.error} />}
      </Card>
    </Link>
  );
}

function percent(share: number | null): string {
  return share === null ? "—" : `${Math.round(share * 100)}%`;
}

function MetricsBlock({ handovers }: { handovers: Handover[] }) {
  const [filter, setFilter] = useState<MetricsFilter>({ handoverId: "", from: "", to: "" });
  const metrics = useMetrics(filter);
  const set = (patch: Partial<MetricsFilter>) => setFilter((f) => ({ ...f, ...patch }));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 className="text-lg font-semibold">Метрики</h2>
        <a
          href={metricsCsvUrl(filter)}
          download
          className="inline-flex items-center gap-2 rounded-md bg-surface px-4 py-2 text-sm font-medium hover:bg-primary-light"
        >
          <Download className="size-4" aria-hidden />
          Выгрузить CSV
        </a>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <Label htmlFor="metrics-handover">Передача дел</Label>
          <Select
            id="metrics-handover"
            className="w-auto"
            value={filter.handoverId}
            onChange={(e) => set({ handoverId: e.target.value })}
          >
            <option value="">Все передачи подразделения</option>
            {handovers.map((h) => (
              <option key={h.id} value={h.id}>
                {handoverLabel(h)}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <Label htmlFor="metrics-from">С</Label>
          <Input
            id="metrics-from"
            type="date"
            className="w-auto"
            value={filter.from}
            onChange={(e) => set({ from: e.target.value })}
          />
        </div>
        <div>
          <Label htmlFor="metrics-to">По</Label>
          <Input
            id="metrics-to"
            type="date"
            className="w-auto"
            value={filter.to}
            onChange={(e) => set({ to: e.target.value })}
          />
        </div>
      </div>
      <ErrorNote error={metrics.error} />
      {metrics.data && <MetricTiles m={metrics.data} />}
    </div>
  );
}

function Tile({ title, value, note }: { title: string; value: string; note?: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs text-ink-muted">{title}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {note && <p className="mt-1 text-xs text-ink-muted">{note}</p>}
    </Card>
  );
}

function MetricTiles({ m }: { m: Metrics }) {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Tile
          title="Время эксперта"
          value={`${m.expert_minutes} мин`}
          note={`интервью ${m.interview_minutes}, записи ${m.recording_minutes}, проверка ${m.review_minutes}`}
        />
        <Tile
          title="Подтверждено карточек"
          value={String(m.cards_approved)}
          note={`${percent(m.approved_share)} из сгенерированных, с правками ${m.cards_approved_edited}`}
        />
        <Tile
          title="Ассистент ответил сам"
          value={percent(m.answered_share)}
          note={`вопросов ${m.questions}, отказов ${percent(m.refused_share)}`}
        />
        <Tile
          title="Оценка «помогло»"
          value={percent(m.helpful_share)}
          note={`оценок ${m.feedback_count}`}
        />
        <Tile
          title="Пробелы"
          value={`${m.gaps_answered} из ${m.gaps_created}`}
          note={`закрыто ответом; открыто сейчас ${m.gaps_open_now}`}
        />
        <Tile
          title="Покрытие ключевых процессов"
          value={percent(m.key_processes_coverage)}
          note="процессы высокой важности"
        />
        <Tile
          title="Задержка ответа p95"
          value={
            m.answer_latency_p95_ms === null
              ? "—"
              : `${(m.answer_latency_p95_ms / 1000).toFixed(1)} с`
          }
        />
      </div>
      {m.top_open_gaps.length > 0 && (
        <div>
          <h3 className="mb-2 font-medium">Открытые вопросы преемника</h3>
          <ul className="space-y-1 text-sm">
            {m.top_open_gaps.map((g) => (
              <li key={g.id}>
                <Link to={`/gaps?handover=${g.handover_id}`} className="hover:underline">
                  {g.question}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
