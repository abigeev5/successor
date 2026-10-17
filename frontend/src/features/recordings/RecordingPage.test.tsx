import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SourceView } from "@/components/SourceView";

import { RecordingPage } from "./RecordingPage";

const STEP = {
  id: "s1",
  idx: 1,
  title: "Найти студента по фамилии",
  action: "Ввести фамилию и нажать «Найти».",
  rationale: "По фамилии быстрее.",
  start_ms: 1_500,
  end_ms: 8_800,
  screenshot_asset_id: "img1",
  screenshot_blurred: true,
};
const READY = {
  id: "r1",
  handover_id: "h1",
  process_id: null,
  title: "Оформление направления на пересдачу",
  status: "ready",
  stage: null,
  error: null,
  duration_ms: 47_000,
  created_at: "2026-10-17T00:00:00Z",
  video_asset_id: "v1",
  steps: [
    STEP,
    {
      ...STEP,
      id: "s2",
      idx: 2,
      title: "Оформить",
      start_ms: 9_000,
      end_ms: 15_000,
      screenshot_blurred: false,
    },
  ],
  card_id: "c1",
  card_status: "draft",
};

function mockApi(routes: Record<string, unknown>) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const url = new URL(input.url);
      const key = `${input.method} ${url.pathname}`;
      calls.push(key);
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
      <MemoryRouter initialEntries={["/recordings/r1"]}>
        <Routes>
          <Route path="/recordings/:id" element={<RecordingPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("RecordingPage", () => {
  it("shows steps with screenshots, the blur note and seeks the video to a step", async () => {
    mockApi({ "GET /api/recordings/r1": READY });
    renderPage();
    expect(await screen.findByText("Найти студента по фамилии")).toBeTruthy();
    expect(screen.getAllByText("Персональные данные скрыты автоматически")).toHaveLength(1);
    expect(screen.getByAltText("Скриншот шага 1").getAttribute("src")).toBe("/api/assets/img1");
    expect(screen.getByRole("link", { name: "Проверить и подтвердить" })).toBeTruthy();

    const video = document.querySelector("video")!;
    fireEvent.click(screen.getByRole("button", { name: /00:09–00:15/ }));
    expect(video.currentTime).toBe(9);
  });

  it("explains a failure and processes the recording again", async () => {
    const calls = mockApi({
      "GET /api/recordings/r1": {
        ...READY,
        status: "failed",
        steps: [],
        card_id: null,
        error: "В записи нет звука.",
      },
      "POST /api/recordings/r1/retry": { ...READY, status: "uploaded", steps: [], card_id: null },
    });
    renderPage();
    expect(await screen.findByText("В записи нет звука.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Обработать заново/ }));
    expect(await screen.findByText(/Запись ждёт обработки/)).toBeTruthy();
    await waitFor(() => expect(calls).toContain("POST /api/recordings/r1/retry"));
  });
});

describe("SourceView", () => {
  it("opens a recording step's video at its start", () => {
    render(
      <SourceView
        source={{
          id: "x",
          source_type: "recording_step",
          source_id: "s1",
          quote: "Ввести фамилию",
          start_ms: 8_000,
          end_ms: 12_000,
          label: "Запись «Пересдача», шаг 1 · 00:08–00:12",
          context: null,
          link: { video_asset_id: "v1", recording_id: "r1" },
          available: true,
        }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Смотреть с 00:08" }));
    expect(document.querySelector("video")!.getAttribute("src")).toBe("/api/assets/v1#t=8");
  });
});
