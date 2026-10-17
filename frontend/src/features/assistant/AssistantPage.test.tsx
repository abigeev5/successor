import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GapsPage } from "@/features/gaps/GapsPage";

import { linkCitations } from "./AnswerView";
import { AssistantPage } from "./AssistantPage";

const HANDOVER = {
  id: "h1",
  org_unit_id: "u1",
  org_unit_name: "Учебный отдел",
  manager: { id: "m", full_name: "Ольга", email: "m@x.ru", role: "manager" },
  experts: [{ id: "e", full_name: "Ирина", email: "e@x.ru", role: "expert" }],
  successors: [{ id: "s", full_name: "Алексей", email: "s@x.ru", role: "successor" }],
  reason: "retirement",
  deadline: null,
  status: "active",
  processes: [{ id: "p1", name: "Отчёт о контингенте", criticality: 3, frequency: "monthly" }],
  created_at: "2026-10-17T00:00:00Z",
  my_role: "successor",
};
const CARD = {
  id: "c1",
  handover_id: "h1",
  process_id: "p1",
  type: "deadline",
  title: "Срок сдачи отчёта — до 5-го числа",
  summary: "Отчёт отправляют до пятого числа.",
  status: "approved",
  origin: "interview",
  version: 1,
  duplicate_of: null,
  updated_at: "2026-10-17T00:00:00Z",
};
const DETAIL = {
  ...CARD,
  body_md: "Отправить в отдел статистики **до 5-го числа**.",
  applies_when: null,
  archived_reason: null,
  reject_reason: null,
  approved_at: "2026-10-17T00:00:00Z",
  review_seconds: 30,
  sources: [
    {
      id: "s1",
      source_type: "interview_message",
      source_id: "m1",
      quote: "сдаю до пятого числа",
      start_ms: null,
      end_ms: null,
      label: "Интервью 15.10.2026, реплика 4",
      context: null,
      link: null,
      available: true,
    },
  ],
};
const answer = (extra: object) => ({
  qa_id: "q1",
  question: "До какого числа сдавать отчёт?",
  status: "answered",
  answer: "Отчёт сдают до 5-го числа [1].",
  sources: [{ n: 1, card_id: "c1", title: CARD.title, type: "deadline" }],
  groundedness: 1,
  verification: "verified",
  refusal_reason: null,
  forwarded_to: null,
  feedback: null,
  created_at: "2026-10-17T00:00:00Z",
  ...extra,
});
const GAP = {
  id: "g1",
  handover_id: "h1",
  question: "Как заказать пропуск для гостя?",
  status: "open",
  asked_by_name: "Алексей",
  assignee_id: "e",
  assignee_name: "Ирина",
  answer_text: null,
  answered_card_id: null,
  answer_on_review: false,
  created_at: "2026-10-17T00:00:00Z",
  answered_at: null,
};

function mockApi(routes: Record<string, unknown>) {
  const calls: { path: string; method: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const url = new URL(input.url);
      const body = input.method === "GET" ? undefined : await input.json().catch(() => undefined);
      calls.push({ path: url.pathname, method: input.method, body });
      const key = `${input.method} ${url.pathname}`;
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

function renderAt(path: string, page: React.ReactNode) {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter initialEntries={[path]}>{page}</MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("linkCitations", () => {
  it("turns [n] into links and leaves markdown links alone", () => {
    expect(linkCitations("До 5-го числа [1][2].")).toBe(
      "До 5-го числа [1](#source-1)[2](#source-2).",
    );
    expect(linkCitations("[сайт](https://x.ru)")).toBe("[сайт](https://x.ru)");
  });
});

describe("AssistantPage", () => {
  it("shows a verified answer whose citation opens the card with its quote", async () => {
    mockApi({
      "GET /api/handovers": [HANDOVER],
      "GET /api/assistant/history": [answer({})],
      "GET /api/cards": [CARD],
      "GET /api/cards/c1": DETAIL,
      "GET /api/gaps": [],
    });
    renderAt("/assistant?handover=h1", <AssistantPage />);
    expect(await screen.findByText("Все утверждения подтверждены источниками")).toBeTruthy();
    expect(screen.getByText("Помогло")).toBeTruthy();
    fireEvent.click(screen.getByTitle(CARD.title)); // the inline [1] chip
    const panel = await screen.findByRole("complementary", { name: "Источник" });
    expect(await within(panel).findByText("«сдаю до пятого числа»")).toBeTruthy();
    expect(within(panel).getByText("Интервью 15.10.2026, реплика 4")).toBeTruthy();
  });

  it("says who got the question when there is no answer", async () => {
    const calls = mockApi({
      "GET /api/handovers": [HANDOVER],
      "GET /api/assistant/history": [],
      "GET /api/cards": [CARD],
      "GET /api/gaps": [],
      "POST /api/assistant/ask": answer({
        question: "Как заказать пропуск?",
        status: "refused",
        answer: null,
        sources: [],
        verification: "none",
        refusal_reason: "no_relevant_sources",
        forwarded_to: "Ирина",
      }),
    });
    renderAt("/assistant?handover=h1", <AssistantPage />);
    expect(await screen.findByText(CARD.title)).toBeTruthy(); // an example from card titles
    const input = screen.getByLabelText("Ваш вопрос");
    fireEvent.change(input, { target: { value: "Как заказать пропуск?" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(await screen.findByText(/В базе знаний нет ответа на этот вопрос/)).toBeTruthy();
    expect(screen.getByText(/Я передал его: Ирина/)).toBeTruthy();
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      handover_id: "h1",
      question: "Как заказать пропуск?",
    });
  });
});

describe("GapsPage", () => {
  it("lets the expert answer an open gap", async () => {
    const calls = mockApi({
      "GET /api/handovers": [{ ...HANDOVER, my_role: "expert" }],
      "GET /api/gaps": [GAP],
      "POST /api/gaps/g1/answer": { ...GAP, answer_text: "У охраны.", answer_on_review: true },
    });
    renderAt("/gaps?handover=h1", <GapsPage />);
    expect(await screen.findByText(GAP.question)).toBeTruthy();
    expect(screen.queryByLabelText("Назначить другого эксперта")).toBeNull(); // manager only
    fireEvent.change(screen.getByLabelText("Ваш ответ"), { target: { value: "У охраны." } });
    fireEvent.click(screen.getByRole("button", { name: "Ответить" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({ text: "У охраны." }),
    );
  });
});
