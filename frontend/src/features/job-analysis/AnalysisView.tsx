import { AlertTriangle, CheckCircle2, ExternalLink, HelpCircle, ShieldAlert, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { FitScoreRing, RecommendationBadge, SimulatedBadge, SkillChips } from "@/components/domain";
import { Badge, Card, CardHeader, Notice } from "@/components/ui/primitives";
import type { Analysis } from "@/types/api";

function Bar({ value }: { value: number | null }) {
  const pct = value === null ? 0 : Math.round(value * 100);
  const color = value === null ? "bg-slate-300" : value >= 0.75 ? "bg-good" : value >= 0.5 ? "bg-amber-500" : "bg-bad";
  return (
    <div className="h-2 w-full rounded-full bg-slate-100" aria-hidden>
      <div className={`h-2 rounded-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function AnalysisView({ analysis }: { analysis: Analysis }) {
  const r = analysis.result;
  return (
    <div className="space-y-4">
      {analysis.profile_changed_since && (
        <Notice tone="warn">Your profile or portfolio changed since this analysis. Re-analyze for an up-to-date score.</Notice>
      )}
      <Card className="p-5">
        <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-start">
          <FitScoreRing score={r.fit_score} />
          <div className="min-w-0 flex-1 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <RecommendationBadge value={r.recommendation} />
              <Badge>Confidence {Math.round(r.score_confidence * 100)}%</Badge>
              <SimulatedBadge show={analysis.is_simulated} />
            </div>
            <div>
              <h3 className="flex items-center gap-1.5 text-sm font-semibold text-ink">
                Explanation
                {r.ai_generated_fields.includes("explanation") && (
                  <Badge tone="brand">
                    <Sparkles className="h-3 w-3" /> AI-written
                  </Badge>
                )}
              </h3>
              <p className="mt-1 text-sm leading-relaxed text-ink-soft">{r.explanation}</p>
            </div>
            <p className="text-xs text-muted">
              Scoring v{analysis.scoring_version} · {analysis.provider}
              {analysis.model ? ` / ${analysis.model}` : ""} · {new Date(analysis.created_at).toLocaleString()}
            </p>
          </div>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Score breakdown" description="Unknown factors are excluded and their weight redistributed — not counted as zero." />
          <ul className="divide-y divide-line">
            {r.score_breakdown.map((b) => (
              <li key={b.factor} className="px-5 py-3">
                <div className="flex items-center justify-between gap-2 text-sm">
                  <span className="font-medium text-ink">{b.label}</span>
                  <span className="text-muted">
                    {b.status === "unknown" ? (
                      <Badge>
                        <HelpCircle className="h-3 w-3" /> Unknown
                      </Badge>
                    ) : (
                      `${b.points?.toFixed(1)} / ${b.effective_weight.toFixed(1)}`
                    )}
                  </span>
                </div>
                <div className="mt-2">
                  <Bar value={b.score} />
                </div>
                <p className="mt-1 text-xs text-muted">{b.detail}</p>
              </li>
            ))}
          </ul>
        </Card>

        <Card>
          <CardHeader title="Skills" description={r.required_skills_inferred ? "Required skills were inferred from the description." : "Compared with your profile skills."} />
          <div className="space-y-4 p-5">
            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-good">Matched</p>
              <SkillChips skills={r.matched_skills} tone="good" />
            </div>
            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-warn">Partially matched</p>
              <SkillChips skills={r.partially_matched_skills.map((p) => `${p.skill} (via ${p.via})`)} tone="warn" />
            </div>
            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-bad">Missing</p>
              <SkillChips skills={r.missing_skills} tone="bad" />
            </div>
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Budget</p>
              <p className="text-sm text-ink-soft">{r.budget_compatibility.detail || "Not compared."}</p>
            </div>
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader title="Relevant portfolio projects" description="Retrieved by semantic similarity from your own portfolio." />
        {r.relevant_portfolio_projects.length === 0 ? (
          <p className="p-5 text-sm text-muted">
            No related portfolio projects found. <Link to="/portfolio" className="text-brand-600 hover:underline">Add projects</Link> to strengthen your evidence.
          </p>
        ) : (
          <ul className="divide-y divide-line">
            {r.relevant_portfolio_projects.map((p) => (
              <li key={p.project_id} className="px-5 py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-ink">{p.title}</span>
                  <div className="flex items-center gap-2">
                    <Badge tone="brand">Similarity {(p.similarity * 100).toFixed(0)}%</Badge>
                    {p.url && (
                      <a href={p.url} target="_blank" rel="noopener noreferrer" aria-label={`Open ${p.title}`} className="text-brand-600">
                        <ExternalLink className="h-4 w-4" />
                      </a>
                    )}
                  </div>
                </div>
                <p className="mt-1 text-sm text-ink-soft">“{p.evidence}”</p>
                {!!p.shared_skills.length && <p className="mt-1 text-xs text-muted">Shared skills: {p.shared_skills.join(", ")}</p>}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Positive signals" />
          <ul className="space-y-2 p-5">
            {r.positive_signals.length === 0 && <li className="text-sm text-muted">None identified.</li>}
            {r.positive_signals.map((s, i) => (
              <li key={i} className="flex gap-2 text-sm text-ink-soft">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-good" /> {s}
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <CardHeader title="Warning signs" description="Potential concerns based on the posting text. They are not accusations." />
          <ul className="space-y-3 p-5">
            {r.red_flags.length === 0 && <li className="text-sm text-muted">No warning signs detected.</li>}
            {r.red_flags.map((f, i) => (
              <li key={i} className="flex gap-2 text-sm">
                {f.severity === "high" ? (
                  <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-bad" />
                ) : (
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
                )}
                <div>
                  <p className="font-medium text-ink">
                    {f.flag} {f.source === "ai" && <Badge tone="brand">AI-identified</Badge>}
                  </p>
                  <p className="text-xs text-muted">{f.evidence}</p>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Feasibility" />
          <p className="p-5 text-sm text-ink-soft">{r.feasibility_assessment}</p>
        </Card>
        <Card>
          <CardHeader title="Recommended next steps" />
          <ol className="list-decimal space-y-1 p-5 pl-9 text-sm text-ink-soft">
            {r.suggested_next_steps.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
          {!!r.missing_information.length && (
            <div className="border-t border-line px-5 py-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">Missing information</p>
              <ul className="mt-1 list-disc pl-5 text-sm text-muted">
                {r.missing_information.map((m, i) => (
                  <li key={i}>{m}</li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
