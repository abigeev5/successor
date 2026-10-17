import { ScrollText } from "lucide-react";
import { useState } from "react";

import { useAuditLog } from "@/api/dashboard";
import { EmptyState } from "@/components/EmptyState";
import { ErrorNote } from "@/components/ErrorNote";
import { FullPageSpinner } from "@/components/Spinner";
import { Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { AUDIT_ACTION_LABELS } from "@/lib/labels";

const ENTITIES: { value: string; label: string }[] = [
  { value: "", label: "Все действия" },
  { value: "card", label: "Карточки" },
  { value: "asset", label: "Просмотр записей и медиа" },
  { value: "recording", label: "Записи экрана" },
  { value: "consent", label: "Согласия" },
  { value: "handover", label: "Передачи дел и удаление данных" },
  { value: "user", label: "Вход и пользователи" },
];

/** Audit log (SPEC 12, UC-08): admin sees everything, a manager — actions of their unit. */
export function AuditPage() {
  const [entity, setEntity] = useState("");
  const log = useAuditLog(entity);

  return (
    <section className="space-y-4">
      <h1 className="text-xl font-semibold">Журнал действий</h1>
      <div>
        <Label htmlFor="audit-entity">Что показать</Label>
        <Select
          id="audit-entity"
          className="w-auto"
          value={entity}
          onChange={(e) => setEntity(e.target.value)}
        >
          {ENTITIES.map((e) => (
            <option key={e.value} value={e.value}>
              {e.label}
            </option>
          ))}
        </Select>
      </div>
      {log.isPending && <FullPageSpinner />}
      <ErrorNote error={log.error} />
      {log.data?.length === 0 && <EmptyState icon={ScrollText}>Записей пока нет.</EmptyState>}
      {log.data && log.data.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-black/10">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead className="bg-surface text-xs text-ink-muted">
              <tr>
                <th className="px-3 py-2 font-medium">Когда</th>
                <th className="px-3 py-2 font-medium">Кто</th>
                <th className="px-3 py-2 font-medium">Действие</th>
              </tr>
            </thead>
            <tbody>
              {log.data.map((e) => (
                <tr key={e.id} className="border-t border-black/10">
                  <td className="whitespace-nowrap px-3 py-2 tabular-nums">
                    {new Date(e.at).toLocaleString("ru-RU")}
                  </td>
                  <td className="px-3 py-2">{e.user_name ?? "система"}</td>
                  <td className="px-3 py-2">{AUDIT_ACTION_LABELS[e.action] ?? e.action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
