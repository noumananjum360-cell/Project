/**
 * Content script for supported job pages.
 *
 * It does nothing until the user clicks one of the injected buttons (or uses
 * the popup). It never clicks page buttons, fills application forms, submits
 * proposals or spends Connects. It reads only the job details visible on the
 * current page.
 */
import { extractJob } from "../shared/extract";
import { parseMessage, type Action } from "../shared/messages";
import type { TabState } from "../shared/types";

const HOST_ID = "bidgenie-ai-root";

function send<T>(msg: unknown): Promise<{ ok: boolean; data?: T; error?: string }> {
  return chrome.runtime.sendMessage(msg);
}

function startExtraction(action: Action) {
  const job = extractJob(document, location.href);
  if (!job) {
    renderPanel({
      status: "error",
      error: "Couldn't find the job title and description on this page. Open the job's own page, or paste it into the BidGenie dashboard.",
    });
    return;
  }
  // Progress is shown as one busy state; the background returns the final result.
  renderPanel({ status: action === "write" ? "writing" : "analyzing", job });
  send<TabState>({ type: "JOB_EXTRACTED", action, job }).then((r) => {
    if (r?.ok && r.data) renderPanel(r.data);
    else renderPanel({ status: "error", error: r?.error ?? "The extension could not process this job." });
  });
}

/* ------------------------------ Injected UI ------------------------------ */

const STYLES = `
:host { all: initial; }
.wrap { position: fixed; right: 16px; bottom: 16px; z-index: 2147483646; font: 14px/1.45 system-ui, -apple-system, Segoe UI, Roboto, sans-serif; color: #0f172a; }
.bar { display: flex; gap: 6px; justify-content: flex-end; }
button { font: inherit; cursor: pointer; border-radius: 8px; border: 1px solid #c7d2fe; background: #fff; color: #4338ca; padding: 7px 12px; font-weight: 600; box-shadow: 0 2px 8px rgba(15,23,42,.12); }
button.primary { background: #4f46e5; color: #fff; border-color: #4f46e5; }
button:focus-visible { outline: 2px solid #6366f1; outline-offset: 2px; }
.panel { margin-top: 8px; width: min(360px, calc(100vw - 32px)); max-height: 70vh; overflow: auto; background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; box-shadow: 0 12px 32px rgba(15,23,42,.18); padding: 14px; }
.head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.title { font-weight: 600; font-size: 14px; margin: 0; }
.score { font-size: 32px; font-weight: 700; }
.good { color: #059669; } .warn { color: #b45309; } .bad { color: #dc2626; }
.chips { display: flex; flex-wrap: wrap; gap: 4px; margin: 4px 0 8px; }
.chip { font-size: 12px; padding: 2px 8px; border-radius: 999px; background: #f1f5f9; }
.chip.g { background: #ecfdf5; color: #059669; } .chip.r { background: #fef2f2; color: #dc2626; }
.label { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: #64748b; margin-top: 10px; font-weight: 600; }
.muted { color: #64748b; font-size: 12px; }
textarea { width: 100%; box-sizing: border-box; min-height: 160px; font: 13px/1.5 inherit; border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px; }
.sim { display: inline-block; font-size: 11px; background: #fffbeb; color: #b45309; padding: 1px 6px; border-radius: 999px; margin-left: 6px; }
.close { box-shadow: none; border: 0; padding: 2px 6px; color: #64748b; }
`;

let shadow: ShadowRoot | null = null;

function ensureRoot(): ShadowRoot {
  if (shadow) return shadow;
  const host = document.createElement("div");
  host.id = HOST_ID;
  document.documentElement.appendChild(host);
  shadow = host.attachShadow({ mode: "closed" });
  const style = document.createElement("style");
  style.textContent = STYLES;
  shadow.appendChild(style);
  const wrap = document.createElement("div");
  wrap.className = "wrap";
  wrap.innerHTML = `<div class="bar" role="toolbar" aria-label="BidGenie AI">
      <button class="primary" data-act="analyze">Analyze with BidGenie</button>
      <button data-act="write">Write with AI</button>
    </div><div class="slot"></div>`;
  wrap.querySelectorAll<HTMLButtonElement>("button[data-act]").forEach((b) =>
    b.addEventListener("click", () => startExtraction(b.dataset.act as Action)),
  );
  shadow.appendChild(wrap);
  return shadow;
}

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
const tone = (n: number) => (n >= 75 ? "good" : n >= 50 ? "warn" : "bad");

