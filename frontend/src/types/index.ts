export type Severity = "info" | "low" | "medium" | "high" | "critical";

export type DetectionStatus =
  | "new"
  | "triaged"
  | "investigating"
  | "contained"
  | "resolved"
  | "false_positive";

export interface Detection {
  id: string;
  title: string;
  description: string;
  severity: Severity;
  status: DetectionStatus;
  spl_query: string;
  entity: string;
  event_count: number;
  created_at: string;
  mitre_tactics: string[];
  src_ips: string[];
  users: string[];
  enrichment: Record<string, unknown>;
}

export interface TriageVerdict {
  detection_id: string;
  is_true_positive: boolean;
  confidence: number;
  rationale: string;
  recommended_severity: Severity;
  suggested_actions: string[];
}

export interface IncidentAction {
  action_type: string;
  target: string;
  rationale: string;
  requires_approval: boolean;
  executed: boolean;
  execution_status: string | null;
  execution_detail: string | null;
  rollback_token: string | null;
}

export interface Investigation {
  id: string;
  detection: Detection;
  verdict: TriageVerdict | null;
  timeline: string[];
  actions: IncidentAction[];
  summary: string;
  assignee: string | null;
  created_at: string;
}

export interface Incident {
  id: string;
  title: string;
  entity: string;
  severity: Severity;
  risk_score: number;
  investigation_ids: string[];
  indicators: string[];
  mitre_tactics: string[];
  created_at: string;
}

export interface InvestigationList {
  investigations: Investigation[];
  total: number;
  limit: number;
  offset: number;
}

export interface SLA {
  ack_target_min: number;
  ack_elapsed_min: number;
  ack_breached: boolean;
  contain_target_min: number;
  contain_elapsed_min: number;
  contain_breached: boolean;
}

export interface AuditEntry {
  id: number;
  actor: string;
  action: string;
  target_type: string;
  target_id: string;
  detail: Record<string, unknown>;
  entry_hash: string;
  created_at: string;
}

export interface AuditList {
  entries: AuditEntry[];
  chain_valid: boolean;
}

export interface CaseNote {
  id: string;
  author: string;
  body: string;
  created_at: string;
}

export interface Rule {
  rule_id: string;
  title: string;
  description: string;
  base_severity: Severity;
  mitre_tactics: string[];
  enabled: boolean;
}

export interface MitreCoverage {
  coverage: Record<string, number>;
  total_rules: number;
  enabled_rules: number;
}

export interface User {
  id: string;
  username: string;
  role: string;
  external_id: string | null;
  created_at: string;
}

export type Role = "viewer" | "analyst" | "responder" | "admin";

export interface TokenResponse {
  access_token: string;
  token_type: string;
  role: Role;
  tenant: string;
}

export interface HealthResponse {
  status: string;
  splunk: boolean;
  backend: string;
}
