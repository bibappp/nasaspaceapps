import { ArrowRight, BarChart3, CloudSun, FileDown, Map as MapIcon, Scale, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import TelegramBotCard from "../components/common/TelegramBotCard";
import PublicLayout from "../components/layout/PublicLayout";

const FEATURES = [
  { key: "fields", icon: MapIcon },
  { key: "monitoring", icon: BarChart3 },
  { key: "risk", icon: ShieldAlert },
  { key: "planner", icon: Scale },
  { key: "drought", icon: CloudSun },
  { key: "reports", icon: FileDown },
];
const DATASETS = ["power", "modis", "smap", "soilgrids"] as const;
const SHOTS = ["planner", "monitoring", "dashboard"] as const;

/** Снимок настоящего интерфейса (делается скриптом scripts/screenshots.cjs на демо-данных). */
function Shot({ name, className = "" }: { name: string; className?: string }) {
  const { t, i18n } = useTranslation();
  const [ok, setOk] = useState(true);
  if (!ok) return null;
  const lang = i18n.language === "en" ? "en" : i18n.language === "kk" ? "kk" : "ru";
  return (
    <img
      src={`/preview/${name}-${lang}.jpg`}
      alt={t(`landing2.shot_${name}`)}
      className={`w-full rounded-lg border border-line bg-white shadow-lg ${className}`}
      loading="lazy"
      onError={() => setOk(false)}
    />
  );
}

export default function Landing() {
  const { t } = useTranslation();
  return (
    <PublicLayout wide>
      <section className="border-b border-line bg-white">
        <div className="mx-auto grid max-w-7xl items-center gap-10 px-4 py-14 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] lg:py-20">
          <div>
            <div className="eyebrow text-field-700">{t("landing2.eyebrow")}</div>
            <h1 className="mt-3 text-3xl font-semibold leading-tight tracking-tight text-ink sm:text-4xl">{t("landing2.title")}</h1>
            <p className="mt-4 max-w-xl text-base leading-relaxed text-ink-2">{t("landing2.lead")}</p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Link to="/register" className="btn-primary btn-lg no-underline">{t("landing2.cta_signup")}</Link>
              <Link to="/demo" className="btn-secondary btn-lg no-underline">{t("landing2.cta_demo")} <ArrowRight className="h-4 w-4" /></Link>
            </div>
            <p className="mt-3 text-xs text-ink-muted">{t("landing2.demo_note")}</p>
          </div>
          <Shot name="planner" />
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-14 sm:px-6">
        <h2 className="h2">{t("landing2.offers_title")}</h2>
        <p className="mt-1 max-w-2xl text-sm text-ink-muted">{t("landing2.offers_lead")}</p>
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ key, icon: Icon }) => (
            <div key={key} className="panel p-5">
              <Icon className="h-5 w-5 text-field-700" />
              <h3 className="h3 mt-3">{t(`landing2.f_${key}`)}</h3>
              <p className="mt-1 text-sm leading-relaxed text-ink-muted">{t(`landing2.f_${key}_text`)}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="border-y border-line bg-surface">
        <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6">
          <TelegramBotCard />
        </div>
      </section>

      <section className="border-y border-line bg-white">
        <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6">
          <h2 className="h2">{t("landing2.how_title")}</h2>
          <ol className="mt-6 grid gap-6 md:grid-cols-4">
            {[1, 2, 3, 4].map((i) => (
              <li key={i}>
                <div className="flex h-7 w-7 items-center justify-center rounded bg-field-700 text-sm font-semibold text-white">{i}</div>
                <h3 className="h3 mt-3">{t(`landing2.how_${i}`)}</h3>
                <p className="mt-1 text-sm leading-relaxed text-ink-muted">{t(`landing2.how_${i}_text`)}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-14 sm:px-6">
        <h2 className="h2">{t("landing2.preview_title")}</h2>
        <p className="mt-1 max-w-2xl text-sm text-ink-muted">{t("landing2.preview_lead")}</p>
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          {SHOTS.slice(1).map((s) => (
            <figure key={s}>
              <Shot name={s} />
              <figcaption className="mt-2 text-sm text-ink-muted">{t(`landing2.shot_${s}`)}</figcaption>
            </figure>
          ))}
        </div>
      </section>

      <section className="border-t border-line bg-white">
        <div className="mx-auto grid max-w-7xl gap-8 px-4 py-14 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
          <div>
            <h2 className="h2">{t("landing2.nasa_title")}</h2>
            <p className="mt-2 text-sm leading-relaxed text-ink-2">{t("landing2.nasa_lead")}</p>
            <Link to="/nasa" className="mt-4 inline-flex items-center gap-1 text-sm font-medium">{t("landing2.nasa_more")} <ArrowRight className="h-4 w-4" /></Link>
          </div>
          <dl className="grid gap-4 sm:grid-cols-2">
            {DATASETS.map((d) => (
              <div key={d} className="rounded-md border border-line p-4">
                <dt className="text-sm font-semibold text-ink">{t(`landing2.ds_${d}`)}</dt>
                <dd className="mt-1 text-xs leading-relaxed text-ink-muted">{t(`landing2.ds_${d}_text`)}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <section className="bg-field-800">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-6 px-4 py-10 sm:px-6">
          <div>
            <h2 className="text-lg font-semibold text-white">{t("landing2.final_title")}</h2>
            <p className="mt-1 text-sm text-white/75">{t("landing2.final_text")}</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link to="/register" className="btn btn-lg bg-white text-field-800 no-underline hover:bg-field-50">{t("landing2.cta_signup")}</Link>
            <Link to="/login" className="btn btn-lg border border-white/40 text-white no-underline hover:bg-white/10">{t("auth.login")}</Link>
          </div>
        </div>
      </section>
    </PublicLayout>
  );
}
