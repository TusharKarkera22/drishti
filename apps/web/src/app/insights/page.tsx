"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import Shell from "@/components/Shell";
import EChart from "@/components/EChart";
import PageIntro from "@/components/PageIntro";
import Freshness from "@/components/Freshness";
import EmptyState from "@/components/EmptyState";
import {
  getInsights,
  getInsightsBrief,
  getCorrelation,
  getPredictions,
  type InsightsResponse,
  type InsightFinding,
  type InsightType,
  type CorrelationResult,
  type PredictionResult,
} from "@/lib/api";
import { useLang } from "@/lib/i18n";
import {
  Sparkles,
  TrendingUp,
  Activity,
  Share2,
  ScanSearch,
  FileWarning,
  ArrowRight,
  ShieldAlert,
  Loader2,
  Gauge,
  Clock,
  Scale,
  Flame,
  Fingerprint,
  Crosshair,
  HourglassIcon,
  type LucideIcon,
} from "lucide-react";

function useTypeMeta() {
  const { t } = useLang();
  const TYPE_META: Record<InsightType, { Icon: LucideIcon; color: string; border: string; tag: string }> = {
    spike:             { Icon: TrendingUp,  color: "text-signal", border: "border-signal/50", tag: t("insights.tagSpike", "Spike") },
    rising_risk:       { Icon: Activity,    color: "text-amber",  border: "border-amber/50",  tag: t("insights.tagRisingRisk", "Rising risk") },
    network_hub:       { Icon: Share2,      color: "text-teal",   border: "border-teal/50",   tag: t("insights.tagNetwork", "Network") },
    anomaly:           { Icon: ScanSearch,  color: "text-amber",  border: "border-amber/40",  tag: t("insights.tagAnomaly", "Anomaly") },
    data_gap:          { Icon: FileWarning, color: "text-dim",    border: "border-line",      tag: t("insights.tagDataGap", "Data gap") },
    spatiotemporal:    { Icon: Clock,       color: "text-teal",   border: "border-teal/50",   tag: t("insights.tagSpatiotemporal", "Time-space") },
    socio_correlation: { Icon: Scale,       color: "text-amber",  border: "border-amber/50",  tag: t("insights.tagSocioEcon", "Socio-economic") },
    emerging_typology: { Icon: Flame,       color: "text-signal", border: "border-signal/50", tag: t("insights.tagEmerging", "Emerging") },
    mo_signature:      { Icon: Fingerprint, color: "text-teal",   border: "border-teal/40",   tag: t("insights.tagMO", "MO signature") },
    predicted_undetected: { Icon: Crosshair,    color: "text-signal", border: "border-signal/50", tag: t("insights.tagPredUndetected", "Detection risk") },
    predicted_stall:      { Icon: HourglassIcon, color: "text-amber",  border: "border-amber/50",  tag: t("insights.tagPredStall", "Stall risk") },
  };
  return TYPE_META;
}

function drillHref(ds: string, f: InsightFinding): string {
  const qs = new URLSearchParams(f.drill.params || {}).toString();
  return `/${f.drill.surface}/?ds=${ds}${qs ? `&${qs}` : ""}`;
}

