import type { HandoverProgress } from "@/api/client";
import { plural } from "@/lib/labels";

/** Progress of one handover (SPEC 7.9); also shown on the handover page. */
export function ProgressFacts({ progress: p }: { progress: HandoverProgress }) {
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-ink-muted">
      <dt>Интервью</dt>
      <dd className="text-ink">
        {plural(p.interview_sessions, "сессия", "сессии", "сессий")}, {p.interview_minutes} мин
      </dd>
      <dt>Записи экрана</dt>
      <dd className="text-ink">
        {p.recordings}
        {p.recording_minutes > 0 && `, ${p.recording_minutes} мин`}
      </dd>
      <dt>Карточки</dt>
      <dd className="text-ink">
        подтверждено {p.cards_approved}, на проверке {p.cards_draft}, отклонено {p.cards_rejected}
      </dd>
      <dt>Открытые пробелы</dt>
      <dd className="text-ink">{p.open_gaps}</dd>
    </dl>
  );
}
