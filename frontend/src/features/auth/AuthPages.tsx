import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";
import { Button, Field, Input, Notice } from "@/components/ui/primitives";
import { errorMessage } from "@/lib/api";
import { authApi } from "@/services";
import { useAuth } from "./AuthProvider";

const email = z.string().trim().min(1, "Email is required").email("Enter a valid email address");
export const passwordRule = z
  .string()
  .min(10, "Use at least 10 characters")
  .max(128, "Use at most 128 characters")
  .refine((v) => /[a-z]/.test(v) && /[A-Z]/.test(v) && /\d/.test(v), "Include upper- and lower-case letters and a number");

const loginSchema = z.object({ email, password: z.string().min(1, "Password is required") });
type LoginValues = z.infer<typeof loginSchema>;

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<LoginValues>({ resolver: zodResolver(loginSchema) });
  const from = (location.state as { from?: string } | null)?.from ?? "/dashboard";

  const onSubmit = async (v: LoginValues) => {
    setError(null);
    try {
      const user = await login(v.email, v.password);
      navigate(user.onboarding_completed ? from : "/onboarding", { replace: true });
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <>
      <h1 className="text-xl font-semibold">Sign in</h1>
      <p className="mt-1 text-sm text-muted">Welcome back to BidGenie AI.</p>
      <form className="mt-6 space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        {error && <Notice tone="bad">{error}</Notice>}
        <Field label="Email" htmlFor="email" error={formState.errors.email?.message}>
          <Input id="email" type="email" autoComplete="email" invalid={!!formState.errors.email} {...register("email")} />
        </Field>
        <Field label="Password" htmlFor="password" error={formState.errors.password?.message}>
          <Input id="password" type="password" autoComplete="current-password" invalid={!!formState.errors.password} {...register("password")} />
        </Field>
        <div className="flex justify-end text-sm">
          <Link to="/forgot-password" className="text-brand-600 hover:underline">
            Forgot password?
          </Link>
        </div>
        <Button type="submit" className="w-full" loading={formState.isSubmitting}>
          Sign in
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted">
        New to BidGenie?{" "}
        <Link to="/register" className="font-medium text-brand-600 hover:underline">
          Create an account
        </Link>
      </p>
    </>
  );
}

const registerSchema = z
  .object({
    full_name: z.string().trim().max(200).optional(),
    email,
    password: passwordRule,
    confirm: z.string(),
    terms: z.literal(true, { errorMap: () => ({ message: "Please confirm to continue" }) }),
  })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords do not match" });
type RegisterValues = z.infer<typeof registerSchema>;

