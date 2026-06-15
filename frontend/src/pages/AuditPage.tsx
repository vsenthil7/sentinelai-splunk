import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { AuditEntry } from "../types";
import { Empty, ErrorBanner, Spinner } from "../components/ui";

export function AuditPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [chainValid, setChainValid] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listAudit();
      setEntries(res.entries);
      setChainValid(res.chain_valid);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load audit log");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div>
      <div className="card-head">
        <h1 className="page-title">Audit Log</h1>
        <span
          className={`health-pill`}
          data-testid="chain-badge"
          style={{ borderColor: chainValid ? "var(--ok)" : "var(--bad)" }}
        >
          <span className={`health-dot ${chainValid ? "ok" : "bad"}`} />
          {chainValid ? "chain verified" : "TAMPERED"}
        </span>
      </div>
      <p className="page-sub">Append-only, hash-chained record of every privileged action.</p>
      {error && <ErrorBanner message={error} />}
      {loading ? (
        <Spinner label="Loading" />
      ) : entries.length === 0 ? (
        <Empty message="No audit entries yet." />
      ) : (
        <div data-testid="audit-list">
          {entries.map((e) => (
            <div className="action-row" key={e.id} data-testid={`audit-${e.id}`}>
              <div className="action-info">
                <span className="action-type">{e.action}</span>
                <span className="action-target">
                  {e.actor} → {e.target_type}:{e.target_id} ·{" "}
                  {new Date(e.created_at).toLocaleString()}
                </span>
              </div>
              <span className="mono" style={{ color: "var(--text-2)", fontSize: 11 }}>
                {e.entry_hash.slice(0, 10)}…
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
