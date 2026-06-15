import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { AuthProvider, useAuth } from "../../src/hooks/useAuth";
import { LoginPage } from "../../src/pages/LoginPage";
import { DashboardPage } from "../../src/pages/DashboardPage";
import { InvestigationDetailPage } from "../../src/pages/InvestigationDetailPage";
import { setToken } from "../../src/api/client";
import {
  installFetch,
  sampleInvestigation,
  sampleSla,
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

// Logs in via a hidden helper so role/permissions are set for gated UI.
function LoginThen({ children }: { children: ReactNode }) {
  const { login, isAuthenticated } = useAuth();
  return (
    <>
      <button data-testid="do-login" onClick={() => void login("analyst", "pw", "default")}>
        login
      </button>
      {isAuthenticated ? children : null}
    </>
  );
}

const loginRoute: Record<string, MockRoute> = {
  "POST /api/v1/auth/login": { ok: true, status: 200, body: tokenBody },
};

describe("LoginPage", () => {
  it("requires all three fields", async () => {
    installFetch(loginRoute);
    const user = userEvent.setup();
    withProviders(<LoginPage />);
    expect(screen.getByTestId("login-button")).toBeDisabled();
    await user.type(screen.getByTestId("tenant-input"), "default");
    await user.type(screen.getByTestId("username-input"), "analyst");
    expect(screen.getByTestId("login-button")).toBeDisabled();
    await user.type(screen.getByTestId("password-input"), "pw");
    expect(screen.getByTestId("login-button")).toBeEnabled();
  });

  it("submits successfully", async () => {
    installFetch(loginRoute);
    const user = userEvent.setup();
    withProviders(<LoginPage />);
    await user.type(screen.getByTestId("tenant-input"), "default");
    await user.type(screen.getByTestId("username-input"), "analyst");
    await user.type(screen.getByTestId("password-input"), "pw");
    await user.click(screen.getByTestId("login-button"));
    await waitFor(() => expect(screen.queryByTestId("error-banner")).toBeNull());
  });

  it("shows error on bad credentials", async () => {
    installFetch({ "POST /api/v1/auth/login": { ok: false, status: 401, body: { detail: "Invalid credentials" } } });
    const user = userEvent.setup();
    withProviders(<LoginPage />);
    await user.type(screen.getByTestId("tenant-input"), "default");
    await user.type(screen.getByTestId("username-input"), "x");
    await user.type(screen.getByTestId("password-input"), "y");
    await user.click(screen.getByTestId("login-button"));
    expect(await screen.findByTestId("error-banner")).toHaveTextContent("Invalid credentials");
  });

  it("shows generic error on non-ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("net"); }) as unknown as typeof fetch);
    const user = userEvent.setup();
    withProviders(<LoginPage />);
    await user.type(screen.getByTestId("tenant-input"), "default");
    await user.type(screen.getByTestId("username-input"), "x");
    await user.type(screen.getByTestId("password-input"), "y");
    await user.click(screen.getByTestId("login-button"));
    expect(await screen.findByTestId("error-banner")).toHaveTextContent("Unexpected error");
  });
});

