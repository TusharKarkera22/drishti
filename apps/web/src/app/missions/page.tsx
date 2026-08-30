"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Clipboard, FileText, MapPinned, Network, Radar, Send, ShieldCheck } from "lucide-react";
import Shell from "@/components/Shell";
import PageIntro from "@/components/PageIntro";
import { contextFromSearchParams, INVESTIGATION_CONTEXT_VERSION, mergeContextIntoHref, type DecodedInvestigationContext, type InvestigationKind } from "@/lib/investigation-context";
import { getInsights, getInsightsBrief, runAgent, type InsightsResponse } from "@/lib/api";
import { useLang } from "@/lib/i18n";

const MISSIONS: { id: InvestigationKind; title: string; titleKn: string; question: string; questionKn: string; playbook: string; Icon: typeof Radar }[] = [
  { id: "emerging-threat", title: "Emerging Threat", titleKn: "ಹೊರಹೊಮ್ಮುವ ಬೆದರಿಕೆ", question: "What changed, where, and how strongly?", questionKn: "ಏನು, ಎಲ್ಲಿ ಮತ್ತು ಎಷ್ಟು ಬದಲಾಗಿದೆ?", playbook: "trend_sentinel", Icon: Radar },
  { id: "hotspot-patrol", title: "Hotspot Patrol", titleKn: "ಹಾಟ್‌ಸ್ಪಾಟ್ ಗಸ್ತು", question: "Where is activity concentrating and when?", questionKn: "ಚಟುವಟಿಕೆ ಎಲ್ಲಿ ಮತ್ತು ಯಾವಾಗ ಕೇಂದ್ರೀಕೃತವಾಗಿದೆ?", playbook: "patrol_planner", Icon: MapPinned },
  { id: "case-linkage", title: "Case Linkage", titleKn: "ಪ್ರಕರಣ ಸಂಪರ್ಕ", question: "Which cases or entities share evidence?", questionKn: "ಯಾವ ಪ್ರಕರಣಗಳು ಅಥವಾ ಘಟಕಗಳು ಸಾಕ್ಷ್ಯ ಹಂಚಿಕೊಳ್ಳುತ್ತವೆ?", playbook: "case_linker", Icon: Network },
];

