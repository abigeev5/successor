import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReviewPage } from "./ReviewPage";

const HANDOVER = {
  id: "h1",
  org_unit_id: "u1",
  org_unit_name: "Учебный отдел",
  manager: { id: "m", full_name: "Ольга", email: "m@x.ru", role: "manager" },
  experts: [],
  successors: [],
  reason: "retirement",
  deadline: null,
  status: "active",
  processes: [{ id: "p1", name: "Подготовка ведомостей", criticality: 3, frequency: "quarterly" }],
  created_at: "2026-10-17T00:00:00Z",
  my_role: "expert",
};
const ITEM = {
  id: "c1",
  handover_id: "h1",
  process_id: "p1",
  type: "rule",
  title: "Ведомость — только со всеми подписями",
  summary: "Суть",
  status: "draft",
  origin: "interview",
  version: 1,
  duplicate_of: null,
  updated_at: "2026-10-17T00:00:00Z",
};
const DETAIL = {
  ...ITEM,
  body_md: "Текст",
  applies_when: null,
  archived_reason: null,
  reject_reason: null,
  approved_at: null,
  review_seconds: 0,
  sources: [
    {
      id: "s1",
      source_type: "interview_message",
      source_id: "m1",
      quote: "только когда стоят все подписи",
      start_ms: null,
      end_ms: null,
      label: "Интервью 15.10.2026, реплика 27",
      context: "Ведомость отправляю в деканат, только когда стоят все подписи экзаменаторов.",
      link: null,
      available: true,
    },
  ],
};

function mockApi() {
  const calls: { url: string; method: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const url = new URL(input.url);
      const body = input.method === "GET" ? undefined : await input.json().catch(() => undefined);
      calls.push({ url: url.pathname + url.search, method: input.method, body });
      const json = (data: unknown) =>
        new Response(JSON.stringify(data), { headers: { "content-type": "application/json" } });
      if (url.pathname === "/api/handovers/h1") return json(HANDOVER);
      if (url.pathname === "/api/cards") return json([ITEM]);
      if (url.pathname === "/api/cards/c1") return json(DETAIL);
      if (url.pathname === "/api/cards/c1/approve") return json({ ...DETAIL, status: "approved" });
      return new Response("{}", { status: 404 });
    }),
  );
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ReviewPage", () => {
  it("highlights the quote and approves with only the changed fields", async () => {
    const calls = mockApi();
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter initialEntries={["/review?handover=h1"]}>
          <ReviewPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const mark = await screen.findByText("только когда стоят все подписи");
    expect(mark.tagName).toBe("MARK");
    expect(screen.getByRole("heading", { name: "Подготовка ведомостей" })).toBeTruthy(); // grouped by process

    expect(screen.getByRole("button", { name: "Подтвердить" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Заголовок"), { target: { value: "Новый заголовок" } });
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить с правками" }));

    await waitFor(() => expect(calls.some((c) => c.url === "/api/cards/c1/approve")).toBe(true));
    const approve = calls.find((c) => c.url === "/api/cards/c1/approve")!;
    expect(approve.body).toMatchObject({ edits: { title: "Новый заголовок" } });
    expect(Object.keys((approve.body as { edits: object }).edits)).toEqual(["title"]);
  });
});
