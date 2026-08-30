"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Database, FileSpreadsheet, History, Plus } from "lucide-react";
import Shell from "@/components/Shell";
import PageIntro from "@/components/PageIntro";
import { getComposition, type Composition } from "@/lib/api";
import { useLang } from "@/lib/i18n";

function DataInner() {
  const { t } = useLang();
  const ds = useSearchParams().get("ds") ?? "";
  const [result, setResult] = useState<{ ds: string; value: Composition | null; error: string } | null>(null);
  useEffect(() => {
    if (!ds) return;
    let active = true;
    getComposition(ds).then((value) => active && setResult({ ds, value, error: "" }))
      .catch(() => active && setResult({ ds, value: null, error: t("data.loadError", "This dataset is unavailable.") }));
    return () => { active = false; };
  }, [ds, t]);
  if (!ds) return <Empty text={t("data.noDataset", "No dataset selected — choose one from Home.")} />;
  if (!result || result.ds !== ds) return <div className="value-mono text-sm text-dim">{t("data.loading", "Loading dataset composition…")}</div>;
  if (!result.value) return <Empty text={result.error} />;
  const data = result.value;
  return <div className="space-y-5">
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <Stat label={t("data.totalRecords", "Total records")} value={data.total_rows.toLocaleString()} />
      <Stat label={t("data.tableCount", "Tables")} value={String(data.tables.length)} />
      <Stat label={t("data.created", "Created")} value={new Date(data.created_at).toLocaleDateString("en-IN")} />
      <Stat label={t("data.updated", "Last updated")} value={data.updated_at ? new Date(data.updated_at).toLocaleDateString("en-IN") : "—"} />
    </div>
    <section className="panel p-5">
      <div className="flex items-center justify-between mb-4"><div className="label-hud flex items-center gap-2"><Database size={14} /> {t("data.tablesHeading", "Tables")}</div><span className={`value-mono text-[10px] px-2 py-1 border ${data.read_only ? "border-amber text-amber" : "border-teal text-teal"}`}>{data.source === "seed" ? t("data.seedBadge", "SEED") : t("data.uploadBadge", "UPLOAD")}</span></div>
      <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3">{data.tables.map((table) => <div key={table.name} className="bg-ink-3 border border-line p-4"><div className="font-display text-sm uppercase tracking-wider text-text truncate">{table.name}</div><div className="value-mono text-xs text-dim mt-2">{table.row_count.toLocaleString()} rows · {table.n_columns} {t("data.columns", "columns")}</div></div>)}</div>
    </section>
    <div className="grid lg:grid-cols-2 gap-4">
      <section className="panel p-5"><div className="label-hud flex items-center gap-2 mb-3"><Plus size={14} /> {t("data.addDataHeading", "Add data")}</div><p className="text-sm text-dim mb-4">{data.read_only ? t("data.readonly", "Demo dataset — read only") : t("data.addDataHint", "Compatible columns merge; new files can add new tables.")}</p><Link href={`/intake/?ds=${encodeURIComponent(ds)}`} className="inline-flex items-center gap-2 px-4 py-2 border border-amber text-amber font-display uppercase tracking-wider text-xs hover:bg-amber/10"><FileSpreadsheet size={15} /> {t("data.addDataHeading", "Add data")}</Link></section>
      <section className="panel p-5"><div className="label-hud flex items-center gap-2 mb-3"><History size={14} /> {t("data.historyHeading", "History")}</div>{!data.history.length ? <p className="text-sm text-dim">No append history yet.</p> : data.history.slice().reverse().slice(0, 6).map((entry, index) => <div key={`${entry.at}-${index}`} className="border-t border-line/60 py-2 value-mono text-[11px] text-dim"><span className="text-text">{entry.action}</span> · {new Date(entry.at).toLocaleString("en-IN", { hour12: false })}</div>)}</section>
    </div>
  </div>;
}

function Stat({ label, value }: { label: string; value: string }) { return <div className="panel p-4"><div className="label-hud mb-1">{label}</div><div className="font-display text-xl text-amber">{value}</div></div>; }
function Empty({ text }: { text: string }) { return <div className="panel p-8 text-center"><p className="text-sm text-dim mb-4">{text}</p><Link href="/" className="value-mono text-xs text-amber">← Home</Link></div>; }

export default function DataPage() {
  const { t } = useLang();
  return <Shell title={t("data.title", "Data")}><PageIntro id="data" text={t("data.intro", "Everything in this dataset — tables, records, source, and append history.")} /><Suspense><DataInner /></Suspense></Shell>;
}
