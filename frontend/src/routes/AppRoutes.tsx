import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import { Spinner } from "@/components/ui/primitives";
import { ForgotPasswordPage, LoginPage, RegisterPage, ResetPasswordPage, VerifyEmailPage } from "@/features/auth/AuthPages";
import AppLayout from "@/layouts/AppLayout";
import AuthLayout from "@/layouts/AuthLayout";
import LandingPage from "@/pages/LandingPage";
import { NotFoundPage, UnauthorizedPage } from "@/pages/StatusPages";
import { AdminRoute, GuestOnlyRoute, ProtectedRoute } from "./guards";

const DashboardPage = lazy(() => import("@/features/dashboard/DashboardPage"));
const JobFeedPage = lazy(() => import("@/features/jobs/JobFeedPage"));
const JobDetailPage = lazy(() => import("@/features/jobs/JobDetailPage"));
const JobAnalysisPage = lazy(() => import("@/features/job-analysis/JobAnalysisPage"));
const PortfolioPage = lazy(() => import("@/features/portfolio/PortfolioPage"));
const ProposalStudioPage = lazy(() => import("@/features/proposals/ProposalStudioPage"));
const ProposalEditorPage = lazy(() => import("@/features/proposals/ProposalEditorPage"));
const TrackerPage = lazy(() => import("@/features/tracking/TrackerPage"));
const AnalyticsPage = lazy(() => import("@/features/analytics/AnalyticsPage"));
const SettingsPage = lazy(() => import("@/features/settings/SettingsPage"));
const ProfilePage = lazy(() => import("@/features/profile/ProfilePage"));
const OnboardingPage = lazy(() => import("@/features/profile/OnboardingPage"));
const NotificationsPage = lazy(() => import("@/features/notifications/NotificationsPage"));
const AdminPage = lazy(() => import("@/features/admin/AdminPage"));

export default function AppRoutes() {
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route element={<AuthLayout />}>
          <Route element={<GuestOnlyRoute />}>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          </Route>
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/verify-email" element={<VerifyEmailPage />} />
        </Route>
        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            <Route path="/onboarding" element={<OnboardingPage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/jobs" element={<JobFeedPage />} />
            <Route path="/jobs/:id" element={<JobDetailPage />} />
            <Route path="/analysis" element={<JobAnalysisPage />} />
            <Route path="/portfolio" element={<PortfolioPage />} />
            <Route path="/proposals" element={<ProposalStudioPage />} />
            <Route path="/proposals/:id" element={<ProposalEditorPage />} />
            <Route path="/tracker" element={<TrackerPage />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="/notifications" element={<NotificationsPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route element={<AdminRoute />}>
              <Route path="/admin" element={<AdminPage />} />
            </Route>
            <Route path="/unauthorized" element={<UnauthorizedPage />} />
          </Route>
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}