function SeverityBar({ value }: { value: number }) {
  const color = value >= 75 ? "bg-signal" : value >= 50 ? "bg-amber" : "bg-teal";
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-ink-3 overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${value}%` }} />
      </div>
      <span className="value-mono text-[10px] text-dim">{value}</span>
    </div>
  );
}

function FindingCard({ ds, f, index }: { ds: string; f: InsightFinding; index: number }) {
  const { t } = useLang();
  const typeMeta = useTypeMeta();
  // Fallback guard: an unknown finding type (e.g. a new backend type not yet in
  // TYPE_META) must never crash the whole Insights page — render a neutral chip.
  const meta = typeMeta[f.type] ?? { Icon: Gauge, color: "text-dim", border: "border-line", tag: String(f.type) };
  return (
    <div
      className={`panel p-4 border-l-2 ${meta.border} sweep-in`}
      style={{ animationDelay: `${index * 0.06}s` }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <meta.Icon size={18} className={`${meta.color} shrink-0 mt-0.5`} />
          <div className="min-w-0">
            <div className="label-hud mb-1">{meta.tag}</div>
            <div className="text-sm text-text leading-snug">{f.title}</div>
          </div>
        </div>
        <SeverityBar value={f.severity} />
      </div>
      <div className="mt-3 pl-7 flex items-center justify-between gap-3">
        <div className="flex items-start gap-1.5 text-dim">
          <ArrowRight size={13} className="text-teal shrink-0 mt-0.5" />
          <span className="value-mono text-[11px] leading-snug">{f.suggested_action}</span>
        </div>
        <Link
          href={drillHref(ds, f)}
          className="value-mono text-[11px] text-amber hover:text-amber-dim whitespace-nowrap"
        >
          {t("insights.view", "View")} →
        </Link>
      </div>
    </div>
  );
}

function useCompMeta() {
  const { t } = useLang();
  return [
    { key: "volume"   as const, label: t("insights.compVolume",   "Volume"),   color: "bg-amber"  },
    { key: "trend"    as const, label: t("insights.compTrend",    "Trend"),    color: "bg-teal"   },
    { key: "spike"    as const, label: t("insights.compSpike",    "Spike"),    color: "bg-signal" },
    { key: "exposure" as const, label: t("insights.compExposure", "Exposure"), color: "bg-ok"     },
  ];
}

function ForecastPanel({ data }: { data: InsightsResponse["forecast"] }) {
  const { t } = useLang();
  const compMeta = useCompMeta();
  const areas = data.areas ?? [];
  if (!areas.length) return null;
  const conf = data.confidence ?? "low";
  const confColor = conf === "high" ? "text-ok" : conf === "medium" ? "text-amber" : "text-dim";
  const confLabel =
    conf === "high"
      ? t("insights.confidenceHigh", "high")
      : conf === "medium"
      ? t("insights.confidenceMedium", "medium")
      : t("insights.confidenceLow", "low");
  return (
    <div className="panel p-5 sweep-in">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Gauge size={16} className="text-amber" />
          <span className="font-display text-sm uppercase tracking-widest text-text">
            {t("insights.sevenDayOutlook", "7-Day Outlook")}
          </span>
        </div>
        <span className={`value-mono text-[10px] ${confColor}`}>
          {t("insights.confidence", "confidence")}: {confLabel}
        </span>
      </div>
      <div className="space-y-4">
        {areas.slice(0, 3).map((a) => {
          const comp = a.components;
          const total = comp ? comp.volume + comp.trend + comp.spike + comp.exposure || 1 : 1;
          return (
            <div key={a.area}>
              <div className="flex items-baseline justify-between mb-1.5">
                <span className="text-sm text-text">{a.area}</span>
                <span className="value-mono text-[11px] text-dim">
                  {t("insights.risk", "risk")} <span className="text-amber">{a.risk_score}</span> · ~
                  {a.forecast_daily?.toFixed(0)}/day
                </span>
              </div>
              {comp && (
                <>
                  <div className="flex h-2 w-full overflow-hidden bg-ink-3">
                    {compMeta.map((c) => (
                      <div
                        key={c.key}
                        className={c.color}
                        style={{ width: `${(comp[c.key] / total) * 100}%` }}
                        title={`${c.label}: ${(comp[c.key] * 100).toFixed(0)}%`}
                      />
                    ))}
                  </div>
                  <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1.5">
                    {compMeta.map((c) => (
                      <span key={c.key} className="flex items-center gap-1 value-mono text-[9px] text-dim">
                        <span className={`inline-block w-2 h-2 ${c.color}`} /> {c.label}
                      </span>
                    ))}
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Credibility({ data }: { data: InsightsResponse }) {
  const { t } = useLang();
  const bt = data.backtest;
  return (
    <div className="panel p-4 flex items-start gap-3 sweep-in">
      <ShieldAlert size={16} className="text-teal shrink-0 mt-0.5" />
      <div>
        <div className="label-hud mb-1">{t("insights.credibilityCheck", "Credibility check")}</div>
        {bt.available ? (
          <p className="value-mono text-[11px] text-dim leading-relaxed">
            {t("insights.credibilityOver", "Over the last")} {bt.folds}{" "}
            {t("insights.credibilityWeeks", "week(s), the top-")}{bt.k}{" "}
            {t("insights.credibilityFlaggedAreas", "flagged areas captured")}{" "}
            <span className="text-amber">{Math.round((bt.capture_rate ?? 0) * 100)}%</span>{" "}
            {t("insights.credibilityCaptured", "of actual incidents in the following")}{" "}
            {bt.window_days} {t("insights.credibilityDays", "days (retrospective, on this dataset's own history).")}
          </p>
        ) : (
          <p className="value-mono text-[11px] text-dim leading-relaxed">
            {t("insights.credibilityNotEnough", "Not enough history for a reliable backtest")} ({bt.reason ?? "insufficient data"}).
          </p>
        )}
      </div>
    </div>
  );
}

function CorrelationScatter({ ds }: { ds: string }) {
  const { t } = useLang();
  const [corr, setCorr] = useState<CorrelationResult | null>(null);

  useEffect(() => {
    if (!ds) return;
    let active = true;
    getCorrelation(ds)
      .then((c) => active && setCorr(c))
      .catch(() => active && setCorr(null));
    return () => { active = false; };
  }, [ds]);

  if (!corr || !corr.available) return null;

  const points = corr.points.filter(
    (p) => p.urbanization_pct !== null && p.rate_per_lakh !== null
  );
  if (!points.length) return null;

  // Find the correlation factor with highest |r|
  const topFactor = corr.correlations.reduce(
    (best, c) => (Math.abs(c.r) > Math.abs(best.r) ? c : best),
    corr.correlations[0]
  );

  const scatterData = points.map((p) => [p.urbanization_pct as number, p.rate_per_lakh, p.area]);

  const option: import("echarts").EChartsOption = {
    tooltip: {
      trigger: "item",
      formatter: (params: unknown) => {
        const p = params as { data: [number, number, string] };
        return `${p.data[2]}<br/>Urbanization: ${p.data[0].toFixed(1)}%<br/>Rate: ${p.data[1].toFixed(1)}/lakh`;
      },
    },
    xAxis: {
      name: t("insights.corrXAxis", "Urbanization %"),
      nameLocation: "middle",
      nameGap: 24,
      type: "value",
      axisLabel: { color: "#6b7a8f", fontSize: 10, fontFamily: "IBM Plex Mono, monospace" },
      splitLine: { lineStyle: { color: "#1d2836" } },
    },
    yAxis: {
      name: t("insights.corrYAxis", "Crime rate / lakh"),
      nameLocation: "middle",
      nameGap: 40,
      type: "value",
      axisLabel: { color: "#6b7a8f", fontSize: 10, fontFamily: "IBM Plex Mono, monospace" },
      splitLine: { lineStyle: { color: "#1d2836" } },
    },
    series: [
      {
        type: "scatter",
        data: scatterData,
        symbolSize: 8,
        itemStyle: { color: "#ffb000", opacity: 0.85 },
        label: { show: false },
      },
    ],
    grid: { left: 56, right: 16, top: 24, bottom: 40 },
  };

  return (
    <div className="panel p-5 sweep-in">
      <div className="flex items-center gap-2 mb-1">
        <Scale size={16} className="text-amber" />
        <span className="font-display text-sm uppercase tracking-widest text-text">
          {t("insights.corrTitle", "Socio-economic correlation — the why behind the where")}
        </span>
      </div>
      {topFactor && (
        <div className="value-mono text-[11px] text-dim mb-3">
          {t("insights.corrSubtitle", "Crime rate vs urbanization")}: r ={" "}
          <span className={Math.abs(topFactor.r) >= 0.5 ? "text-amber" : "text-teal"}>
            {topFactor.r.toFixed(3)}
          </span>{" "}
          <span className="text-dim">({topFactor.direction})</span>
        </div>
      )}
      <EChart option={option} height={260} />
    </div>
  );
}

function PredictiveTriage({ ds }: { ds: string }) {
  const { t } = useLang();
  const [pred, setPred] = useState<PredictionResult | null>(null);

  useEffect(() => {
    if (!ds) return;
    let active = true;
    getPredictions(ds)
      .then((p) => active && setPred(p))
      .catch(() => active && setPred(null));
    return () => { active = false; };
  }, [ds]);

  if (!pred || !pred.available || !pred.flagged.length) return null;

  const { flagged, by_area, meta } = pred;

  // Worst-detected areas at top: sort ascending by predicted_detection_rate.
  const sortedAreas = [...by_area].sort(
    (a, b) => a.predicted_detection_rate - b.predicted_detection_rate
  );

  const option: import("echarts").EChartsOption = {
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params: unknown) => {
        const arr = params as { name: string; value: number }[];
        const p = arr[0];
        return `${p.name}<br/>${t("insights.triageDetectionRate", "Predicted detection rate")}: ${p.value.toFixed(1)}%`;
      },
    },
    xAxis: {
      type: "value",
      max: 100,
      axisLabel: {
        color: "#6b7a8f",
        fontSize: 10,
        fontFamily: "IBM Plex Mono, monospace",
        formatter: "{value}%",
      },
      splitLine: { lineStyle: { color: "#1d2836" } },
    },
    yAxis: {
      type: "category",
      data: sortedAreas.map((a) => a.area),
      axisLabel: { color: "#6b7a8f", fontSize: 10, fontFamily: "IBM Plex Mono, monospace" },
    },
    grid: { left: 96, right: 24, top: 16, bottom: 28 },
    series: [
      {
        type: "bar",
        data: sortedAreas.map((a) => a.predicted_detection_rate * 100),
        itemStyle: { color: "#ff3b30" },
        barMaxWidth: 18,
      },
    ],
  };

  return (
    <div className="panel p-5 sweep-in">
      <div className="flex items-center justify-between gap-3 mb-1">
        <div className="flex items-center gap-2">
          <Crosshair size={16} className="text-signal" />
          <span className="font-display text-sm uppercase tracking-widest text-text">
            {t("insights.triageTitle", "Predictive Case Triage")}
          </span>
        </div>
        <span className="value-mono text-[9px] text-amber border border-amber/40 px-1.5 py-0.5 uppercase tracking-wide">
          {t("insights.triageAdvisory", "advisory")}
        </span>
      </div>
      {(meta.detection_auc != null || meta.n_open != null) && (
        <div className="value-mono text-[11px] text-dim mb-3">
          {meta.detection_auc != null && (
            <>
              {t("insights.triageAucLabel", "Detection model AUC")}{" "}
              <span className="text-teal">{meta.detection_auc.toFixed(2)}</span>
            </>
          )}
          {meta.detection_auc != null && meta.n_open != null && " · "}
          {meta.n_open != null && (
            <>
              {meta.n_open} {t("insights.triageOpenCasesScored", "open cases scored")}
            </>
          )}
        </div>
      )}

      {sortedAreas.length > 0 && (
        <div className="mb-4">
          <div className="label-hud mb-2">
            {t("insights.triageByAreaTitle", "Predicted detection rate by area")}
          </div>
          <EChart option={option} height={Math.max(160, sortedAreas.length * 32)} />
        </div>
      )}

      <div className="label-hud mb-2">
        {t("insights.triageFlaggedTitle", "Top flagged cases")}
      </div>
      <div className="space-y-2">
        {flagged.map((c) => {
          const undetectedRisk = (1 - c.detection_prob) * 100;
          const highRisk = undetectedRisk >= 60;
          return (
            <div
              key={c.id}
              className="border border-line p-2.5 flex flex-wrap items-center gap-2 justify-between"
            >
              <div className="flex items-center gap-2 min-w-0">
                <span className="value-mono text-xs text-text truncate">{c.id}</span>
                <span
                  className={`value-mono text-[10px] px-1.5 py-0.5 whitespace-nowrap ${
                    highRisk
                      ? "text-signal border border-signal/50 bg-signal/10"
                      : "text-amber border border-amber/40"
                  }`}
                >
                  {undetectedRisk.toFixed(0)}% {t("insights.triageUndetectedRisk", "undetected-risk")}
                </span>
                {c.predicted_days != null && c.stall && (
                  <span className="value-mono text-[10px] text-dim border border-line px-1.5 py-0.5 flex items-center gap-1 whitespace-nowrap">
                    <HourglassIcon size={10} />
                    ~{c.predicted_days}{t("insights.triageDaysStall", "d, stall")}
                  </span>
                )}
              </div>
              <div className="flex flex-wrap gap-1">
                {c.factors.map((f) => (
                  <span
                    key={f}
                    className="value-mono text-[9px] text-dim border border-line px-1.5 py-0.5"
                  >
                    {f}
                  </span>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-4 pt-3 border-t border-line value-mono text-[10px] text-dim leading-relaxed">
        {t(
          "insights.triageGovernance",
          "AI advisory for case prioritisation — not an individual risk score; human review required."
        )}
      </div>
    </div>
  );
}

// Staged narration cycling through what the backend is actually doing while
// the (multi-second) insights bundle computes, instead of one static
// "Synthesizing…" spinner line. Purely cosmetic — the request is a single
// call; these stages just narrate its known phases.
function useLoadingStage(active: boolean) {
  const [stage, setStage] = useState(0);
  useEffect(() => {
    if (!active) {
      setStage(0);
      return;
    }
    const id = setInterval(() => setStage((s) => (s + 1) % 4), 1500);
    return () => clearInterval(id);
  }, [active]);
  return stage;
}

function StagedLoading() {
  const { t } = useLang();
  const stage = useLoadingStage(true);
  const stages = [
    t("insights.load1", "Scanning for spikes…"),
    t("insights.load2", "Scoring district risk…"),
    t("insights.load3", "Detecting anomalies…"),
    t("insights.load4", "Ranking findings…"),
  ];
  return (
    <div className="flex items-center justify-center gap-3 py-20 text-dim">
      <Loader2 size={18} className="animate-spin text-amber" />
      <span className="value-mono text-sm">{stages[stage]}</span>
    </div>
  );
}

function InsightsInner() {
  const { t, lang } = useLang();
  const params = useSearchParams();
  const ds = params.get("ds") ?? "";
  const [data, setData] = useState<InsightsResponse | null>(null);
  const [error, setError] = useState("");
  const [brief, setBrief] = useState<string>("");
  const [briefLoading, setBriefLoading] = useState(false);
  // Bumped by the Freshness "refresh" button to force a `&refresh=1` refetch
  // of both the insights bundle and the brief.
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    if (!ds) return;
    let active = true;
    setData(null);
    setError("");
    getInsights(ds, lang, refreshTick > 0)
      .then((d) => active && setData(d))
      .catch((e) => active && setError(String(e)));
    return () => {
      active = false;
    };
  }, [ds, lang, refreshTick]);

  useEffect(() => {
    if (!ds || !data) return;
    let active = true;
    setBriefLoading(true);
    getInsightsBrief(ds, lang, refreshTick > 0)
      .then((r) => active && setBrief(r.brief))
      .catch(() => active && setBrief(""))
      .finally(() => active && setBriefLoading(false));
    return () => {
      active = false;
    };
  }, [ds, data, lang, refreshTick]);

  const refresh = () => setRefreshTick((n) => n + 1);

  if (!ds) {
    return (
      <EmptyState
        title={t("common.noDatasetTitle", "No dataset open")}
        text={t("insights.noDataset", "No dataset selected — pick one from the home screen.")}
        ctaHref="/"
        ctaLabel={t("common.goHome", "Open a dataset from Home to begin")}
      />
    );
  }
  if (error) {
    return (
      <div className="panel p-4 value-mono text-xs text-signal">
        {error} {t("insights.apiError", "— is the API running?")}
      </div>
    );
  }
  if (!data) {
    return <StagedLoading />;
  }

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <div className="flex justify-end -mb-2">
        <Freshness computedAt={data.computed_at} cached={data.cached} onRefresh={refresh} />
      </div>
      {/* Hero: Commander's Brief */}
      <div className="panel p-5 sweep-in">
        <div className="flex items-center gap-2 mb-3">
          <Sparkles size={16} className="text-teal" />
          <span className="font-display text-sm uppercase tracking-widest text-teal">
            {t("insights.commandersBrief", "Commander's Brief")}
          </span>
        </div>
        {briefLoading ? (
          <div className="flex items-center gap-2 text-dim py-2">
            <Loader2 size={14} className="animate-spin text-teal" />
            <span className="value-mono text-xs">{t("insights.drafting", "drafting…")}</span>
          </div>
        ) : (
          <p className="text-[15px] text-text leading-relaxed">
            {brief || t("insights.noBrief", "No brief available.")}
          </p>
        )}
        {data.signals_used.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {data.signals_used.map((s) => (
              <span key={s} className="value-mono text-[9px] text-dim border border-line px-1.5 py-0.5">
                {s}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Ranked findings */}
      <div>
        <div className="label-hud mb-2 flex items-center gap-1.5">
          <ShieldAlert size={11} /> {t("insights.priorityFindings", "Priority findings")}
        </div>
        {data.findings.length ? (
          <div className="space-y-3">
            {data.findings.map((f, i) => (
              <FindingCard key={f.id} ds={ds} f={f} index={i} />
            ))}
          </div>
        ) : (
          <div className="panel p-4 text-dim text-sm">
            {t(
              "insights.noProblems",
              "No significant problems detected — the data looks clean and stable."
            )}
          </div>
        )}
      </div>

      {/* Forecast + credibility */}
      <div className="grid md:grid-cols-2 gap-4">
        <ForecastPanel data={data.forecast} />
        <Credibility data={data} />
      </div>

      {/* Socio-economic correlation scatter */}
      <CorrelationScatter ds={ds} />

      {/* Predictive case triage */}
      <PredictiveTriage ds={ds} />
    </div>
  );
}

export default function InsightsPage() {
  const { t } = useLang();
  return (
    <Suspense>
      <Shell title={t("insights.title", "Insights")}>
        <PageIntro
          id="insights"
          text={t(
            "insights.pageIntro",
            "DRISHTI's answer-first view: the top problems in your data, ranked by severity. Click any finding to jump to its evidence."
          )}
        />
        <InsightsInner />
      </Shell>
    </Suspense>
  );
}
