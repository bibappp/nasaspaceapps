import { AlertTriangle, Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { Status } from "../../api/types";

/** Значок «требует проверки» для значений со статусом assumption. */
export default function StatusBadge({ status }: { status: Status }) {
  const { t } = useTranslation();
  if (status === "verified") {
    return (
      <span className="badge-green">
        <Check className="h-3 w-3" /> {t("app.verified")}
      </span>
    );
  }
  return (
    <span title={t("app.needs_check_title")} className="badge-amber">
      <AlertTriangle className="h-3 w-3" /> {t("app.needs_check")}
    </span>
  );
}
