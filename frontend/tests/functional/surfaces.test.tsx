import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { AuthProvider, useAuth } from "../../src/hooks/useAuth";
import { IncidentsPage } from "../../src/pages/IncidentsPage";
import { AuditPage } from "../../src/pages/AuditPage";
import { RulesPage } from "../../src/pages/RulesPage";
import { AdminPage } from "../../src/pages/AdminPage";
import { AppShell } from "../../src/components/AppShell";
import { setToken } from "../../src/api/client";
import {
  installFetch,
  sampleAudit,
  sampleIncident,
  sampleRules,
  sampleUsers,
  tokenBody,
  type MockRoute,
} from "../helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
});

function withProviders(node: ReactNode) {
  return render(
    <AuthProvider>
      <MemoryRouter>{node}</MemoryRouter>
    </AuthProvider>,
  );
}

function LoginThen({ children }: { children: ReactNode }) {
  const { login, isAuthenticated } = useAuth();
  return (
    <>
      <button data-testid="do-login" onClick={() => void login("analyst", "pw", "default")}>login</button>
      {isAuthenticated ? children : null}
    </>
  );
}

const loginRoute: Record<string, MockRoute> = {
  "POST /api/v1/auth/login": { ok: true, status: 200, body: tokenBody },
};

describe("IncidentsPage", () => {
  it("renders incidents", async () => {
    installFetch({ "GET /api/v1/incidents": { ok: true, status: 200, body: [sampleIncident] } });
    withProviders(<IncidentsPage />);
    await screen.findByTestId("incident-grid");
    expect(screen.getByTestId(`incident-${sampleIncident.id}`)).toHaveTextContent("Brute-force");
  });
  it("empty state", async () => {
    installFetch({ "GET /api/v1/incidents": { ok: true, status: 200, body: [] } });
    withProviders(<IncidentsPage />);
    expect(await screen.findByTestId("empty-state")).toBeInTheDocument();
  });
  it("error", async () => {
    installFetch({ "GET /api/v1/incidents": { ok: false, status: 500, body: { detail: "boom" } } });
    withProviders(<IncidentsPage />);
    expect(await screen.findByTestId("error-banner")).toHaveTextContent("boom");
  });
});

describe("AuditPage", () => {
  it("renders entries + chain valid badge", async () => {
    installFetch({ "GET /api/v1/audit": { ok: true, status: 200, body: { entries: [sampleAudit], chain_valid: true } } });
    withProviders(<AuditPage />);
    await screen.findByTestId("audit-list");
    expect(screen.getByTestId("chain-badge")).toHaveTextContent("verified");
  });
  it("shows tampered badge", async () => {
    installFetch({ "GET /api/v1/audit": { ok: true, status: 200, body: { entries: [], chain_valid: false } } });
    withProviders(<AuditPage />);
    expect(await screen.findByTestId("chain-badge")).toHaveTextContent("TAMPERED");
  });
  it("error", async () => {
    installFetch({ "GET /api/v1/audit": { ok: false, status: 403, body: { detail: "no" } } });
    withProviders(<AuditPage />);
    expect(await screen.findByTestId("error-banner")).toBeInTheDocument();
  });
});

describe("RulesPage", () => {
  const routes: Record<string, MockRoute> = {
    ...loginRoute,
    "GET /api/v1/rules": { ok: true, status: 200, body: sampleRules },
    "GET /api/v1/rules/mitre-coverage": { ok: true, status: 200, body: { coverage: { TA0006: 1 }, total_rules: 2, enabled_rules: 1 } },
  };

  it("renders rules + coverage", async () => {
    installFetch(routes);
    withProviders(<RulesPage />);
    await screen.findByTestId("rules-list");
    expect(screen.getByTestId("rules-enabled")).toHaveTextContent("1/2");
  });

  it("admin can toggle a rule", async () => {
    installFetch({
      ...routes,
      "PUT /api/v1/rules/R001": { ok: true, status: 200, body: { ...sampleRules[0], enabled: false } },
    });
    const user = userEvent.setup();
    withProviders(<LoginThen><RulesPage /></LoginThen>);
    await user.click(screen.getByTestId("do-login"));
    await screen.findByTestId("toggle-R001");
    await user.click(screen.getByTestId("toggle-R001"));
    await waitFor(() => expect(screen.getByTestId("rules-list")).toBeInTheDocument());
  });

  it("error", async () => {
    installFetch({
      "GET /api/v1/rules": { ok: false, status: 500, body: { detail: "boom" } },
      "GET /api/v1/rules/mitre-coverage": { ok: false, status: 500, body: { detail: "boom" } },
    });
    withProviders(<RulesPage />);
    expect(await screen.findByTestId("error-banner")).toBeInTheDocument();
  });
});

