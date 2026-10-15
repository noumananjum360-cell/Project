import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import {
  BarChart3,
  Bell,
  Briefcase,
  FileText,
  FolderKanban,
  Gauge,
  KanbanSquare,
  LayoutDashboard,
  LogOut,
  Menu,
  Settings,
  Shield,
  User as UserIcon,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/features/auth/AuthProvider";
import { dashboardApi, notificationsApi } from "@/services";

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/jobs", label: "Find Jobs", icon: Briefcase },
  { to: "/analysis", label: "Job Analysis", icon: Gauge },
  { to: "/portfolio", label: "Portfolio", icon: FolderKanban },
  { to: "/proposals", label: "Proposal Studio", icon: FileText },
  { to: "/tracker", label: "Application Tracker", icon: KanbanSquare },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/settings", label: "Settings", icon: Settings },
];

function Logo() {
  return (
    <Link to="/dashboard" className="flex items-center gap-2 px-2 font-semibold text-ink">
      <img src="/favicon.svg" alt="" className="h-7 w-7" />
      <span>BidGenie AI</span>
    </Link>
  );
}

function SidebarNav({ isAdmin, onNavigate }: { isAdmin: boolean; onNavigate?: () => void }) {
  const items = isAdmin ? [...NAV, { to: "/admin", label: "Admin", icon: Shield }] : NAV;
  return (
    <nav aria-label="Main" className="mt-6 space-y-1">
      {items.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          onClick={onNavigate}
          className={({ isActive }) =>
            clsx(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              isActive ? "bg-brand-50 text-brand-700" : "text-ink-soft hover:bg-slate-100",
            )
          }
        >
          <Icon className="h-4 w-4" aria-hidden />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}

function AIStatusBanner() {
  const { data } = useQuery({ queryKey: ["dashboard", "summary"], queryFn: dashboardApi.summary, staleTime: 60_000 });
  const s = data?.ai_status;
  if (!s) return null;
  if (!s.configured)
    return (
      <div role="status" className="border-b border-amber-200 bg-warn-soft px-4 py-2 text-center text-xs text-warn">
        AI features are not configured on the server. Job analysis, portfolio matching and proposal generation are unavailable until an administrator sets an AI provider key.
      </div>
    );
  if (s.simulated)
    return (
      <div role="status" className="border-b border-amber-200 bg-warn-soft px-4 py-2 text-center text-xs text-warn">
        Demo mode: AI results are <strong>simulated</strong> by a deterministic mock provider and are not real AI output.
      </div>
    );
  return null;
}

export default function AppLayout() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { data: notes } = useQuery({
    queryKey: ["notifications", "badge"],
    queryFn: () => notificationsApi.list({ unread_only: true, page_size: 1 }),
    refetchInterval: 60_000,
  });

  useEffect(() => setOpen(false), [location.pathname]);

  const onLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">
        Skip to content
      </a>
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-line bg-white px-3 py-5 lg:block">
        <Logo />
        <SidebarNav isAdmin={user?.role === "ADMIN"} />
      </aside>

      {/* Mobile drawer */}
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/40" onClick={() => setOpen(false)} aria-hidden />
          <aside className="absolute inset-y-0 left-0 w-72 max-w-[85vw] bg-white px-3 py-5 shadow-xl" aria-label="Navigation menu">
            <div className="flex items-center justify-between">
              <Logo />
              <button className="rounded-md p-2 text-muted hover:bg-slate-100" onClick={() => setOpen(false)} aria-label="Close menu">
                <X className="h-5 w-5" />
              </button>
            </div>
            <SidebarNav isAdmin={user?.role === "ADMIN"} onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}

      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-2 border-b border-line bg-white/90 px-4 backdrop-blur sm:px-6">
          <button className="rounded-md p-2 text-ink-soft hover:bg-slate-100 lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu">
            <Menu className="h-5 w-5" />
          </button>
          <div className="lg:hidden">
            <Logo />
          </div>
          <div className="ml-auto flex items-center gap-1">
            <Link to="/notifications" className="relative rounded-md p-2 text-ink-soft hover:bg-slate-100" aria-label={`Notifications${notes?.unread ? ` (${notes.unread} unread)` : ""}`}>
              <Bell className="h-5 w-5" />
              {!!notes?.unread && (
                <span className="absolute right-1 top-1 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-bad px-1 text-[10px] font-semibold text-white">
                  {notes.unread > 9 ? "9+" : notes.unread}
                </span>
              )}
            </Link>
            <Link to="/profile" className="flex items-center gap-2 rounded-md p-2 text-sm text-ink-soft hover:bg-slate-100" aria-label="Your profile">
              <UserIcon className="h-5 w-5" />
              <span className="hidden max-w-[12rem] truncate sm:inline">{user?.full_name || user?.email}</span>
            </Link>
            <button onClick={onLogout} className="rounded-md p-2 text-ink-soft hover:bg-slate-100" aria-label="Sign out">
              <LogOut className="h-5 w-5" />
            </button>
          </div>
        </header>
        <AIStatusBanner />
        <main id="main" className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
