import { useState } from "react";
import type { Message } from "./messages";
import type { TabState } from "./types";

export async function call<T>(msg: Message): Promise<T> {
  const r = (await chrome.runtime.sendMessage(msg)) as { ok: boolean; data?: T; error?: string } | undefined;
  if (!r) throw new Error("No response from the extension background worker.");
  if (!r.ok) throw new Error(r.error ?? "Request failed.");
  return r.data as T;
}

export async function activeTab(): Promise<chrome.tabs.Tab | undefined> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

const tone = (n: number) => (n >= 75 ? "good" : n >= 50 ? "warn" : "bad");
const BUSY: Partial<Record<TabState["status"], string>> = {
  extracting: "Reading the visible job details…",
  saving: "Saving the job to BidGenie…",
  analyzing: "Scoring this job against your profile…",
  writing: "Writing a proposal from your verified experience…",
};

export function ResultView({ state, dashboardUrl, onRetry }: { state: TabState; dashboardUrl: string; onRetry?: () => void }) {
  const [copied, setCopied] = useState(false);
  const [text, setText] = useState<string | null>(null);
  const a = state.analysis;
  const p = state.proposal;
  const content = text ?? p?.content ?? "";
  return (
    <div className="stack">
      {state.job && <h2 className="job-title">{state.job.title}</h2>}
      {BUSY[state.status] && (
        <p className="muted" role="status">
          {BUSY[state.status]}
        </p>
      )}
      {state.status === "error" && (
        <div className="alert" role="alert">
          <p>{state.error}</p>
          {onRetry && (
            <button className="btn" onClick={onRetry}>
              Retry
            </button>
          )}
        </div>
      )}
      {a && (
        <section className="card">
          <div className="row">
            <span className={`score ${tone(a.fit_score)}`}>{a.fit_score}</span>
            <div>
              <div className="strong">{a.recommendation}</div>
              <div className="muted">Confidence {Math.round(a.score_confidence * 100)}%</div>
            </div>
            {a.is_simulated && <span className="sim">Simulated AI</span>}
          </div>
          <p className="muted small">{a.explanation}</p>
          <h3>Matched skills</h3>
          <div className="chips">{a.matched_skills.length ? a.matched_skills.map((s) => <span key={s} className="chip g">{s}</span>) : <span className="muted">None</span>}</div>
          <h3>Missing skills</h3>
          <div className="chips">{a.missing_skills.length ? a.missing_skills.map((s) => <span key={s} className="chip r">{s}</span>) : <span className="muted">None</span>}</div>
          <h3>Warning signs</h3>
          {a.red_flags.length ? (
            <ul className="list">
              {a.red_flags.map((f, i) => (
                <li key={i} className={f.severity === "high" ? "bad" : "warn"}>
                  {f.flag}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">None detected</p>
          )}
          <h3>Relevant portfolio projects</h3>
          {a.portfolio.length ? (
            <ul className="list">
              {a.portfolio.map((pr) => (
                <li key={pr.title}>
                  {pr.title} <span className="muted">({Math.round(pr.similarity * 100)}%)</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No related projects</p>
          )}
          <a className="link" href={`${dashboardUrl}/jobs/${a.job_id}`} target="_blank" rel="noreferrer">
            Open full analysis in dashboard ↗
          </a>
        </section>
      )}
      {p && (
        <section className="card">
          <h3>
            Proposal draft {p.is_simulated && <span className="sim">Simulated AI</span>}
          </h3>
          {p.warnings.map((w, i) => (
            <p key={i} className="warn small">
              {w}
            </p>
          ))}
          <label className="sr-only" htmlFor="proposal">
            Proposal draft
          </label>
          <textarea id="proposal" value={content} onChange={(e) => setText(e.target.value)} rows={10} />
          <div className="row">
            <button
              className="btn primary"
              onClick={async () => {
                await navigator.clipboard.writeText(content);
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              }}
            >
              {copied ? "Copied" : "Copy proposal"}
            </button>
            <a className="link" href={`${dashboardUrl}/proposals/${p.id}`} target="_blank" rel="noreferrer">
              Edit in dashboard ↗
            </a>
          </div>
          <p className="muted small">Edits here are not saved. Review before use — BidGenie never submits proposals for you.</p>
        </section>
      )}
    </div>
  );
}
