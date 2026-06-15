import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { AuthProvider, useAuth } from "../../src/hooks/useAuth";
import { AdminPage } from "../../src/pages/AdminPage";
import { IncidentsPage } from "../../src/pages/IncidentsPage";
import { InvestigationDetailPage } from "../../src/pages/InvestigationDetailPage";
import { RulesPage } from "../../src/pages/RulesPage";
import { setToken } from "../../src/api/client";
import {
  installFetch,
  sampleIncident,
  sampleInvestigation,
  sampleSla,
  sampleUsers,
  tokenBody,
  type MockRoute,
} from "../helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
});

function withProviders(node: ReactNode, entries = ["/"]) {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={entries}>{node}</MemoryRouter>
    </AuthProvider>,
  );
}

function LoginThen({ children }: { children: ReactNode }) {
  const { login, isAuthenticated } = useAuth();
  return (
    <>
      <button data-testid="do-login" onClick={() => void login("u", "pw", "default")}>login</button>
      {isAuthenticated ? children : null}
    </>
  );
}

// Stub fetch that throws (non-ApiError) for everything after an initial GET.
function throwingAfter(initial: Record<string, MockRoute>) {
  let first = true;
  const initialFn = installFetch(initial);
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const method = (init?.method ?? "GET").toUpperCase();
    if (first && method === "GET") {
      first = false;
      return initialFn(url, init);
    }
    if (method === "GET") return initialFn(url, init);
    throw new Error("network");
  }) as unknown as typeof fetch);
}

describe("non-ApiError fallbacks", () => {
  it("AdminPage create shows generic error", async () => {
    throwingAfter({
      "POST /api/v1/auth/login": { ok: true, status: 200, body: tokenBody },
      "GET /api/v1/admin/users": { ok: true, status: 200, body: sampleUsers },
    });
    const user = userEvent.setup();
    withProviders(<AdminPage />);
    await screen.findByTestId("user-list");
    await user.type(screen.getByTestId("new-username"), "x");
    await user.type(screen.getByTestId("new-password"), "password123");
    await user.click(screen.getByTestId("create-user"));
    expect(await screen.findByTestId("error-banner")).toHaveTextContent("Create failed");
  });

  it("IncidentsPage generic error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("net"); }) as unknown as typeof fetch);
    withProviders(<IncidentsPage />);
    expect(await screen.findByTestId("error-banner")).toHaveTextContent("Failed to load incidents");
  });

  it("RulesPage generic error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("net"); }) as unknown as typeof fetch);
    withProviders(<RulesPage />);
    expect(await screen.findByTestId("error-banner")).toHaveTextContent("Failed to load rules");
  });
});

describe("display branches", () => {
  it("single-investigation incident renders singular", async () => {
    const single = { ...sampleIncident, investigation_ids: ["INV-1"], indicators: [] };
    installFetch({ "GET /api/v1/incidents": { ok: true, status: 200, body: [single] } });
    withProviders(<IncidentsPage />);
    await screen.findByTestId("incident-grid");
    expect(screen.getByTestId(`incident-${single.id}`)).toHaveTextContent("1 investigation");
  });

  it("many indicators show +more", async () => {
    const many = { ...sampleIncident, indicators: ["a", "b", "c", "d", "e", "f", "g", "h"] };
    installFetch({ "GET /api/v1/incidents": { ok: true, status: 200, body: [many] } });
    withProviders(<IncidentsPage />);
    await screen.findByTestId("incident-grid");
    expect(screen.getByTestId(`incident-${many.id}`)).toHaveTextContent("more");
  });
});

describe("permission-aware action display", () => {
  function detailRoutes(inv = sampleInvestigation): Record<string, MockRoute> {
    return {
      "POST /api/v1/auth/login": { ok: true, status: 200, body: { ...tokenBody, role: "analyst" } },
      [`GET /api/v1/investigations/${inv.id}`]: { ok: true, status: 200, body: inv },
      [`GET /api/v1/investigations/${inv.id}/sla`]: { ok: true, status: 200, body: sampleSla },
      [`GET /api/v1/investigations/${inv.id}/notes`]: { ok: true, status: 200, body: [] },
    };
  }

  it("analyst sees 'awaiting approval' (no approve button)", async () => {
    installFetch(detailRoutes());
    const user = userEvent.setup();
    withProviders(
      <Routes>
        <Route path="/investigations/:id" element={<LoginThen><InvestigationDetailPage /></LoginThen>} />
      </Routes>,
      [`/investigations/${sampleInvestigation.id}`],
    );
    await user.click(screen.getByTestId("do-login"));
    await screen.findByTestId("inv-title");
    expect(screen.queryByTestId("approve-0")).toBeNull();
    expect(screen.getByText("awaiting approval")).toBeInTheDocument();
  });

  it("analyst sees 'approved' on a pre-approved action (no execute button)", async () => {
    const approved = { ...sampleInvestigation, actions: [{ ...sampleInvestigation.actions[0], requires_approval: false }] };
    installFetch(detailRoutes(approved));
    const user = userEvent.setup();
    withProviders(
      <Routes>
        <Route path="/investigations/:id" element={<LoginThen><InvestigationDetailPage /></LoginThen>} />
      </Routes>,
      [`/investigations/${approved.id}`],
    );
    await user.click(screen.getByTestId("do-login"));
    await screen.findByTestId("inv-title");
    expect(screen.queryByTestId("execute-0")).toBeNull();
    expect(screen.getByText("approved")).toBeInTheDocument();
  });
});
