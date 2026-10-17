import { useState } from "react";

import type { Candidate, CandidateDecision, ProcessFrequency } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { CRITICALITY_LABELS, FREQUENCY_LABELS } from "@/lib/labels";

/** «Карта обязанностей» (SPEC 7.4, phase map): the expert confirms processes found in the answers. */
export function CandidatesPanel({
  candidates,
  pending,
  onConfirm,
}: {
  candidates: Candidate[];
  pending: boolean;
  onConfirm: (items: CandidateDecision[]) => void;
}) {
  // The parent remounts this panel (key) when the candidates change.
  const [items, setItems] = useState<CandidateDecision[]>(() =>
    candidates.map((c) => ({
      name: c.name,
      description: c.description ?? "",
      include: true,
      frequency: "monthly",
      criticality: 2,
    })),
  );

  function update(index: number, patch: Partial<CandidateDecision>) {
    setItems((all) => all.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  }

  return (
    <section aria-labelledby="map-title" className="space-y-3 rounded-md bg-primary-light/60 p-3">
      <h2 id="map-title" className="text-sm font-semibold">
        Карта обязанностей
      </h2>
      <p className="text-xs text-ink-muted">
        Задачи из ваших ответов. Отметьте свои, укажите частоту и важность.
      </p>
      <ul className="space-y-3">
        {items.map((item, i) => (
          <li key={item.name} className="space-y-1.5 rounded-md bg-white p-2">
            <label className="flex items-center gap-2 text-sm font-medium">
              <input
                type="checkbox"
                checked={item.include ?? true}
                onChange={(e) => update(i, { include: e.target.checked })}
              />
              {item.name}
            </label>
            <div className="grid grid-cols-2 gap-1.5">
              <Select
                aria-label={`Частота: ${item.name}`}
                className="px-2 py-1 text-xs"
                value={item.frequency}
                onChange={(e) => update(i, { frequency: e.target.value as ProcessFrequency })}
              >
                {Object.entries(FREQUENCY_LABELS).map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </Select>
              <Select
                aria-label={`Важность: ${item.name}`}
                className="px-2 py-1 text-xs"
                value={item.criticality}
                onChange={(e) => update(i, { criticality: Number(e.target.value) })}
              >
                {[3, 2, 1].map((c) => (
                  <option key={c} value={c}>
                    Важность: {CRITICALITY_LABELS[c].toLowerCase()}
                  </option>
                ))}
              </Select>
            </div>
          </li>
        ))}
      </ul>
      <Button className="w-full" disabled={pending} onClick={() => onConfirm(items)}>
        Подтвердить
      </Button>
    </section>
  );
}
