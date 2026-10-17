import { CalendarClock, FolderKanban, Plus } from "lucide-react";
import { useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { useMe } from "@/api/auth";
import { useHandovers } from "@/api/handovers";
import { EmptyState } from "@/components/EmptyState";
import { ErrorNote } from "@/components/ErrorNote";
import { FullPageSpinner } from "@/components/Spinner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { daysLeft, REASON_LABELS } from "@/lib/labels";

import { CreateHandoverForm } from "./CreateHandoverForm";

export function HandoversPage() {
  const me = useMe();
  const handovers = useHandovers();
  const [creating, setCreating] = useState(false);
  const canCreate = me.data?.role === "manager" || me.data?.role === "admin";

  if (handovers.isPending) return <FullPageSpinner />;
  if (handovers.isError) return <ErrorNote error={handovers.error} />;
  // An expert usually has exactly one handover: go straight to it (SPEC 9.1).
  if (me.data?.role === "expert" && handovers.data.length === 1) {
    return <Navigate to={`/handovers/${handovers.data[0].id}`} replace />;
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Передачи дел</h1>
        {canCreate && !creating && (
          <Button onClick={() => setCreating(true)}>
            <Plus className="size-4" aria-hidden />
            Новая передача
          </Button>
        )}
      </div>

      {creating && <CreateHandoverForm onDone={() => setCreating(false)} />}

      {handovers.data.length === 0 && !creating ? (
        <EmptyState icon={FolderKanban} title="Передач дел пока нет">
          {canCreate
            ? "Создайте передачу: выберите эксперта, преемника, процессы и срок."
            : "Когда руководитель создаст передачу дел с вашим участием, она появится здесь."}
        </EmptyState>
      ) : (
        <ul className="grid gap-4 md:grid-cols-2">
          {handovers.data.map((h) => (
            <li key={h.id}>
              <Link to={`/handovers/${h.id}`} className="block">
                <Card className="transition-colors hover:bg-primary-light/60">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium">
                        {h.experts.map((e) => e.full_name).join(", ") || "Эксперт не назначен"}
                      </p>
                      <p className="text-sm text-ink-muted">
                        {REASON_LABELS[h.reason]} ·{" "}
                        {h.successors.length
                          ? `преемник: ${h.successors.map((s) => s.full_name).join(", ")}`
                          : "преемник не назначен"}
                      </p>
                    </div>
                    {h.deadline && (
                      <span className="flex shrink-0 items-center gap-1 text-xs text-ink-muted">
                        <CalendarClock className="size-3.5" aria-hidden />
                        {daysLeft(h.deadline)}
                      </span>
                    )}
                  </div>
                  <p className="mt-3 text-sm text-ink-muted">
                    Процессов: {h.processes.length} · {h.org_unit_name}
                  </p>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
