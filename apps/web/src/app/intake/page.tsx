"use client";

import { Fragment, Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import Shell from "@/components/Shell";
import PageIntro from "@/components/PageIntro";
import { useLang } from "@/lib/i18n";
import {
  startIntakeClean,
  getIntakeStatus,
  type IntakeStatus,
  type IntakeIteration,
} from "@/lib/api";
import {
  Upload,
  FileSpreadsheet,
  Sparkles,
  ScanSearch,
  Cog,
  ClipboardCheck,
  FileText,
  Database,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  ArrowRight,
  CalendarClock,
  Phone,
  Banknote,
  Tags,
  Users,
  FileWarning,
  Copy,
  type LucideIcon,
} from "lucide-react";

const OP_META: Record<string, { label: string; Icon: LucideIcon; verb: string; keys: string[] }> = {
  normalize_dates: { label: "Normalize dates", Icon: CalendarClock, verb: "parsed", keys: ["parsed"] },
  normalize_phones: { label: "Normalize phones", Icon: Phone, verb: "fixed", keys: ["normalized"] },
  normalize_money: { label: "Normalize amounts", Icon: Banknote, verb: "parsed", keys: ["parsed"] },
  standardize_values: { label: "Standardize values", Icon: Tags, verb: "standardized", keys: ["standardized"] },
  resolve_persons: { label: "Resolve identities", Icon: Users, verb: "merged", keys: ["merged_clusters"] },
  handle_missing: { label: "Handle missing", Icon: FileWarning, verb: "flagged", keys: ["dropped", "flagged"] },
  dedupe_rows: { label: "Remove duplicates", Icon: Copy, verb: "removed", keys: ["dropped"] },
};

function statCount(op: string, stats?: Record<string, number>): number {
  const meta = OP_META[op];
  if (!stats || !meta) return 0;
  for (const k of meta.keys) if (typeof stats[k] === "number") return stats[k];
  return 0;
}

const STAGES: { label: string; Icon: LucideIcon; hint: string; ai?: boolean }[] = [
  { label: "Profile", Icon: ScanSearch, hint: "digest columns" },
  { label: "Plan", Icon: Sparkles, hint: "AI plans fixes", ai: true },
  { label: "Execute", Icon: Cog, hint: "cleaners run" },
  { label: "Assess", Icon: ClipboardCheck, hint: "AI verifies", ai: true },
  { label: "Report", Icon: FileText, hint: "audit + summary" },
];

// derive which conceptual stage is "live" from the job status
function activeStage(s: IntakeStatus | null): number {
  if (!s) return 0;
  if (s.done) return 4;
  if (s.iterations.length === 0) return 1; // profiled, AI planning
  return 3; // looping execute/assess
}

function StageFlow({ status }: { status: IntakeStatus | null }) {
  const { t } = useLang();
  const active = activeStage(status);
  const done = status?.done ?? false;
  return (
    <div className="flex items-start w-full min-w-0">
      {STAGES.map((st, i) => {
        const isDone = done ? true : i < active;
        const isActive = !done && i === active;
        const lit = isDone || isActive;
        return (
          <Fragment key={st.label}>
            <div className="flex flex-col items-center gap-2 w-[4.25rem] shrink-0">
              <div
                className={`relative flex items-center justify-center w-11 h-11 rounded-sm border ${
                  isDone
                    ? "border-amber/70 bg-amber/10"
                    : isActive
                    ? "border-amber bg-amber/15 pulse-amber"
                    : "border-line bg-ink-2"
                }`}
              >
                {isActive ? (
                  <Loader2 size={18} className="text-amber animate-spin" />
                ) : isDone ? (
                  <CheckCircle2 size={18} className="text-amber" />
                ) : (
                  <st.Icon size={17} className="text-dim" />
                )}
                {st.ai && (
                  <Sparkles
                    size={10}
                    className={`absolute -top-1 -right-1 ${lit ? "text-teal" : "text-dim/60"}`}
                  />
                )}
              </div>
              <div className="text-center">
                <div
                  className={`font-display text-[11px] uppercase tracking-wide leading-none ${
                    lit ? "text-amber" : "text-dim"
                  }`}
                >
                  {t(`intake.stage.${st.label.toLowerCase()}`, st.label)}
                </div>
                <div className="value-mono text-[8.5px] text-dim leading-tight mt-1">{t(`intake.stage.hint.${st.label.toLowerCase()}`, st.hint)}</div>
              </div>
            </div>
            {i < STAGES.length - 1 && (
              <div className="flex-1 min-w-[0.5rem] flex items-center" style={{ height: "2.75rem" }}>
                <div className={`h-px w-full ${i < active || done ? "bg-amber-dim" : "bg-line"}`} />
              </div>
            )}
          </Fragment>
        );
      })}
    </div>
  );
}

function IterationCard({ it, index }: { it: IntakeIteration; index: number }) {
  const { t } = useLang();
  const ok = it.applied.filter((a) => !a.error);
  const corrective = it.assessment?.corrective_plan?.length;
  return (
    <div className="panel p-4 sweep-in" style={{ animationDelay: `${index * 0.08}s` }}>
      <div className="flex items-center justify-between mb-3">
        <span className="label-hud text-amber">{t("intake.pass", "Pass")} {it.iteration}</span>
        <span className="value-mono text-[10px] text-dim">
          {it.n_changes} {t("intake.changes", "changes")} · {it.n_quarantined} {t("intake.quarantined", "quarantined")}
        </span>
      </div>
      <div className="flex flex-wrap gap-2">
        {ok.map((a, j) => {
          const meta = OP_META[a.op];
          const Icon = meta?.Icon ?? Cog;
          const n = statCount(a.op, a.stats);
          return (
            <div
              key={j}
              className="flex items-center gap-2 px-2.5 py-1.5 bg-ink-3 border border-line/70 sweep-in"
              style={{ animationDelay: `${index * 0.08 + j * 0.05}s` }}
            >
              <Icon size={14} className="text-teal shrink-0" />
              <span className="text-xs text-text">{t(`intake.op.${a.op}`, meta?.label ?? a.op)}</span>
              {a.column && <span className="value-mono text-[9px] text-dim">{a.column}</span>}
              {n > 0 && (
                <span className="value-mono text-[11px] text-amber">
                  {n.toLocaleString()} {t(`intake.verb.${a.op}`, meta?.verb ?? "")}
                </span>
              )}
            </div>
          );
        })}
        {it.applied
          .filter((a) => a.error)
          .map((a, j) => (
            <div key={`e${j}`} className="flex items-center gap-1.5 px-2.5 py-1.5 border border-line/40 opacity-50">
              <AlertTriangle size={13} className="text-signal" />
              <span className="text-xs text-dim line-through">{t(`intake.op.${a.op}`, OP_META[a.op]?.label ?? a.op)}</span>
            </div>
          ))}
      </div>
      <div className="mt-3 flex items-center gap-2">
        {it.assessment?.done ? (
          <>
            <CheckCircle2 size={14} className="text-ok" />
            <span className="value-mono text-[11px] text-ok">{t("intake.verdictDone", "AI verdict: clean enough — done.")}</span>
          </>
        ) : corrective ? (
          <>
            <Loader2 size={14} className="text-teal" />
            <span className="value-mono text-[11px] text-teal">
              {t("intake.verdictCorrective", "AI found residual issues — queuing a corrective pass.")}
            </span>
          </>
        ) : (
          <span className="value-mono text-[11px] text-dim">{t("intake.assessing", "Assessing…")}</span>
        )}
      </div>
    </div>
  );
}

function Results({ status }: { status: IntakeStatus }) {
  const { t } = useLang();
  const dropped = (status.rows_in ?? 0) - (status.rows_out ?? 0);
  return (
    <div className="panel p-5 sweep-in">
      <div className="flex items-center gap-2 mb-4">
        <CheckCircle2 size={18} className="text-ok" />
        <span className="font-display text-base uppercase tracking-widest text-ok">{t("intake.cleaningComplete", "Cleaning Complete")}</span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
        <Stat label={t("intake.statRowsIn", "Rows in")} value={(status.rows_in ?? 0).toLocaleString()} />
        <Stat label={t("intake.statRowsOut", "Rows out")} value={(status.rows_out ?? 0).toLocaleString()} accent />
        <Stat label={t("intake.statDuplicates", "Duplicates removed")} value={dropped > 0 ? dropped.toLocaleString() : "0"} />
        <Stat label={t("intake.statQuarantined", "Quarantined")} value={(status.quarantined ?? 0).toLocaleString()} warn />
      </div>
      {status.report && (
        <div className="border-l-2 border-teal/60 pl-3 mb-5">
          <div className="label-hud text-teal mb-1 flex items-center gap-1.5">
            <Sparkles size={11} /> {t("intake.aiReport", "AI cleaning report")}
          </div>
          <p className="text-sm text-text leading-relaxed">{status.report}</p>
        </div>
      )}
      {status.note && (
        <div className="border-l-2 border-amber/60 pl-3 mb-5">
          <p className="text-sm text-dim leading-relaxed">{status.note}</p>
        </div>
      )}
      {status.appended_to && (
        <div className="mb-5">
          <p className="value-mono text-xs text-ok mb-3">
            +{(status.added ?? 0).toLocaleString()} {t("intake.appendAdded", "rows added")} ·{" "}
            {(status.duplicates_skipped ?? 0).toLocaleString()} {t("intake.appendDuplicates", "duplicates skipped")}
          </p>
          <Link
            href={`/data/?ds=${status.appended_to}`}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-amber text-ink font-display uppercase tracking-wider text-sm hover:bg-amber-dim transition-colors"
          >
            <Database size={16} /> {t("intake.openData", "Open dataset")} <ArrowRight size={16} />
          </Link>
        </div>
      )}
      {status.output_dataset_id && !status.appended_to && (
        <Link
          href={`/dashboard/?ds=${status.output_dataset_id}`}
          className="inline-flex items-center gap-2 px-4 py-2.5 bg-amber text-ink font-display uppercase tracking-wider text-sm hover:bg-amber-dim transition-colors"
        >
          <Database size={16} /> {t("intake.openDashboard", "Open dashboard on cleaned data")} <ArrowRight size={16} />
        </Link>
      )}
    </div>
  );
}

function Stat({ label, value, accent, warn }: { label: string; value: string; accent?: boolean; warn?: boolean }) {
  return (
    <div className="bg-ink-3 border border-line/70 p-3">
      <div className="label-hud mb-1">{label}</div>
      <div className={`font-display text-2xl ${accent ? "text-amber" : warn ? "text-signal" : "text-text"}`}>
        {value}
      </div>
    </div>
  );
}

function IntakeInner() {
  const { t } = useLang();
  const params = useSearchParams();
  const ds = params.get("ds") ?? "";
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [jobId, setJobId] = useState<string>("");
  const [status, setStatus] = useState<IntakeStatus | null>(null);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const [destMode, setDestMode] = useState<"append" | "new">("append");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!jobId) return;
    let active = true;
    const poll = async () => {
      try {
        const s = await getIntakeStatus(jobId);
        if (!active) return;
        setStatus(s);
        if (!s.done) setTimeout(poll, 1200);
      } catch (e) {
        if (active) setError(String(e));
      }
    };
    poll();
    return () => {
      active = false;
    };
  }, [jobId]);

  const pickFile = (f: File | null) => {
    if (!f) return;
    setFile(f);
    if (!name) setName(f.name.replace(/\.[^.]+$/, ""));
  };

  const start = async () => {
    if (!file) return;
    setError("");
    try {
      const destDatasetId = ds && destMode === "append" ? ds : undefined;
      const { job_id } = await startIntakeClean(file, name || file.name, destDatasetId);
      setJobId(job_id);
    } catch (e) {
      setError(String(e));
    }
  };

  const reset = () => {
    setFile(null);
    setName("");
    setJobId("");
    setStatus(null);
    setError("");
  };

  // ---- upload screen ----
  if (!jobId) {
    return (
      <div className="max-w-3xl mx-auto">
        <div className="mb-6">
          <h2 className="font-display text-xl uppercase tracking-wider text-text mb-1">{t("intake.heading", "Agentic Data Intake")}</h2>
          <p className="text-sm text-dim leading-relaxed">
            {t("intake.intro", "Drop a raw, messy CSV or Excel file. An AI agent profiles it, plans the cleaning, runs deterministic cleaners, checks its own work, and self-corrects — every change auditable, nothing silently dropped.")}
          </p>
        </div>

        <label
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            pickFile(e.dataTransfer.files?.[0] ?? null);
          }}
          className={`flex flex-col items-center justify-center gap-3 h-52 border-2 border-dashed cursor-pointer transition-colors ${
            dragging ? "border-amber bg-amber/5" : "border-line hover:border-amber/50 bg-ink-2/40"
          }`}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".csv,.xlsx,.xls"
            className="hidden"
            onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
          />
          {file ? (
            <>
              <FileSpreadsheet size={36} className="text-amber" />
              <div className="value-mono text-sm text-text">{file.name}</div>
              <div className="value-mono text-[10px] text-dim">{(file.size / 1024).toFixed(0)} KB · click to replace</div>
            </>
          ) : (
            <>
              <Upload size={36} className={dragging ? "text-amber" : "text-dim"} />
              <div className="font-display uppercase tracking-wider text-sm text-dim">
                {t("intake.dropHint", "Drop CSV / Excel, or click to browse")}
              </div>
            </>
          )}
        </label>

        {ds && (
          <div className="flex items-center gap-2 mt-4 p-1 bg-ink-2 border border-line w-fit">
            <button
              type="button"
              onClick={() => setDestMode("append")}
              className={`px-3 py-1.5 value-mono text-xs transition-colors ${
                destMode === "append" ? "bg-amber text-ink" : "text-dim hover:text-text"
              }`}
            >
              {t("intake.destAppend", "Add cleaned rows to the current dataset")}
            </button>
            <button
              type="button"
              onClick={() => setDestMode("new")}
              className={`px-3 py-1.5 value-mono text-xs transition-colors ${
                destMode === "new" ? "bg-amber text-ink" : "text-dim hover:text-text"
              }`}
            >
              {t("intake.destNew", "Create a new dataset")}
            </button>
          </div>
        )}

        <div className="flex items-center gap-3 mt-4">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("intake.namePlaceholder", "Cleaned dataset name")}
            className="flex-1 bg-ink-2 border border-line px-3 py-2.5 text-sm text-text value-mono focus:border-amber/60 outline-none"
          />
          <button
            onClick={start}
            disabled={!file}
            className="flex items-center gap-2 px-5 py-2.5 bg-amber text-ink font-display uppercase tracking-wider text-sm disabled:opacity-30 disabled:cursor-not-allowed hover:bg-amber-dim transition-colors"
          >
            <Sparkles size={16} /> {t("intake.cleanBtn", "Clean with AI")}
          </button>
        </div>
        {error && <div className="value-mono text-xs text-signal mt-3">{error}</div>}

        <div className="mt-8 panel p-4">
          <div className="label-hud mb-3">{t("intake.pipelineWorks", "How the pipeline works")}</div>
          <StageFlow status={null} />
        </div>
      </div>
    );
  }

  // ---- running / done screen ----
  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <FileSpreadsheet size={20} className="text-amber" />
          <div>
            <div className="font-display text-base uppercase tracking-wider text-text">{status?.name ?? name}</div>
            <div className="value-mono text-[10px] text-dim">
              {status?.done ? t("intake.pipelineComplete", "pipeline complete") : status?.status ?? t("intake.starting", "starting…")}
            </div>
          </div>
        </div>
        <button onClick={reset} className="value-mono text-xs text-dim hover:text-amber transition-colors">
          {t("intake.newFile", "← new file")}
        </button>
      </div>

      <div className="panel p-5">
        <StageFlow status={status} />
      </div>

      {status?.error && (
        <div className="panel p-4 border-signal/50">
          <div className="flex items-center gap-2 text-signal">
            <AlertTriangle size={16} />
            <span className="value-mono text-xs">{status.error}</span>
          </div>
        </div>
      )}

      {status && !status.done && status.iterations.length === 0 && (
        <div className="flex items-center justify-center gap-3 py-8 text-dim">
          <Loader2 size={18} className="animate-spin text-amber" />
          <span className="value-mono text-sm">{t("intake.profiling", "Profiling columns and asking the agent for a cleaning plan…")}</span>
        </div>
      )}

      <div className="space-y-3">
        {status?.iterations.map((it, i) => (
          <IterationCard key={i} it={it} index={i} />
        ))}
      </div>

      {status?.done && !status.error && <Results status={status} />}
    </div>
  );
}

export default function IntakePage() {
  const { t } = useLang();
  return (
    <Suspense>
      <Shell title={t("intake.title", "Data Intake")}>
        <PageIntro
          id="intake"
          text={t(
            "intake.pageIntro",
            "Upload a messy file and DRISHTI's cleaning agent fixes formats, merges duplicates and quarantines bad rows — then adds the result to your dataset."
          )}
        />
        <IntakeInner />
      </Shell>
    </Suspense>
  );
}
