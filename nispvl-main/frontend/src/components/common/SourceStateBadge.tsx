import { CheckCircle2, CircleDashed, KeyRound, WifiOff, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { DataSourceInfo } from "../../api/types";

export const DATA_SOURCE_STATES: DataSourceInfo["state"][] = ["active", "planned", "needs_credentials", "offline"];

const STATE_VISUAL: Record<DataSourceInfo["state"], { className: string; Icon: LucideIcon }> = {
  active: { className: "badge-green", Icon: CheckCircle2 },
  planned: { className: "badge-neutral", Icon: CircleDashed },
  needs_credentials: { className: "badge-amber", Icon: KeyRound },
  offline: { className: "badge-red", Icon: WifiOff },
};

export default function SourceStateBadge({ state }: { state: DataSourceInfo["state"] }) {
  const { t } = useTranslation();
  const { className, Icon } = STATE_VISUAL[state];
  const label = t(`methodology.state.${state}`);
  return (
    <span className={className}>
      <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden />
      <span>{label}</span>
    </span>
  );
}