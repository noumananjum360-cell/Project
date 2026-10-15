import { Component, type ErrorInfo, type ReactNode } from "react";
import { LinkButton } from "@/components/ui/primitives";

function StatusLayout({ code, title, text, action }: { code: string; title: string; text: string; action: ReactNode }) {
  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center px-4 text-center">
      <p className="text-sm font-semibold text-brand-600">{code}</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-3 max-w-md text-ink-soft">{text}</p>
      <div className="mt-6">{action}</div>
    </div>
  );
}

export function NotFoundPage() {
  return <StatusLayout code="404" title="Page not found" text="The page you're looking for doesn't exist or was moved." action={<LinkButton to="/">Go home</LinkButton>} />;
}

export function UnauthorizedPage() {
  return (
    <StatusLayout
      code="403"
      title="Not authorized"
      text="You don't have permission to view this page."
      action={<LinkButton to="/dashboard">Back to dashboard</LinkButton>}
    />
  );
}

export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo) {
    // Hook for an error-monitoring integration (e.g. Sentry) — see docs/DEPLOYMENT.md.
  }

  render() {
    if (this.state.error)
      return (
        <div className="flex min-h-[70vh] flex-col items-center justify-center px-4 text-center">
          <p className="text-sm font-semibold text-bad">Error</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">Something went wrong</h1>
          <p className="mt-3 max-w-md text-ink-soft">An unexpected error occurred while displaying this page.</p>
          <button className="mt-6 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white" onClick={() => window.location.assign("/dashboard")}>
            Reload dashboard
          </button>
        </div>
      );
    return this.props.children;
  }
}
