import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DashboardPage } from "./DashboardPage";

const ASPECTS = [
  { key: "steps", label: "Шаги", status: "covered" },
  { key: "exceptions", label: "Исключения", status: "partial" },
  { key: "timing", label: "Сроки и календарь", status: "missing" },
];
const PROCESS = {
  holders: [],
  open_gaps: 2,
  deadline: "2099-01-01",
  days_left: 30_000,
  aspects: ASPECTS,
};
const RISK = {
  org_unit_id: "u1",
  org_unit_name: "Учебный отдел (демо)",
  high_threshold: 0.35,
  medium_threshold: 0.15,
  processes: [
    {
      ...PROCESS,
      process_id: "p1",
      name: "Отчёт о движении контингента",
      criticality: 3,
      coverage: 0.27,
      risk: 0.51,
      level: "high",
    },
    {
      ...PROCESS,
      process_id: "p2",
      name: "Оформление пересдач",
      criticality: 2,
      holders: [{ user_id: "m1", full_name: "Марина Андреевна", level: "knows" }],
      coverage: 0.8,
      risk: 0.03,
      level: "low",
    },
  ],
};
const METRICS = {
  handover_id: null,
  org_unit_id: "u1",
  date_from: null,
  date_to: null,
  expert_minutes: 95,
  interview_minutes: 60,
  recording_minutes: 5,
  review_minutes: 30,
  interview_turns: 40,
  recordings_processed: 1,
  cards_generated: 30,
  cards_dropped_no_evidence: 2,
  cards_approved: 25,
  cards_approved_edited: 6,
  cards_rejected: 3,
  approved_share: 0.8333,
  questions: 10,
  answered_share: 0.7,
  partial_share: 0.1,
  refused_share: 0.2,
  helpful_share: 0.9,
  feedback_count: 8,
  answer_latency_p95_ms: 12_400,
  gaps_created: 2,
  gaps_answered: 1,
  gaps_open_now: 1,
  key_processes_coverage: 0.5,
  top_open_gaps: [
    { id: "g1", handover_id: "h1", question: "Куда сдавать отчёт?", created_at: "2026-10-17" },
  ],
};

function mockApi(routes: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const url = new URL(input.url);
      const key = `${input.method} ${url.pathname}`;
      if (key in routes) {
        return new Response(JSON.stringify(routes[key]), {
          headers: { "content-type": "application/json" },
        });
      }
      return new Response("{}", { status: 404 });
    }),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("DashboardPage", () => {
  it("shows the risk map with words, not only colors, and the metrics", async () => {
    mockApi({
      "GET /api/dashboard/risk": RISK,
      "GET /api/handovers": [],
      "GET /api/dashboard/metrics": METRICS,
    });
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter>
          <DashboardPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const table = (await screen.findByText("Карта рисков")).closest("div")!.parentElement!;
    const rows = within(table).getAllByRole("row");
    expect(within(rows[1]).getByText("Отчёт о движении контингента")).toBeTruthy();
    expect(within(rows[1]).getByText("Высокий")).toBeTruthy();
    expect(within(rows[1]).getByText("никто")).toBeTruthy();
    expect(within(rows[2]).getByText("Низкий")).toBeTruthy();
    expect(within(rows[2]).getByText("Марина Андреевна")).toBeTruthy();

    expect(screen.getAllByText("Шаги: есть подтверждённая карточка")).toHaveLength(2);
    expect(await screen.findByText("95 мин")).toBeTruthy();
    expect(screen.getByText("Куда сдавать отчёт?")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Выгрузить CSV/ }).getAttribute("href")).toBe(
      "/api/dashboard/metrics.csv",
    );
  });
});
