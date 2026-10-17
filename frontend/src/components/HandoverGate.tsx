import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import type { Handover } from "@/api/client";
import { useHandovers } from "@/api/handovers";
import { EmptyState } from "@/components/EmptyState";
import { ErrorNote } from "@/components/ErrorNote";
import { FullPageSpinner } from "@/components/Spinner";
import { Select } from "@/components/ui/select";

export function handoverLabel(h: Handover): string {
  const expert = h.experts[0]?.full_name ?? "эксперт не назначен";
  const successor = h.successors[0]?.full_name;
  return successor ? `${expert} → ${successor}` : expert;
}

/**
 * Pages scoped to one handover take it from `?handover=`; without it the first one is opened.
 * Renders `children` with the chosen handover and a switcher (shown when there are several).
 */
export function HandoverGate({
  icon,
  emptyTitle,
  emptyText,
  children,
}: {
  icon: LucideIcon;
  emptyTitle: string;
  emptyText: string;
  children: (handover: Handover, switcher: ReactNode) => ReactNode;
}) {
  const [params] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const handovers = useHandovers();
  const id = params.get("handover");

  if (handovers.isPending) return <FullPageSpinner />;
  if (handovers.isError) return <ErrorNote error={handovers.error} />;
  const list = handovers.data;
  const current = list.find((h) => h.id === id);
  if (!current) {
    if (list.length === 0) {
      return (
        <EmptyState icon={icon} title={emptyTitle}>
          {emptyText}
        </EmptyState>
      );
    }
    const next = new URLSearchParams(params);
    next.set("handover", list[0].id);
    return <Navigate to={`${location.pathname}?${next}`} replace />;
  }

  const switcher =
    list.length > 1 ? (
      <Select
        aria-label="Передача дел"
        className="w-auto max-w-xs"
        value={current.id}
        onChange={(event) => navigate(`${location.pathname}?handover=${event.target.value}`)}
      >
        {list.map((h) => (
          <option key={h.id} value={h.id}>
            {handoverLabel(h)}
          </option>
        ))}
      </Select>
    ) : (
      <span className="text-sm text-ink-muted">{handoverLabel(current)}</span>
    );
  return <>{children(current, switcher)}</>;
}