function MissionWorkspace({ decoded, lang }: { decoded: DecodedInvestigationContext; lang: "en" | "kn" }) {
  const ds = decoded.context.dataset ?? "";
  const initial = decoded.context.investigation ?? "emerging-threat";
  const [mission, setMission] = useState<InvestigationKind>(initial);
  const [area, setArea] = useState(decoded.context.area ?? "");
  const [question, setQuestion] = useState("");
  const [insights, setInsights] = useState<InsightsResponse | null>(null);
  const [brief, setBrief] = useState<{ text: string; source: string } | null>(null);
  const [answer, setAnswer] = useState<{ key: string; report: string; steps: { tool: string; result_preview: string }[] } | null>(null);
  const askId = useRef(0);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(decoded.discarded.length ? `Some link state was discarded: ${decoded.discarded.join(", ")}` : "");
  const selected = MISSIONS.find((item) => item.id === mission)!;
  const c = (english: string, kannada: string) => lang === "kn" ? kannada : english;
  const selectedTitle = lang === "kn" ? selected.titleKn : selected.title;
  const selectedQuestion = lang === "kn" ? selected.questionKn : selected.question;
  const context = useMemo(() => ({ ...decoded.context, version: INVESTIGATION_CONTEXT_VERSION, dataset: ds, investigation: mission, area: area || undefined }), [decoded.context, ds, mission, area]);
  const contextKey = `${ds}|${lang}|${mission}|${area}`;
  useEffect(() => { askId.current += 1; }, [contextKey]);
  useEffect(() => { if (!ds) return; let active = true; Promise.all([getInsights(ds, lang), getInsightsBrief(ds, lang)]).then(([i, b]) => { if (!active) return; setInsights(i); setBrief({ text: b.brief, source: b.source }); }).catch(() => { if (active) setNotice("Deterministic mission evidence is temporarily unavailable."); }); return () => { active = false; }; }, [ds, lang]);
  if (!ds) return <div className="panel p-8 text-center text-dim">Choose a dataset before launching Mission Control.</div>;
  const ask = async () => { if (!question.trim()) return; const requestId = ++askId.current; setBusy(true); setAnswer(null); try { const prompt = `${question.trim()}\n\nSelected operational context: mission=${mission}; area=${area || "all areas"}. Use tools for every factual claim and distinguish associations from verified facts.`; const value = await runAgent(ds, selected.playbook, prompt, lang); if (askId.current === requestId) setAnswer({ key: contextKey, report: value.report, steps: value.steps }); } catch { if (askId.current === requestId) setNotice("Narrative service is unavailable. Deterministic evidence and the fallback briefing remain below."); } finally { if (askId.current === requestId) setBusy(false); } };
  const share = async () => { const url = new URL(mergeContextIntoHref(window.location.pathname, context), window.location.origin).toString(); await navigator.clipboard.writeText(url); setNotice("Safe investigation link copied. No prompt, raw row, or memory is included."); };
  return <div className="space-y-5 print:text-black">
    <div className="grid md:grid-cols-3 gap-3 print:hidden">{MISSIONS.map((item) => <button key={item.id} aria-pressed={mission === item.id} onClick={() => setMission(item.id)} className={`panel p-4 text-left border ${mission === item.id ? "border-amber" : "border-line"}`}><item.Icon size={18} className={mission === item.id ? "text-amber" : "text-dim"} /><div className="font-display uppercase tracking-wider mt-3">{lang === "kn" ? item.titleKn : item.title}</div><p className="text-xs text-dim mt-1">{lang === "kn" ? item.questionKn : item.question}</p></button>)}</div>
    {notice && <div role="status" aria-live="polite" className="value-mono text-xs text-amber">{notice}</div>}
    <div className="grid xl:grid-cols-[260px_1fr_320px] gap-4">
      <aside className="panel p-4 space-y-4"><div><div className="label-hud">{c("Mission", "ಕಾರ್ಯಾಚರಣೆ")}</div><div className="font-display text-lg text-amber mt-1">{selectedTitle}</div></div><label className="block"><span className="label-hud">{c("Selected district / area", "ಆಯ್ದ ಜಿಲ್ಲೆ / ಪ್ರದೇಶ")}</span><input value={area} onChange={(e) => setArea(e.target.value)} placeholder={c("All areas", "ಎಲ್ಲಾ ಪ್ರದೇಶಗಳು")} maxLength={120} className="mt-2 w-full bg-ink-3 border border-line px-3 py-2 text-sm" /></label><ol className="space-y-2 value-mono text-[11px] text-dim"><li className="text-teal">01 {c("Context", "ಸಂದರ್ಭ")}</li><li>02 {c("Investigate", "ತನಿಖೆ")}</li><li>03 {c("Evidence", "ಸಾಕ್ಷ್ಯ")}</li><li>04 {c("Briefing", "ಸಂಕ್ಷಿಪ್ತ ವರದಿ")}</li></ol><div className="flex flex-wrap gap-2 print:hidden"><button onClick={() => void share()} className="px-2 py-1 border border-teal text-teal value-mono text-[10px] flex items-center gap-1"><Clipboard size={11} /> {c("Share", "ಹಂಚಿ")}</button><Link href={mergeContextIntoHref("/tracker/", context)} className="px-2 py-1 border border-amber text-amber value-mono text-[10px]">{c("Pin", "ಪಿನ್")}</Link><button onClick={() => window.print()} className="px-2 py-1 border border-line text-dim value-mono text-[10px] flex items-center gap-1"><FileText size={11} /> {c("Print", "ಮುದ್ರಿಸಿ")}</button></div></aside>
      <main className="space-y-4"><section className="panel p-4"><label htmlFor="mission-question" className="label-hud mb-3 block">{c("Ask about this context", "ಈ ಸಂದರ್ಭದ ಬಗ್ಗೆ ಕೇಳಿ")}</label><div className="flex gap-2 print:hidden"><textarea id="mission-question" value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={800} placeholder={`${c("Ask", "ಕೇಳಿ")}: ${selectedQuestion}`} className="flex-1 min-h-20 bg-ink-3 border border-line p-3 text-sm" /><button aria-label={c("Send investigation question", "ತನಿಖಾ ಪ್ರಶ್ನೆಯನ್ನು ಕಳುಹಿಸಿ")} disabled={busy} onClick={() => void ask()} className="self-end px-4 py-2 border border-amber text-amber disabled:opacity-50"><Send size={16} /></button></div>{answer?.key === contextKey && <div className="mt-4"><p className="text-sm leading-relaxed whitespace-pre-wrap">{answer.report}</p><div className="mt-4 border-t border-line pt-3"><div className="label-hud mb-2">{c("Tool trace", "ಸಾಧನ ಪಥ")}</div>{answer.steps.map((step, index) => <div key={index} className="value-mono text-[10px] text-dim mb-1"><span className="text-teal">{step.tool}</span> — {step.result_preview}</div>)}</div></div>}</section><section className="panel p-4"><div className="label-hud mb-3">{c("Mission briefing", "ಕಾರ್ಯಾಚರಣೆ ವರದಿ")} · {brief?.source === "llm" ? c("interpreted draft", "ವ್ಯಾಖ್ಯಾನಿತ ಕರಡು") : c("deterministic fallback", "ನಿರ್ಣಾಯಕ ಪರ್ಯಾಯ")}</div><p className="text-sm leading-relaxed whitespace-pre-wrap">{brief?.text ?? c("Loading evidence-backed briefing…", "ಸಾಕ್ಷ್ಯಾಧಾರಿತ ವರದಿ ಲೋಡ್ ಆಗುತ್ತಿದೆ…")}</p></section></main>
      <aside className="panel p-4"><div className="label-hud text-teal flex items-center gap-2 mb-4"><ShieldCheck size={14} /> {c("Trust & provenance", "ವಿಶ್ವಾಸ ಮತ್ತು ಮೂಲ")}</div><Trust label={c("Dataset", "ಡೇಟಾಸೆಟ್")} value={ds} /><Trust label={c("Generated", "ರಚಿಸಲಾಗಿದೆ")} value={insights?.generated_at ? new Date(insights.generated_at).toLocaleString("en-IN", { hour12: false }) : c("loading", "ಲೋಡ್ ಆಗುತ್ತಿದೆ")} /><Trust label={c("Signals", "ಸಂಕೇತಗಳು")} value={insights?.signals_used.join(", ") || c("loading", "ಲೋಡ್ ಆಗುತ್ತಿದೆ")} /><Trust label={c("Findings", "ಫಲಿತಾಂಶಗಳು")} value={String(insights?.findings.length ?? 0)} /><Trust label={c("Backtest", "ಹಿಂದಿನ ಪರೀಕ್ಷೆ")} value={insights?.backtest.available ? `${Math.round((insights.backtest.capture_rate ?? 0) * 100)}% capture · ${insights.backtest.folds} folds` : insights?.backtest.reason ?? c("unavailable", "ಲಭ್ಯವಿಲ್ಲ")} /><Trust label={c("Narrative", "ವಿವರಣೆ")} value={brief?.source === "llm" ? c("AI draft — verify against evidence", "AI ಕರಡು — ಸಾಕ್ಷ್ಯದೊಂದಿಗೆ ಪರಿಶೀಲಿಸಿ") : c("fallback — no model dependency", "ಪರ್ಯಾಯ — ಮಾದರಿ ಅವಲಂಬನೆ ಇಲ್ಲ")} /><p className="value-mono text-[9px] text-dim border-t border-line pt-3 mt-3">{c("Synthetic demo data. Human review required. Associations are investigative leads, not verified allegations or deployment instructions.", "ಸಂಶ್ಲೇಷಿತ ಡೆಮೊ ಡೇಟಾ. ಮಾನವ ಪರಿಶೀಲನೆ ಅಗತ್ಯ. ಸಂಬಂಧಗಳು ತನಿಖಾ ಸುಳಿವುಗಳು ಮಾತ್ರ; ದೃಢೀಕೃತ ಆರೋಪಗಳು ಅಥವಾ ನಿಯೋಜನಾ ಸೂಚನೆಗಳಲ್ಲ.")}</p></aside>
    </div>
  </div>;
}

