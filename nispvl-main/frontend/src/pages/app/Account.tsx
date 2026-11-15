import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../../api/client";
import type { Lang } from "../../api/types";
import { ErrorBox, Notice, PageHeader } from "../../components/ui/ui";
import { errorText } from "../../lib/async";
import { useAuth } from "../../lib/auth";

export default function Account() {
  const { t, i18n } = useTranslation();
  const { user, setUser } = useAuth();
  const [form, setForm] = useState({ name: user?.name ?? "", farm_name: user?.farm_name ?? "", lang: (user?.lang ?? i18n.language) as Lang });
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!user) return null;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const u = await api.updateProfile(form);
      setUser(u);
      void i18n.changeLanguage(u.lang);
      setMsg(t("account.saved"));
    } catch (err) {
      setError(errorText(err, t));
    }
  };
  return (
    <div className="max-w-xl">
      <PageHeader title={t("account.title")} subtitle={user.email} />
      <form className="panel panel-body space-y-4" onSubmit={(e) => void submit(e)}>
        {error && <ErrorBox message={error} />}
        {msg && <Notice>{msg}</Notice>}
        <label className="block">
          <span className="label">{t("auth.name")}</span>
          <input className="input" maxLength={120} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </label>
        <label className="block">
          <span className="label">{t("auth.farm_name")}</span>
          <input className="input" maxLength={160} value={form.farm_name} onChange={(e) => setForm({ ...form, farm_name: e.target.value })} />
        </label>
        <label className="block">
          <span className="label">{t("account.lang")}</span>
          <select className="input" value={form.lang} onChange={(e) => setForm({ ...form, lang: e.target.value as Lang })}>
            {(["ru", "kk", "en"] as Lang[]).map((l) => <option key={l} value={l}>{t(`app.lang.${l}_name`)}</option>)}
          </select>
        </label>
        <button type="submit" className="btn-primary">{t("app.save")}</button>
      </form>
    </div>
  );
}
