"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import Shell from "@/components/Shell";
import PageIntro from "@/components/PageIntro";
import { useLang } from "@/lib/i18n";
import {
  appendFiles,
  getComposition,
  type AppendResult,
  type Composition,
} from "@/lib/api";
import {
  Upload,
  Database,
  FileSpreadsheet,
  Lock,
  History,
  CheckCircle2,
  AlertTriangle,
  Loader2,
} from "lucide-react";

function fmtDate(iso: string | null | undefined) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", { hour12: false });
}

function SummaryStrip({ c }: { c: Composition }) {
  const { t } = useLang();
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div className="bg-ink-3 border border-line/70 p-3">
        <div className="label-hud mb-1">{t("data.totalRecords", "Total records")}</div>
        <div className="font-display text-2xl text-amber">{c.total_rows.toLocaleString()}</div>
      </div>
      <div className="bg-ink-3 border border-line/70 p-3">
        <div className="label-hud mb-1">{t("data.tableCount", "Tables")}</div>
        <div className="font-display text-2xl text-text">{c.tables.length}</div>
      </div>
      <div className="bg-ink-3 border border-line/70 p-3">
        <div className="label-hud mb-1">{t("data.created", "Created")}</div>
        <div className="value-mono text-xs text-text mt-2">{fmtDate(c.created_at)}</div>
      </div>
      <div className="bg-ink-3 border border-line/70 p-3">
        <div className="label-hud mb-1">{t("data.updated", "Last updated")}</div>
        <div className="value-mono text-xs text-text mt-2">{fmtDate(c.updated_at)}</div>
      </div>
    </div>
  );
}

