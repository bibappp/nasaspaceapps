import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { ErrorBox } from "../../components/ui/ui";
import { errorText } from "../../lib/async";
import { useAuth } from "../../lib/auth";
import AuthLayout from "./AuthLayout";

export default function Login() {
  const { t } = useTranslation();
  const { user, login, demo } = useAuth();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from ?? "/app";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to={from} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(errorText(err, t));
    } finally {
      setBusy(false);
    }
  };
  const startDemo = async () => {
    setBusy(true);
    try {
      await demo();
      navigate("/app", { replace: true });
    } catch (err) {
      setError(errorText(err, t));
      setBusy(false);
    }
  };

  return (
    <AuthLayout
      title={t("auth.login_title")}
      subtitle={t("auth.login_subtitle")}
      footer={
        <>
          {t("auth.no_account")} <Link to="/register">{t("auth.signup")}</Link>
        </>
      }
    >
      <form className="space-y-4" onSubmit={(e) => void submit(e)}>
        {error && <ErrorBox message={error} />}
        <label className="block">
          <span className="label">{t("auth.email")}</span>
          <input className="input" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="block">
          <span className="label">{t("auth.password")}</span>
          <input className="input" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <button type="submit" className="btn-primary w-full" disabled={busy}>
          {t("auth.login")}
        </button>
      </form>
      <div className="my-5 flex items-center gap-3 text-xs text-ink-subtle">
        <span className="h-px flex-1 bg-line" />
        {t("auth.or")}
        <span className="h-px flex-1 bg-line" />
      </div>
      <button type="button" className="btn-secondary w-full" disabled={busy} onClick={() => void startDemo()}>
        {t("auth.demo_start")}
      </button>
      <p className="hint">{t("auth.demo_hint")}</p>
    </AuthLayout>
  );
}
