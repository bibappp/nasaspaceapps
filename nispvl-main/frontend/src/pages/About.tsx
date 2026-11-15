import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { LandingFact } from "../api/types";

// Какие сноски стоят у каждого абзаца (ключи из content/sources.yaml)
const FOOTNOTES: Record<string, string[]> = {
  problem_1: ["wheat_share_87"],
  problem_2: ["fertility_minus_17", "degradation_75", "loss_2_4_bn"],
  problem_3: ["humus_50_100_years"],
  problem_4: ["harvest_2021", "emergency_2023"],
  state_text: ["wheat_minus_730k", "legumes_nitrogen", "prices_oilseeds", "prodcorp_forward"],
  why_3: ["nasa_free"],
};
const ORDER = Object.values(FOOTNOTES).flat();

function Refs({ k }: { k: string }) {
  return (
    <>
      {(FOOTNOTES[k] ?? []).map((id) => (
        <sup key={id} className="ml-0.5">
          <a href={`#fn-${id}`} className="font-semibold no-underline">[{ORDER.indexOf(id) + 1}]</a>
        </sup>
      ))}
    </>
  );
}

export default function About() {
  const { t } = useTranslation();
  const [facts, setFacts] = useState<Record<string, LandingFact>>({});
  useEffect(() => {
    api.landing().then((r) => setFacts(r.facts)).catch(() => setFacts({}));
  }, []);

  const P = ({ k }: { k: string }) => (
    <p>
      {t(`landing.${k}`)}
      <Refs k={k} />
    </p>
  );
  const List = ({ keys }: { keys: string[] }) => (
    <ul className="space-y-3">
      {keys.map((k) => (
        <li key={k} className="flex gap-3">
          <span aria-hidden className="mt-2 h-1.5 w-1.5 flex-none rounded-full bg-field-600" />
          <span>
            {t(`landing.${k}`)}
            <Refs k={k} />
          </span>
        </li>
      ))}
    </ul>
  );

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <section>
        <div className="eyebrow mb-1">{t("nav.about")}</div>
        <h1 className="h1 max-w-3xl">{t("landing.hero_title")}</h1>
        <p className="mt-2 max-w-3xl text-ink-2">{t("landing.hero_text")}</p>
      </section>

      <section className="card space-y-4">
        <h2 className="h2">{t("landing.problem_title")}</h2>
        <p className="font-semibold">{t("landing.problem_lead")}</p>
        <List keys={["problem_1", "problem_2", "problem_3", "problem_4"]} />
      </section>

      <div className="grid gap-6 md:grid-cols-2">
        <section className="card space-y-3">
          <h2 className="h2">{t("landing.state_title")}</h2>
          <P k="state_text" />
        </section>
        <section className="card space-y-3">
          <h2 className="h2">{t("landing.why_title")}</h2>
          <List keys={["why_1", "why_2", "why_3", "why_4"]} />
        </section>
      </div>

      <section className="card">
        <h2 className="h2">{t("landing.how_title")}</h2>
        <ol className="mt-4 grid gap-4 sm:grid-cols-3">
          {["how_1", "how_2", "how_3"].map((k, i) => (
            <li key={k} className="rounded-md border border-line bg-surface p-4">
              <div className="mb-2 flex h-7 w-7 items-center justify-center rounded bg-field-700 text-sm font-semibold text-white">{i + 1}</div>
              {t(`landing.${k}`)}
            </li>
          ))}
        </ol>
        <div className="mt-6 flex flex-col gap-3 sm:flex-row">
          <Link to="/register" className="btn-primary">{t("landing.cta_own")}</Link>
          <Link to="/demo" className="btn-secondary">{t("landing2.cta_demo")}</Link>
        </div>
      </section>

      <div className="grid gap-6 md:grid-cols-2">
        <section className="card space-y-3">
          <h2 className="h2">{t("landing.for_title")}</h2>
          <List keys={["for_1", "for_2", "for_3"]} />
        </section>
        <section className="card space-y-3">
          <h2 className="h2">{t("landing.change_title")}</h2>
          <List keys={["change_1", "change_2", "change_3"]} />
        </section>
      </div>

      <section className="card">
        <h2 className="h3">{t("landing.footnotes")}</h2>
        <ol className="mt-3 space-y-1.5 text-sm">
          {ORDER.map((id, i) => {
            const f = facts[id];
            const todo = !f || f.url.startsWith("TODO");
            return (
              <li key={id} id={`fn-${id}`} className="flex gap-2">
                <span className="font-semibold">[{i + 1}]</span>
                <span>
                  {f?.name ?? id}{" "}
                  {todo ? (
                    <span className="badge-amber">TODO: {t("landing.todo_link")}</span>
                  ) : (
                    <a href={f.url} target="_blank" rel="noreferrer" className="break-all">{f.url}</a>
                  )}
                </span>
              </li>
            );
          })}
        </ol>
      </section>
    </div>
  );
}
