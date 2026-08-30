"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import Shell from "@/components/Shell";
import PageIntro from "@/components/PageIntro";
import { contextFromSearchParams, contextToPersistedState, daysBefore, INVESTIGATION_CONTEXT_VERSION, mergeContextIntoHref, type InvestigationContext } from "@/lib/investigation-context";
import { createInvestigationCard, createWatchRule, deleteInvestigationCard, deleteWatchRule, evaluateWatchRule, listInvestigationCards, listWatchEvents, listWatchRules, updateInvestigationCard, updateWatchRule, type InvestigationCard, type InvestigationPriority, type WatchEvent, type WatchRule } from "@/lib/api";
import { useLang } from "@/lib/i18n";

const statuses: InvestigationCard["status"][] = ["new", "reviewing", "actioned", "resolved"];
const priorities: InvestigationPriority[] = ["low", "medium", "high", "critical"];
const COPY = {
  en: { persistence: "Demo-instance persistence", persistenceBody: "Cards and rules survive navigation but may reset when Catalyst recycles or redeploys the instance. Shared URLs remain self-contained.", pin: "Pin current investigation", watch: "Create aggregate watch rule", pinAction: "Pin", watchAction: "Watch", owner: "Owner", notes: "Notes", remove: "Delete", evaluate: "Evaluate", rules: "Watch rules", events: "Rule events", unavailable: "Tracker state is unavailable." },
  kn: { persistence: "ಡೆಮೊ-ಇನ್‌ಸ್ಟಾನ್ಸ್ ಸಂಗ್ರಹ", persistenceBody: "ಕಾರ್ಡ್‌ಗಳು ಮತ್ತು ನಿಯಮಗಳು ನ್ಯಾವಿಗೇಶನ್‌ನಲ್ಲಿ ಉಳಿಯುತ್ತವೆ; Catalyst ಮರುಪ್ರಾರಂಭ ಅಥವಾ ಮರುನಿಯೋಜನೆಯಾಗಿದಾಗ ಅಳಿಯಬಹುದು. ಹಂಚಿದ URL ಗಳು ಸ್ವತಂತ್ರವಾಗಿರುತ್ತವೆ.", pin: "ಪ್ರಸ್ತುತ ತನಿಖೆಯನ್ನು ಪಿನ್ ಮಾಡಿ", watch: "ಒಟ್ಟು ವೀಕ್ಷಣಾ ನಿಯಮ ರಚಿಸಿ", pinAction: "ಪಿನ್", watchAction: "ವೀಕ್ಷಿಸಿ", owner: "ಮಾಲೀಕ", notes: "ಟಿಪ್ಪಣಿಗಳು", remove: "ಅಳಿಸಿ", evaluate: "ಮೌಲ್ಯಮಾಪನ", rules: "ವೀಕ್ಷಣಾ ನಿಯಮಗಳು", events: "ನಿಯಮ ಘಟನೆಗಳು", unavailable: "ಟ್ರ್ಯಾಕರ್ ಸ್ಥಿತಿ ಲಭ್ಯವಿಲ್ಲ." },
} as const;

async function fetchTrackerState(ds: string) {
  const [cards, rules, events] = await Promise.all([listInvestigationCards(ds), listWatchRules(ds), listWatchEvents(ds)]);
  return { cards, rules, events };
}