export function RegisterPage() {
  const { register: signUp } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<RegisterValues>({ resolver: zodResolver(registerSchema) });

  const onSubmit = async (v: RegisterValues) => {
    setError(null);
    try {
      await signUp(v.email, v.password, v.full_name || undefined);
      navigate("/onboarding", { replace: true });
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <>
      <h1 className="text-xl font-semibold">Create your account</h1>
      <p className="mt-1 text-sm text-muted">Evaluate jobs and write honest, personalised proposals.</p>
      <form className="mt-6 space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        {error && <Notice tone="bad">{error}</Notice>}
        <Field label="Full name" htmlFor="full_name" error={formState.errors.full_name?.message}>
          <Input id="full_name" autoComplete="name" {...register("full_name")} />
        </Field>
        <Field label="Email" htmlFor="email" error={formState.errors.email?.message}>
          <Input id="email" type="email" autoComplete="email" invalid={!!formState.errors.email} {...register("email")} />
        </Field>
        <Field label="Password" htmlFor="password" error={formState.errors.password?.message} hint="At least 10 characters with upper- and lower-case letters and a number.">
          <Input id="password" type="password" autoComplete="new-password" invalid={!!formState.errors.password} {...register("password")} />
        </Field>
        <Field label="Confirm password" htmlFor="confirm" error={formState.errors.confirm?.message}>
          <Input id="confirm" type="password" autoComplete="new-password" invalid={!!formState.errors.confirm} {...register("confirm")} />
        </Field>
        <div>
          <label className="flex items-start gap-2 text-sm text-ink-soft">
            <input type="checkbox" className="mt-0.5" {...register("terms")} />
            <span>I understand BidGenie never submits proposals or spends Connects on my behalf, and AI output must be reviewed before use.</span>
          </label>
          {formState.errors.terms && (
            <p role="alert" className="mt-1 text-xs text-bad">
              {formState.errors.terms.message}
            </p>
          )}
        </div>
        <Button type="submit" className="w-full" loading={formState.isSubmitting}>
          Create account
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-brand-600 hover:underline">
          Sign in
        </Link>
      </p>
    </>
  );
}

export function ForgotPasswordPage() {
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<{ email: string }>({ resolver: zodResolver(z.object({ email })) });
  const onSubmit = async (v: { email: string }) => {
    setError(null);
    try {
      setSent((await authApi.forgot(v.email)).message);
    } catch (e) {
      setError(errorMessage(e));
    }
  };
  return (
    <>
      <h1 className="text-xl font-semibold">Reset your password</h1>
      <p className="mt-1 text-sm text-muted">We'll email you a reset link if an account exists.</p>
      {sent ? (
        <div className="mt-6 space-y-4">
          <Notice tone="good">{sent}</Notice>
          <Link to="/login" className="block text-center text-sm font-medium text-brand-600 hover:underline">
            Back to sign in
          </Link>
        </div>
      ) : (
        <form className="mt-6 space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          {error && <Notice tone="bad">{error}</Notice>}
          <Field label="Email" htmlFor="email" error={formState.errors.email?.message}>
            <Input id="email" type="email" autoComplete="email" {...register("email")} />
          </Field>
          <Button type="submit" className="w-full" loading={formState.isSubmitting}>
            Send reset link
          </Button>
          <Link to="/login" className="block text-center text-sm text-muted hover:underline">
            Back to sign in
          </Link>
        </form>
      )}
    </>
  );
}

const resetSchema = z
  .object({ password: passwordRule, confirm: z.string() })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords do not match" });

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const { register, handleSubmit, formState } = useForm<z.infer<typeof resetSchema>>({ resolver: zodResolver(resetSchema) });
  const onSubmit = async (v: z.infer<typeof resetSchema>) => {
    setError(null);
    try {
      await authApi.reset(token, v.password);
      setDone(true);
      setTimeout(() => navigate("/login"), 1500);
    } catch (e) {
      setError(errorMessage(e));
    }
  };
  if (!token) return <Notice tone="bad">This reset link is missing its token. Request a new link.</Notice>;
  return (
    <>
      <h1 className="text-xl font-semibold">Choose a new password</h1>
      {done ? (
        <div className="mt-6">
          <Notice tone="good">Password updated. Redirecting to sign in…</Notice>
        </div>
      ) : (
        <form className="mt-6 space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          {error && <Notice tone="bad">{error}</Notice>}
          <Field label="New password" htmlFor="password" error={formState.errors.password?.message}>
            <Input id="password" type="password" autoComplete="new-password" {...register("password")} />
          </Field>
          <Field label="Confirm password" htmlFor="confirm" error={formState.errors.confirm?.message}>
            <Input id="confirm" type="password" autoComplete="new-password" {...register("confirm")} />
          </Field>
          <Button type="submit" className="w-full" loading={formState.isSubmitting}>
            Update password
          </Button>
        </form>
      )}
    </>
  );
}

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [state, setState] = useState<{ ok: boolean; msg: string } | null>(null);
  useEffect(() => {
    if (!token) return;
    authApi
      .verifyEmail(token)
      .then((r) => setState({ ok: true, msg: r.message }))
      .catch((e) => setState({ ok: false, msg: errorMessage(e) }));
  }, [token]);
  return (
    <>
      <h1 className="text-xl font-semibold">Email verification</h1>
      <div className="mt-6">
        {!token ? (
          <Notice tone="bad">The verification link is missing its token.</Notice>
        ) : !state ? (
          <p className="text-sm text-muted">Verifying…</p>
        ) : (
          <Notice tone={state.ok ? "good" : "bad"}>{state.msg}</Notice>
        )}
        <Link to="/dashboard" className="mt-4 block text-center text-sm font-medium text-brand-600 hover:underline">
          Continue to BidGenie
        </Link>
      </div>
    </>
  );
}
