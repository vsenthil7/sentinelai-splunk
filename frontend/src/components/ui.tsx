import type { Severity } from "../types";

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={`badge badge-${severity}`} data-testid="severity-badge">
      {severity}
    </span>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span data-testid="spinner">
      <span className="spinner" aria-hidden="true" />
      {label}
    </span>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="error-banner" role="alert" data-testid="error-banner">
      {message}
    </div>
  );
}

export function Empty({ message }: { message: string }) {
  return (
    <div className="empty" data-testid="empty-state">
      {message}
    </div>
  );
}
