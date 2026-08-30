"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Pause, Play, RefreshCw } from "lucide-react";
import { getTemporalComparison, type TemporalComparisonData, type TemporalComparisonFrame } from "@/lib/api";
import { daysAfter, daysBefore } from "@/lib/investigation-context";
import { useLang } from "@/lib/i18n";

interface TemporalControlsProps {
  ds: string; maxDate: string; area?: string; category?: string;
  initialFrom?: string; initialTo?: string; initialFrame?: number;
  onFrame: (frame: TemporalComparisonFrame | null) => void;
}

const TEMPORAL_COPY = {
  kn: { from: "ಪ್ರಸ್ತುತ ಅವಧಿ", to: "ವರೆಗೆ", compare: "ಹೋಲಿಸಿ", play: "ಚಲಾಯಿಸಿ", pause: "ವಿರಾಮ", frame: "ಚೌಕಟ್ಟು", evidence: "ಸಾಕ್ಷ್ಯ", rows: "ದಾಖಲೆಗಳು", unavailable: "ಹಿಂದಿನ ಇತಿಹಾಸ ಲಭ್ಯವಿಲ್ಲ" },
  en: { from: "Current from", to: "to", compare: "Compare", play: "Play", pause: "Pause", frame: "frame", evidence: "Evidence", rows: "rows", unavailable: "Prior history unavailable" },
} as const;

export default function TemporalControls({ ds, maxDate, area, category, initialFrom, initialTo, initialFrame = 0, onFrame }: TemporalControlsProps) {
  const { lang } = useLang();
  const copy = TEMPORAL_COPY[lang];
  const exclusiveMax = daysAfter(maxDate, 1);
  const [from, setFrom] = useState(() => initialFrom ?? daysBefore(initialTo ?? exclusiveMax, 28));
  const [to, setTo] = useState(initialTo ?? exclusiveMax);
  const [result, setResult] = useState<TemporalComparisonData | null>(null);
  const [error, setError] = useState("");
  const [frame, setFrame] = useState(initialFrame);
  const [playing, setPlaying] = useState(false);
  const requestId = useRef(0);
  const initialLoadStarted = useRef(false);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setPlaying(false);
    try {
      const value = await getTemporalComparison(ds, from, to, { frame_days: "7", ...(area ? { area } : {}), ...(category ? { category } : {}) });
      if (id !== requestId.current) return;
      if (!("frames" in value)) { setResult(null); setError(value.reason || copy.unavailable); return; }
      setError(""); setResult(value); setFrame(Math.min(initialFrame, Math.max(value.frames.length - 1, 0)));
    } catch (reason) {
      if (id !== requestId.current) return;
      setError(String(reason)); setResult(null);
    }
  }, [ds, from, to, area, category, initialFrame, copy.unavailable]);

  useEffect(() => {
    if (initialLoadStarted.current) return;
    initialLoadStarted.current = true;
    const timer = window.setTimeout(() => void load(), 0);
    return () => { window.clearTimeout(timer); requestId.current += 1; onFrame(null); };
  }, [load, onFrame]);
  useEffect(() => { if (!playing || !result?.frames.length) return; const timer = window.setInterval(() => setFrame((current) => (current + 1) % result.frames.length), 1000); return () => window.clearInterval(timer); }, [playing, result]);
  useEffect(() => { onFrame(result?.frames[frame] ?? null); }, [frame, result, onFrame]);

  return <div className="panel p-3 space-y-3">
    <div className="flex flex-wrap items-end gap-2">
      <label className="label-hud">{copy.from}<input type="date" value={from} onChange={(event) => setFrom(event.target.value)} className="block mt-1 bg-ink-3 border border-line px-2 py-1 value-mono text-xs" /></label>
      <label className="label-hud">{copy.to}<input type="date" value={to} onChange={(event) => setTo(event.target.value)} className="block mt-1 bg-ink-3 border border-line px-2 py-1 value-mono text-xs" /></label>
      <button onClick={() => void load()} className="h-8 px-3 border border-amber text-amber value-mono text-xs flex items-center gap-1"><RefreshCw size={12} /> {copy.compare}</button>
      {result?.frames.length ? <button aria-pressed={playing} onClick={() => setPlaying((value) => !value)} className="h-8 px-3 border border-teal text-teal value-mono text-xs flex items-center gap-1">{playing ? <Pause size={12} /> : <Play size={12} />}{playing ? copy.pause : copy.play}</button> : null}
      {result && <div className="ml-auto value-mono text-xs"><span className={result.delta.absolute >= 0 ? "text-signal" : "text-ok"}>{result.delta.absolute >= 0 ? "+" : ""}{result.delta.absolute} · {result.delta.percent ?? "new"}%</span><span className="text-dim ml-2">{result.current.rows} vs {result.previous.rows}</span></div>}
    </div>
    {result?.frames.length ? <div><input aria-label="Hotspot playback frame" type="range" min={0} max={result.frames.length - 1} value={frame} onChange={(event) => { setPlaying(false); setFrame(Number(event.target.value)); }} className="w-full accent-amber" /><div className="flex justify-between value-mono text-[10px] text-dim"><span>{result.frames[frame].from}</span><span>{copy.frame} {frame + 1}/{result.frames.length} · {result.frames[frame].rows} {copy.rows}</span><span>{result.frames[frame].to}</span></div></div> : null}
    {result && <div className="grid sm:grid-cols-2 gap-2 value-mono text-[10px]">{result.areas.slice(0, 3).map((row) => <div key={`area-${row.key}`} className="border-t border-line pt-1"><span>{row.key}</span><span className={row.absolute >= 0 ? "text-signal float-right" : "text-ok float-right"}>{row.absolute >= 0 ? "+" : ""}{row.absolute}</span></div>)}{result.categories.slice(0, 3).map((row) => <div key={`category-${row.key}`} className="border-t border-line pt-1"><span>{row.key}</span><span className={row.absolute >= 0 ? "text-signal float-right" : "text-ok float-right"}>{row.absolute >= 0 ? "+" : ""}{row.absolute}</span></div>)}</div>}
    {result && !result.available && <div className="value-mono text-xs text-amber">{result.reason ?? copy.unavailable}</div>}
    {error && <div role="status" aria-live="polite" className="value-mono text-xs text-signal">{error}</div>}
    {result && <div className="value-mono text-[9px] text-dim">{copy.evidence} {result.evidence_id} · version {result.dataset_version} · generated {new Date(result.generated_at).toLocaleString("en-IN", { hour12: false })}</div>}
  </div>;
}
