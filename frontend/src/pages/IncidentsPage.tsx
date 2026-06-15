import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Incident } from "../types";
import { Empty, ErrorBanner, SeverityBadge, Spinner } from "../components/ui";

export function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setIncidents(await api.listIncidents());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load incidents");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div>
      <h1 className="page-title">Incidents</h1>
      <p className="page-sub">
        Correlated groups of related investigations, ranked by risk.
      </p>
      {error && <ErrorBanner message={error} />}
      {loading ? (
        <Spinner label="Loading" />
      ) : incidents.length === 0 ? (
        <Empty message="No incidents. Run the detection pipeline from the console." />
      ) : (
        <div className="grid grid-cards" data-testid="incident-grid">
          {incidents.map((inc) => (
            <div className="card" key={inc.id} data-testid={`incident-${inc.id}`}>
              <div className="card-head">
                <span className="card-title">{inc.title}</span>
                <SeverityBadge severity={inc.severity} />
              </div>
              <div className="card-meta">
                {inc.entity} · risk {inc.risk_score} · {inc.investigation_ids.length} investigation
                {inc.investigation_ids.length === 1 ? "" : "s"}
              </div>
              <div style={{ marginTop: 10 }}>
                {inc.mitre_tactics.map((t) => (
                  <span className="tag" key={t}>{t}</span>
                ))}
              </div>
              {inc.indicators.length > 0 && (
                <p style={{ marginTop: 10, color: "var(--text-1)", fontSize: 12 }} className="mono">
                  {inc.indicators.slice(0, 6).join(", ")}
                  {inc.indicators.length > 6 ? ` +${inc.indicators.length - 6} more` : ""}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