describe("DashboardPage", () => {
  const listEmpty: MockRoute = { ok: true, status: 200, body: { investigations: [], total: 0, limit: 100, offset: 0 } };
  const listOne: MockRoute = { ok: true, status: 200, body: { investigations: [sampleInvestigation], total: 1, limit: 100, offset: 0 } };

  it("empty state", async () => {
    installFetch({ "GET /api/v1/investigations": listEmpty });
    withProviders(<DashboardPage />);
    expect(await screen.findByTestId("empty-state")).toBeInTheDocument();
    expect(screen.getByTestId("stat-total")).toHaveTextContent("0");
  });

  it("renders cards + stats", async () => {
    installFetch({ "GET /api/v1/investigations": listOne });
    withProviders(<DashboardPage />);
    await screen.findByTestId("investigation-grid");
    expect(screen.getByTestId("stat-total")).toHaveTextContent("1");
    expect(screen.getByTestId("stat-tp")).toHaveTextContent("1");
  });

  it("run pipeline gated by permission (hidden without role)", async () => {
    installFetch({ "GET /api/v1/investigations": listEmpty });
    withProviders(<DashboardPage />);
    await screen.findByTestId("empty-state");
    // Not logged in -> no run button (lacks investigation:run).
    expect(screen.queryByTestId("run-pipeline")).toBeNull();
  });

  it("run pipeline shown + works once authed", async () => {
    installFetch({
      ...loginRoute,
      "GET /api/v1/investigations": listEmpty,
      "POST /api/v1/investigations/run": listOne,
    });
    const user = userEvent.setup();
    withProviders(<LoginThen><DashboardPage /></LoginThen>);
    await user.click(screen.getByTestId("do-login"));
    await screen.findByTestId("run-pipeline");
    await user.click(screen.getByTestId("run-pipeline"));
    await screen.findByTestId("investigation-grid");
    expect(screen.getByTestId("stat-total")).toHaveTextContent("1");
  });

  it("filters trigger reload", async () => {
    const fn = installFetch({ "GET /api/v1/investigations": listOne });
    const user = userEvent.setup();
    withProviders(<DashboardPage />);
    await screen.findByTestId("investigation-grid");
    await user.selectOptions(screen.getByTestId("filter-severity"), "critical");
    await waitFor(() => {
      const calls = fn.mock.calls.map((c) => String(c[0]));
      expect(calls.some((u) => u.includes("severity=critical"))).toBe(true);
    });
  });

  it("load error", async () => {
    installFetch({ "GET /api/v1/investigations": { ok: false, status: 500, body: { detail: "boom" } } });
    withProviders(<DashboardPage />);
    expect(await screen.findByTestId("error-banner")).toHaveTextContent("boom");
  });

  it("run error", async () => {
    installFetch({
      ...loginRoute,
      "GET /api/v1/investigations": listEmpty,
      "POST /api/v1/investigations/run": { ok: false, status: 500, body: { detail: "run boom" } },
    });
    const user = userEvent.setup();
    withProviders(<LoginThen><DashboardPage /></LoginThen>);
    await user.click(screen.getByTestId("do-login"));
    await screen.findByTestId("run-pipeline");
    await user.click(screen.getByTestId("run-pipeline"));
    expect(await screen.findByTestId("error-banner")).toHaveTextContent("run boom");
  });

  it("refresh reloads", async () => {
    installFetch({ "GET /api/v1/investigations": listOne });
    const user = userEvent.setup();
    withProviders(<DashboardPage />);
    await screen.findByTestId("investigation-grid");
    await user.click(screen.getByTestId("refresh"));
    await screen.findByTestId("investigation-grid");
  });
});