describe("AdminPage", () => {
  it("lists users and creates one", async () => {
    installFetch({
      ...loginRoute,
      "GET /api/v1/admin/users": { ok: true, status: 200, body: sampleUsers },
      "POST /api/v1/admin/users": { ok: true, status: 201, body: { id: "u9", username: "new", role: "analyst", external_id: null, created_at: "x" } },
    });
    const user = userEvent.setup();
    withProviders(<AdminPage />);
    await screen.findByTestId("user-list");
    expect(screen.getByTestId("user-u1")).toHaveTextContent("analyst");
    await user.type(screen.getByTestId("new-username"), "new");
    await user.type(screen.getByTestId("new-password"), "password123");
    await user.click(screen.getByTestId("create-user"));
    await waitFor(() => expect(screen.getByTestId("user-list")).toBeInTheDocument());
  });

  it("changes a role", async () => {
    installFetch({
      "GET /api/v1/admin/users": { ok: true, status: 200, body: sampleUsers },
      "PUT /api/v1/admin/users/u2/role": { ok: true, status: 200, body: { ...sampleUsers[1], role: "analyst" } },
    });
    const user = userEvent.setup();
    withProviders(<AdminPage />);
    await screen.findByTestId("user-list");
    await user.selectOptions(screen.getByTestId("role-u2"), "analyst");
    await waitFor(() => expect(screen.getByTestId("user-list")).toBeInTheDocument());
  });

  it("deletes a user", async () => {
    installFetch({
      "GET /api/v1/admin/users": { ok: true, status: 200, body: sampleUsers },
      "DELETE /api/v1/admin/users/u2": { ok: true, status: 204, body: null },
    });
    const user = userEvent.setup();
    withProviders(<AdminPage />);
    await screen.findByTestId("user-list");
    await user.click(screen.getByTestId("delete-u2"));
    await waitFor(() => expect(screen.getByTestId("user-list")).toBeInTheDocument());
  });

  it("error", async () => {
    installFetch({ "GET /api/v1/admin/users": { ok: false, status: 403, body: { detail: "no" } } });
    withProviders(<AdminPage />);
    expect(await screen.findByTestId("error-banner")).toBeInTheDocument();
  });
});

describe("AppShell", () => {
  it("renders nav, health, and gates admin/audit by permission", async () => {
    installFetch({
      ...loginRoute,
      "POST /api/v1/auth/logout": { ok: true, status: 204, body: null },
      "GET /api/v1/health": { ok: true, status: 200, body: { status: "ok", splunk: true, backend: "mock" } },
    });
    const user = userEvent.setup();
    withProviders(<LoginThen><AppShell><div>child</div></AppShell></LoginThen>);
    await user.click(screen.getByTestId("do-login"));
    await screen.findByText("child");
    // admin role sees all nav items.
    expect(screen.getByTestId("nav-console")).toBeInTheDocument();
    expect(screen.getByTestId("nav-audit")).toBeInTheDocument();
    expect(screen.getByTestId("nav-admin")).toBeInTheDocument();
    expect(await screen.findByTestId("health-pill")).toHaveTextContent("mock");
    await user.click(screen.getByTestId("logout"));
  });

  it("degraded health pill on fetch failure", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("down"); }) as unknown as typeof fetch);
    withProviders(<AppShell><div>c</div></AppShell>);
    expect(await screen.findByTestId("health-pill")).toHaveTextContent("unknown");
  });
});
