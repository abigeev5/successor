import type { ReactNode } from "react";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0 space-y-1.5">
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1 className="text-[28px] leading-tight font-semibold tracking-tight">{title}</h1>
        {description && <div className="max-w-2xl text-sm text-ink-muted">{description}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-3">{actions}</div>}
    </div>
  );
}

export function Section({
  title,
  description,
  actions,
  children,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
          {description && <p className="max-w-3xl text-sm text-ink-muted">{description}</p>}
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}

export function StatTile({
  value,
  title,
  note,
}: {
  value: ReactNode;
  title: ReactNode;
  note?: ReactNode;
}) {
  return (
    <div className="rounded-[var(--radius-card)] bg-surface p-5">
      <p className="text-[34px] leading-none font-semibold tracking-tight text-primary tabular-nums">
        {value}
      </p>
      <p className="mt-3 text-sm font-medium text-ink">{title}</p>
      {note && <p className="mt-1 text-xs text-ink-muted">{note}</p>}
    </div>
  );
}

export const TABLE_WRAP = "overflow-x-auto rounded-[var(--radius-card)] bg-white ring-1 ring-line";
export const TABLE_HEAD = "bg-surface text-xs font-medium text-ink-muted";

export function MiniStat({
  value,
  label,
  note,
}: {
  value: ReactNode;
  label: ReactNode;
  note?: ReactNode;
}) {
  return (
    <div>
      <p className="text-2xl leading-none font-semibold tracking-tight text-primary tabular-nums">
        {value}
      </p>
      <p className="mt-1.5 text-xs font-medium text-ink">{label}</p>
      {note && <p className="text-xs text-ink-soft">{note}</p>}
    </div>
  );
}
