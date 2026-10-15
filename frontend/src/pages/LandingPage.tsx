import { BadgeCheck, FileText, Gauge, Search, ShieldCheck, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { LinkButton } from "@/components/ui/primitives";
import { useAuth } from "@/features/auth/AuthProvider";

const FEATURES = [
  { icon: Gauge, title: "Transparent Fit Score", text: "A 0–100 score with a factor-by-factor breakdown. Missing information is treated as unknown, not as a penalty." },
  { icon: Search, title: "Semantic portfolio matching", text: "Your projects are embedded and matched to each job, with the evidence shown so you can judge the match yourself." },
  { icon: FileText, title: "Honest proposals", text: "Hook → Solution → Proof → Call to Action, written only from facts you supplied. Never invented clients or results." },
  { icon: ShieldCheck, title: "Warning signs", text: "Flags potential issues such as off-platform payment requests or unpaid test work, with the exact wording as evidence." },
  { icon: BadgeCheck, title: "You stay in control", text: "Every output is editable. BidGenie never submits proposals, clicks Apply or spends Connects for you." },
  { icon: Sparkles, title: "Track what works", text: "A tracker and analytics built only from records you enter — no invented success rates." },
];

export default function LandingPage() {
  const { user } = useAuth();
  return (
    <div className="min-h-screen bg-white">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-5 sm:px-6">
        <Link to="/" className="flex items-center gap-2 font-semibold">
          <img src="/favicon.svg" alt="" className="h-8 w-8" /> BidGenie AI
        </Link>
        <nav className="flex items-center gap-2">
          {user ? (
            <LinkButton to="/dashboard">Open dashboard</LinkButton>
          ) : (
            <>
              <LinkButton to="/login" variant="ghost">
                Sign in
              </LinkButton>
              <LinkButton to="/register">Get started</LinkButton>
            </>
          )}
        </nav>
      </header>
      <main>
        <section className="mx-auto max-w-4xl px-4 pb-16 pt-12 text-center sm:px-6 sm:pt-20">
          <p className="mb-4 inline-block rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700">AI assistant for Upwork freelancers</p>
          <h1 className="text-4xl font-semibold tracking-tight text-ink sm:text-5xl">Spend Connects on jobs you can actually win.</h1>
          <p className="mx-auto mt-5 max-w-2xl text-lg text-ink-soft">
            BidGenie scores each job against your real skills and portfolio, explains why, and drafts a personalised proposal you can edit before you apply.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <LinkButton to={user ? "/dashboard" : "/register"} size="lg">
              {user ? "Go to dashboard" : "Create a free account"}
            </LinkButton>
            {!user && (
              <LinkButton to="/login" size="lg" variant="outline">
                Sign in
              </LinkButton>
            )}
          </div>
          <p className="mt-4 text-xs text-muted">BidGenie does not guarantee interviews or hires. It helps you decide and write — you stay in charge.</p>
        </section>
        <section className="border-t border-line bg-canvas py-16">
          <div className="mx-auto grid max-w-6xl gap-5 px-4 sm:grid-cols-2 sm:px-6 lg:grid-cols-3">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <div key={title} className="rounded-xl border border-line bg-white p-6 shadow-sm">
                <Icon className="h-6 w-6 text-brand-600" aria-hidden />
                <h2 className="mt-3 font-semibold">{title}</h2>
                <p className="mt-1 text-sm text-ink-soft">{text}</p>
              </div>
            ))}
          </div>
        </section>
      </main>
      <footer className="border-t border-line py-8 text-center text-xs text-muted">BidGenie AI · Not affiliated with Upwork.</footer>
    </div>
  );
}
