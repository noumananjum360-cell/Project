/**
 * Background service worker: the only context that talks to the backend.
 * All incoming messages are validated (shape + sender) before being acted on.
 */
import { BackendClient, BackendError, type TokenStore } from "../services/api";
import { isSupportedPage, parseMessage, type Action, type Message } from "../shared/messages";
import { DEFAULT_CONFIG, emptyTabState, type ConnectionStatus, type ExtensionConfig, type ExtractedJob, type TabState } from "../shared/types";

const tokenStore: TokenStore = {
  async get() {
    const local = await chrome.storage.local.get(["refreshToken", "email"]);
    const session = await chrome.storage.session.get(["accessToken"]);
    return {
      access: (session.accessToken as string) ?? null,
      refresh: (local.refreshToken as string) ?? null,
      email: (local.email as string) ?? null,
    };
  },
  async set(v) {
    await chrome.storage.session.set({ accessToken: v.access });
    await chrome.storage.local.set({ refreshToken: v.refresh, email: v.email });
  },
};

async function getConfig(): Promise<ExtensionConfig> {
  const c = await chrome.storage.local.get(["backendUrl", "dashboardUrl"]);
  return {
    backendUrl: (c.backendUrl as string) || DEFAULT_CONFIG.backendUrl,
    dashboardUrl: (c.dashboardUrl as string) || DEFAULT_CONFIG.dashboardUrl,
  };
}

async function client(): Promise<BackendClient> {
  return new BackendClient((await getConfig()).backendUrl, tokenStore);
}

const stateKey = (tabId: number) => `tab:${tabId}`;

async function getTabState(tabId: number): Promise<TabState> {
  const got = await chrome.storage.session.get(stateKey(tabId));
  return (got[stateKey(tabId)] as TabState) ?? emptyTabState();
}

async function setTabState(tabId: number, patch: Partial<TabState>): Promise<TabState> {
  const next = { ...(await getTabState(tabId)), ...patch, updatedAt: Date.now() };
  await chrome.storage.session.set({ [stateKey(tabId)]: next });
  // Notify the content script (injected panel) and any open popup/side panel.
  chrome.tabs.sendMessage(tabId, { type: "TAB_STATE_CHANGED", tabId }).catch(() => undefined);
  chrome.runtime.sendMessage({ type: "TAB_STATE_CHANGED", tabId }).catch(() => undefined);
  return next;
}

function friendly(e: unknown): string {
  if (e instanceof BackendError) return e.message;
  return e instanceof Error ? e.message : "Something went wrong.";
}

async function status(): Promise<ConnectionStatus> {
  const api = await client();
  const out: ConnectionStatus = { backendReachable: false, signedIn: false, email: null, aiConfigured: null, aiSimulated: null, error: null };
  try {
    const h = await api.health();
    out.backendReachable = true;
    out.aiConfigured = h.ai_configured;
    out.aiSimulated = h.ai_simulated;
  } catch (e) {
    out.error = friendly(e);
    return out;
  }
  try {
    out.email = (await api.me()).email;
    out.signedIn = true;
  } catch (e) {
    if (!(e instanceof BackendError && e.status === 401)) out.error = friendly(e);
  }
  return out;
}

async function runJob(tabId: number, action: Action, job: ExtractedJob): Promise<TabState> {
  const api = await client();
  const prev = await getTabState(tabId);
  const sameJob = prev.job?.url && prev.job.url === job.url && prev.jobId;
  try {
    await setTabState(tabId, { status: "saving", job, error: null, ...(sameJob ? {} : { analysis: null, proposal: null, jobId: null }) });
    const jobId = sameJob ? prev.jobId! : await api.saveJob(job);
    await setTabState(tabId, { jobId });
    if (action === "analyze" || !prev.analysis || !sameJob) {
      await setTabState(tabId, { status: "analyzing" });
      const analysis = await api.analyze(jobId);
      await setTabState(tabId, { analysis });
    }
    if (action === "write") {
      await setTabState(tabId, { status: "writing" });
      const proposal = await api.writeProposal(jobId);
      await setTabState(tabId, { proposal });
    }
    return await setTabState(tabId, { status: "done" });
  } catch (e) {
    return await setTabState(tabId, { status: "error", error: friendly(e) });
  }
}

/** Ask the content script on the tab to extract the visible job (user-initiated from popup/side panel). */
async function runOnTab(tabId: number, action: Action): Promise<TabState> {
  const tab = await chrome.tabs.get(tabId);
  if (!isSupportedPage(tab.url)) {
    return setTabState(tabId, { status: "error", error: "This page isn't a supported job page. Paste the job into the BidGenie dashboard instead." });
  }
  await setTabState(tabId, { status: "extracting", error: null });
  try {
    await chrome.tabs.sendMessage(tabId, { type: "EXTRACT_JOB", action });
    return getTabState(tabId);
  } catch {
    return setTabState(tabId, { status: "error", error: "Could not read this page. Reload the tab and try again." });
  }
}

async function handle(msg: Message, sender: chrome.runtime.MessageSender): Promise<unknown> {
  // Extension pages (popup, side panel) are identified by their own origin; content
  // scripts report the URL of the page they run in.
  const fromExtensionPage = !!sender.url?.startsWith(`chrome-extension://${chrome.runtime.id}/`);
  const fromContent = !fromExtensionPage && !!sender.tab && isSupportedPage(sender.url ?? sender.tab.url);

  // Content scripts may only report an extracted job (and only from supported pages).
  if (msg.type === "JOB_EXTRACTED") {
    if (!fromContent || sender.tab?.id === undefined) throw new Error("Rejected message from unsupported sender.");
    return runJob(sender.tab.id, msg.action, msg.job);
  }
  if (!fromExtensionPage) throw new Error("Rejected message from unsupported sender.");

  switch (msg.type) {
    case "GET_STATUS":
      return status();
    case "GET_CONFIG":
      return getConfig();
    case "SET_CONFIG":
      await chrome.storage.local.set({ backendUrl: msg.backendUrl.replace(/\/+$/, ""), dashboardUrl: msg.dashboardUrl.replace(/\/+$/, "") });
      return getConfig();
    case "LOGIN":
      return { email: await (await client()).login(msg.email, msg.password) };
    case "LOGOUT":
      await (await client()).logout();
      return { ok: true };
    case "GET_TAB_STATE":
      return getTabState(msg.tabId);
    case "RUN_ON_TAB":
      return runOnTab(msg.tabId, msg.action);
    default:
      throw new Error("Unsupported message.");
  }
}

chrome.runtime.onMessage.addListener((raw, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id) return false;
  const msg = parseMessage(raw);
  if (!msg) {
    sendResponse({ ok: false, error: "Invalid message." });
    return false;
  }
  handle(msg, sender)
    .then((data) => sendResponse({ ok: true, data }))
    .catch((e) => sendResponse({ ok: false, error: friendly(e) }));
  return true; // async response
});

chrome.tabs.onRemoved.addListener((tabId) => {
  chrome.storage.session.remove(stateKey(tabId)).catch(() => undefined);
});

// Restrict storage.session to trusted extension contexts (not content scripts).
chrome.storage.session.setAccessLevel?.({ accessLevel: "TRUSTED_CONTEXTS" }).catch(() => undefined);
