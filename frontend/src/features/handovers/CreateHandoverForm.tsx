import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import type { HandoverReason, ProcessFrequency } from "@/api/client";
import { useCreateHandover, useCreateProcess, useProcesses, useUsers } from "@/api/handovers";
import { ErrorNote } from "@/components/ErrorNote";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { CRITICALITY_LABELS, FREQUENCY_LABELS, REASON_LABELS } from "@/lib/labels";

export function CreateHandoverForm({ onDone }: { onDone: () => void }) {
  const experts = useUsers("expert");
  const successors = useUsers("successor");
  const processes = useProcesses();
  const create = useCreateHandover();
  const createProcess = useCreateProcess();
  const navigate = useNavigate();

  const [expertId, setExpertId] = useState("");
  const [successorId, setSuccessorId] = useState("");
  const [reason, setReason] = useState<HandoverReason>("retirement");
  const [deadline, setDeadline] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [newName, setNewName] = useState("");
  const [newCriticality, setNewCriticality] = useState(2);
  const [newFrequency, setNewFrequency] = useState<ProcessFrequency>("monthly");

  function toggle(id: string) {
    setSelected((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));
  }

  function addProcess() {
    createProcess.mutate(
      { name: newName.trim(), criticality: newCriticality, frequency: newFrequency },
      {
        onSuccess: (process) => {
          setSelected((ids) => [...ids, process.id]);
          setNewName("");
        },
      },
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate(
      {
        expert_id: expertId,
        successor_id: successorId || null,
        reason,
        deadline: deadline || null,
        process_ids: selected,
      },
      { onSuccess: (handover) => navigate(`/handovers/${handover.id}`) },
    );
  }

  return (
    <Card>
      <form onSubmit={submit} className="space-y-5">
        <h2 className="text-lg font-semibold">Новая передача дел</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <Label htmlFor="expert">Эксперт (кто передаёт дела)</Label>
            <Select
              id="expert"
              value={expertId}
              onChange={(e) => setExpertId(e.target.value)}
              required
            >
              <option value="">Выберите сотрудника</option>
              {experts.data?.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="successor">Преемник</Label>
            <Select
              id="successor"
              value={successorId}
              onChange={(e) => setSuccessorId(e.target.value)}
            >
              <option value="">Пока не назначен</option>
              {successors.data?.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="reason">Причина</Label>
            <Select
              id="reason"
              value={reason}
              onChange={(e) => setReason(e.target.value as HandoverReason)}
            >
              {Object.entries(REASON_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="deadline">Срок</Label>
            <Input
              id="deadline"
              type="date"
              value={deadline}
              onChange={(e) => setDeadline(e.target.value)}
            />
          </div>
        </div>

        <fieldset>
          <legend className="mb-2 text-sm font-medium">Какие процессы передаются</legend>
          {processes.data?.length === 0 && (
            <p className="text-sm text-ink-muted">
              Процессов пока нет. Добавьте их ниже — или эксперт перечислит их сам в начале
              интервью.
            </p>
          )}
          <ul className="space-y-1">
            {processes.data?.map((p) => (
              <li key={p.id}>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={selected.includes(p.id)}
                    onChange={() => toggle(p.id)}
                  />
                  <span>{p.name}</span>
                  <span className="text-xs text-ink-muted">
                    · важность: {CRITICALITY_LABELS[p.criticality].toLowerCase()} ·{" "}
                    {p.holders.length
                      ? `знают: ${p.holders.map((h) => h.full_name).join(", ")}`
                      : "никто не отмечен"}
                  </span>
                </label>
              </li>
            ))}
          </ul>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <div className="min-w-48 flex-1">
              <Label htmlFor="new-process">Новый процесс</Label>
              <Input
                id="new-process"
                value={newName}
                placeholder="Например, «Отчёт о движении контингента»"
                onChange={(e) => setNewName(e.target.value)}
              />
            </div>
            <Select
              aria-label="Частота"
              className="w-auto"
              value={newFrequency}
              onChange={(e) => setNewFrequency(e.target.value as ProcessFrequency)}
            >
              {Object.entries(FREQUENCY_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
            <Select
              aria-label="Важность"
              className="w-auto"
              value={newCriticality}
              onChange={(e) => setNewCriticality(Number(e.target.value))}
            >
              {[3, 2, 1].map((c) => (
                <option key={c} value={c}>
                  Важность: {CRITICALITY_LABELS[c].toLowerCase()}
                </option>
              ))}
            </Select>
            <Button
              type="button"
              variant="secondary"
              onClick={addProcess}
              disabled={!newName.trim() || createProcess.isPending}
            >
              Добавить
            </Button>
          </div>
          <ErrorNote error={createProcess.error} />
        </fieldset>

        <ErrorNote error={create.error} />
        <div className="flex gap-2">
          <Button type="submit" disabled={!expertId || create.isPending}>
            {create.isPending ? "Создаём…" : "Создать передачу"}
          </Button>
          <Button type="button" variant="ghost" onClick={onDone}>
            Отмена
          </Button>
        </div>
      </form>
    </Card>
  );
}
