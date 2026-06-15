import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Role, User } from "../types";
import { ErrorBanner, Spinner } from "../components/ui";

const ROLES: Role[] = ["viewer", "analyst", "responder", "admin"];

export function AdminPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [newUser, setNewUser] = useState("");
  const [newPass, setNewPass] = useState("");
  const [newRole, setNewRole] = useState<Role>("analyst");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setUsers(await api.listUsers());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load users");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function create() {
    setBusy(true);
    setError(null);
    try {
      await api.createUser(newUser, newPass, newRole);
      setNewUser("");
      setNewPass("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Create failed");
    } finally {
      setBusy(false);
    }
  }

  async function changeRole(id: string, role: string) {
    setBusy(true);
    setError(null);
    try {
      await api.updateRole(id, role);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Role update failed");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setBusy(true);
    setError(null);
    try {
      await api.deleteUser(id);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Spinner label="Loading users" />;

  return (
    <div>
      <h1 className="page-title">Administration</h1>
      <p className="page-sub">Manage operators and roles for your tenant.</p>
      {error && <ErrorBanner message={error} />}

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-title" style={{ marginBottom: 12 }}>Add operator</div>
        <div className="toolbar">
          <input
            className="field"
            style={{ background: "var(--bg-0)", border: "1px solid var(--border)", borderRadius: 6, padding: "8px 12px", color: "var(--text-0)" }}
            placeholder="username"
            data-testid="new-username"
            value={newUser}
            onChange={(e) => setNewUser(e.target.value)}
          />
          <input
            className="field"
            type="password"
            style={{ background: "var(--bg-0)", border: "1px solid var(--border)", borderRadius: 6, padding: "8px 12px", color: "var(--text-0)" }}
            placeholder="password (min 8)"
            data-testid="new-password"
            value={newPass}
            onChange={(e) => setNewPass(e.target.value)}
          />
          <select
            data-testid="new-role"
            value={newRole}
            onChange={(e) => setNewRole(e.target.value as Role)}
            style={{ background: "var(--bg-0)", border: "1px solid var(--border)", borderRadius: 6, padding: "8px 12px", color: "var(--text-0)" }}
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
          <button
            className="btn btn-primary"
            data-testid="create-user"
            disabled={busy || !newUser || newPass.length < 8}
            onClick={() => void create()}
          >
            Create
          </button>
        </div>
      </div>

      <div data-testid="user-list">
        {users.map((u) => (
          <div className="action-row" key={u.id} data-testid={`user-${u.id}`}>
            <div className="action-info">
              <span className="action-type">{u.username}</span>
              <span className="action-target">
                {u.external_id ? `SSO: ${u.external_id}` : "local account"}
              </span>
            </div>
            <div className="toolbar" style={{ margin: 0 }}>
              <select
                value={u.role}
                data-testid={`role-${u.id}`}
                disabled={busy}
                onChange={(e) => void changeRole(u.id, e.target.value)}
                style={{ background: "var(--bg-0)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 10px", color: "var(--text-0)" }}
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
              <button
                className="btn btn-sm"
                data-testid={`delete-${u.id}`}
                disabled={busy}
                onClick={() => void remove(u.id)}
              >
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
