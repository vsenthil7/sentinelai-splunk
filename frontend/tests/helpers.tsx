import { vi } from "vitest";
import type { Investigation, Incident, AuditEntry, Rule, User } from "../src/types";

export interface MockRoute {
  ok: boolean;
  status: number;
  body: unknown;
}

// Match by "METHOD path" or just "path"; supports query-string-insensitive match.
export function installFetch(routes: Record<string, MockRoute>) {
  const fn = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const raw = typeof url === "string" ? url : url.toString();
    const path = raw.split("?")[0];
    const method = (init?.method ?? "GET").toUpperCase();
    const route =
      routes[`${method} ${raw}`] ??
      routes[`${method} ${path}`] ??
      routes[raw] ??
      routes[path];
    if (!route) {
      throw new Error(`No mock route for ${method} ${raw}`);
    }
    return {
      ok: route.ok,
      status: route.status,
      headers: new Headers(),
      json: async () => route.body,
    } as unknown as Response;
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

export const tokenBody = {
  access_token: "tok",
  token_type: "bearer",
  role: "admin",
  tenant: "default",
};

export const sampleDetectionEnrichment = {
  asset_criticality: "high",
  threat_intel: { verdict: "malicious" },
  risk_boost: 1.4,
  indicators: ["203.0.113.5"],
};

export const sampleInvestigation: Investigation = {
  id: "INV-abc12345",
  detection: {
    id: "DET-1",
    title: "Brute-force authentication",
    description: "High volume of failed auth attempts.",
    severity: "high",
    status: "investigating",
    spl_query: "search index=auth failed",
    entity: "web-prod-01",
    event_count: 12,
    created_at: "2026-06-08T10:00:00Z",
    mitre_tactics: ["TA0006"],
    src_ips: ["203.0.113.5"],
    users: ["admin"],
    enrichment: sampleDetectionEnrichment,
  },
  verdict: {
    detection_id: "DET-1",
    is_true_positive: true,
    confidence: 0.92,
    rationale: "Indicators consistent with an active attack.",
    recommended_severity: "high",
    suggested_actions: ["isolate_host"],
  },
  timeline: ["Detection raised", "Triage verdict: TRUE positive"],
  actions: [
    {
      action_type: "isolate_host",
      target: "web-prod-01",
      rationale: "Recommended by triage.",
      requires_approval: true,
      executed: false,
      execution_status: null,
      execution_detail: null,
      rollback_token: null,
    },
  ],
  summary: "Coordinated intrusion attempt; containment queued.",
  assignee: null,
  created_at: "2026-06-08T10:00:00Z",
};

export const sampleSla = {
  ack_target_min: 15,
  ack_elapsed_min: 2.0,
  ack_breached: false,
  contain_target_min: 60,
  contain_elapsed_min: 5.0,
  contain_breached: false,
};

export const sampleIncident: Incident = {
  id: "INC-1",
  title: "Brute-force authentication (+1 related)",
  entity: "web-prod-01",
  severity: "critical",
  risk_score: 95,
  investigation_ids: ["INV-abc12345", "INV-def"],
  indicators: ["203.0.113.5"],
  mitre_tactics: ["TA0006"],
  created_at: "2026-06-08T10:00:00Z",
};

export const sampleAudit: AuditEntry = {
  id: 1,
  actor: "analyst",
  action: "investigation.created",
  target_type: "investigation",
  target_id: "INV-abc12345",
  detail: {},
  entry_hash: "abc123def456",
  created_at: "2026-06-08T10:00:00Z",
};

export const sampleRules: Rule[] = [
  {
    rule_id: "R001",
    title: "Brute-force authentication",
    description: "High volume of failed auth.",
    base_severity: "high",
    mitre_tactics: ["TA0006"],
    enabled: true,
  },
  {
    rule_id: "R002",
    title: "Suspicious outbound traffic",
    description: "Large outbound transfer.",
    base_severity: "high",
    mitre_tactics: ["TA0010"],
    enabled: false,
  },
];

export const sampleUsers: User[] = [
  { id: "u1", username: "analyst", role: "admin", external_id: null, created_at: "2026-06-08T10:00:00Z" },
  { id: "u2", username: "bob", role: "viewer", external_id: "okta|x", created_at: "2026-06-08T10:00:00Z" },
];