function TrackerWorkspace({ context, lang }: { context: InvestigationContext; lang: "en" | "kn" }) {
  const copy = COPY[lang];
  const ds = context.dataset ?? "";
  const [cards, setCards] = useState<InvestigationCard[]>([]);
  const [rules, setRules] = useState<WatchRule[]>([]);
  const [events, setEvents] = useState<WatchEvent[]>([]);
  const [title, setTitle] = useState(context.area ? `${context.area} investigation` : "Current investigation");
  const [priority, setPriority] = useState<InvestigationPriority>("medium");
  const [owner, setOwner] = useState("");
  const [notes, setNotes] = useState("");
  const [ruleName, setRuleName] = useState("Emerging activity watch");
  const [threshold, setThreshold] = useState(25);
  const [message, setMessage] = useState("");
  const requestId = useRef(0);
  const applyState = useCallback((next: Awaited<ReturnType<typeof fetchTrackerState>>) => { setCards(next.cards); setRules(next.rules); setEvents(next.events); }, []);
  const reload = useCallback(async () => {
    if (!ds) return;
    const id = ++requestId.current;
    try { const next = await fetchTrackerState(ds); if (id === requestId.current) applyState(next); }
    catch { if (id === requestId.current) setMessage(copy.unavailable); }
  }, [ds, applyState, copy.unavailable]);
  useEffect(() => { const timer = window.setTimeout(() => void reload(), 0); return () => { window.clearTimeout(timer); requestId.current += 1; }; }, [reload]);

  if (!ds) return <div className="panel p-8 text-center text-dim">Choose a dataset before opening Tracker.</div>;
  const mutate = async (action: () => Promise<unknown>, notice = "") => { await action(); if (notice) setMessage(notice); await reload(); };
  const save = () => mutate(() => createInvestigationCard(ds, { title, kind: context.node ? "entity" : context.area ? "area" : "mission", target: context.node ?? context.area ?? "", priority, owner, notes, state: contextToPersistedState(context) }), "Investigation pinned. Demo-instance state may reset after redeployment.");
  const addRule = async () => { const to = context.to ?? new Date().toISOString().slice(0, 10); const from = context.from ?? daysBefore(to, 28); const rule = await createWatchRule(ds, { name: ruleName, metric: "percent_change", operator: "gte", threshold, from_date: from, to_date: to, area: context.area ?? "", category: context.category ?? "", enabled: true }); await evaluateWatchRule(ds, rule.id); setMessage("Watch evaluated against the selected period."); await reload(); };

  return <div className="space-y-5">
    <div className="panel p-4 border-l-2 border-amber"><div className="label-hud text-amber mb-1">{copy.persistence}</div><p className="text-xs text-dim">{copy.persistenceBody}</p></div>
    <div className="grid lg:grid-cols-2 gap-4">
      <section className="panel p-4 space-y-2"><label htmlFor="tracker-title" className="label-hud block">{copy.pin}</label><input id="tracker-title" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={160} className="w-full bg-ink-3 border border-line px-3 py-2 text-sm" /><div className="grid grid-cols-2 gap-2"><select aria-label="Priority" value={priority} onChange={(event) => setPriority(event.target.value as InvestigationPriority)} className="bg-ink-3 border border-line px-2 text-xs">{priorities.map((value) => <option key={value}>{value}</option>)}</select><input aria-label={copy.owner} value={owner} onChange={(event) => setOwner(event.target.value)} maxLength={80} placeholder={copy.owner} className="bg-ink-3 border border-line px-2 text-xs" /></div><textarea aria-label={copy.notes} value={notes} onChange={(event) => setNotes(event.target.value)} maxLength={2000} placeholder={copy.notes} className="w-full bg-ink-3 border border-line px-2 py-1 text-xs" /><button onClick={() => void save()} className="px-4 py-2 border border-amber text-amber value-mono text-xs">{copy.pinAction}</button></section>
      <section className="panel p-4"><label htmlFor="rule-name" className="label-hud mb-3 block">{copy.watch}</label><div className="flex gap-2"><input id="rule-name" value={ruleName} onChange={(event) => setRuleName(event.target.value)} maxLength={120} className="flex-1 bg-ink-3 border border-line px-3 py-2 text-sm" /><input aria-label="Percent threshold" type="number" value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} className="w-20 bg-ink-3 border border-line px-2 value-mono text-xs" /><button onClick={() => void addRule()} className="px-3 border border-teal text-teal value-mono text-xs">{copy.watchAction}</button></div></section>
    </div>
    {message && <div role="status" aria-live="polite" className="value-mono text-xs text-teal">{message}</div>}
    <div className="grid xl:grid-cols-4 gap-3">{statuses.map((status) => <section key={status} className="panel p-3 min-h-48"><div className="label-hud mb-3">{status}</div>{cards.filter((card) => card.status === status).map((card) => <article key={card.id} className="bg-ink-3 border border-line p-3 mb-2 space-y-2"><div className="text-sm text-text">{card.title}</div><div className="flex gap-2"><select aria-label={`Status for ${card.title}`} value={card.status} onChange={(event) => void mutate(() => updateInvestigationCard(ds, card.id, { status: event.target.value as InvestigationCard["status"] }))} className="bg-ink-2 border border-line value-mono text-[9px]">{statuses.map((value) => <option key={value}>{value}</option>)}</select><select aria-label={`Priority for ${card.title}`} value={card.priority} onChange={(event) => void mutate(() => updateInvestigationCard(ds, card.id, { priority: event.target.value as InvestigationPriority }))} className="bg-ink-2 border border-line value-mono text-[9px]">{priorities.map((value) => <option key={value}>{value}</option>)}</select></div><input aria-label={`${copy.owner} for ${card.title}`} defaultValue={card.owner} maxLength={80} onBlur={(event) => void mutate(() => updateInvestigationCard(ds, card.id, { owner: event.target.value }))} placeholder={copy.owner} className="w-full bg-ink-2 border border-line px-2 value-mono text-[9px]" /><textarea aria-label={`${copy.notes} for ${card.title}`} defaultValue={card.notes} maxLength={2000} onBlur={(event) => void mutate(() => updateInvestigationCard(ds, card.id, { notes: event.target.value }))} placeholder={copy.notes} className="w-full bg-ink-2 border border-line px-2 value-mono text-[9px]" /><div className="flex gap-3"><Link href={mergeContextIntoHref(card.kind === "entity" ? "/network/" : "/map/", { version: INVESTIGATION_CONTEXT_VERSION, dataset: ds, ...card.state })} className="value-mono text-[10px] text-teal">Open</Link><button onClick={() => void mutate(() => deleteInvestigationCard(ds, card.id))} className="value-mono text-[10px] text-signal">{copy.remove}</button></div></article>)}</section>)}</div>
    <div className="grid lg:grid-cols-2 gap-4"><section className="panel p-4"><div className="label-hud mb-3">{copy.rules}</div>{rules.map((rule) => <div key={rule.id} className="border-t border-line py-2 grid grid-cols-[1fr_auto] gap-2 text-xs"><div><div>{rule.name}</div><input aria-label={`Threshold for ${rule.name}`} type="number" defaultValue={rule.threshold} onBlur={(event) => void mutate(() => updateWatchRule(ds, rule.id, { threshold: Number(event.target.value) }))} className="mt-1 w-20 bg-ink-3 border border-line px-1 value-mono text-[9px]" />%</div><div className="flex items-center gap-2"><button aria-pressed={rule.enabled} className={rule.enabled ? "value-mono text-ok" : "value-mono text-dim"} onClick={() => void mutate(() => updateWatchRule(ds, rule.id, { enabled: !rule.enabled }))}>{rule.enabled ? "On" : "Off"}</button><button disabled={!rule.enabled} className="value-mono text-teal disabled:opacity-40" onClick={() => void mutate(() => evaluateWatchRule(ds, rule.id))}>{copy.evaluate}</button><button className="value-mono text-signal" onClick={() => void mutate(() => deleteWatchRule(ds, rule.id))}>{copy.remove}</button></div></div>)}</section><section className="panel p-4"><div className="label-hud mb-3">{copy.events}</div>{events.map((event) => <div key={event.id} className="border-t border-line py-2 text-xs"><span className={event.matched ? "text-signal" : "text-dim"}>{event.rule_name}: {event.value ?? "n/a"}%</span><div className="value-mono text-[9px] text-dim">{event.evidence_id}</div></div>)}</section></div>
  </div>;
}

function TrackerInner() {
  const params = useSearchParams();
  const { lang } = useLang();
  const query = params.toString();
  return <TrackerWorkspace key={`${query}|${lang}`} context={contextFromSearchParams(query).context} lang={lang} />;
}

export default function TrackerPage() { const { lang } = useLang(); return <Shell title={lang === "kn" ? "ತನಿಖಾ ಟ್ರ್ಯಾಕರ್" : "Investigation Tracker"}><PageIntro id="tracker" text={lang === "kn" ? "ವಿಶ್ಲೇಷಣಾ ಸ್ಥಿತಿಯನ್ನು ಪಿನ್ ಮಾಡಿ, ಪರಿಶೀಲನಾ ಹಂತಗಳಲ್ಲಿ ಸಾಗಿಸಿ ಮತ್ತು ಮಾನವ-ನಿರ್ಧರಿತ ಒಟ್ಟು ವೀಕ್ಷಣಾ ನಿಯಮಗಳನ್ನು ಮೌಲ್ಯಮಾಪನ ಮಾಡಿ." : "Pin analytical state, move it through review, and evaluate human-defined aggregate watch rules."} /><Suspense><TrackerInner /></Suspense></Shell>; }
