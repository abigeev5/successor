import { FlaskConical } from "lucide-react";

import { useMeta } from "@/api/auth";

/** SPEC 13.1: demo data is fictional and marked in the UI. */
export function DemoBanner() {
  const { data } = useMeta();
  if (!data?.demo_mode) return null;
  return (
    <div
      role="note"
      className="flex items-center justify-center gap-2 bg-warning-light px-4 py-1.5 text-xs text-ink"
    >
      <FlaskConical className="size-3.5" aria-hidden />
      <span>Демо-режим: все люди, процессы и данные вымышленные</span>
    </div>
  );
}
