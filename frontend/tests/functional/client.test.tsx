import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, getToken, setToken } from "../../src/api/client";
import { installFetch, sampleInvestigation, tokenBody } from "../helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
});

describe("token management", () => {
  it("sets and gets and clears", () => {
    setToken("abc");
    expect(getToken()).toBe("abc");
    setToken(null);
    expect(getToken()).toBeNull();
  });
});

describe("login + auth header", () => {
  it("posts credentials with tenant", async () => {
    const fn = installFetch({ "POST /api/v1/auth/login": { ok: true, status: 200, body: tokenBody } });
    const resp = await api.login("analyst", "pw", "default");
    expect(resp.role).toBe("admin");
    const sent = JSON.parse((fn.mock.calls[0][1]?.body as string) ?? "{}");
    expect(sent.tenant).toBe("default");
  });

  it("attaches bearer token when set", async () => {
    setToken("my-token");
    const fn = installFetch({
      "POST /api/v1/investigations/run": {
        ok: true,
        status: 200,
        body: { investigations: [sampleInvestigation], total: 1, limit: 1, offset: 0 },
      },
    });
    await api.runInvestigations();
    const headers = fn.mock.calls[0][1]?.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer my-token");
  });
});

describe("endpoints", () => {
  it("listInvestigations builds query string", async () => {
    const fn = installFetch({
      "GET /api/v1/investigations?severity=critical&limit=10": {
        ok: true,
        status: 200,
        body: { investigations: [], total: 0, limit: 10, offset: 0 },
      },
    });
    await api.listInvestigations({ severity: "critical", limit: 10 });
    expect(fn.mock.calls[0][0]).toContain("severity=critical");
  });

  it("getInvestigation / approve / execute / status / sla / assign / notes", async () => {
    installFetch({
      [`GET /api/v1/investigations/${sampleInvestigation.id}`]: { ok: true, status: 200, body: sampleInvestigation },
      [`POST /api/v1/investigations/${sampleInvestigation.id}/approve`]: { ok: true, status: 200, body: sampleInvestigation },
      [`POST /api/v1/investigations/${sampleInvestigation.id}/execute`]: { ok: true, status: 200, body: sampleInvestigation },
      [`POST /api/v1/investigations/${sampleInvestigation.id}/status`]: { ok: true, status: 200, body: sampleInvestigation },
      [`GET /api/v1/investigations/${sampleInvestigation.id}/sla`]: { ok: true, status: 200, body: { ack_elapsed_min: 1 } },
      [`POST /api/v1/investigations/${sampleInvestigation.id}/assign`]: { ok: true, status: 200, body: sampleInvestigation },
      [`POST /api/v1/investigations/${sampleInvestigation.id}/notes`]: { ok: true, status: 200, body: { id: "n1" } },
      [`GET /api/v1/investigations/${sampleInvestigation.id}/notes`]: { ok: true, status: 200, body: [] },
    });
    expect((await api.getInvestigation(sampleInvestigation.id)).id).toBe(sampleInvestigation.id);
    await api.approveAction(sampleInvestigation.id, 0);
    await api.executeAction(sampleInvestigation.id, 0);
    await api.transitionStatus(sampleInvestigation.id, "contained");
    await api.getSla(sampleInvestigation.id);
    await api.assign(sampleInvestigation.id, "bob");
    await api.addNote(sampleInvestigation.id, "note");
    expect(await api.listNotes(sampleInvestigation.id)).toEqual([]);
  });

  it("incidents / audit / rules / coverage / detections / health", async () => {
    installFetch({
      "GET /api/v1/incidents": { ok: true, status: 200, body: [] },
      "GET /api/v1/incidents/INC-1": { ok: true, status: 200, body: { id: "INC-1" } },
      "GET /api/v1/audit": { ok: true, status: 200, body: { entries: [], chain_valid: true } },
      "GET /api/v1/rules": { ok: true, status: 200, body: [] },
      "PUT /api/v1/rules/R001": { ok: true, status: 200, body: { rule_id: "R001" } },
      "GET /api/v1/rules/mitre-coverage": { ok: true, status: 200, body: { coverage: {}, total_rules: 0, enabled_rules: 0 } },
      "POST /api/v1/detections/run": { ok: true, status: 200, body: [] },
      "GET /api/v1/health": { ok: true, status: 200, body: { status: "ok", splunk: true, backend: "mock" } },
    });
    await api.listIncidents();
    await api.getIncident("INC-1");
    await api.listAudit();
    await api.listRules();
    await api.toggleRule("R001", false);
    await api.mitreCoverage();
    await api.runDetections();
    expect((await api.health()).backend).toBe("mock");
  });

  it("admin endpoints", async () => {
    installFetch({
      "GET /api/v1/admin/users": { ok: true, status: 200, body: [] },
      "POST /api/v1/admin/users": { ok: true, status: 201, body: { id: "u9" } },
      "PUT /api/v1/admin/users/u9/role": { ok: true, status: 200, body: { id: "u9", role: "admin" } },
      "DELETE /api/v1/admin/users/u9": { ok: true, status: 204, body: null },
    });
    await api.listUsers();
    await api.createUser("x", "password123", "analyst");
    await api.updateRole("u9", "admin");
    await api.deleteUser("u9");
  });
});

describe("error handling", () => {
  it("throws ApiError with string detail", async () => {
    installFetch({ "GET /api/v1/health": { ok: false, status: 401, body: { detail: "Invalid credentials" } } });
    await expect(api.health()).rejects.toThrow("Invalid credentials");
  });

  it("stringifies non-string detail", async () => {
    installFetch({ "GET /api/v1/health": { ok: false, status: 422, body: { detail: [{ msg: "bad" }] } } });
    await expect(api.health()).rejects.toThrow(/bad/);
  });

  it("falls back when body is not JSON", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: false, status: 500, headers: new Headers(),
      json: async () => { throw new Error("no json"); },
    })) as unknown as typeof fetch);
    await expect(api.health()).rejects.toThrow(/Request failed \(500\)/);
  });

  it("exposes status on ApiError", async () => {
    installFetch({ "GET /api/v1/health": { ok: false, status: 404, body: { detail: "x" } } });
    try {
      await api.health();
      expect.unreachable();
    } catch (e) {
      expect((e as ApiError).status).toBe(404);
    }
  });

  it("returns undefined on 204", async () => {
    installFetch({ "DELETE /api/v1/admin/users/u1": { ok: true, status: 204, body: null } });
    expect(await api.deleteUser("u1")).toBeUndefined();
  });
});
