"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useLang } from "@/lib/i18n";
import Shell from "@/components/Shell";
import EChart from "@/components/EChart";
import PageIntro from "@/components/PageIntro";
import Freshness from "@/components/Freshness";
import EmptyState from "@/components/EmptyState";
import {
  downloadCsv,
  getManifest,
  getRisk,
  getSpikes,
  primaryTable,
  runAgent,
  runQuery,
  type ChartSpec,
  type KpiSpec,
  type Manifest,
  type QueryRequest,
  type QueryResult,
  type RiskArea,
} from "@/lib/api";

type Filters = Record<string, unknown>;

function KpiCard({
  ds,
  kpi,
  filters,
  onResult,
  refreshKey = 0,
  forceRefreshAt = 0,
}: {
  ds: string;
  kpi: KpiSpec;
  filters: Filters;
  onResult?: (r: QueryResult) => void;
  refreshKey?: number;
  forceRefreshAt?: number;
}) {
  const [value, setValue] = useState<string>("—");
  useEffect(() => {
    runQuery(
      ds,
      {
        table: kpi.table,
        measures: [{ agg: kpi.agg, column: kpi.column ?? undefined, alias: "v" }],
        filters: { ...kpi.filters, ...filters },
      },
      refreshKey > 0 && refreshKey === forceRefreshAt
    )
      .then((r) => {
        onResult?.(r);
        const v = Number(r.rows[0]?.[0] ?? 0);
        setValue(
          v >= 1e7 ? `${(v / 1e7).toFixed(2)} Cr` : v >= 1e5 ? `${(v / 1e5).toFixed(1)} L` : v.toLocaleString()
        );
      })
      .catch(() => setValue("—"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ds, kpi, filters, refreshKey, forceRefreshAt]);
  return (
    <div className="panel p-4 sweep-in">
      <div className="label-hud">{kpi.title}</div>
      <div className="value-mono text-3xl text-amber mt-2">{value}</div>
    </div>
  );
}

function chartQuery(spec: ChartSpec, filters: Filters, forExport = false): QueryRequest {
  const isTime = spec.kind === "timeseries";
  return {
    table: spec.table,
    ...(isTime
      ? { time_dimension: spec.dimension ?? undefined, time_grain: spec.time_grain ?? "week" }
      : { dimensions: spec.dimension ? [spec.dimension] : [] }),
    measures: [{ agg: spec.measure_agg, column: spec.measure_column ?? undefined, alias: "v" }],
    filters,
    ...(isTime ? {} : { order_by: "v", desc: true, limit: forExport ? 1000 : 12 }),
  };
}

function ChartPanel({
  ds,
  spec,
  filters,
  onSelect,
  refreshKey = 0,
  forceRefreshAt = 0,
}: {
  ds: string;
  spec: ChartSpec;
  filters: Filters;
  onSelect?: (dim: string, value: string) => void;
  refreshKey?: number;
  forceRefreshAt?: number;
}) {
  const [data, setData] = useState<{ name: string; value: number }[]>([]);
  useEffect(() => {
    runQuery(ds, chartQuery(spec, filters), refreshKey > 0 && refreshKey === forceRefreshAt)
      .then((r) =>
        setData(r.rows.map((row) => ({ name: String(row[0] ?? "?"), value: Number(row[1] ?? 0) })))
      )
      .catch(() => setData([]));
  }, [ds, spec, filters, refreshKey, forceRefreshAt]);

  const option = useMemo(() => {
    if (spec.kind === "timeseries") {
      return {
        xAxis: {
          type: "category" as const,
          data: data.map((d) => d.name.slice(0, 10)),
          axisLine: { lineStyle: { color: "#1d2836" } },
        },
        yAxis: { type: "value" as const, splitLine: { lineStyle: { color: "#141c28" } } },
        series: [
          {
            type: "line" as const,
            data: data.map((d) => d.value),
            symbol: "none",
            lineStyle: { width: 1.5 },
            areaStyle: { opacity: 0.12 },
          },
        ],
      };
    }
    return {
      grid: { left: 110, right: 16, top: 8, bottom: 24 },
      xAxis: { type: "value" as const, splitLine: { lineStyle: { color: "#141c28" } } },
      yAxis: {
        type: "category" as const,
        data: data.map((d) => (d.name.length > 18 ? d.name.slice(0, 17) + "…" : d.name)).reverse(),
        axisLine: { lineStyle: { color: "#1d2836" } },
      },
      series: [
        {
          type: "bar" as const,
          data: data.map((d) => d.value).reverse(),
          barWidth: 10,
          itemStyle: { color: "#ffb000" },
        },
      ],
    };
  }, [spec.kind, data]);

  return (
    <div className="panel p-4 sweep-in">
      <div className="flex items-center justify-between mb-2">
        <div className="label-hud">{spec.title}</div>
        <button
          onClick={() => downloadCsv(ds, chartQuery(spec, filters, true), `${spec.id}.csv`)}
          title="Export this view as CSV"
          className="value-mono text-[10px] px-2 py-0.5 border border-line text-dim hover:text-amber hover:border-amber"
        >
          ⬇ CSV
        </button>
      </div>
      <EChart
        option={option}
        height={250}
        onClick={
          spec.kind !== "timeseries" && spec.dimension && onSelect
            ? (p) => {
                const idx = data.length - 1 - (p.dataIndex ?? 0);
                if (data[idx]) onSelect(spec.dimension!, data[idx].name);
              }
            : undefined
        }
      />
    </div>
  );
}

function AskBar({ ds }: { ds: string }) {
  const { t, lang } = useLang();
  const [q, setQ] = useState("");
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState("");
  const [toolCount, setToolCount] = useState(0);
  const [error, setError] = useState("");

  const ask = async () => {
    if (!q.trim() || asking) return;
    setAsking(true);
    setAnswer("");
    setError("");
    try {
      const r = await runAgent(ds, "analyst", q, lang);
      setAnswer(r.report);
      setToolCount(r.steps.length);
    } catch {
      setError("LLM endpoint unavailable — agents need LLM_BASE_URL configured on the API.");
    } finally {
      setAsking(false);
    }
  };

  return (
    <div className="panel p-3 space-y-2">
      <div className="flex items-center gap-2">
        <span className="label-hud text-amber shrink-0">{t("dashboard.askLabel", "Ask DRISHTI")}</span>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask()}
          placeholder={t("dashboard.askPlaceholder", "ask the data anything — e.g. which district has the biggest cybercrime rise?")}
          className="flex-1 bg-ink-3 border border-line px-3 py-1.5 text-xs value-mono outline-none focus:border-amber"
        />
        <button
          onClick={ask}
          disabled={asking}
          className="px-4 py-1.5 text-xs font-display uppercase tracking-wider border border-amber text-amber hover:bg-amber hover:text-ink transition-colors disabled:opacity-40"
        >
          {asking ? t("dashboard.askAnalyzing", "Analyzing…") : t("dashboard.askRun", "Ask")}
        </button>
      </div>
      {asking && (
        <div className="value-mono text-xs text-amber animate-pulse">
          {t("dashboard.askThinking", "agent planning → querying the dataset → writing answer…")}
        </div>
      )}
      {error && <div className="value-mono text-xs text-signal">{error}</div>}
      {answer && (
        <div className="border-l-2 border-amber pl-3 py-1 sweep-in">
          <div className="text-sm leading-relaxed whitespace-pre-wrap text-text">{answer}</div>
          <a
            href={`/agents/?ds=${ds}`}
            className="value-mono text-[10px] text-dim hover:text-amber"
          >
            grounded in {toolCount} live tool call{toolCount === 1 ? "" : "s"} → full trace in Agents
          </a>
        </div>
      )}
    </div>
  );
}

function AlertsTicker({ ds }: { ds: string }) {
  const { t } = useLang();
  const [alerts, setAlerts] = useState<Record<string, string | number>[]>([]);
  useEffect(() => {
    getSpikes(ds).then((r) => setAlerts(r.alerts)).catch(() => setAlerts([]));
  }, [ds]);
  if (!alerts.length) return null;
  return (
    <div className="panel p-3 flex items-center gap-4 overflow-x-auto">
      <span className="flex items-center gap-2 shrink-0">
        <span className="w-2.5 h-2.5 rounded-full bg-signal pulse-red" />
        <span className="label-hud text-signal">{t("dashboard.emergingAlerts", "Emerging Trend Alerts")}</span>
      </span>
      {alerts.slice(0, 4).map((a, i) => (
        <span key={i} className="value-mono text-xs text-text shrink-0">
          {String(a.district ?? a.area ?? "")} · {String(a.crime_group ?? a.category ?? "")} ·{" "}
          <span className="text-signal">+{a.pct_change}%</span> vs baseline (z={a.z_score})
        </span>
      ))}
    </div>
  );
}

function RiskBoard({ ds }: { ds: string }) {
  const { t } = useLang();
  const [areas, setAreas] = useState<RiskArea[]>([]);
  const [demoUsed, setDemoUsed] = useState(false);
  const [perCapita, setPerCapita] = useState(false);
  useEffect(() => {
    getRisk(ds)
      .then((r) => {
        setAreas(r.areas);
        setDemoUsed(Boolean(r.demographics_used));
      })
      .catch(() => setAreas([]));
  }, [ds]);
  if (!areas.length) return null;

  const shown = perCapita
    ? [...areas].sort((a, b) => (b.per_lakh_daily ?? 0) - (a.per_lakh_daily ?? 0)).slice(0, 8)
    : areas.slice(0, 8);
  const maxPc = Math.max(...shown.map((a) => a.per_lakh_daily ?? 0), 0.001);

  return (
    <div className="panel p-4 sweep-in">
      <div className="flex items-center justify-between mb-3">
        <div className="label-hud">
          {t("dashboard.riskBoard", "Predictive Risk Board · next 7 days")}
          {demoUsed && t("dashboard.demoFactored", " · socio-demographic exposure factored in")}
        </div>
        {demoUsed && (
          <div className="flex gap-1">
            {[
              { v: false, label: t("dashboard.toggleComposite", "Composite") },
              { v: true, label: t("dashboard.togglePerLakh", "Per 1L Pop") },
            ].map((o) => (
              <button
                key={o.label}
                onClick={() => setPerCapita(o.v)}
                className={`value-mono text-[10px] px-2 py-0.5 border ${
                  perCapita === o.v
                    ? "border-amber text-amber"
                    : "border-line text-dim hover:text-text"
                }`}
              >
                {o.label}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="space-y-2">
        {shown.map((a) => {
          const width = perCapita ? ((a.per_lakh_daily ?? 0) / maxPc) * 100 : a.risk_score;
          const val = perCapita ? (a.per_lakh_daily ?? 0).toFixed(2) : a.risk_score;
          return (
            <div key={a.area} className="flex items-center gap-3">
              <span className="value-mono text-xs w-36 truncate text-text">{a.area}</span>
              <div className="flex-1 h-2 bg-ink-3">
                <div
                  className={`h-2 ${width > 60 ? "bg-signal" : width > 35 ? "bg-amber" : "bg-teal"}`}
                  style={{ width: `${width}%` }}
                />
              </div>
              <span className="value-mono text-xs w-14 text-right text-dim">{val}</span>
              <span className="value-mono text-[10px] w-24 text-right text-dim">
                {perCapita
                  ? `pop ${((a.population ?? 0) / 1e5).toFixed(1)} L`
                  : `~${a.forecast_daily}/day`}
              </span>
            </div>
          );
        })}
      </div>
      {perCapita && (
        <div className="label-hud mt-2">
          {t("dashboard.perCapitaNote", "cases per day per 1 lakh residents — census demographics joined automatically from the dataset")}
        </div>
      )}
    </div>
  );
}

function DashboardInner() {
  const { t } = useLang();
  const params = useSearchParams();
  const ds = params.get("ds") ?? "";
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [filters, setFilters] = useState<Filters>({});
  const [error, setError] = useState("");
  const [firstResult, setFirstResult] = useState<QueryResult | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  // Which refreshKey value corresponds to a manual ⟳ click (vs. a filters
  // change, which also happens to touch these panels' effects but must not
  // force a cache-bypassing refetch). Set just before bumping refreshKey so
  // the child effects that fire on the resulting re-render see a match.
  const forceRefreshAtRef = useRef(0);

  useEffect(() => {
    if (!ds) return;
    getManifest(ds).then(setManifest).catch((e) => setError(String(e)));
  }, [ds]);

  const refresh = () => {
    setFirstResult(null);
    setRefreshKey((k) => {
      forceRefreshAtRef.current = k + 1;
      return k + 1;
    });
  };

  if (!ds)
    return (
      <EmptyState
        title={t("common.noDatasetTitle", "No dataset open")}
        text={t("dashboard.noDataset", "Pick a dataset from the home screen.")}
        ctaHref="/"
        ctaLabel={t("common.goHome", "Open a dataset from Home to begin")}
      />
    );
  if (error) return <div className="text-signal value-mono text-sm">{error}</div>;
  if (!manifest) return <div className="text-dim animate-pulse">{t("dashboard.loadingManifest", "Loading manifest…")}</div>;

  const pt = primaryTable(manifest);
  const drillCharts = manifest.charts.filter(
    (c) => c.kind === "bar" || c.kind === "timeseries"
  );

  return (
    <div className="space-y-4">
      {firstResult?.computed_at && (
        <div className="flex justify-end -mb-2">
          <Freshness computedAt={firstResult.computed_at} cached={firstResult.cached} onRefresh={refresh} />
        </div>
      )}
      <AskBar ds={ds} />
      <AlertsTicker ds={ds} />

      {Object.keys(filters).length > 0 && (
        <div className="flex items-center gap-2">
          <span className="label-hud">{t("dashboard.drillDown", "Drill-down:")}</span>
          {Object.entries(filters).map(([k, v]) => (
            <button
              key={k}
              onClick={() =>
                setFilters((f) => {
                  const n = { ...f };
                  delete n[k];
                  return n;
                })
              }
              className="value-mono text-xs px-2 py-1 border border-amber text-amber hover:bg-ink-3"
            >
              {k}={String(v)} ✕
            </button>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {manifest.kpis.slice(0, 4).map((k, i) => (
          <KpiCard
            key={k.id}
            ds={ds}
            kpi={k}
            filters={filters}
            refreshKey={refreshKey}
            forceRefreshAt={forceRefreshAtRef.current}
            onResult={i === 0 ? setFirstResult : undefined}
          />
        ))}
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        {drillCharts.map((c) => (
          <ChartPanel
            key={c.id}
            ds={ds}
            spec={c}
            filters={filters}
            refreshKey={refreshKey}
            forceRefreshAt={forceRefreshAtRef.current}
            onSelect={(dim, value) => {
              if (dim.includes("(")) return; // derived dims (hour()) aren't filterable
              setFilters((f) => ({ ...f, [dim]: value }));
            }}
          />
        ))}
      </div>

      <RiskBoard ds={ds} />

      <div className="label-hud">
        {pt.row_count.toLocaleString()} records · pack: {manifest.domain_pack} · manifest-driven —
        nothing on this screen is hardcoded to this dataset
      </div>
    </div>
  );
}

function DashboardPageInner() {
  const { t } = useLang();
  return (
    <Shell title={t("dashboard.title", "Overview")}>
      <PageIntro
        id="dashboard"
        text={t(
          "dashboard.intro",
          "Auto-built KPIs and charts. Click any chart segment to drill into the records behind it."
        )}
      />
      <Suspense>
        <DashboardInner />
      </Suspense>
    </Shell>
  );
}

export default function DashboardPage() {
  return (
    <Suspense>
      <DashboardPageInner />
    </Suspense>
  );
}
