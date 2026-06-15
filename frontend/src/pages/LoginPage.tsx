import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { ApiError } from "../api/client";
import { ErrorBanner, Spinner } from "../components/ui";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [tenant, setTenant] = useState("default");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit() {
    setError(null);
    setLoading(true);
    try {
      await login(username, password, tenant);
      navigate("/");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Unexpected error. Try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1>SentinelAI</h1>
        <p>Agentic threat detection &amp; response on Splunk</p>
        {error && <ErrorBanner message={error} />}
        <div className="field">
          <label htmlFor="tenant">Tenant</label>
          <input
            id="tenant"
            data-testid="tenant-input"
            value={tenant}
            onChange={(e) => setTenant(e.target.value)}
            autoComplete="organization"
          />
        </div>
        <div className="field">
          <label htmlFor="username">Operator</label>
          <input
            id="username"
            data-testid="username-input"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
        </div>
        <div className="field">
          <label htmlFor="password">Passphrase</label>
          <input
            id="password"
            type="password"
            data-testid="password-input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleSubmit();
            }}
          />
        </div>
        <button
          className="btn btn-primary"
          style={{ width: "100%" }}
          data-testid="login-button"
          onClick={() => void handleSubmit()}
          disabled={loading || !username || !password || !tenant}
        >
          {loading ? <Spinner label="Authenticating" /> : "Sign in"}
        </button>
      </div>
    </div>
  );
}