function MissionsInner() {
  const params = useSearchParams();
  const { lang } = useLang();
  const query = params.toString();
  return <MissionWorkspace key={`${query}|${lang}`} decoded={contextFromSearchParams(query)} lang={lang} />;
}

function Trust({ label, value }: { label: string; value: string }) { return <div className="border-t border-line/60 py-2"><div className="label-hud">{label}</div><div className="value-mono text-[11px] text-text mt-1 break-words">{value}</div></div>; }
export default function MissionsPage() { const { lang } = useLang(); return <Shell title={lang === "kn" ? "ದೃಷ್ಟಿ ಕಾರ್ಯಾಚರಣೆ ನಿಯಂತ್ರಣ" : "Drishti Mission Control"}><PageIntro id="missions" text={lang === "kn" ? "ಕಾರ್ಯಾಚರಣೆಯ ಪ್ರಶ್ನೆಯನ್ನು ಆಯ್ಕೆ ಮಾಡಿ, ನಿರ್ಣಾಯಕ ಸಾಕ್ಷ್ಯ ಪರಿಶೀಲಿಸಿ, ಸಂದರ್ಭಾಧಾರಿತ ಪ್ರಶ್ನೆ ಕೇಳಿ ಮತ್ತು ಅದೇ ಸಂದರ್ಭವನ್ನು ಹಂಚಿಕೊಳ್ಳಿ." : "Choose an operational question, inspect deterministic evidence, ask a grounded follow-up, then share or brief the exact context."} /><Suspense><MissionsInner /></Suspense></Shell>; }
