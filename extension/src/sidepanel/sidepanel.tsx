import { useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { isSupportedPage } from "../shared/messages";
import type { ExtensionConfig, TabState } from "../shared/types";
import { activeTab, call, ResultView } from "../shared/ui";

function SidePanel() {
  const [config, setConfig] = useState<ExtensionConfig | null>(null);
  const [tab, setTab] = useState<chrome.tabs.Tab | undefined>();
  const [state, setState] = useState<TabState | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setConfig(await call<ExtensionConfig>({ type: "GET_CONFIG" }));
      const t = await activeTab();
      setTab(t);
      setState(t?.id !== undefined ? await call<TabState>({ type: "GET_TAB_STATE", tabId: t.id }) : null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
    const onMsg = (m: { type?: string; tabId?: number }) => {
      if (m?.type === "TAB_STATE_CHANGED") load();
    };
    const onActivated = () => load();
    chrome.runtime.onMessage.addListener(onMsg);
    chrome.tabs.onActivated.addListener(onActivated);
    chrome.tabs.onUpdated.addListener(onActivated);
    return () => {
      chrome.runtime.onMessage.removeListener(onMsg);
      chrome.tabs.onActivated.removeListener(onActivated);
      chrome.tabs.onUpdated.removeListener(onActivated);
    };
  }, [load]);

  const run = async (action: "analyze" | "write") => {
    if (tab?.id === undefined) return;
    try {
      setState(await call<TabState>({ type: "RUN_ON_TAB", tabId: tab.id, action }));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <main className="stack wide">
      <header className="row between">
        <h1>
          <img src="icons/icon-32.png" alt="" width={20} height={20} /> BidGenie AI
        </h1>
        {config && (
          <a className="link small" href={config.dashboardUrl} target="_blank" rel="noreferrer">
            Dashboard ↗
          </a>
        )}
      </header>
      {error && (
        <p className="bad small" role="alert">
          {error}
        </p>
      )}
      {isSupportedPage(tab?.url) ? (
        <div className="row">
          <button className="btn primary" onClick={() => run("analyze")}>
            Analyze with BidGenie
          </button>
          <button className="btn" onClick={() => run("write")}>
            Write with AI
          </button>
        </div>
      ) : (
        <p className="muted small">This tab is not a supported job page. You can paste any job into the BidGenie dashboard.</p>
      )}
      {state && state.status !== "idle" && config ? (
        <ResultView state={state} dashboardUrl={config.dashboardUrl} onRetry={() => run(state.proposal ? "write" : "analyze")} />
      ) : (
        <p className="muted small">Results for the current tab will appear here.</p>
      )}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<SidePanel />);
