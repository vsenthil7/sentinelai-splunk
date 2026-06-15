import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useAuth } from "../hooks/useAuth";
import type { Investigation } from "../types";
import { Empty, ErrorBanner, SeverityBadge, Spinner } from "../components/ui";

const SEVERITIES = ["", "critical", "high", "medium", "low", "info"];
const STATUSES = ["", "investigating", "contained", "resolved", "false_positive"];

export function DashboardPage() {
  const { can } = useAuth();
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [severity, setSeverity] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await api.listInvestigations({
        severity: severity || undefined,
        status: statusFilter || undefined,
        limit: 100,
      });
      setInvestigations(resp.investigations);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load investigations");
    } finally {
      setLoading(false);
    }
  }, [severity, statusFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  async function runPipeline() {
    setRunning(true);
    setError(null);
    try {
      const resp = await api.runInvestigations();
      setInvestigations(resp.investigations);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Pipeline failed");
    } finally {
      setRunning(false);
    }
  }

  const truePositives = investigations.filter((i) => i.verdict?.is_true_positive).length;
  const critical = investigations.filter(
    (i) => i.detection.severity === "critical",
  ).length;

  return (
    <div>
      <h1 className="page-title">Operations Console</h1>
      <p className="page-sub">
        AI agents detect, triage, and plan response across your Splunk telemetry.
      </p>

      <div className="stat-row">
        <div className="stat">
          <div className="stat-value" data-testid="stat-total">
            {investigations.length}
          </div>
          <div className="stat-label">Investigations</div>
        </div>
        <div className="stat">
          <div className="stat-value" data-testid="stat-tp">
            {truePositives}
          </div>
          <div className="stat-label">True Positives</div>
        </div>
        <div className="stat">
          <div className="stat-value" data-testid="stat-critical">
            {critical}
          </div>
          <div className="stat-label">Critical</div>
        </div>
      </div>

      <div className="toolbar">
        {can("investigation:run") && (
          <button
            className="btn btn-primary"
            data-testid="run-pipeline"
            onClick={() => void runPipeline()}
            disabled={running}
          >
            {running ? <Spinner label="Running agents" /> : "Run detection pipeline"}
          </button>
        )}
        <select
          data-testid="filter-severity"
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
          style={{ background: "var(--bg-1)", border: "1px solid var(--border-bright)", borderRadius: 6, padding: "8px 12px", color: "var(--text-0)" }}
        >
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>{s ? `severity: ${s}` : "all severities"}</option>
          ))}
        </select>
        <select
          data-testid="filter-status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          style={{ background: "var(--bg-1)", border: "1px solid var(--border-bright)", borderRadius: 6, padding: "8px 12px", color: "var(--text-0)" }}
        >
          {STATUSES.map((s) => (
            <option key={s} value={s}>{s ? `status: ${s}` : "all statuses"}</option>
          ))}
        </select>
        <button
          className="btn"
          data-testid="refresh"
          onClick={() => void load()}
          disabled={loading}
        >
          Refresh
        </button>
      </div>

      {error && <ErrorBanner message={error} />}

      {loading ? (
        <Spinner label="Loading" />
      ) : investigations.length === 0 ? (
        <Empty message="No investigations yet. Run the detection pipeline to begin." />
      ) : (
        <div className="grid grid-cards" data-testid="investigation-grid">
          {investigations.map((inv) => (
            <Link
              key={inv.id}
              to={`/investigations/${inv.id}`}
              className="card"
              data-testid={`inv-card-${inv.id}`}
            >
              <div className="card-head">
                <span className="card-title">{inv.detection.title}</span>
                <SeverityBadge severity={inv.detection.severity} />
              </div>
              <div className="card-meta">
                {inv.detection.entity} · {inv.detection.event_count} events
              </div>
              <p style={{ marginTop: 10, color: "var(--text-1)", fontSize: 13 }}>
                {inv.detection.description}
              </p>
              <div style={{ marginTop: 12 }}>
                {inv.detection.mitre_tactics.map((t) => (
                  <span className="tag" key={t}>
                    {t}
                  </span>
                ))}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
