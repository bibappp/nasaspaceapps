import { AlertTriangle, BarChart3, FileDown, History as HistoryIcon, LayoutGrid, Map as MapIcon, Pencil, Scale, Sprout, Wind } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../../api/client";
import type { Analysis, Lang } from "../../api/types";
import BareSoilTab from "../../components/workspace/BareSoilTab";
import FieldMap from "../../components/workspace/FieldMap";
import History from "../../components/workspace/History";
import Monitoring from "../../components/workspace/Monitoring";
import Overview from "../../components/workspace/Overview";
import Planner from "../../components/workspace/Planner";
import Reports from "../../components/workspace/Reports";
import RiskTab from "../../components/workspace/RiskTab";
import SuitabilityTab from "../../components/workspace/SuitabilityTab";
import { ErrorBox, Loading, PageHeader, Tabs } from "../../components/ui/ui";
import { errorText, useAsync } from "../../lib/async";
import { useConfig } from "../../lib/config";
import { fmtNum } from "../../lib/format";
import { tx } from "../../lib/i18n-text";

const TABS = ["overview", "monitoring", "map", "history", "bare_soil", "risk", "planner", "suitability", "reports"] as const;
type Tab = (typeof TABS)[number];
const ICONS: Record<Tab, typeof MapIcon> = { overview: LayoutGrid, monitoring: BarChart3, map: MapIcon, history: HistoryIcon, bare_soil: Wind, risk: AlertTriangle, planner: Scale, suitability: Sprout, reports: FileDown };

export default function FieldWorkspace() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const { id } = useParams();
  const fieldId = Number(id);
  const { config } = useConfig();
  const [params, setParams] = useSearchParams();
  const tab = (TABS as readonly string[]).includes(params.get("tab") ?? "") ? (params.get("tab") as Tab) : "overview";
  const field = useAsync(() => api.field(fieldId), [fieldId]);
  const [overview, setOverview] = useState<Analysis | null>(null);
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [visited, setVisited] = useState<Set<Tab>>(new Set([tab]));

  useEffect(() => setVisited((v) => (v.has(tab) ? v : new Set([...v, tab]))), [tab]);
  useEffect(() => {
    let alive = true;
    setOverview(null);
    setOverviewError(null);
    api
      .fieldOverview(fieldId)
      .then((a) => alive && setOverview(a))
      .catch((e: unknown) => alive && setOverviewError(errorText(e, t)));
    return () => {
      alive = false;
    };
  }, [fieldId, field.data?.updated_at]); // eslint-disable-line react-hooks/exhaustive-deps

  if (field.error) return <ErrorBox message={errorText(field.error, t)} onRetry={field.reload} />;
  if (!field.data) return <Loading />;
  const f = field.data;
  const region = tx(config?.regions.find((r) => r.id === f.region)?.name, lang) || f.region;

  // вкладки монтируются при первом открытии и остаются в памяти — переключение не сбрасывает состояние планировщика
  const panel = (k: Tab) => {
    switch (k) {
      case "overview": return <Overview field={f} overview={overview} error={overviewError} />;
      case "monitoring": return <Monitoring fieldId={f.id} />;
      case "map": return <FieldMap fieldId={f.id} geometry={f.geometry} />;
      case "history": return <History fieldId={f.id} />;
      case "bare_soil": return <BareSoilTab fieldId={f.id} />;
      case "risk": return <RiskTab fieldId={f.id} />;
      case "planner": return <Planner field={f} overview={overview} />;
      case "suitability": return <SuitabilityTab fieldId={f.id} />;
      case "reports": return <Reports fieldId={f.id} />;
    }
  };

  return (
    <div>
      <PageHeader
        eyebrow={<Link to="/app/fields" className="text-ink-muted no-underline hover:text-ink">{t("fields.title")}</Link>}
        title={f.name}
        subtitle={`${region} · ${fmtNum(f.area_ha, 1)} ${t("units.ha")} · ${fmtNum(f.centroid_lat, 3)}°, ${fmtNum(f.centroid_lon, 3)}°`}
        actions={
          <>
            <Link to={`/app/fields/${f.id}/edit`} className="btn-secondary no-underline"><Pencil className="h-4 w-4" /> {t("fields.edit")}</Link>
            <button type="button" className="btn-primary" onClick={() => setParams({ tab: "planner" })}><Scale className="h-4 w-4" /> {t("dashboard.open_planner")}</button>
          </>
        }
      />
      <Tabs tabs={TABS.map((k) => { const I = ICONS[k]; return { id: k, label: t(`tabs.${k}`), icon: <I className="h-4 w-4" /> }; })} value={tab} onChange={(k) => setParams({ tab: k })} />
      {TABS.filter((k) => visited.has(k)).map((k) => (
        <div key={k} hidden={k !== tab} role="tabpanel">{panel(k)}</div>
      ))}
    </div>
  );
}
