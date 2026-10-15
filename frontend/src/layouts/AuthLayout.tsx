import { Link, Outlet } from "react-router-dom";

export default function AuthLayout() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 py-10">
      <Link to="/" className="mb-8 flex items-center gap-2 text-lg font-semibold text-ink">
        <img src="/favicon.svg" alt="" className="h-8 w-8" />
        BidGenie AI
      </Link>
      <div className="w-full max-w-md rounded-2xl border border-line bg-white p-6 shadow-sm sm:p-8">
        <Outlet />
      </div>
    </div>
  );
}
