import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import { useAuth } from "../hooks/useAuth";
import type { MitreCoverage, Rule } from "../types";
import { ErrorBanner, SeverityBadge, Spinner } from "../components/ui";

export function RulesPage() {
  const { can } = useAuth();
  const [rules, setRules] = useState<Rule[]>([]);
  const [coverage, setCoverage] = useState<MitreCoverage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [r, c] = await Promise.all([api.listRules(), api.mitreCoverage()]);
      setRules(r);
      setCoverage(c);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load rules");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function toggle(ruleId: string, enabled: boolean) {
    setBusy(ruleId);
    setError(null);
    try {
      await api.toggleRule(ruleId, enabled);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Toggle failed");
    } finally {
      setBusy(null);
    }
  }

  if (loading) return <Spinner label="Loading rules" />;

  return (
    <div>
      <h1 className="page-title">Detection Rules</h1>
      <p className="page-sub">MITRE-mapped detection library and per-tenant coverage.</p>
      {error && <ErrorBanner message={error} />}

      {coverage && (
        <div className="stat-row">
          <div className="stat">
            <div className="stat-value" data-testid="rules-enabled">
              {coverage.enabled_rules}/{coverage.total_rules}
            </div>
            <div className="stat-label">Rules enabled</div>
          </div>
          <div className="stat">
            <div className="stat-value">{Object.keys(coverage.coverage).length}</div>
            <div className="stat-label">MITRE tactics covered</div>
          </div>
        </div>
      )}

      <div data-testid="rules-list">
        {rules.map((r) => (
          <div className="action-row" key={r.rule_id} data-testid={`rule-${r.rule_id}`}>
            <div className="action-info">
              <span className="action-type">
                {r.rule_id} · {r.title} <SeverityBadge severity={r.base_severity} />
              </span>
              <span className="action-target">
                {r.description} · {r.mitre_tactics.join(", ")}
              </span>
            </div>
            {can("admin:*") ? (
              <button
                className={`btn btn-sm ${r.enabled ? "" : "btn-primary"}`}
                data-testid={`toggle-${r.rule_id}`}
                disabled={busy !== null}
                onClick={() => void toggle(r.rule_id, !r.enabled)}
              >
                {r.enabled ? "Disable" : "Enable"}
              </button>
            ) : (
              <span className="pill-approved">{r.enabled ? "enabled" : "disabled"}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