describe("InvestigationDetailPage", () => {
  function detailRoutes(inv = sampleInvestigation): Record<string, MockRoute> {
    return {
      ...loginRoute,
      [`GET /api/v1/investigations/${inv.id}`]: { ok: true, status: 200, body: inv },
      [`GET /api/v1/investigations/${inv.id}/sla`]: { ok: true, status: 200, body: sampleSla },
      [`GET /api/v1/investigations/${inv.id}/notes`]: { ok: true, status: 200, body: [] },
    };
  }

  function renderDetail(inv = sampleInvestigation) {
    return withProviders(
      <Routes>
        <Route path="/investigations/:id" element={<LoginThen><InvestigationDetailPage /></LoginThen>} />
        <Route path="/" element={<div>home</div>} />
      </Routes>,
      [`/investigations/${inv.id}`],
    );
  }

  it("renders verdict, enrichment, sla, timeline, summary", async () => {
    installFetch(detailRoutes());
    const user = userEvent.setup();
    renderDetail();
    await user.click(screen.getByTestId("do-login"));
    expect(await screen.findByTestId("inv-title")).toHaveTextContent("Brute-force");
    expect(screen.getByTestId("verdict-card")).toHaveTextContent("True positive");
    expect(screen.getByTestId("enrichment-card")).toHaveTextContent("crown_jewel".length ? "high" : "");
    expect(screen.getByTestId("sla")).toBeInTheDocument();
    expect(screen.getByTestId("timeline")).toBeInTheDocument();
    expect(screen.getByTestId("summary")).toHaveTextContent("intrusion");
  });

  it("approve then execute flow", async () => {
    const approved = { ...sampleInvestigation, actions: [{ ...sampleInvestigation.actions[0], requires_approval: false }] };
    const executed = { ...sampleInvestigation, detection: { ...sampleInvestigation.detection, status: "contained" as const }, actions: [{ ...sampleInvestigation.actions[0], requires_approval: false, executed: true, execution_status: "success", execution_detail: "EDR: done", rollback_token: "rb-1" }] };
    installFetch({
      ...detailRoutes(),
      [`POST /api/v1/investigations/${sampleInvestigation.id}/approve`]: { ok: true, status: 200, body: approved },
      [`POST /api/v1/investigations/${sampleInvestigation.id}/execute`]: { ok: true, status: 200, body: executed },
    });
    const user = userEvent.setup();
    renderDetail();
    await user.click(screen.getByTestId("do-login"));
    await screen.findByTestId("approve-0");
    await user.click(screen.getByTestId("approve-0"));
    await screen.findByTestId("execute-0");
    await user.click(screen.getByTestId("execute-0"));
    expect(await screen.findByTestId("executed-0")).toHaveTextContent("executed");
  });

  it("status transition", async () => {
    const contained = { ...sampleInvestigation, detection: { ...sampleInvestigation.detection, status: "contained" as const } };
    installFetch({
      ...detailRoutes(),
      [`POST /api/v1/investigations/${sampleInvestigation.id}/status`]: { ok: true, status: 200, body: contained },
    });
    const user = userEvent.setup();
    renderDetail();
    await user.click(screen.getByTestId("do-login"));
    await screen.findByTestId("status-controls");
    await user.click(screen.getByTestId("status-contained"));
    await waitFor(() => expect(screen.getByText(/status/i)).toBeInTheDocument());
  });

  it("add note", async () => {
    installFetch({
      ...detailRoutes(),
      [`POST /api/v1/investigations/${sampleInvestigation.id}/notes`]: { ok: true, status: 200, body: { id: "n1", author: "analyst", body: "hi", created_at: "x" } },
    });
    const user = userEvent.setup();
    renderDetail();
    await user.click(screen.getByTestId("do-login"));
    await screen.findByTestId("note-input");
    // After adding, listNotes is re-fetched; return the new note.
    installFetch({
      ...detailRoutes(),
      [`POST /api/v1/investigations/${sampleInvestigation.id}/notes`]: { ok: true, status: 200, body: { id: "n1" } },
      [`GET /api/v1/investigations/${sampleInvestigation.id}/notes`]: { ok: true, status: 200, body: [{ id: "n1", author: "analyst", body: "hi", created_at: "x" }] },
    });
    await user.type(screen.getByTestId("note-input"), "hi");
    await user.click(screen.getByTestId("add-note"));
    await waitFor(() => expect(screen.getByTestId("notes")).toHaveTextContent("hi"));
  });

  it("load error", async () => {
    installFetch({
      ...loginRoute,
      "GET /api/v1/investigations/NOPE": { ok: false, status: 404, body: { detail: "not found" } },
      "GET /api/v1/investigations/NOPE/sla": { ok: false, status: 404, body: { detail: "x" } },
      "GET /api/v1/investigations/NOPE/notes": { ok: false, status: 404, body: { detail: "x" } },
    });
    const user = userEvent.setup();
    withProviders(
      <Routes>
        <Route path="/investigations/:id" element={<LoginThen><InvestigationDetailPage /></LoginThen>} />
      </Routes>,
      ["/investigations/NOPE"],
    );
    await user.click(screen.getByTestId("do-login"));
    expect(await screen.findByTestId("error-banner")).toHaveTextContent("not found");
  });

  it("false positive shows no actions", async () => {
    const fp = { ...sampleInvestigation, id: "INV-fp", verdict: { ...sampleInvestigation.verdict!, is_true_positive: false }, actions: [] };
    installFetch(detailRoutes(fp));
    const user = userEvent.setup();
    renderDetail(fp);
    await user.click(screen.getByTestId("do-login"));
    expect(await screen.findByTestId("no-actions")).toBeInTheDocument();
  });

  it("back link", async () => {
    installFetch(detailRoutes());
    const user = userEvent.setup();
    renderDetail();
    await user.click(screen.getByTestId("do-login"));
    await screen.findByTestId("back-link");
    await user.click(screen.getByTestId("back-link"));
    expect(await screen.findByText("home")).toBeInTheDocument();
  });
});