function renderPanel(state: Partial<TabState>) {
  const root = ensureRoot();
  const slot = root.querySelector(".slot")!;
  const busy: Record<string, string> = {
    extracting: "Reading the job details on this page…",
    saving: "Saving the job to BidGenie…",
    analyzing: "Scoring this job against your profile…",
    writing: "Writing your proposal from your verified experience…",
  };
  let body = "";
  if (state.status && busy[state.status]) body = `<p class="muted" role="status">${busy[state.status]}</p>`;
  if (state.status === "error") body = `<p class="bad" role="alert">${esc(state.error ?? "Something went wrong.")}</p><button data-act="retry">Retry</button>`;
  const a = state.analysis;
  if (a) {
    body += `<div class="label">Fit Score</div>
      <div><span class="score ${tone(a.fit_score)}">${a.fit_score}</span> <span class="muted">/100 · ${esc(a.recommendation)}</span>${a.is_simulated ? '<span class="sim">Simulated AI</span>' : ""}</div>
      <div class="label">Matched skills</div><div class="chips">${a.matched_skills.map((s) => `<span class="chip g">${esc(s)}</span>`).join("") || '<span class="muted">None</span>'}</div>
      <div class="label">Missing skills</div><div class="chips">${a.missing_skills.map((s) => `<span class="chip r">${esc(s)}</span>`).join("") || '<span class="muted">None</span>'}</div>
      <div class="label">Warning signs</div>${a.red_flags.length ? a.red_flags.map((f) => `<p class="${f.severity === "high" ? "bad" : "warn"}">${esc(f.flag)}</p>`).join("") : '<p class="muted">None detected</p>'}
      <div class="label">Relevant portfolio</div>${a.portfolio.length ? a.portfolio.map((p) => `<p>${esc(p.title)} <span class="muted">(${Math.round(p.similarity * 100)}%)</span></p>`).join("") : '<p class="muted">No related projects</p>'}`;
  }
  const p = state.proposal;
  if (p) {
    body += `<div class="label">Proposal draft${p.is_simulated ? '<span class="sim">Simulated AI</span>' : ""}</div>
      ${p.warnings.map((w) => `<p class="warn">${esc(w)}</p>`).join("")}
      <textarea aria-label="Proposal draft (editable)">${esc(p.content)}</textarea>
      <p class="muted">Review and edit before use. BidGenie never submits proposals for you.</p>
      <button data-act="copy">Copy proposal</button>`;
  }
  slot.innerHTML = `<div class="panel" role="dialog" aria-label="BidGenie results">
      <div class="head"><p class="title">${esc(state.job?.title ?? "BidGenie AI")}</p><button class="close" data-act="close" aria-label="Close">✕</button></div>
      ${body}</div>`;
  slot.querySelector('[data-act="close"]')?.addEventListener("click", () => {
    slot.innerHTML = "";
  });
  slot.querySelector('[data-act="retry"]')?.addEventListener("click", () => startExtraction(state.proposal ? "write" : "analyze"));
  slot.querySelector('[data-act="copy"]')?.addEventListener("click", async (ev) => {
    const text = (slot.querySelector("textarea") as HTMLTextAreaElement).value;
    await navigator.clipboard.writeText(text);
    (ev.target as HTMLButtonElement).textContent = "Copied";
  });
}

chrome.runtime.onMessage.addListener((raw, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id) return false;
  const msg = parseMessage(raw);
  if (!msg) return false;
  if (msg.type === "EXTRACT_JOB") {
    startExtraction(msg.action);
    sendResponse({ ok: true });
  } else if (msg.type === "PING_PAGE") {
    sendResponse({ ok: true, data: { hasJob: !!extractJob(document, location.href) } });
  }
  return false;
});

ensureRoot();
