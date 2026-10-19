import { ArrowUpRight, CalendarClock, Download, LayoutDashboard } from "lucide-react";
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
import { PageHeader, Section, StatTile, TABLE_HEAD, TABLE_WRAP } from "@/components/PageHeader";
import { ProgressFacts } from "@/components/ProgressFacts";
import { FullPageSpinner } from "@/components/Spinner";
import { AspectCellIcon, CELL_LEGEND, ProgressBar, RiskBadge } from "@/components/StatusBadges";
import { Input, Label } from "@/components/ui/input";
import { Pill } from "@/components/ui/pill";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/cn";
import { CRITICALITY_LABELS, daysLeft, plural } from "@/lib/labels";

export function DashboardPage() {
  const risk = useRiskMap();
  const handovers = useHandovers();

  if (risk.isPending) return <FullPageSpinner />;
  if (risk.isError) return <ErrorNote error={risk.error} />;
  const processes = risk.data.processes;

  return (
    <div className="space-y-12">
      <PageHeader
        eyebrow={risk.data.org_unit_name}
        title="Панель руководителя"
        description="Какие процессы держатся на одном человеке и сколько знаний уже сохранено."
      />

      {processes.length === 0 ? (
        <EmptyState icon={LayoutDashboard} title="Процессов пока нет">
          Добавьте процессы подразделения при создании передачи дел — здесь появится карта рисков:
          какие из них держатся на одном человеке и сколько знаний уже сохранено.
        </EmptyState>
      ) : (
        <>
          <Summary processes={processes} />
          <RiskTable processes={processes} />
          <AspectMatrix processes={processes} />
        </>
      )}

      {handovers.data && handovers.data.length > 0 && (
        <Section title="Передачи дел">
          <div className="grid gap-4 md:grid-cols-2">
            {handovers.data.map((h) => (
              <HandoverProgressCard key={h.id} handover={h} />
            ))}
          </div>
        </Section>
      )}

      <MetricsBlock handovers={handovers.data ?? []} />
    </div>
  );
}

function percent(share: number | null): string {
  return share === null ? "—" : `${Math.round(share * 100)}%`;
}

function Summary({ processes }: { processes: ProcessRisk[] }) {
  const atRisk = processes.filter((p) => p.level !== "low").length;
  const alone = processes.filter((p) => p.holders.length === 0).length;
  const coverage = processes.reduce((sum, p) => sum + p.coverage, 0) / processes.length;
  const days = processes.flatMap((p) => (p.days_left === null ? [] : [p.days_left]));
  const nearest = days.length > 0 ? Math.min(...days) : null;
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatTile
        value={`${atRisk} из ${processes.length}`}
        title="процессов под риском"
        note="уровень «Средний» или «Высокий»"
      />
      <StatTile value={alone} title="держатся на одном человеке" note="больше никто не знает" />
      <StatTile
        value={percent(coverage)}
        title="покрытие карточками"
        note="в среднем по процессам"
      />
      <StatTile
        value={nearest === null ? "—" : plural(Math.max(nearest, 0), "день", "дня", "дней")}
        title="до ближайшего срока"
        note={nearest !== null && nearest < 0 ? "срок уже прошёл" : "передачи дел подразделения"}
      />
    </div>
  );
}

