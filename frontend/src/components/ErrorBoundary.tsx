import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  message: string;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: "" };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // In production this would report to an error tracker (Sentry, etc).
    console.error("Unhandled UI error:", error, info.componentStack);
  }

  handleReset = (): void => {
    this.setState({ hasError: false, message: "" });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="login-wrap" data-testid="error-boundary">
          <div className="login-card">
            <h1>Something went wrong</h1>
            <p>The console hit an unexpected error. Your data is safe.</p>
            <div className="error-banner" role="alert">
              {this.state.message}
            </div>
            <button
              className="btn btn-primary"
              style={{ width: "100%" }}
              data-testid="error-reset"
              onClick={this.handleReset}
            >
              Try again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
