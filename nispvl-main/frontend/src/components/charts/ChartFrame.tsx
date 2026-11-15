import { Table2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

export const AXIS = { fontSize: 12, fill: "#5B6470" };
export const GRID = "#E3E6EA";
export const C = {
  precip: "#2a78d6",
  normal: "#5B6470",
  dry: "#c2410c",
  ndvi: "#2E6B47",
  band: "#C4DACB",
  warm: "#c2410c",
  cool: "#2a78d6",
  moisture: "#1c4f8f",
};

export interface TableSpec {
  columns: string[];
  rows: (string | number | null)[][];
}

/** Рамка графика: заголовок, подпись с источником, переключатель «таблица» (доступность и проверка чисел). */
export default function ChartFrame({ title, caption, legend, table, children, height = 260 }: {
  title: ReactNode;
  caption?: ReactNode;
  legend?: { color: string; label: string; dashed?: boolean; band?: boolean }[];
  table?: TableSpec;
  children: ReactNode;
  height?: number;
}) {
  const { t } = useTranslation();
  const [showTable, setShowTable] = useState(false);
  return (
    <figure className="panel">
      <div className="panel-head">
        <figcaption className="h3">{title}</figcaption>
        {table && (
          <button type="button" className="btn-ghost h-7 px-2 text-xs" aria-pressed={showTable} onClick={() => setShowTable((s) => !s)}>
            <Table2 className="h-3.5 w-3.5" /> {showTable ? t("charts.show_chart") : t("charts.show_table")}
          </button>
        )}
      </div>
      <div className="panel-body pt-3">
        {legend && legend.length > 1 && !showTable && (
          <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
            {legend.map((l) => (
              <li key={l.label} className="flex items-center gap-1.5">
                {l.band ? (
                  <span className="inline-block h-2.5 w-4 rounded-sm" style={{ background: l.color }} />
                ) : l.dashed ? (
                  <span className="inline-block w-4 border-t-2 border-dashed" style={{ borderColor: l.color }} />
                ) : (
                  <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: l.color }} />
                )}
                {l.label}
              </li>
            ))}
          </ul>
        )}
        {showTable && table ? (
          <div className="max-h-[320px] overflow-auto rounded border border-line">
            <table className="table">
              <thead className="sticky top-0 bg-white">
                <tr>{table.columns.map((c) => <th key={c}>{c}</th>)}</tr>
              </thead>
              <tbody>
                {table.rows.map((r, i) => (
                  <tr key={i}>
                    {r.map((v, j) => (
                      <td key={j} className={j > 0 ? "num" : ""}>{v ?? "—"}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div style={{ height }}>{children}</div>
        )}
        {caption && <p className="mt-2 text-xs leading-relaxed text-ink-muted">{caption}</p>}
      </div>
    </figure>
  );
}

export function TooltipBox({ title, rows }: { title: ReactNode; rows: { label: string; value: string; color?: string }[] }) {
  return (
    <div className="rounded-md border border-line bg-white px-3 py-2 text-xs shadow">
      <div className="mb-1 font-semibold text-ink">{title}</div>
      {rows.map((r) => (
        <div key={r.label} className="flex items-center justify-between gap-4 text-ink-2">
          <span className="flex items-center gap-1.5">
            {r.color && <span className="inline-block h-2 w-2 rounded-sm" style={{ background: r.color }} />}
            {r.label}
          </span>
          <span className="font-medium tabular-nums text-ink">{r.value}</span>
        </div>
      ))}
    </div>
  );
}
