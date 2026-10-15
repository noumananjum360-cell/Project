import clsx from "clsx";
import { FlaskConical, X } from "lucide-react";
import { useId, useState, type KeyboardEvent } from "react";
import type { AppStatus, Recommendation } from "@/types/api";
import { Badge } from "./ui/primitives";

export function scoreTone(score: number | null | undefined): "good" | "warn" | "bad" | "neutral" {
  if (score === null || score === undefined) return "neutral";
  if (score >= 75) return "good";
  if (score >= 50) return "warn";
  return "bad";
}

const ringColor = { good: "#059669", warn: "#d97706", bad: "#dc2626", neutral: "#94a3b8" };

export function FitScoreRing({ score, size = 140, label = "Fit Score" }: { score: number | null; size?: number; label?: string }) {
  const stroke = Math.max(6, size / 14);
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = score === null ? 0 : Math.max(0, Math.min(100, score));
  const tone = scoreTone(score);
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} role="img" aria-label={`${label}: ${score ?? "not available"} out of 100`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e2e8f0" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={ringColor[tone]}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c - (pct / 100) * c}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="font-semibold text-ink" style={{ fontSize: size / 3.6 }}>
          {score ?? "—"}
        </span>
        <span className="text-xs text-muted">{label}</span>
      </div>
    </div>
  );
}

export function ScorePill({ score }: { score: number | null }) {
  if (score === null) return <Badge>Not analyzed</Badge>;
  return <Badge tone={scoreTone(score)}>Fit {score}</Badge>;
}

export function RecommendationBadge({ value }: { value: Recommendation | null }) {
  if (!value) return null;
  const tone = { "Strong Match": "good", "Possible Match": "warn", "Weak Match": "bad", "Insufficient Information": "neutral" } as const;
  return <Badge tone={tone[value]}>{value}</Badge>;
}

export function SimulatedBadge({ show = true, label = "Simulated AI" }: { show?: boolean; label?: string }) {
  if (!show) return null;
  return (
    <Badge tone="warn">
      <FlaskConical className="h-3 w-3" aria-hidden /> {label}
    </Badge>
  );
}

export function DemoBadge({ show = true }: { show?: boolean }) {
  if (!show) return null;
  return <Badge tone="neutral">Demo data</Badge>;
}

export const STATUS_LABELS: Record<AppStatus, string> = {
  draft: "Draft",
  ready: "Ready to Submit",
  sent: "Sent",
  interview: "Interview",
  hired: "Hired",
  declined: "Declined",
  archived: "Archived",
};

export function StatusBadge({ status }: { status: AppStatus }) {
  const tone = { draft: "neutral", ready: "brand", sent: "brand", interview: "warn", hired: "good", declined: "bad", archived: "neutral" } as const;
  return <Badge tone={tone[status]}>{STATUS_LABELS[status]}</Badge>;
}

export function SkillChips({ skills, tone = "neutral" }: { skills: string[]; tone?: "neutral" | "good" | "warn" | "bad" | "brand" }) {
  if (!skills.length) return <span className="text-sm text-muted">None</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {skills.map((s) => (
        <Badge key={s} tone={tone}>
          {s}
        </Badge>
      ))}
    </div>
  );
}

/** Comma/Enter separated chip input for lists such as skills. */
export function TagInput({
  value,
  onChange,
  placeholder,
  id,
  max = 40,
  ariaLabel,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
  id?: string;
  max?: number;
  ariaLabel?: string;
}) {
  const [draft, setDraft] = useState("");
  const autoId = useId();
  const inputId = id ?? autoId;
  const add = (raw: string) => {
    const parts = raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const next = [...value];
    for (const p of parts) if (!next.some((x) => x.toLowerCase() === p.toLowerCase()) && next.length < max) next.push(p.slice(0, 60));
    onChange(next);
    setDraft("");
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      if (draft.trim()) add(draft);
    } else if (e.key === "Backspace" && !draft && value.length) {
      onChange(value.slice(0, -1));
    }
  };
  return (
    <div className="flex min-h-10 flex-wrap items-center gap-1.5 rounded-lg border border-line bg-white px-2 py-1.5 focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-brand-100">
      {value.map((t) => (
        <span key={t} className="inline-flex items-center gap-1 rounded-md bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700">
          {t}
          <button type="button" aria-label={`Remove ${t}`} onClick={() => onChange(value.filter((x) => x !== t))}>
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
      <input
        id={inputId}
        aria-label={ariaLabel}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKey}
        onBlur={() => draft.trim() && add(draft)}
        placeholder={value.length ? "" : placeholder}
        className="min-w-[8rem] flex-1 border-0 bg-transparent px-1 py-1 text-sm outline-none"
      />
    </div>
  );
}

export function formatMoney(min: string | null, max: string | null, currency: string, type: string): string {
  const unit = type === "hourly" ? "/hr" : "";
  const f = (v: string) => Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (min && max && min !== max) return `${currency} ${f(min)}–${f(max)}${unit}`;
  if (max || min) return `${currency} ${f((max ?? min) as string)}${unit}`;
  return "Budget not specified";
}

export function formatDate(iso: string | null | undefined, withTime = false): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return withTime ? d.toLocaleString() : d.toLocaleDateString();
}

export function Truncate({ text, lines = 2, className }: { text: string; lines?: 2 | 3; className?: string }) {
  return <p className={clsx(lines === 2 ? "line-clamp-2" : "line-clamp-3", "text-sm text-muted", className)}>{text}</p>;
}