function TableCards({ c }: { c: Composition }) {
  const { t } = useLang();
  return (
    <div>
      <div className="label-hud mb-3">{t("data.tablesHeading", "Tables")}</div>
      <div className="grid gap-3 sm:grid-cols-2">
        {c.tables.map((tbl) => (
          <div key={tbl.name} className="panel p-4 flex items-center justify-between">
            <div className="flex items-center gap-3 min-w-0">
              <FileSpreadsheet size={18} className="text-amber shrink-0" />
              <div className="min-w-0">
                <div className="font-display uppercase tracking-wider text-text truncate">{tbl.name}</div>
                <div className="value-mono text-[10px] text-dim mt-0.5">
                  {tbl.n_columns} {t("data.columns", "columns")}
                </div>
              </div>
            </div>
            <div className="value-mono text-lg text-teal shrink-0">{tbl.row_count.toLocaleString()}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function AppendResults({ result }: { result: AppendResult }) {
  const { t } = useLang();
  return (
    <div className="panel p-4 sweep-in space-y-2">
      <div className="flex items-center gap-2 mb-1">
        <CheckCircle2 size={16} className="text-ok" />
        <span className="font-display text-sm uppercase tracking-wider text-ok">
          {t("data.appendSuccess", "Data added")}
        </span>
      </div>
      {result.tables.map((tr) => (
        <div key={tr.name} className="text-xs text-text value-mono">
          +{tr.added.toLocaleString()} {t("data.rowsTo", "rows to")} {tr.name}
          {tr.new_table && <span className="text-teal"> ({t("data.newTable", "new table")})</span>} ·{" "}
          {tr.duplicates_skipped.toLocaleString()} {t("data.duplicatesSkipped", "duplicates skipped")}
          {tr.extras_ignored > 0 && (
            <> · {tr.extras_ignored.toLocaleString()} {t("data.extrasIgnored", "extra columns ignored")}</>
          )}
        </div>
      ))}
      <div className="text-[11px] text-dim pt-1">{t("data.insightsRefresh", "insights will refresh")}</div>
    </div>
  );
}

function AddDataDropzone({ dsId, onDone }: { dsId: string; onDone: () => void }) {
  const { t } = useLang();
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<AppendResult | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const upload = useCallback(
    async (files: File[]) => {
      if (!files.length) return;
      setUploading(true);
      setError("");
      setResult(null);
      try {
        const res = await appendFiles(dsId, files);
        setResult(res);
        onDone();
      } catch (e) {
        let msg = String(e);
        // Try to extract detail from JSON error response: "400: {...detail:...}"
        try {
          const match = msg.match(/:\s*(\{.*\})/);
          if (match) {
            const parsed = JSON.parse(match[1]);
            if (parsed.detail) {
              msg = parsed.detail;
            }
          }
        } catch {
          // Fall back to raw message
        }
        setError(msg);
      } finally {
        setUploading(false);
      }
    },
    [dsId, onDone]
  );

  return (
    <div>
      <div className="label-hud mb-3">{t("data.addDataHeading", "Add data")}</div>
      <div
        className={`panel p-8 text-center cursor-pointer transition-colors ${dragOver ? "bg-ink-3" : ""}`}
        onClick={() => fileInput.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          upload(Array.from(e.dataTransfer.files));
        }}
      >
        <input
          ref={fileInput}
          type="file"
          multiple
          accept=".csv,.xlsx,.xls"
          className="hidden"
          onChange={(e) => upload(Array.from(e.target.files ?? []))}
        />
        {uploading ? (
          <div className="flex items-center justify-center gap-2 font-display uppercase tracking-widest text-amber animate-pulse">
            <Loader2 size={18} className="animate-spin" />
            {t("data.appending", "Appending rows…")}
          </div>
        ) : (
          <>
            <Upload size={30} className="mx-auto mb-2 text-dim" />
            <div className="font-display text-lg uppercase tracking-widest text-text">
              {t("data.addDataCta", "Drop CSV / Excel to append")}
            </div>
            <div className="label-hud mt-2">
              {t("data.addDataHint", "matching columns merge in — new files can also add new tables")}
            </div>
          </>
        )}
      </div>
      {error && (
        <div className="mt-3 panel p-3 text-signal text-xs value-mono">{error}</div>
      )}
      {result && <div className="mt-3"><AppendResults result={result} /></div>}
    </div>
  );
}

function ReadOnlyNote() {
  const { t } = useLang();
  return (
    <div className="panel p-5 flex items-start gap-3">
      <Lock size={18} className="text-dim shrink-0 mt-0.5" />
      <div className="text-sm text-dim leading-relaxed">
        {t("data.readonly", "Demo dataset — read-only")}
      </div>
    </div>
  );
}

function HistoryList({ c }: { c: Composition }) {
  const { t } = useLang();
  if (!c.history.length) return null;
  return (
    <div>
      <div className="label-hud mb-3 flex items-center gap-1.5">
        <History size={12} /> {t("data.historyHeading", "History")}
      </div>
      <div className="space-y-2">
        {c.history.map((h, i) => (
          <div key={i} className="panel p-3 sweep-in" style={{ animationDelay: `${i * 0.04}s` }}>
            <div className="flex items-center justify-between mb-1.5">
              <span className="value-mono text-xs text-amber uppercase">{h.action}</span>
              <span className="value-mono text-[10px] text-dim">{fmtDate(h.at)}</span>
            </div>
            {h.files.length > 0 && (
              <div className="value-mono text-[10px] text-dim mb-1.5 truncate">{h.files.join(", ")}</div>
            )}
            <div className="flex flex-wrap gap-2">
              {h.tables.map((tr, j) => (
                <span key={j} className="value-mono text-[10px] text-text bg-ink-3 border border-line/60 px-2 py-1">
                  {tr.name}: +{tr.added.toLocaleString()}
                  {tr.new_table && <span className="text-teal"> new</span>}
                  {tr.duplicates_skipped > 0 && (
                    <span className="text-dim"> · {tr.duplicates_skipped.toLocaleString()} dup</span>
                  )}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function DataInner() {
  const { t } = useLang();
  const params = useSearchParams();
  const ds = params.get("ds") ?? "";
  const [comp, setComp] = useState<Composition | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    if (!ds) {
      setLoading(false);
      return;
    }
    setLoading(true);
    getComposition(ds)
      .then((c) => {
        setComp(c);
        setError("");
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [ds]);

  // Defer out of the effect body: calling load() synchronously sets state during
  // the effect and triggers a cascading render (same idiom as Tracker/Network).
  useEffect(() => {
    const timer = window.setTimeout(() => load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  if (!ds) {
    return (
      <div className="panel p-8 max-w-lg mx-auto text-center">
        <Database size={28} className="mx-auto mb-3 text-dim" />
        <p className="text-dim text-sm mb-4">
          {t("data.noDataset", "No dataset selected — pick one from the home screen.")}
        </p>
        <Link
          href="/"
          className="inline-flex items-center gap-2 px-4 py-2 bg-amber text-ink font-display uppercase tracking-wider text-sm hover:bg-amber-dim transition-colors"
        >
          {t("data.goHome", "Go to home")}
        </Link>
      </div>
    );
  }

  if (error) {
    return (
      <div className="panel p-4 flex items-center gap-2 text-signal">
        <AlertTriangle size={16} />
        <span className="value-mono text-xs">{error}</span>
      </div>
    );
  }

  if (loading || !comp) {
    return <div className="text-dim animate-pulse text-sm">{t("data.loading", "Loading dataset composition…")}</div>;
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <span className="font-display text-xl uppercase tracking-wider text-text">{comp.name}</span>
          <span
            className={`label-hud px-2 py-0.5 border ${
              comp.source === "seed" ? "border-line text-dim" : "border-amber text-amber"
            }`}
          >
            {comp.source === "seed" ? t("data.seedBadge", "seed") : t("data.uploadBadge", "upload")}
          </span>
        </div>
      </div>

      <SummaryStrip c={comp} />
      <TableCards c={comp} />

      {comp.read_only ? (
        <ReadOnlyNote />
      ) : (
        <AddDataDropzone dsId={ds} onDone={load} />
      )}

      <HistoryList c={comp} />
    </div>
  );
}

export default function DataPage() {
  const { t } = useLang();
  return (
    <Suspense>
      <Shell title={t("data.title", "Data")}>
        <PageIntro
          id="data"
          text={t(
            "data.intro",
            "Everything this dataset contains — files, tables, and records. Drop new Excel/CSV files here to add data; duplicates are skipped automatically."
          )}
        />
        <DataInner />
      </Shell>
    </Suspense>
  );
}
