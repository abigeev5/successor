import type { ProcessCoverage } from "@/api/client";
import { AspectBadge, ProgressBar } from "@/components/StatusBadges";
import { cn } from "@/lib/cn";

export function CoveragePanel({
  coverage,
  currentProcessId,
}: {
  coverage: ProcessCoverage[];
  currentProcessId: string | null | undefined;
}) {
  return (
    <section aria-labelledby="coverage-title" className="space-y-3">
      <h2 id="coverage-title" className="text-sm font-semibold">
        Покрытие
      </h2>
      {coverage.length === 0 && (
        <p className="text-xs text-ink-muted">
          Процессы появятся, когда вы подтвердите карту обязанностей.
        </p>
      )}
      {coverage.map((p) => {
        const current = p.process_id === currentProcessId;
        return (
          <details
            key={p.process_id}
            open={current}
            className={cn("rounded-md bg-white p-3", current && "ring-2 ring-primary")}
          >
            <summary className="cursor-pointer list-none text-sm">
              <span className="font-medium">{p.name}</span>
              {current && <span className="ml-2 text-xs text-primary">сейчас</span>}
              <div className="mt-1.5">
                <ProgressBar value={p.coverage} label={`Покрытие «${p.name}»`} />
              </div>
            </summary>
            <ul className="mt-2 space-y-1">
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
        );
      })}
    </section>
  );
}
