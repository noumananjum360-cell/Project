import { Navigate, Outlet, useLocation } from "react-router-dom";
import { Spinner } from "@/components/ui/primitives";
import { useAuth } from "@/features/auth/AuthProvider";

export function ProtectedRoute() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Spinner label="Checking your session" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <Outlet />;
}

export function AdminRoute() {
  const { user } = useAuth();
  if (user?.role !== "ADMIN") return <Navigate to="/unauthorized" replace />;
  return <Outlet />;
}

export function GuestOnlyRoute() {
  const { user, loading } = useAuth();
  if (loading) return <Spinner label="Loading" />;
  if (user) return <Navigate to={user.onboarding_completed ? "/dashboard" : "/onboarding"} replace />;
  return <Outlet />;
}
