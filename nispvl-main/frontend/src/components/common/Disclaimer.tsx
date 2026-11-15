import { Info } from "lucide-react";
import { useTranslation } from "react-i18next";

export default function Disclaimer({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation();
  return (
    <div role="note" className={`flex items-start gap-2 rounded-md border border-line bg-surface text-ink-2 ${compact ? "px-3 py-2 text-xs" : "px-4 py-3 text-sm"}`}>
      <Info className="mt-0.5 h-4 w-4 flex-none text-ink-muted" />
      {t("app.disclaimer")}
    </div>
  );
}
