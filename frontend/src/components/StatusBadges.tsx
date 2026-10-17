import { CheckCircle2, Circle, CircleDot, MinusCircle } from "lucide-react";

import { cn } from "@/lib/cn";

/** Aspect coverage: always icon + text, not only color (SPEC 9.2). */
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
      ? { icon: CheckCircle2, text: "раскрыто", className: "text-emerald-700" }
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
        className="h-2 flex-1 overflow-hidden rounded-full bg-black/10"
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
