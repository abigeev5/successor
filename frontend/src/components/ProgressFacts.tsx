import type { HandoverProgress } from "@/api/client";
import { plural } from "@/lib/labels";

import { MiniStat } from "./PageHeader";

export function ProgressFacts({ progress: p }: { progress: HandoverProgress }) {
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-5">
      <MiniStat
        value={`${p.interview_minutes} мин`}
        label="интервью"
        note={plural(p.interview_sessions, "сессия", "сессии", "сессий")}
      />
      <MiniStat
        value={p.recordings}
        label="записи экрана"
        note={p.recording_minutes > 0 ? `${p.recording_minutes} мин` : undefined}
      />
      <MiniStat
        value={p.cards_approved}
        label="карточек подтверждено"
        note={`на проверке ${p.cards_draft}, отклонено ${p.cards_rejected}`}
      />
      <MiniStat value={p.open_gaps} label="открытых вопросов" />
    </div>
  );
}
