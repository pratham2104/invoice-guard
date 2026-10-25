import { Component, type ReactNode } from "react";

/** One bad field from the API must never blank the console: the failing panel shows a quiet note instead. */
export class Boundary extends Component<{ children: ReactNode; label: string; resetKey?: unknown }, { err: Error | null }> {
  state = { err: null as Error | null };
  static getDerivedStateFromError(err: Error) { return { err }; }
  componentDidCatch(err: Error) { console.error(`[${this.props.label}]`, err); }
  componentDidUpdate(prev: { resetKey?: unknown }) {
    if (prev.resetKey !== this.props.resetKey && this.state.err) this.setState({ err: null });
  }
  render() {
    if (this.state.err) {
      return (
        <div style={{ padding: 16, margin: 16, border: "1px solid var(--line)", borderRadius: 8, fontSize: 13, color: "var(--ink-2)", background: "var(--canvas)" }}>
          {this.props.label} couldn't be shown for this data. The rest of the console still works.
          <div className="mono t12 ink3" style={{ marginTop: 6 }}>{this.state.err.message}</div>
        </div>
      );
    }
    return this.props.children;
  }
}
