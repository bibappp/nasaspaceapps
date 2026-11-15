import { ArrowRight, ExternalLink } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Lang } from "../api/types";
import SourceStateBadge, { DATA_SOURCE_STATES } from "../components/common/SourceStateBadge";
import { ErrorBox, Loading, Notice, PageHeader, SectionTitle } from "../components/ui/ui";
import { errorText, useAsync } from "../lib/async";
import { tx } from "../lib/i18n-text";

const DEMO_STEPS = ["select", "environment", "history", "compare", "priorities", "drought", "explain", "export"] as const;

export default function NasaData() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const rules = useAsync(() => api.rules(), []);
  const sources = rules.data?.data_sources;
  const connectedCount = sources?.filter((d) => d.state === "active").length ?? 0;
  const totalCount = sources?.length ?? 0;
  const needsEarthdata = sources?.some((d) => d.state === "needs_credentials") ?? false;

  return (
    <div className="space-y-10">
      <PageHeader eyebrow={t("nasa.eyebrow")} title={t("nasa.title")} subtitle={t("nasa.subtitle")} />

      <section className="grid gap-6 lg:grid-cols-3">
        {(["problem", "approach", "data"] as const).map((k) => (
          <div key={k} className="panel p-5">
            <h2 className="h3">{t(`nasa.pitch.${k}_title`)}</h2>
            <p className="mt-2 text-sm leading-relaxed text-ink-2">{t(`nasa.pitch.${k}`)}</p>
          </div>
        ))}
      </section>

      <section>
        <SectionTitle title={t("nasa.datasets_title")} hint={t("nasa.datasets_hint")} />
        {rules.error ? <ErrorBox message={errorText(rules.error, t)} onRetry={rules.reload} /> : null}
        {!rules.data && !rules.error && <Loading />}
        {sources && (
          <div className="space-y-4">
            <div className="space-y-3 rounded-xl border border-line bg-surface-sunken px-4 py-3">
              <p className="text-sm font-semibold text-ink" role="status">
                {t("nasa.connected_summary", { connected: connectedCount, total: totalCount })}
              </p>
              <p className="text-xs text-ink-muted">{t("nasa.states_legend")}</p>
              <div className="flex flex-wrap gap-2" role="list" aria-label={t("nasa.states_legend")}>
                {DATA_SOURCE_STATES.map((state) => (
                  <span key={state} role="listitem">
                    <SourceStateBadge state={state} />
                  </span>
                ))}
              </div>
            </div>
            <div className="space-y-3">
              {sources.map((d) => (
                <article key={d.id} className="panel">
                  <div className="panel-head">
                    <div className="min-w-0">
                      <h3 className="h3">{d.title}</h3>
                      <div className="text-xs text-ink-muted">{d.provider}</div>
                    </div>
                    <SourceStateBadge state={d.state} />
                  </div>
                  <div className="panel-body space-y-4">
                    {d.state !== "active" ? (
                      <div className="rounded-xl border border-line bg-surface-sunken px-4 py-3 text-sm">
                        <div className="eyebrow mb-1">{t("nasa.not_active_reason")}</div>
                        <p className="text-ink-2">{tx(d.limitations, lang)}</p>
                        {d.state === "needs_credentials" ? (
                          <p className="mt-2 text-ink-2">
                            <span className="font-semibold text-ink">{t("methodology.access")}: </span>
                            {tx(d.access, lang)}
                          </p>
                        ) : null}
                        {d.state === "offline" ? (
                          <p className="mt-2 text-ink-muted">{t("nasa.offline_note")}</p>
                        ) : null}
                      </div>
                    ) : null}
                    <div className="grid gap-4 text-sm sm:grid-cols-2 xl:grid-cols-3">
                      <div>
                        <div className="eyebrow mb-1">{t("methodology.used_for")}</div>
                        <p className="text-ink-2">{tx(d.used_for, lang)}</p>
                      </div>
                      <div>
                        <div className="eyebrow mb-1">{t("methodology.provenance")}</div>
                        <p className="text-ink-2">{tx(d.provenance, lang)}</p>
                      </div>
                      <div>
                        <div className="eyebrow mb-1">{t("methodology.resolution")}</div>
                        <p className="text-ink-2">{tx(d.spatial_resolution, lang)}</p>
                      </div>
                      <div>
                        <div className="eyebrow mb-1">{t("methodology.coverage")}</div>
                        <p className="text-ink-2">{tx(d.temporal_coverage, lang)}</p>
                      </div>
                      <div>
                        <div className="eyebrow mb-1">{t("methodology.access")}</div>
                        <p className="text-ink-2">{tx(d.access, lang)}</p>
                      </div>
                      <div className="sm:col-span-2 xl:col-span-3">
                        <div className="eyebrow mb-1">{t("methodology.limitations")}</div>
                        <p className="text-ink-2">{tx(d.limitations, lang)}</p>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-line pt-3 text-xs text-ink-muted">
                      <a href={d.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1">
                        {t("nasa.docs")} <ExternalLink className="h-3 w-3" />
                      </a>
                      {d.doi ? (
                        <a href={d.doi} target="_blank" rel="noreferrer">
                          DOI
                        </a>
                      ) : null}
                      <span>
                        {t("methodology.checked")}: {d.checked}
                      </span>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </div>
        )}
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="panel p-5">
          <h2 className="h3">{t("nasa.honest_title")}</h2>
          <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm text-ink-2">
            {[1, 2, 3, 4].map((i) => (
              <li key={i}>{t(`nasa.honest_${i}`)}</li>
            ))}
            {needsEarthdata ? <li>{t("nasa.honest_earthdata")}</li> : null}
          </ul>
        </div>
        <div className="panel p-5">
          <h2 className="h3">{t("nasa.demo_title")}</h2>
          <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-sm text-ink-2">
            {DEMO_STEPS.map((s) => (
              <li key={s}>{t(`nasa.demo.${s}`)}</li>
            ))}
          </ol>
          <Link to="/demo" className="btn-primary mt-4 no-underline">
            {t("landing2.cta_demo")} <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>
      <Notice>{t("nasa.affiliation")}</Notice>
    </div>
  );
}