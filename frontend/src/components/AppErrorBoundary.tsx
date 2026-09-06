import { Component, type ErrorInfo, type ReactNode } from "react";

type AppErrorBoundaryProps = {
  children: ReactNode;
};

type AppErrorBoundaryState = {
  error: Error | null;
};

export class AppErrorBoundary extends Component<
  AppErrorBoundaryProps,
  AppErrorBoundaryState
> {
  state: AppErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): AppErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Serenita render failed", error, info);
  }

  render() {
    const { error } = this.state;
    if (!error) {
      return this.props.children;
    }

    return (
      <main className="app-crash-page">
        <section aria-live="assertive" className="app-crash-panel" role="alert">
          <span className="app-crash-brand">Serenita</span>
          <h1>页面暂时无法显示</h1>
          <p>页面数据没有被删除。请重新载入；如果问题仍然出现，可以保留此页并查看错误详情。</p>
          <button className="control control--primary command-button control-primary" onClick={() => window.location.reload()} type="button">
            重新载入
          </button>
          {import.meta.env.DEV ? (
            <details className="app-crash-details">
              <summary>错误详情</summary>
              <pre>{error.message}</pre>
            </details>
          ) : null}
        </section>
      </main>
    );
  }
}
