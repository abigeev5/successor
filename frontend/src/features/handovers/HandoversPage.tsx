import { ArrowUpRight, CalendarClock, FolderKanban, Plus } from "lucide-react";
import { useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { useMe } from "@/api/auth";
import { useHandovers } from "@/api/handovers";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { ErrorNote } from "@/components/ErrorNote";
import { FullPageSpinner } from "@/components/Spinner";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import { daysLeft, REASON_LABELS } from "@/lib/labels";

import { CreateHandoverForm } from "./CreateHandoverForm";

export function HandoversPage() {
  const me = useMe();
  const handovers = useHandovers();
  const [creating, setCreating] = useState(false);
  const canCreate = me.data?.role === "manager" || me.data?.role === "admin";

  if (handovers.isPending) return <FullPageSpinner />;
  if (handovers.isError) return <ErrorNote error={handovers.error} />;
  if (me.data?.role === "expert" && handovers.data.length === 1) {
    return <Navigate to={`/handovers/${handovers.data[0].id}`} replace />;
  }

  return (
    <section className="space-y-6">
      <PageHeader
        title="Передачи дел"
        description="Эксперт, преемник, процессы и срок: всё, что нужно передать до ухода сотрудника."
        actions={
          canCreate &&
          !creating && (
            <Button onClick={() => setCreating(true)}>
              <Plus className="size-4" aria-hidden />
              Новая передача
            </Button>
          )
        }
      />

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
              <Link
                to={`/handovers/${h.id}`}
                className="group block h-full rounded-[var(--radius-card)] bg-surface p-6 transition-colors hover:bg-primary-faint"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex flex-wrap gap-2">
                    <Pill>{REASON_LABELS[h.reason]}</Pill>
                    {h.deadline && (
                      <Pill tone="white">
                        <CalendarClock className="size-3.5" aria-hidden />
                        {daysLeft(h.deadline)}
                      </Pill>
                    )}
                  </div>
                  <ArrowUpRight
                    className="size-5 shrink-0 text-ink-soft transition-colors group-hover:text-primary"
                    aria-hidden
                  />
                </div>
                <p className="mt-4 text-lg font-semibold tracking-tight">
                  {h.experts.map((e) => e.full_name).join(", ") || "Эксперт не назначен"}
                  <span className="font-normal text-ink-soft"> → </span>
                  {h.successors.map((s) => s.full_name).join(", ") || "преемник не назначен"}
                </p>
                <p className="mt-1 text-sm text-ink-muted">
                  {h.org_unit_name} · процессов: {h.processes.length}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
