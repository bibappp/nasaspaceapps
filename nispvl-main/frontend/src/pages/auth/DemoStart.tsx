import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { ErrorBox, Loading } from "../../components/ui/ui";
import { errorText } from "../../lib/async";
import { useAuth } from "../../lib/auth";
import AuthLayout from "./AuthLayout";

/** /demo — создаёт отдельную демо-песочницу (поля Шортанды и Костанай с реальными данными) и открывает дашборд. */
export default function DemoStart() {
  const { t } = useTranslation();
  const { user, demo } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    if (user) {
      navigate("/app", { replace: true });
      return;
    }
    demo()
      .then(() => navigate("/app", { replace: true }))
      .catch((e: unknown) => setError(errorText(e, t)));
  }, [user, demo, navigate, t]);
  return (
    <AuthLayout title={t("auth.demo_title")} subtitle={t("auth.demo_hint")}>
      {error ? <ErrorBox message={error} /> : <Loading label={t("auth.demo_preparing")} />}
    </AuthLayout>
  );
}
