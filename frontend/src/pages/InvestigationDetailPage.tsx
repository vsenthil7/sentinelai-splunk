import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useAuth } from "../hooks/useAuth";
import type { CaseNote, Investigation, SLA } from "../types";
import { ErrorBanner, SeverityBadge, Spinner } from "../components/ui";

const STATUS_OPTIONS = [
  "triaged",
  "investigating",
  "contained",
  "resolved",
  "false_positive",
];

export function InvestigationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const [inv, setInv] = useState<Investigation | null>(null);
  const [sla, setSla] = useState<SLA | null>(null);
  const [notes, setNotes] = useState<CaseNote[]>([]);
  const [noteText, setNoteText] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const [i, s, n] = await Promise.all([
        api.getInvestigation(id),
        api.getSla(id),
        api.listNotes(id),
      ]);
      setInv(i);
      setSla(s);
      setNotes(n);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load investigation");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function act(label: string, fn: () => Promise<Investigation>) {
    setBusy(label);
    setError(null);
    try {
      setInv(await fn());
      if (id) setSla(await api.getSla(id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : `${label} failed`);
    } finally {
      setBusy(null);
    }
  }

  async function submitNote() {
    if (!id || !noteText.trim()) return;
    setBusy("note");
    try {
      await api.addNote(id, noteText.trim());
      setNoteText("");
      setNotes(await api.listNotes(id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Note failed");
    } finally {
      setBusy(null);
    }
  }

  if (loading) return <Spinner label="Loading investigation" />;
  if (error && !inv) return <ErrorBanner message={error} />;
  if (!inv) return null;

  const verdict = inv.verdict;
  const enr = inv.detection.enrichment as Record<string, unknown>;

  return (
    <div>
      <Link to="/" data-testid="back-link" style={{ fontSize: 13 }}>
        ← Back to console
      </Link>
      <div className="card-head" style={{ marginTop: 16 }}>
        <h1 className="page-title" data-testid="inv-title">
          {inv.detection.title}
        </h1>
        <SeverityBadge severity={inv.detection.severity} />
      </div>
      <p className="page-sub">
        {inv.id} · <code>{inv.detection.entity}</code> · {inv.detection.event_count} events ·
        status <strong>{inv.detection.status}</strong>
        {inv.assignee ? ` · assigned to ${inv.assignee}` : " · unassigned"}
      </p>

      {error && <ErrorBanner message={error} />}

      {sla && (
        <div className="stat-row" data-testid="sla">
          <div className="stat">
            <div className="stat-value" style={{ color: sla.ack_breached ? "var(--bad)" : "var(--ok)" }}>
              {sla.ack_elapsed_min}m
            </div>
            <div className="stat-label">Time to ack (target {sla.ack_target_min}m)</div>
          </div>
          <div className="stat">
            <div className="stat-value" style={{ color: sla.contain_breached ? "var(--bad)" : "var(--ok)" }}>
              {sla.contain_elapsed_min}m
            </div>
            <div className="stat-label">Time to contain (target {sla.contain_target_min}m)</div>
          </div>
        </div>
      )}

      {verdict && (
        <div className="card" data-testid="verdict-card">
          <div className="card-head">
            <span className="card-title">Triage verdict</span>
            <span className={`badge badge-${verdict.is_true_positive ? "high" : "info"}`}>
              {verdict.is_true_positive ? "True positive" : "False positive"}
            </span>
          </div>
          <div className="card-meta">confidence {(verdict.confidence * 100).toFixed(0)}%</div>
          <p style={{ marginTop: 10 }}>{verdict.rationale}</p>
        </div>
      )}

      <div className="card" data-testid="enrichment-card" style={{ marginTop: 16 }}>
        <div className="card-title" style={{ marginBottom: 8 }}>Enrichment</div>
        <div className="card-meta">
          asset criticality: <strong>{String(enr.asset_criticality ?? "n/a")}</strong> ·
          threat intel: <strong>{String((enr.threat_intel as Record<string, unknown>)?.verdict ?? "n/a")}</strong> ·
          risk boost: <strong>{String(enr.risk_boost ?? "1.0")}</strong>
        </div>
        <div style={{ marginTop: 8 }}>
          {inv.detection.mitre_tactics.map((t) => (
            <span className="tag" key={t}>{t}</span>
          ))}
        </div>
      </div>

      <div className="summary-box" data-testid="summary">{inv.summary}</div>

      {can("case:write") && (
        <div className="toolbar" data-testid="status-controls">
          {STATUS_OPTIONS.map((s) => (
            <button
              key={s}
              className="btn btn-sm"
              data-testid={`status-${s}`}
              disabled={busy !== null || inv.detection.status === s}
              onClick={() => void act(`status-${s}`, () => api.transitionStatus(inv.id, s))}
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <h2 style={{ fontSize: 15, margin: "20px 0 8px", fontFamily: "var(--font-display)" }}>Timeline</h2>
      <ul className="timeline" data-testid="timeline">
        {inv.timeline.map((t, i) => (
          <li key={i}>{t}</li>
        ))}
      </ul>

      <h2 style={{ fontSize: 15, margin: "20px 0 8px", fontFamily: "var(--font-display)" }}>Response actions</h2>
      {inv.actions.length === 0 ? (
        <p style={{ color: "var(--text-1)", fontSize: 13 }} data-testid="no-actions">
          No response actions required.
        </p>
      ) : (
        <div data-testid="actions">
          {inv.actions.map((a, i) => (
            <div className="action-row" key={i} data-testid={`action-${i}`}>
              <div className="action-info">
                <span className="action-type">{a.action_type}</span>
                <span className="action-target">
                  target: {a.target}
                  {a.executed && a.execution_detail ? ` — ${a.execution_detail}` : ""}
                </span>
              </div>
              {a.executed ? (
                <span className="pill-approved" data-testid={`executed-${i}`}>
                  ✓ executed ({a.execution_status})
                </span>
              ) : a.requires_approval ? (
                can("action:approve") ? (
                  <button
                    className="btn btn-sm btn-primary"
                    data-testid={`approve-${i}`}
                    disabled={busy !== null}
                    onClick={() => void act(`approve-${i}`, () => api.approveAction(inv.id, i))}
                  >
                    Approve
                  </button>
                ) : (
                  <span className="pill-approved">awaiting approval</span>
                )
              ) : can("action:approve") ? (
                <button
                  className="btn btn-sm btn-primary"
                  data-testid={`execute-${i}`}
                  disabled={busy !== null}
                  onClick={() => void act(`execute-${i}`, () => api.executeAction(inv.id, i))}
                >
                  Execute
                </button>
              ) : (
                <span className="pill-approved">approved</span>
              )}
            </div>
          ))}
        </div>
      )}

      <h2 style={{ fontSize: 15, margin: "20px 0 8px", fontFamily: "var(--font-display)" }}>Case notes</h2>
      <div data-testid="notes">
        {notes.map((n) => (
          <div className="action-row" key={n.id}>
            <div className="action-info">
              <span className="action-type">{n.author}</span>
              <span className="action-target">{n.body}</span>
            </div>
          </div>
        ))}
        {notes.length === 0 && (
          <p style={{ color: "var(--text-1)", fontSize: 13 }}>No notes yet.</p>
        )}
      </div>
      {can("case:write") && (
        <div className="toolbar" style={{ marginTop: 12 }}>
          <input
            className="field"
            style={{ flex: 1, background: "var(--bg-0)", border: "1px solid var(--border)", borderRadius: 6, padding: "8px 12px", color: "var(--text-0)" }}
            placeholder="Add a note…"
            data-testid="note-input"
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
          />
          <button
            className="btn btn-primary"
            data-testid="add-note"
            disabled={busy !== null || !noteText.trim()}
            onClick={() => void submitNote()}
          >
            Add note
          </button>
        </div>
      )}
    </div>
  );
}
