import { useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { isSupportedPage, isValidUrl } from "../shared/messages";
import type { ConnectionStatus, ExtensionConfig, TabState } from "../shared/types";
import { activeTab, call, ResultView } from "../shared/ui";

function Settings({ config, onSaved }: { config: ExtensionConfig; onSaved: (c: ExtensionConfig) => void }) {
  const [backendUrl, setBackend] = useState(config.backendUrl);
  const [dashboardUrl, setDashboard] = useState(config.dashboardUrl);
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    setError(null);
    if (!isValidUrl(backendUrl) || !isValidUrl(dashboardUrl)) return setError("Enter full http(s):// URLs.");
    const u = new URL(backendUrl);
    const isLocal = ["localhost", "127.0.0.1"].includes(u.hostname);
    if (!isLocal && u.protocol !== "https:") return setError("Use HTTPS for non-local backends.");
    if (!isLocal) {
      // Ask for access to this backend origin only (optional host permission).
      const granted = await chrome.permissions.request({ origins: [`${u.origin}/*`] });
      if (!granted) return setError("Permission to contact this backend was not granted.");
    }
    try {
      onSaved(await call<ExtensionConfig>({ type: "SET_CONFIG", backendUrl, dashboardUrl }));
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <details className="card">
      <summary>Connection settings</summary>
      <label htmlFor="backend">Backend URL</label>
      <input id="backend" value={backendUrl} onChange={(e) => setBackend(e.target.value)} />
      <label htmlFor="dashboard">Dashboard URL</label>
      <input id="dashboard" value={dashboardUrl} onChange={(e) => setDashboard(e.target.value)} />
      {error && (
        <p className="bad small" role="alert">
          {error}
        </p>
      )}
      <button className="btn" onClick={save}>
        Save
      </button>
    </details>
  );
}

function Login({ onDone }: { onDone: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="card stack"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
          await call({ type: "LOGIN", email, password });
          onDone();
        } catch (err) {
          setError((err as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      <h2>Sign in to BidGenie</h2>
      <label htmlFor="email">Email</label>
      <input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      <label htmlFor="password">Password</label>
      <input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
      {error && (
        <p className="bad small" role="alert">
          {error}
        </p>
      )}
      <button className="btn primary" disabled={busy} type="submit">
        {busy ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}

function Popup() {
  const [config, setConfig] = useState<ExtensionConfig | null>(null);
  const [status, setStatus] = useState<ConnectionStatus | null>(null);
  const [tab, setTab] = useState<chrome.tabs.Tab | undefined>();
  const [state, setState] = useState<TabState | null>(null);

  const refresh = useCallback(async () => {
    setConfig(await call<ExtensionConfig>({ type: "GET_CONFIG" }));
    setStatus(await call<ConnectionStatus>({ type: "GET_STATUS" }));
    const t = await activeTab();
    setTab(t);
    if (t?.id !== undefined) setState(await call<TabState>({ type: "GET_TAB_STATE", tabId: t.id }));
  }, []);

  useEffect(() => {
    refresh().catch((e) =>
      setStatus({ backendReachable: false, signedIn: false, email: null, aiConfigured: null, aiSimulated: null, error: (e as Error).message }),
    );
    const onMsg = (m: { type?: string; tabId?: number }) => {
      if (m?.type === "TAB_STATE_CHANGED" && tab?.id === m.tabId)
        call<TabState>({ type: "GET_TAB_STATE", tabId: m.tabId! }).then(setState).catch(() => undefined);
    };
    chrome.runtime.onMessage.addListener(onMsg);
    return () => chrome.runtime.onMessage.removeListener(onMsg);
  }, [refresh, tab?.id]);

  const supported = isSupportedPage(tab?.url);
  const run = async (action: "analyze" | "write") => {
    if (tab?.id === undefined) return;
    setState(await call<TabState>({ type: "RUN_ON_TAB", tabId: tab.id, action }));
  };

  return (
    <main className="stack">
      <header className="row between">
        <h1>
          <img src="icons/icon-32.png" alt="" width={20} height={20} /> BidGenie AI
        </h1>
        {status?.signedIn && (
          <button className="btn ghost small" onClick={async () => (await call({ type: "LOGOUT" }), refresh())}>
            Sign out
          </button>
        )}
      </header>

      <div className="status" aria-live="polite">
        {!status ? (
          <span className="muted">Checking connection…</span>
        ) : !status.backendReachable ? (
          <span className="bad">● Backend unreachable — {status.error}</span>
        ) : status.signedIn ? (
          <span className="good">● Connected as {status.email}</span>
        ) : (
          <span className="warn">● Backend reachable — not signed in</span>
        )}
        {status?.backendReachable && status.aiConfigured === false && <p className="warn small">AI is not configured on the server; analysis is unavailable.</p>}
        {status?.aiSimulated && <p className="warn small">Server is in demo mode: AI results are simulated.</p>}
      </div>

      {status?.backendReachable && !status.signedIn && <Login onDone={refresh} />}

      {status?.signedIn && (
        <section className="card stack">
          {supported ? (
            <>
              <p className="small">Supported job page detected. Nothing is read until you click.</p>
              <div className="row">
                <button className="btn primary" onClick={() => run("analyze")}>
                  Analyze with BidGenie
                </button>
                <button className="btn" onClick={() => run("write")}>
                  Write with AI
                </button>
              </div>
            </>
          ) : (
            <p className="muted small">Open a job's page to analyze it, or paste any job into the dashboard.</p>
          )}
          <div className="row">
            <button
              className="btn ghost small"
              onClick={async () => {
                if (tab?.windowId !== undefined) await chrome.sidePanel.open({ windowId: tab.windowId });
              }}
            >
              Open side panel
            </button>
            {config && (
              <a className="link small" href={config.dashboardUrl} target="_blank" rel="noreferrer">
                Open dashboard ↗
              </a>
            )}
          </div>
        </section>
      )}

      {state && state.status !== "idle" && config && <ResultView state={state} dashboardUrl={config.dashboardUrl} onRetry={() => run(state.proposal ? "write" : "analyze")} />}
      {config && <Settings config={config} onSaved={(c) => (setConfig(c), refresh())} />}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<Popup />);
