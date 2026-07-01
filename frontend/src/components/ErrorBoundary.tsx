import { Component, type ErrorInfo, type ReactNode } from "react";

// A render throw in the SVG-heavy plan/space views (e.g. a malformed layout) would otherwise
// white-screen the whole app. This catches it and shows a recoverable, on-brand fallback.
type Props = { children: ReactNode };
type State = { error: Error | null };

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Studio render error:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="error-boundary" role="alert">
        <div className="glyph" aria-hidden="true">⚠</div>
        <p className="lead">Something in the plan view broke.</p>
        <p className="detail">{this.state.error.message}</p>
        <button className="ds-btn ds-btn--primary" onClick={() => this.setState({ error: null })}>
          Try again
        </button>
      </div>
    );
  }
}
