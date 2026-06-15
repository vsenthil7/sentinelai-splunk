import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { App } from "../../src/App";
import { setToken } from "../../src/api/client";
import { installFetch, tokenBody, type MockRoute } from "../helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
});

function renderApp(entries: string[]) {
  return render(
    <MemoryRouter initialEntries={entries}>
      <App />
    </MemoryRouter>,
  );
}

const healthRoute: MockRoute = { ok: true, status: 200, body: { status: "ok", splunk: true, backend: "mock" } };

describe("route protection", () => {
  it("redirects unauthenticated dashboard to login", async () => {
    renderApp(["/"]);
    expect(await screen.findByTestId("login-button")).toBeInTheDocument();
  });

  it("redirects unauthenticated detail to login", async () => {
    renderApp(["/investigations/INV-1"]);
    expect(await screen.findByTestId("login-button")).toBeInTheDocument();
  });

  it("redirects unauthenticated incidents/rules/audit/admin to login", async () => {
    for (const path of ["/incidents", "/rules", "/audit", "/admin"]) {
      const { unmount } = renderApp([path]);
      expect(await screen.findByTestId("login-button")).toBeInTheDocument();
      unmount();
    }
  });

  it("unknown route redirects to dashboard (then login when unauthed)", async () => {
    renderApp(["/totally/unknown"]);
    expect(await screen.findByTestId("login-button")).toBeInTheDocument();
  });

  it("full login flow lands on console", async () => {
    installFetch({
      "POST /api/v1/auth/login": { ok: true, status: 200, body: tokenBody },
      "GET /api/v1/health": healthRoute,
      "GET /api/v1/investigations": { ok: true, status: 200, body: { investigations: [], total: 0, limit: 100, offset: 0 } },
    });
    const user = userEvent.setup();
    renderApp(["/login"]);
    await user.type(screen.getByTestId("tenant-input"), "default");
    await user.type(screen.getByTestId("username-input"), "analyst");
    await user.type(screen.getByTestId("password-input"), "pw");
    await user.click(screen.getByTestId("login-button"));
    await waitFor(() => expect(screen.getByText("Operations Console")).toBeInTheDocument());
  });

  it("viewer is denied audit/admin via permission guard", async () => {
    installFetch({
      "POST /api/v1/auth/login": { ok: true, status: 200, body: { ...tokenBody, role: "viewer" } },
      "GET /api/v1/health": healthRoute,
      "GET /api/v1/investigations": { ok: true, status: 200, body: { investigations: [], total: 0, limit: 100, offset: 0 } },
    });
    const user = userEvent.setup();
    renderApp(["/login"]);
    await user.type(screen.getByTestId("tenant-input"), "default");
    await user.type(screen.getByTestId("username-input"), "v");
    await user.type(screen.getByTestId("password-input"), "pw");
    await user.click(screen.getByTestId("login-button"));
    await waitFor(() => expect(screen.getByText("Operations Console")).toBeInTheDocument());
    // viewer nav should not include audit/admin
    expect(screen.queryByTestId("nav-audit")).toBeNull();
    expect(screen.queryByTestId("nav-admin")).toBeNull();
  });
});
