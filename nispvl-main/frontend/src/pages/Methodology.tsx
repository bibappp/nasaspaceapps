import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import type { Evidence, Lang, RulesCatalog } from "../api/types";
import SourceStateBadge from "../components/common/SourceStateBadge";
import Spinner from "../components/common/Spinner";
import StatusBadge from "../components/common/StatusBadge";
import { tx } from "../lib/i18n-text";

function fmtValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return Object.entries(v as Record<string, unknown>).map(([k, x]) => `${k}: ${String(x)}`).join(", ");
  return String(v);
}

export default function Methodology() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const [data, setData] = useState<RulesCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [onlyAssumptions, setOnlyAssumptions] = useState(false);
  const [query, setQuery] = useState("");
  const [evidence, setEvidence] = useState<Evidence | "">("");

  useEffect(() => {
    api.rules().then(setData).catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <p className="card text-red-900">{t("app.network_error")}</p>;
  if (!data) return <Spinner label={t("app.loading")} />;

  const params = data.params.filter(
    (p) => (!onlyAssumptions || p.status === "assumption") && (!evidence || p.evidence === evidence) && (!query || `${p.path} ${p.note} ${p.source.name}`.toLowerCase().includes(query.toLowerCase())),
  );

  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <h1 className="h1">{t("methodology.title")}</h1>
        <p className="text-lg">{t("methodology.lead")}</p>
        <p className="font-semibold">{t("methodology.counts", data.counts)}</p>
        <p>{t("methodology.evidence_counts", data.counts.by_evidence)}</p>
        <p className="text-sm text-ink-2">{t("methodology.audit_link")}</p>
      </header>

      <section className="card space-y-2">
        <h2 className="h2">{t("methodology.model_title")}</h2>
        <ol className="list-decimal space-y-2 pl-5">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <li key={i}>{t(`methodology.model_${i}`)}</li>
          ))}
        </ol>
      </section>

      <section className="space-y-3">
        <h2 className="h2">{t("methodology.sources_title")}</h2>
        <div className="grid gap-4 lg:grid-cols-2">
          {data.data_sources.map((s) => (
            <article key={s.id} className="card space-y-2 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="h3">{s.title}</h3>
                <SourceStateBadge state={s.state} />
              </div>
              <p className="text-ink-2">{s.provider} · <a href={s.url} target="_blank" rel="noreferrer" className="break-all">{s.url}</a>{s.doi && <> · <a href={s.doi} target="_blank" rel="noreferrer">DOI</a></>}</p>
              <dl className="space-y-1.5">
                {(
                  [
                    ["used_for", s.used_for],
                    ["provenance", s.provenance],
                    ["resolution", s.spatial_resolution],
                    ["coverage", s.temporal_coverage],
                    ["access", s.access],
                    ["limitations", s.limitations],
                  ] as const
                ).map(([k, v]) => (
                  <div key={k}>
                    <dt className="font-semibold">{t(`methodology.${k}`)}</dt>
                    <dd>{tx(v, lang)}</dd>
                  </div>
                ))}
                <div>
                  <dt className="font-semibold">{t("methodology.checked")}</dt>
                  <dd className="text-ink-2">{s.checked}</dd>
                </div>
              </dl>
            </article>
          ))}
        </div>
      </section>

      <section className="card space-y-2">
        <h2 className="h2">{t("methodology.limits_title")}</h2>
        <ul className="list-disc space-y-1.5 pl-5">
          {[1, 2, 3, 4, 5, 6, 7].map((i) => (
            <li key={i}>{t(`methodology.limit_${i}`)}</li>
          ))}
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="h2">{t("methodology.rules_title")}</h2>
        <div className="flex flex-wrap gap-3">
          <div role="group" className="flex overflow-hidden rounded-xl border-2 border-field-700">
            <button type="button" className={`px-4 py-2 font-semibold ${!onlyAssumptions ? "bg-field-700 text-white" : ""}`} onClick={() => setOnlyAssumptions(false)}>{t("methodology.filter_all")}</button>
            <button type="button" className={`px-4 py-2 font-semibold ${onlyAssumptions ? "bg-field-700 text-white" : ""}`} onClick={() => setOnlyAssumptions(true)}>{t("methodology.filter_assumption")}</button>
          </div>
          <label className="flex items-center gap-2">
            <span className="text-sm font-semibold">{t("methodology.filter_evidence")}</span>
            <select className="input w-auto" value={evidence} onChange={(e) => setEvidence(e.target.value as Evidence | "")}>
              <option value="">{t("methodology.filter_evidence_all")}</option>
              {(["literature", "agronomist_review", "preliminary", "definition"] as const).map((e) => (
                <option key={e} value={e}>{t(`methodology.evidence.${e}`)}</option>
              ))}
            </select>
          </label>
          <input className="input max-w-xs" type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="wheat, ky, price…" />
        </div>
        <div className="card overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="bg-surface text-left">
              <tr>
                <th className="px-3 py-2">{t("methodology.col_rule")}</th>
                <th className="px-3 py-2">{t("methodology.col_value")}</th>
                <th className="px-3 py-2">{t("methodology.col_status")}</th>
                <th className="px-3 py-2">{t("methodology.evidence_title")}</th>
                <th className="px-3 py-2">{t("methodology.col_source")}</th>
                <th className="px-3 py-2">{t("methodology.col_note")}</th>
              </tr>
            </thead>
            <tbody>
              {params.map((p) => (
                <tr key={p.path} className="border-t align-top">
                  <td className="px-3 py-2"><code className="text-xs">{p.path}</code></td>
                  <td className="whitespace-nowrap px-3 py-2 font-semibold">{fmtValue(p.value)} {p.unit}</td>
                  <td className="px-3 py-2"><StatusBadge status={p.status} /></td>
                  <td className="px-3 py-2 text-xs">{t(`methodology.evidence.${p.evidence}`)}</td>
                  <td className="px-3 py-2">
                    {p.source.url.startsWith("http") ? <a href={p.source.url} target="_blank" rel="noreferrer">{p.source.name}</a> : <span>{p.source.name} <span className="text-amber-900">({p.source.url})</span></span>}
                  </td>
                  <td className="px-3 py-2 text-ink-2">{p.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {data.todo_sources.length > 0 && (
        <section className="card space-y-2">
          <h2 className="h3">{t("methodology.todo_title")}</h2>
          <ul className="list-disc pl-5 text-sm">
            {data.todo_sources.map((s) => (
              <li key={s.id}>{s.name}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
