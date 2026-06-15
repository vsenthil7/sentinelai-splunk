import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, renderHook, act } from "@testing-library/react";
import type { ReactNode } from "react";
import { Empty, ErrorBanner, SeverityBadge, Spinner } from "../../src/components/ui";
import { AuthProvider, useAuth } from "../../src/hooks/useAuth";
import { can } from "../../src/api/rbac";
import { getToken, setToken } from "../../src/api/client";
import { installFetch, tokenBody } from "../helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
});

describe("UI components", () => {
  it("SeverityBadge", () => {
    render(<SeverityBadge severity="critical" />);
    expect(screen.getByTestId("severity-badge")).toHaveClass("badge-critical");
  });
  it("Spinner with/without label", () => {
    const { rerender } = render(<Spinner label="Loading" />);
    expect(screen.getByTestId("spinner")).toHaveTextContent("Loading");
    rerender(<Spinner />);
    expect(screen.getByTestId("spinner")).toBeInTheDocument();
  });
  it("ErrorBanner", () => {
    render(<ErrorBanner message="boom" />);
    expect(screen.getByRole("alert")).toHaveTextContent("boom");
  });
  it("Empty", () => {
    render(<Empty message="nothing" />);
    expect(screen.getByTestId("empty-state")).toHaveTextContent("nothing");
  });
});

describe("rbac helper", () => {
  it("admin can everything", () => {
    expect(can("admin", "admin:*")).toBe(true);
    expect(can("admin", "audit:read")).toBe(true);
  });
  it("viewer limited", () => {
    expect(can("viewer", "investigation:read")).toBe(true);
    expect(can("viewer", "investigation:run")).toBe(false);
  });
  it("responder approves, analyst doesn't", () => {
    expect(can("responder", "action:approve")).toBe(true);
    expect(can("analyst", "action:approve")).toBe(false);
  });
  it("null role denies", () => {
    expect(can(null, "investigation:read")).toBe(false);
  });
});

function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

describe("useAuth", () => {
  it("starts unauthenticated", () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.role).toBeNull();
  });

  it("login stores token, role, tenant", async () => {
    installFetch({ "POST /api/v1/auth/login": { ok: true, status: 200, body: tokenBody } });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await act(async () => {
      await result.current.login("analyst", "pw", "default");
    });
    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.role).toBe("admin");
    expect(result.current.tenant).toBe("default");
    expect(result.current.can("admin:*")).toBe(true);
    expect(getToken()).toBe("tok");
  });

  it("logout clears state and calls revocation endpoint", async () => {
    const fn = installFetch({
      "POST /api/v1/auth/login": { ok: true, status: 200, body: tokenBody },
      "POST /api/v1/auth/logout": { ok: true, status: 204, body: null },
    });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await act(async () => {
      await result.current.login("analyst", "pw", "default");
    });
    await act(async () => {
      result.current.logout();
    });
    expect(result.current.isAuthenticated).toBe(false);
    expect(getToken()).toBeNull();
    const calledLogout = fn.mock.calls.some((c) => String(c[0]).includes("/auth/logout"));
    expect(calledLogout).toBe(true);
  });

  it("throws outside provider", () => {
    expect(() => renderHook(() => useAuth())).toThrow(/within AuthProvider/);
  });
});
