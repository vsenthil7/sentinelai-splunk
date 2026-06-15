import type {
  AuditList,
  CaseNote,
  Detection,
  HealthResponse,
  Incident,
  Investigation,
  InvestigationList,
  MitreCoverage,
  Rule,
  SLA,
  TokenResponse,
  User,
} from "../types";

const BASE = "/api/v1";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

let authToken: string | null = null;

export function setToken(token: string | null): void {
  authToken = token;
}

export function getToken(): string | null {
  return authToken;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) ?? {}),
  };
  if (authToken) {
    headers.Authorization = `Bearer ${authToken}`;
  }
  const resp = await fetch(`${BASE}${path}`, { ...options, headers });
  if (resp.status === 204) {
    return undefined as T;
  }
  if (!resp.ok) {
    let detail = `Request failed (${resp.status})`;
    try {
      const body = await resp.json();
      if (body?.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // non-JSON error body; keep default detail
    }
    throw new ApiError(resp.status, detail);
  }
  return (await resp.json()) as T;
}

export const api = {
  health: (): Promise<HealthResponse> => request<HealthResponse>("/health"),

  login: (username: string, password: string, tenant: string): Promise<TokenResponse> =>
    request<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password, tenant }),
    }),

  logout: (): Promise<void> => request<void>("/auth/logout", { method: "POST" }),

  runDetections: (): Promise<Detection[]> =>
    request<Detection[]>("/detections/run", { method: "POST" }),

  runInvestigations: (): Promise<InvestigationList> =>
    request<InvestigationList>("/investigations/run", { method: "POST" }),

  listInvestigations: (params?: {
    status?: string;
    severity?: string;
    assignee?: string;
    limit?: number;
    offset?: number;
  }): Promise<InvestigationList> => {
    const q = new URLSearchParams();
    if (params?.status) q.set("status", params.status);
    if (params?.severity) q.set("severity", params.severity);
    if (params?.assignee) q.set("assignee", params.assignee);
    if (params?.limit != null) q.set("limit", String(params.limit));
    if (params?.offset != null) q.set("offset", String(params.offset));
    const qs = q.toString();
    return request<InvestigationList>(`/investigations${qs ? `?${qs}` : ""}`);
  },

  getInvestigation: (id: string): Promise<Investigation> =>
    request<Investigation>(`/investigations/${id}`),

  approveAction: (id: string, actionIndex: number): Promise<Investigation> =>
    request<Investigation>(`/investigations/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ action_index: actionIndex }),
    }),

  executeAction: (id: string, actionIndex: number): Promise<Investigation> =>
    request<Investigation>(`/investigations/${id}/execute`, {
      method: "POST",
      body: JSON.stringify({ action_index: actionIndex }),
    }),

  transitionStatus: (id: string, status: string): Promise<Investigation> =>
    request<Investigation>(`/investigations/${id}/status`, {
      method: "POST",
      body: JSON.stringify({ status }),
    }),

  getSla: (id: string): Promise<SLA> => request<SLA>(`/investigations/${id}/sla`),

  assign: (id: string, assignee: string | null): Promise<Investigation> =>
    request<Investigation>(`/investigations/${id}/assign`, {
      method: "POST",
      body: JSON.stringify({ assignee }),
    }),

  addNote: (id: string, body: string): Promise<CaseNote> =>
    request<CaseNote>(`/investigations/${id}/notes`, {
      method: "POST",
      body: JSON.stringify({ body }),
    }),

  listNotes: (id: string): Promise<CaseNote[]> =>
    request<CaseNote[]>(`/investigations/${id}/notes`),

  listIncidents: (): Promise<Incident[]> => request<Incident[]>("/incidents"),

  getIncident: (id: string): Promise<Incident> => request<Incident>(`/incidents/${id}`),

  listAudit: (): Promise<AuditList> => request<AuditList>("/audit"),

  listRules: (): Promise<Rule[]> => request<Rule[]>("/rules"),

  toggleRule: (ruleId: string, enabled: boolean): Promise<Rule> =>
    request<Rule>(`/rules/${ruleId}`, {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),

  mitreCoverage: (): Promise<MitreCoverage> =>
    request<MitreCoverage>("/rules/mitre-coverage"),

  listUsers: (): Promise<User[]> => request<User[]>("/admin/users"),

  createUser: (username: string, password: string, role: string): Promise<User> =>
    request<User>("/admin/users", {
      method: "POST",
      body: JSON.stringify({ username, password, role }),
    }),

  updateRole: (userId: string, role: string): Promise<User> =>
    request<User>(`/admin/users/${userId}/role`, {
      method: "PUT",
      body: JSON.stringify({ role }),
    }),

  deleteUser: (userId: string): Promise<void> =>
    request<void>(`/admin/users/${userId}`, { method: "DELETE" }),
};
