import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, Navigate, useNavigate } from "react-router-dom";
import type { Lang } from "../../api/types";
import { ErrorBox } from "../../components/ui/ui";
import { errorText } from "../../lib/async";
import { useAuth } from "../../lib/auth";
import AuthLayout from "./AuthLayout";

export default function Register() {
  const { t, i18n } = useTranslation();
  const { user, register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: "", password: "", password2: "", name: "", farm_name: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (user && !user.is_demo) return <Navigate to="/app" replace />;
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (form.password !== form.password2) {
      setError(t("auth.password_mismatch"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await register({ email: form.email, password: form.password, name: form.name, farm_name: form.farm_name, lang: i18n.language as Lang });
      navigate("/app/fields/new", { replace: true });
    } catch (err) {
      setError(errorText(err, t));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout
      title={t("auth.register_title")}
      subtitle={t("auth.register_subtitle")}
      footer={
        <>
          {t("auth.have_account")} <Link to="/login">{t("auth.login")}</Link>
        </>
      }
    >
      <form className="space-y-4" onSubmit={(e) => void submit(e)}>
        {error && <ErrorBox message={error} />}
        <label className="block">
          <span className="label">{t("auth.name")}</span>
          <input className="input" autoComplete="name" value={form.name} onChange={set("name")} maxLength={120} />
        </label>
        <label className="block">
          <span className="label">{t("auth.farm_name")}</span>
          <input className="input" autoComplete="organization" value={form.farm_name} onChange={set("farm_name")} maxLength={160} />
        </label>
        <label className="block">
          <span className="label">{t("auth.email")}</span>
          <input className="input" type="email" autoComplete="email" required value={form.email} onChange={set("email")} />
        </label>
        <label className="block">
          <span className="label">{t("auth.password")}</span>
          <input className="input" type="password" autoComplete="new-password" required minLength={8} value={form.password} onChange={set("password")} />
          <span className="hint">{t("auth.password_hint")}</span>
        </label>
        <label className="block">
          <span className="label">{t("auth.password2")}</span>
          <input className="input" type="password" autoComplete="new-password" required minLength={8} value={form.password2} onChange={set("password2")} />
        </label>
        <button type="submit" className="btn-primary w-full" disabled={busy}>
          {t("auth.create_account")}
        </button>
        <p className="hint">{t("auth.privacy_note")}</p>
      </form>
    </AuthLayout>
  );
}
