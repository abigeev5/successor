import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  CircleAlert,
  CircleDot,
  MinusCircle,
  ShieldCheck,
} from "lucide-react";

import type { AspectCell, RiskLevel } from "@/api/client";
import { cn } from "@/lib/cn";
import { RISK_LEVEL_LABELS } from "@/lib/labels";

/** Statuses are always icon + text, never color alone. */
export function AspectBadge({
  label,
  status,
  notApplicable,
}: {
  label: string;
  status: string;
  notApplicable: boolean;
}) {
  const view = notApplicable
    ? { icon: MinusCircle, text: "не относится", className: "text-ink-muted" }
    : status === "covered"
      ? { icon: CheckCircle2, text: "раскрыто", className: "text-primary" }
      : status === "partial"
        ? { icon: CircleDot, text: "частично", className: "text-amber-700" }
        : { icon: Circle, text: "нет", className: "text-ink-muted/70" };
  const Icon = view.icon;
  return (
    <li className="flex items-center gap-2 text-xs" title={`${label}: ${view.text}`}>
      <Icon className={cn("size-3.5 shrink-0", view.className)} aria-hidden />
      <span className="flex-1">{label}</span>
      <span className={cn("shrink-0", view.className)}>{view.text}</span>
    </li>
  );
}

export function ProgressBar({ value, label }: { value: number; label?: string }) {
  const percent = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2" title={label}>
      <div
        className="h-1.5 flex-1 overflow-hidden rounded-full bg-black/[0.08]"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
      >
        <div className="h-full rounded-full bg-primary" style={{ width: `${percent}%` }} />
      </div>
      <span className="w-10 text-right text-xs tabular-nums text-ink-muted">{percent}%</span>
    </div>
  );
}

const RISK_VIEW: Record<RiskLevel, { icon: typeof Circle; className: string }> = {
  high: { icon: AlertTriangle, className: "bg-danger-light text-danger" },
  medium: { icon: CircleAlert, className: "bg-warning-light text-amber-800" },
  low: { icon: ShieldCheck, className: "bg-primary-faint text-primary-dark" },
};

export function RiskBadge({ level }: { level: RiskLevel }) {
  const { icon: Icon, className } = RISK_VIEW[level];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium whitespace-nowrap",
        className,
      )}
    >
      <Icon className="size-3.5 shrink-0" aria-hidden />
      {RISK_LEVEL_LABELS[level]}
    </span>
  );
}

const CELL_VIEW: Record<
  AspectCell["status"],
  { icon: typeof Circle; text: string; className: string }
> = {
  covered: {
    icon: CheckCircle2,
    text: "есть подтверждённая карточка",
    className: "text-primary",
  },
  partial: { icon: CircleDot, text: "рассказано, карточки пока нет", className: "text-amber-700" },
  missing: { icon: Circle, text: "нет", className: "text-ink-muted/60" },
  not_applicable: { icon: MinusCircle, text: "не относится", className: "text-ink-muted" },
};

/** A cell of the «processes × aspects» matrix; the text is for screen readers and the tooltip. */
export function AspectCellIcon({ cell }: { cell: AspectCell }) {
  const { icon: Icon, text, className } = CELL_VIEW[cell.status];
  return (
    <span title={`${cell.label}: ${text}`} className="inline-flex">
      <Icon className={cn("size-4", className)} aria-hidden />
      <span className="sr-only">
        {cell.label}: {text}
      </span>
    </span>
  );
}

export const CELL_LEGEND = Object.entries(CELL_VIEW).map(([status, view]) => ({ status, ...view }));
