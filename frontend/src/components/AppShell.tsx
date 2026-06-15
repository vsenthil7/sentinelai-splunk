import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { api } from "../api/client";
import type { HealthResponse } from "../types";

export function AppShell({ children }: { children: ReactNode }) {
  const { username, role, tenant, logout, can } = useAuth();
  const location = useLocation();
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    let active = true;
    api
      .health()
      .then((h) => {
        if (active) setHealth(h);
      })
      .catch(() => {
        if (active) setHealth({ status: "down", splunk: false, backend: "unknown" });
      });
    return () => {
      active = false;
    };
  }, []);

  const splunkOk = health?.splunk ?? false;

  const navItems: { to: string; label: string; show: boolean }[] = [
    { to: "/", label: "Console", show: true },
    { to: "/incidents", label: "Incidents", show: true },
    { to: "/rules", label: "Rules", show: true },
    { to: "/audit", label: "Audit", show: can("audit:read") },
    { to: "/admin", label: "Admin", show: can("admin:*") },
  ];

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" />
          SentinelAI
          <nav className="nav" data-testid="nav">
            {navItems
              .filter((n) => n.show)
              .map((n) => (
                <Link
                  key={n.to}
                  to={n.to}
                  className={`nav-link ${location.pathname === n.to ? "active" : ""}`}
                  data-testid={`nav-${n.label.toLowerCase()}`}
                >
                  {n.label}
                </Link>
              ))}
          </nav>
        </div>
        <div className="topbar-right">
          <span className="health-pill" data-testid="health-pill">
            <span className={`health-dot ${splunkOk ? "ok" : "bad"}`} />
            splunk:{health?.backend ?? "…"}
          </span>
          <span className="user-name">
            {username} · {role} @ {tenant}
          </span>
          <button className="btn btn-sm" data-testid="logout" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>
      <main className="content">{children}</main>
    </div>
  );
}