function RiskTable({ processes }: { processes: ProcessRisk[] }) {
  return (
    <Section
      title="Карта рисков"
      description="Риск выше, если процесс важный, его больше никто не знает, срок близко, а подтверждённых карточек мало."
    >
      <div className={TABLE_WRAP}>
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className={TABLE_HEAD}>
            <tr>
              <th className="px-4 py-3 font-medium">Процесс</th>
              <th className="px-4 py-3 font-medium">Важность</th>
              <th className="px-4 py-3 font-medium">Кто ещё знает</th>
              <th className="w-44 px-4 py-3 font-medium">Покрытие карточками</th>
              <th className="px-4 py-3 font-medium">Пробелы</th>
              <th className="px-4 py-3 font-medium">Срок</th>
              <th className="px-4 py-3 font-medium">Риск</th>
            </tr>
          </thead>
          <tbody>
            {processes.map((p) => (
              <tr key={p.process_id} className="border-t border-line align-middle">
                <td className="px-4 py-3.5 font-medium">{p.name}</td>
                <td className="px-4 py-3.5 text-ink-muted">{CRITICALITY_LABELS[p.criticality]}</td>
                <td className="px-4 py-3.5">
                  {p.holders.length > 0 ? (
                    p.holders.map((h) => h.full_name).join(", ")
                  ) : (
                    <span className="font-medium text-danger">никто</span>
                  )}
                </td>
                <td className="px-4 py-3.5">
                  <ProgressBar value={p.coverage} label={`Покрытие процесса «${p.name}»`} />
                </td>
                <td className="px-4 py-3.5 tabular-nums">{p.open_gaps}</td>
                <td className="px-4 py-3.5">
                  {p.deadline ? (
                    <span className="flex items-center gap-1.5 whitespace-nowrap text-ink-muted">
                      <CalendarClock className="size-3.5 shrink-0" aria-hidden />
                      {daysLeft(p.deadline)}
                    </span>
                  ) : (
                    <span className="text-ink-soft">нет</span>
                  )}
                </td>
                <td className="px-4 py-3.5" title={`Оценка риска: ${p.risk.toFixed(2)}`}>
                  <RiskBadge level={p.level} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function AspectMatrix({ processes }: { processes: ProcessRisk[] }) {
  const aspects = processes[0].aspects;
  return (
    <Section
      title="Что уже передано"
      description="Процессы × аспекты: что подтверждено карточками, что только рассказано в интервью."
      actions={
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-muted">
          {CELL_LEGEND.map(({ status, icon: Icon, text, className }) => (
            <li key={status} className="flex items-center gap-1.5">
              <Icon className={cn("size-3.5", className)} aria-hidden />
              {text}
            </li>
          ))}
        </ul>
      }
    >
      <div className={TABLE_WRAP}>
        <table className="w-full min-w-[960px] text-sm">
          <thead className={TABLE_HEAD}>
            <tr>
              <th className="px-4 py-3 text-left font-medium">Процесс</th>
              {aspects.map((a) => (
                <th key={a.key} className="px-1.5 py-3 text-center align-bottom font-medium">
                  {a.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {processes.map((p) => (
              <tr key={p.process_id} className="border-t border-line">
                <td className="px-4 py-3 font-medium">{p.name}</td>
                {p.aspects.map((cell) => (
                  <td key={cell.key} className="px-1.5 py-3 text-center">
                    <AspectCellIcon cell={cell} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function HandoverProgressCard({ handover }: { handover: Handover }) {
  const progress = useProgress(handover.id);
  return (
    <Link
      to={`/handovers/${handover.id}`}
      className="group block rounded-[var(--radius-card)] bg-surface p-6 transition-colors hover:bg-primary-faint"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-2">
          {handover.deadline && <Pill>Срок {daysLeft(handover.deadline)}</Pill>}
          <p className="text-lg font-semibold tracking-tight">{handoverLabel(handover)}</p>
        </div>
        <ArrowUpRight
          className="size-5 shrink-0 text-ink-soft transition-colors group-hover:text-primary"
          aria-hidden
        />
      </div>
      <div className="mt-4 text-sm">
        {progress.data ? (
          <ProgressFacts progress={progress.data} />
        ) : (
          <ErrorNote error={progress.error} />
        )}
      </div>
    </Link>
  );
}

function MetricsBlock({ handovers }: { handovers: Handover[] }) {
  const [filter, setFilter] = useState<MetricsFilter>({ handoverId: "", from: "", to: "" });
  const metrics = useMetrics(filter);
  const set = (patch: Partial<MetricsFilter>) => setFilter((f) => ({ ...f, ...patch }));

  return (
    <Section
      title="Метрики"
      description="Время эксперта, качество карточек и ответов ассистента за выбранный период."
      actions={
        <a
          href={metricsCsvUrl(filter)}
          download
          className="inline-flex h-10 items-center gap-2 rounded-xl bg-white px-5 text-sm font-medium ring-1 ring-line ring-inset transition-colors hover:text-primary-dark hover:ring-primary/40"
        >
          <Download className="size-4" aria-hidden />
          Выгрузить CSV
        </a>
      }
    >
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <Label htmlFor="metrics-handover">Передача дел</Label>
          <Select
            id="metrics-handover"
            fit
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
            fit
            value={filter.from}
            onChange={(e) => set({ from: e.target.value })}
          />
        </div>
        <div>
          <Label htmlFor="metrics-to">По</Label>
          <Input
            id="metrics-to"
            type="date"
            fit
            value={filter.to}
            onChange={(e) => set({ to: e.target.value })}
          />
        </div>
      </div>
      <ErrorNote error={metrics.error} />
      {metrics.data && <MetricTiles m={metrics.data} />}
    </Section>
  );
}

function MetricTiles({ m }: { m: Metrics }) {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          value={`${m.expert_minutes} мин`}
          title="Время эксперта"
          note={`интервью ${m.interview_minutes}, записи ${m.recording_minutes}, проверка ${m.review_minutes}`}
        />
        <StatTile
          value={m.cards_approved}
          title="Подтверждено карточек"
          note={`${percent(m.approved_share)} из сгенерированных, с правками ${m.cards_approved_edited}`}
        />
        <StatTile
          value={percent(m.answered_share)}
          title="Ассистент ответил сам"
          note={`вопросов ${m.questions}, отказов ${percent(m.refused_share)}`}
        />
        <StatTile
          value={percent(m.helpful_share)}
          title="Оценка «помогло»"
          note={`оценок ${m.feedback_count}`}
        />
        <StatTile
          value={`${m.gaps_answered} из ${m.gaps_created}`}
          title="Пробелы закрыты ответом"
          note={`открыто сейчас ${m.gaps_open_now}`}
        />
        <StatTile
          value={percent(m.key_processes_coverage)}
          title="Покрытие ключевых процессов"
          note="процессы высокой важности"
        />
        <StatTile
          value={
            m.answer_latency_p95_ms === null
              ? "—"
              : `${(m.answer_latency_p95_ms / 1000).toFixed(1)} с`
          }
          title="Задержка ответа p95"
        />
      </div>
      {m.top_open_gaps.length > 0 && (
        <div className="rounded-[var(--radius-card)] bg-surface p-6">
          <p className="eyebrow">Открытые вопросы преемника</p>
          <ul className="mt-3 divide-y divide-line">
            {m.top_open_gaps.map((g) => (
              <li key={g.id}>
                <Link
                  to={`/gaps?handover=${g.handover_id}`}
                  className="flex items-center justify-between gap-3 py-3 text-sm transition-colors hover:text-primary-dark"
                >
                  {g.question}
                  <ArrowUpRight className="size-4 shrink-0 text-ink-soft" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
