"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import Shell from "@/components/Shell";
import EChart from "@/components/EChart";
import PageIntro from "@/components/PageIntro";
import EmptyState from "@/components/EmptyState";
import { useLang } from "@/lib/i18n";
import {
  getHandbook,
  getHandbookSummary,
  type Handbook,
  type QueryResult,
} from "@/lib/api";

function saveCsv(data: QueryResult, filename: string) {
  const esc = (v: unknown) => {
    const s = String(v ?? "");
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const text = [data.columns, ...data.rows].map((r) => r.map(esc).join(",")).join("\n");
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function fmt(v: unknown): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v ?? "—");
  if (n >= 1e7) return `${(n / 1e7).toFixed(2)} Cr`;
  if (n >= 1e5) return `${(n / 1e5).toFixed(1)} L`;
  return n.toLocaleString();
}

function StatTable({
  title,
  data,
  extraColumns,
  onCsv,
}: {
  title: string;
  data: QueryResult;
  extraColumns?: { header: string; cell: (row: (string | number | null)[]) => string }[];
  onCsv?: () => void;
}) {
  return (
    <div className="panel p-4 print-break">
      <div className="flex items-center justify-between mb-2">
        <div className="label-hud">{title}</div>
        {onCsv && (
          <button
            onClick={onCsv}
            className="value-mono text-[10px] px-2 py-0.5 border border-line text-dim hover:text-amber hover:border-amber print:hidden"
          >
            ⬇ CSV
          </button>
        )}
      </div>
      <table className="w-full text-xs value-mono">
        <thead>
          <tr className="text-left text-dim border-b border-line">
            {data.columns.map((c) => (
              <th key={c} className="py-1 pr-3 font-normal uppercase text-[10px] tracking-wider">
                {c.replace(/_/g, " ")}
              </th>
            ))}
            {extraColumns?.map((c) => (
              <th key={c.header} className="py-1 pr-3 font-normal uppercase text-[10px] tracking-wider text-right">
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r, i) => (
            <tr key={i} className="border-b border-line/40 text-text">
              {r.map((v, j) => (
                <td key={j} className="py-1 pr-3">
                  {j === 0 ? String(v ?? "—") : fmt(v)}
                </td>
              ))}
              {extraColumns?.map((c) => (
                <td key={c.header} className="py-1 pr-3 text-right text-dim">
                  {c.cell(r)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReportInner() {
  const { t, lang } = useLang();
  const params = useSearchParams();
  const ds = params.get("ds") ?? "";
  const [hb, setHb] = useState<Handbook | null>(null);
  const [error, setError] = useState("");
  const [summary, setSummary] = useState("");
  const [summaryState, setSummaryState] = useState<"idle" | "loading" | "error">("idle");

  useEffect(() => {
    if (!ds) return;
    getHandbook(ds).then(setHb).catch((e) => setError(String(e)));
  }, [ds]);

  useEffect(() => {
    if (!ds) return;
    setSummaryState("loading");
    getHandbookSummary(ds, lang)
      .then((r) => {
        setSummary(r.summary);
        setSummaryState("idle");
      })
      .catch(() => setSummaryState("error"));
  }, [ds, lang]);

  const trendOption = useMemo(() => {
    const rows = hb?.monthly_trend?.rows ?? [];
    return {
      grid: { left: 48, right: 16, top: 12, bottom: 24 },
      xAxis: {
        type: "category" as const,
        data: rows.map((r) => String(r[0] ?? "").slice(0, 7)),
        axisLine: { lineStyle: { color: "#1d2836" } },
      },
      yAxis: { type: "value" as const, splitLine: { lineStyle: { color: "#141c28" } } },
      series: [
        {
          type: "bar" as const,
          data: rows.map((r) => Number(r[1] ?? 0)),
          barWidth: "55%",
          itemStyle: { color: "#ffb000" },
        },
      ],
    };
  }, [hb]);

  if (!ds)
    return (
      <EmptyState
        title={t("common.noDatasetTitle", "No dataset open")}
        text={t("report.pickDataset", "Pick a dataset from the home screen.")}
        ctaHref="/"
        ctaLabel={t("common.goHome", "Open a dataset from Home to begin")}
      />
    );
  if (error) return <div className="text-signal value-mono text-sm">{error}</div>;
  if (!hb) return <div className="text-dim animate-pulse">{t("report.assembling", "Assembling handbook…")}</div>;

  const demo = hb.demographics ?? {};
  const hasDemo = Object.keys(demo).length > 0;
  const risk = hb.risk;

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      {/* toolbar — never printed */}
      <div className="flex items-center gap-3 print:hidden">
        <button
          onClick={() => window.print()}
          className="px-4 py-2 font-display uppercase tracking-widest text-sm border border-amber text-amber hover:bg-amber hover:text-ink transition-colors"
        >
          {t("report.print", "Print / Save PDF")}
        </button>
        <span className="label-hud">
          {t("report.toolbarTagline", "The static annual handbook, replaced: live, drillable, printable.")}
        </span>
      </div>

      {/* document header */}
      <div className="panel p-6 print-break">
        <div className="label-hud">Digital Crime Handbook · {hb.period === "full" ? "Full Range" : hb.period}</div>
        <div className="font-display text-2xl uppercase tracking-[0.1em] text-text mt-1">
          {hb.dataset}
        </div>
        <div className="value-mono text-[10px] text-dim mt-2">
          generated {new Date(hb.generated_at).toLocaleString("en-IN", { hour12: false })} ·
          domain pack: {hb.domain_pack} · every figure assembled live from the dataset manifest
        </div>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {hb.kpis.map((k) => (
          <div key={k.id} className="panel p-4 print-break">
            <div className="label-hud">{k.title}</div>
            <div className="value-mono text-2xl text-amber mt-2">{fmt(k.value)}</div>
          </div>
        ))}
      </div>

      {/* executive summary */}
      <div className="panel p-4 print-break">
        <div className="flex items-center justify-between mb-2">
          <div className="label-hud text-amber">{t("report.executiveSummary", "Executive Summary · AI-drafted")}</div>
        </div>
        {summaryState === "loading" && (
          <div className="text-dim text-xs animate-pulse">{t("report.summaryLoading", "Drafting summary…")}</div>
        )}
        {summaryState === "error" && (
          <div className="text-dim text-xs">
            {t("report.summaryError", "LLM endpoint unavailable — the handbook is fully usable without it.")}
          </div>
        )}
        {summaryState === "idle" && summary && (
          <div className="text-sm leading-relaxed text-text whitespace-pre-wrap">{summary}</div>
        )}
      </div>

      {/* monthly trend */}
      {hb.monthly_trend && (
        <div className="panel p-4 print-break">
          <div className="label-hud mb-2">{t("report.monthlyTrend", "Monthly Volume")}</div>
          <EChart option={trendOption} height={220} />
        </div>
      )}

      {/* emerging trends */}
      {hb.spikes && hb.spikes.length > 0 && (
        <div className="panel p-4 print-break">
          <div className="label-hud mb-2 text-signal">{t("report.emergingTrends", "Emerging Trends · statistical spikes vs own baseline")}</div>
          <div className="space-y-1">
            {hb.spikes.map((s, i) => (
              <div key={i} className="value-mono text-xs text-text">
                <span className="text-signal">▲</span>{" "}
                {Object.entries(s)
                  .filter(([k]) => !["z_score", "baseline_daily", "recent_daily", "pct_change", "window_days"].includes(k))
                  .map(([, v]) => v)
                  .join(" · ")}{" "}
                — <span className="text-signal">+{s.pct_change}%</span> (z={s.z_score},{" "}
                {s.baseline_daily}→{s.recent_daily}/day)
              </div>
            ))}
          </div>
        </div>
      )}

      {/* risk board */}
      {risk && risk.areas.length > 0 && (
        <div className="panel p-4 print-break">
          <div className="label-hud mb-2">
            {t("report.riskBoard", "Composite Risk Board · next 7 days")}
            {risk.demographics_used && ` ${t("report.riskBoardWithDemo", "· incl. socio-demographic exposure")}`}
          </div>
          <table className="w-full text-xs value-mono">
            <thead>
              <tr className="text-left text-dim border-b border-line">
                <th className="py-1 font-normal uppercase text-[10px] tracking-wider">{t("report.colArea", "Area")}</th>
                <th className="py-1 font-normal uppercase text-[10px] tracking-wider text-right">{t("report.colRisk", "Risk")}</th>
                <th className="py-1 font-normal uppercase text-[10px] tracking-wider text-right">{t("report.colDailyAvg", "Daily Avg")}</th>
                {risk.demographics_used && (
                  <th className="py-1 font-normal uppercase text-[10px] tracking-wider text-right">
                    {t("report.colPerLakh", "Per 1L Pop/Day")}
                  </th>
                )}
                <th className="py-1 font-normal uppercase text-[10px] tracking-wider text-right">{t("report.colForecast", "Forecast/Day")}</th>
              </tr>
            </thead>
            <tbody>
              {risk.areas.slice(0, 10).map((a) => (
                <tr key={a.area} className="border-b border-line/40 text-text">
                  <td className="py-1">{a.area}</td>
                  <td className={`py-1 text-right ${a.risk_score > 60 ? "text-signal" : a.risk_score > 35 ? "text-amber" : "text-teal"}`}>
                    {a.risk_score}
                  </td>
                  <td className="py-1 text-right">{a.recent_daily_avg}</td>
                  {risk.demographics_used && (
                    <td className="py-1 text-right text-dim">{a.per_lakh_daily ?? "—"}</td>
                  )}
                  <td className="py-1 text-right">{a.forecast_daily}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* by area, with per-capita when demographics exist */}
      {hb.by_area && (
        <StatTable
          title={`${t("report.byArea", `By ${hb.area_label ?? "Area"}`)}${hasDemo ? ` ${t("report.perCapita", "· incl. per-capita")}` : ""}`}
          data={hb.by_area}
          extraColumns={
            hasDemo
              ? [
                  {
                    header: t("report.per1LPop", "per 1L pop"),
                    cell: (r) => {
                      const d = demo[String(r[0])];
                      if (!d?.population) return "—";
                      return ((Number(r[1]) / d.population) * 100000).toFixed(0);
                    },
                  },
                ]
              : undefined
          }
          onCsv={() => saveCsv(hb.by_area!, `${ds}_by_area.csv`)}
        />
      )}

      {hb.by_category && (
        <StatTable
          title={t("report.byCategory", `By ${hb.category_label ?? "Category"}`)}
          data={hb.by_category}
          onCsv={() => saveCsv(hb.by_category!, `${ds}_by_category.csv`)}
        />
      )}
      {hb.by_status && (
        <StatTable
          title={t("report.byStatus", "Case Status")}
          data={hb.by_status}
          onCsv={() => saveCsv(hb.by_status!, `${ds}_by_status.csv`)}
        />
      )}

      {/* network highlights */}
      {hb.network && (
        <div className="panel p-4 print-break">
          <div className="label-hud mb-2">{t("report.networkHighlights", "Network Intelligence Highlights")}</div>
          <div className="value-mono text-xs text-dim mb-2">
            {hb.network.nodes.toLocaleString()} entities · {hb.network.edges.toLocaleString()} links
          </div>
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <div className="label-hud text-[9px] mb-1">{t("report.networkRepeatOffenders", "Top Repeat Offenders")}</div>
              {hb.network.repeat_offenders.map((r) => (
                <div key={r.node} className="flex justify-between value-mono text-xs text-text py-0.5">
                  <span className="truncate">{r.label}</span>
                  <span className="text-amber ml-2 shrink-0">{r.case_count} cases</span>
                </div>
              ))}
            </div>
            <div>
              <div className="label-hud text-[9px] mb-1">{t("report.networkKeyPlayers", "Key Players · centrality")}</div>
              {hb.network.key_players.map((k) => (
                <div key={k.node} className="flex justify-between value-mono text-xs text-text py-0.5">
                  <span className="truncate">{k.label}</span>
                  <span className="text-teal ml-2 shrink-0">{k.connections}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="label-hud pb-6">
        {t("report.footer", "DRISHTI digital handbook — replaces the static annual crime handbook with a live, manifest-driven document.")}
      </div>
    </div>
  );
}

export default function ReportPage() {
  const { t } = useLang();
  return (
    <Shell title={t("report.title", "Handbook")}>
      <PageIntro
        id="report"
        text={t(
          "report.intro",
          "A printable digital handbook of this dataset — KPIs, trends, risk and network highlights. Use your browser's print for PDF."
        )}
      />
      <Suspense>
        <ReportInner />
      </Suspense>
    </Shell>
  );
}
