import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { homePath, NAV } from "@/lib/roles";

import { App } from "./App";

function mockApi(routes: Record<string, { status: number; body: unknown }>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request | string) => {
      const url = typeof input === "string" ? input : input.url;
      const path = new URL(url, "http://localhost").pathname;
      const route = routes[path] ?? {
        status: 404,
        body: { detail: "Не найдено", code: "not_found" },
      };
      return new Response(JSON.stringify(route.body), {
        status: route.status,
        headers: { "content-type": "application/json" },
      });
    }),
  );
}

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const META = { status: 200, body: { demo_mode: true, offline_mode: false, version: "0.1.0" } };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("roles", () => {
  it("every role has a home section", () => {
    for (const role of Object.keys(NAV) as (keyof typeof NAV)[]) {
      expect(homePath(role)).toMatch(/^\//);
    }
    expect(homePath("manager")).toBe("/dashboard");
    expect(homePath("successor")).toBe("/assistant");
  });
});

describe("App", () => {
  it("anonymous user is sent to login with demo accounts", async () => {
    mockApi({
      "/api/auth/me": {
        status: 401,
        body: { detail: "Войдите в систему", code: "not_authenticated" },
      },
      "/api/meta": META,
    });
    renderAt("/dashboard");
    expect(await screen.findByRole("button", { name: /Войти/ })).toBeTruthy();
    expect(await screen.findByText("Демо-учётки")).toBeTruthy();
  });

  it("logged-in successor lands on the assistant and does not see the dashboard", async () => {
    mockApi({
      "/api/auth/me": {
        status: 200,
        body: {
          id: "1",
          email: "successor@demo.local",
          full_name: "Дмитрий",
          role: "successor",
          is_active: true,
          org_unit_id: null,
        },
      },
      "/api/meta": META,
    });
    renderAt("/dashboard");
    expect(await screen.findByRole("heading", { name: "Ассистент" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Панель" })).toBeNull();
    expect(screen.getByText("Дмитрий")).toBeTruthy();
  });
});
