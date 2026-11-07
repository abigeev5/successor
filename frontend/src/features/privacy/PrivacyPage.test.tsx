import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PrivacyPage } from "./PrivacyPage";

const HANDOVER = {
  id: "h1",
  org_unit_id: "u1",
  org_unit_name: "Учебный отдел (демо)",
  manager: { id: "m", full_name: "Ольга Викторовна", email: "m@demo.local", role: "manager" },
  experts: [{ id: "e", full_name: "Ирина Сергеевна", email: "e@demo.local", role: "expert" }],
  successors: [],
  reason: "retirement",
  deadline: null,
  status: "active",
  processes: [],
  created_at: "2026-10-17T00:00:00Z",
  my_role: "expert",
};
const MY_DATA = {
  handover_id: "h1",
  consent: {
    id: "c1",
    handover_id: "h1",
    text_version: "1",
    accepted_at: "2026-10-17T00:00:00Z",
    revoked_at: null,
  },
  counts: {
    interview_messages: 38,
    recordings: 1,
    gap_answers: 0,
    files: 2,
    files_bytes: 2_097_152,
  },
};
const RECORDING = {
  id: "r1",
  handover_id: "h1",
  process_id: null,
  title: "Оформление пересдачи",
  status: "ready",
  stage: null,
  error: null,
  duration_ms: 47_000,
  created_at: "2026-10-17T00:00:00Z",
};

function mockApi(routes: Record<string, unknown>) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const url = new URL(input.url);
      const key = `${input.method} ${url.pathname}`;
      calls.push(`${key}${url.search}`);
      if (key in routes) {
        return new Response(JSON.stringify(routes[key]), {
          headers: { "content-type": "application/json" },
        });
      }
      return new Response("{}", { status: 404 });
    }),
  );
  return calls;
}

function renderPage() {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter initialEntries={["/privacy?handover=h1"]}>
        <PrivacyPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("PrivacyPage", () => {
  it("shows what is stored and erases everything after a second confirmation", async () => {
    const calls = mockApi({
      "GET /api/handovers": [HANDOVER],
      "GET /api/privacy/my-data": MY_DATA,
      "GET /api/recordings": [RECORDING],
      "DELETE /api/privacy/my-data": {
        counts: { interview_messages: 38, recordings: 1, gap_answers: 0 },
        files: 2,
        sources: 40,
      },
    });
    renderPage();
    expect(await screen.findByText("38")).toBeTruthy();
    expect(screen.getByText(/2,0 МБ/)).toBeTruthy();
    expect(await screen.findByText("Оформление пересдачи")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Удалить мои данные/ }));
    expect(calls.some((c) => c.startsWith("DELETE"))).toBe(false); // asks first
    fireEvent.click(screen.getByRole("button", { name: "Да, удалить всё" }));
    expect(
      await screen.findByText("Удалено — Сообщения интервью: 38, Записи экрана: 1, файлов: 2."),
    ).toBeTruthy();
    await waitFor(() => expect(calls).toContain("DELETE /api/privacy/my-data?handover_id=h1"));
  });

  it("deletes one recording", async () => {
    const calls = mockApi({
      "GET /api/handovers": [HANDOVER],
      "GET /api/privacy/my-data": MY_DATA,
      "GET /api/recordings": [RECORDING],
      "DELETE /api/recordings/r1": null,
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Удалить запись/ }));
    fireEvent.click(screen.getByRole("button", { name: "Да, удалить запись" }));
    await waitFor(() => expect(calls).toContain("DELETE /api/recordings/r1"));
  });
});
