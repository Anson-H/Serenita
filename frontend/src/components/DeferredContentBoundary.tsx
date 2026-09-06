import { Component, type ErrorInfo, type ReactNode } from "react";

type DeferredContentBoundaryProps = {
  children: ReactNode;
  surface?: "dialog" | "workspace";
};

type DeferredContentBoundaryState = {
  error: Error | null;
};

export class DeferredContentBoundary extends Component<
  DeferredContentBoundaryProps,
  DeferredContentBoundaryState
> {
  state: DeferredContentBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): DeferredContentBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Serenita deferred content failed", error, info);
  }

  render() {
    if (!this.state.error) return this.props.children;

    const content = (
      <section
        aria-live="assertive"
        className="deferred-content-state"
        role="alert"
      >
        <strong>该工作区暂时无法载入</strong>
        <p>页面数据没有被删除，请重新载入后再试。</p>
        <button
          className="control control--primary command-button control-primary"
          onClick={() => window.location.reload()}
          type="button"
        >
          重新载入
        </button>
      </section>
    );

    if (this.props.surface === "dialog") {
      return (
        <div className="content-dialog-backdrop deferred-dialog-state dialog-viewport-backdrop">
          <div className="content-dialog dialog-viewport-surface dialog-title-ellipsis">{content}</div>
        </div>
      );
    }
    return content;
  }
}

export function DeferredLoadingState({
  label,
  surface = "workspace"
}: {
  label: string;
  surface?: "dialog" | "workspace";
}) {
  const content = (
    <section
      aria-busy="true"
      aria-live="polite"
      className="deferred-content-state"
      role="status"
    >
      <span>{label}</span>
    </section>
  );

  if (surface === "dialog") {
    return (
      <div className="content-dialog-backdrop deferred-dialog-state dialog-viewport-backdrop">
        <div className="content-dialog dialog-viewport-surface dialog-title-ellipsis">{content}</div>
      </div>
    );
  }
  return content;
}
