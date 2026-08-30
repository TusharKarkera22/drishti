"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getDatasets, ingestFiles } from "@/lib/api";
import { useLang } from "@/lib/i18n";

type DatasetRow = Awaited<ReturnType<typeof getDatasets>>[number];

export default function Home() {
  const router = useRouter();
  const { t } = useLang();
  const [datasets, setDatasets] = useState<DatasetRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getDatasets()
      .then(setDatasets)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  const upload = useCallback(
    async (files: File[]) => {
      if (!files.length) return;
      setUploading(true);
      setError("");
      try {
        const name = files[0].name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ");
        const manifest = await ingestFiles(files, name);
        router.push(`/insights/?ds=${manifest.id}`);
      } catch (e) {
        setError(String(e));
        setUploading(false);
      }
    },
    [router]
  );

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 py-16">
      <div className="w-full max-w-3xl sweep-in">
        <div className="text-center mb-12">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/app/drishti-emblem.png"
            alt="DRISHTI"
            width={104}
            height={104}
            className="mx-auto mb-4"
          />
          <div className="font-display text-6xl font-bold tracking-[0.2em] text-amber">
            DRISHTI
          </div>
          <p className="label-hud mt-3 text-sm">
            {t("home.tagline", "Crime Intelligence Platform · दृष्टि")}
          </p>
          <p className="text-dim mt-4 max-w-xl mx-auto text-sm leading-relaxed">
            {t("home.description", "Drop any dataset — crime records, accidents, anything tabular. DRISHTI profiles it, understands what each column means, and builds the dashboards, maps, network graphs, and AI agents automatically.")}
          </p>
        </div>

        <div
          className={`panel p-10 text-center cursor-pointer transition-colors ${
            dragOver ? "bg-ink-3" : ""
          }`}
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
            accept=".csv,.xlsx"
            className="hidden"
            onChange={(e) => upload(Array.from(e.target.files ?? []))}
          />
          {uploading ? (
            <div className="font-display uppercase tracking-widest text-amber animate-pulse">
              {t("home.uploading", "Profiling dataset · detecting semantics · building manifest…")}
            </div>
          ) : (
            <>
              <div className="font-display text-xl uppercase tracking-widest text-text">
                {t("home.ingest", "Ingest New Dataset")}
              </div>
              <div className="label-hud mt-2">
                {t("home.dropHint", "drag & drop CSV / Excel — multiple files become linked tables")}
              </div>
            </>
          )}
        </div>

        <p className="value-mono text-[10px] text-dim mt-3 text-center">
          {t("home.demoDataNotice", "Public demo — upload synthetic or non-sensitive data only. CSV/XLSX limits are enforced.")}
        </p>

        {error && (
          <div className="mt-4 panel p-3 text-signal text-xs value-mono">
            {error} {t("home.apiError", "— is the API running?")}
          </div>
        )}

        <div className="mt-10">
          <div className="label-hud mb-3">{t("home.registeredDatasets", "Registered Datasets")}</div>
          <div className="grid gap-3">
            {datasets.map((d) => (
              <button
                key={d.id}
                onClick={() => router.push(`/insights/?ds=${d.id}`)}
                className="panel p-4 flex items-center justify-between text-left hover:bg-ink-3 transition-colors"
              >
                <div>
                  <div className="font-display uppercase tracking-wider text-text">
                    {d.name}
                  </div>
                  <div className="value-mono text-xs text-dim mt-1">
                    {d.tables.map((t) => `${t.name}:${t.row_count.toLocaleString()}`).join(" · ")}
                  </div>
                  <div className="value-mono text-xs text-teal mt-1">
                    {d.tables.reduce((s, t) => s + t.row_count, 0).toLocaleString()}{" "}
                    {t("home.records", "records")}
                  </div>
                </div>
                <span
                  className={`label-hud px-2 py-1 border ${
                    d.domain_pack === "crime"
                      ? "border-amber text-amber"
                      : "border-line text-dim"
                  }`}
                >
                  {d.domain_pack} {t("home.pack", "pack")}
                </span>
              </button>
            ))}
            {loading && (
              <>
                <div className="panel p-4 h-[58px] animate-pulse opacity-60" />
                <div className="panel p-4 h-[58px] animate-pulse opacity-30" />
                <div className="value-mono text-xs text-dim animate-pulse">
                  {t("home.loadingDatasets", "Loading datasets…")}
                </div>
              </>
            )}
            {!loading && !datasets.length && !error && (
              <div className="text-dim text-sm">{t("home.noDatasets", "No datasets yet — upload one above.")}</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
