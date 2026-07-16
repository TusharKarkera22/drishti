"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import Shell from "@/components/Shell";
import PageIntro from "@/components/PageIntro";
import {
  getPlaybooks, runAgent,
  listThreads, getThread, getAgentMemory, clearAgentMemory,
  type AgentThreadHeader, type AgentMemoryItem,
} from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { ArrowLeft, Send, Loader2, History, Plus, Brain, X, Trash2 } from "lucide-react";

type Playbook = { id: string; name: string; description: string };
type Step = { tool: string; args: Record<string, unknown>; result_preview: string };
type Msg = { role: "user" | "agent"; text: string; steps?: Step[] };

// Each playbook id maps to a Nano-Banana agent avatar in public/agents/.
const AVATARS: Record<string, string> = {
  analyst: "/app/agents/analyst.png",
  patrol_planner: "/app/agents/patrol_planner.png",
  case_linker: "/app/agents/case_linker.png",
  trend_sentinel: "/app/agents/trend_sentinel.png",
};
const avatarFor = (id: string) => AVATARS[id] ?? "/app/drishti-emblem.png";

function relTime(iso?: string) {
  if (!iso) return "";
  const ms = new Date(iso).getTime();
  if (Number.isNaN(ms)) return "";
  const s = Math.max(0, (Date.now() - ms) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function AgentsInner() {
  const params = useSearchParams();
  const { t, lang } = useLang();
  const ds = params.get("ds") ?? "";
  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);
  const [selected, setSelected] = useState<Playbook | null>(null);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [threads, setThreads] = useState<AgentThreadHeader[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [memory, setMemory] = useState<AgentMemoryItem[]>([]);
  const [showMemory, setShowMemory] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getPlaybooks().then(setPlaybooks).catch(() => {});
  }, []);
  useEffect(() => {
    if (ds) getAgentMemory(ds).then(setMemory).catch(() => {});
  }, [ds]);
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, running]);

  const refreshThreads = (pid: string) => {
    if (!ds) return;
    listThreads(ds, pid).then(setThreads).catch(() => setThreads([]));
  };

  const open = (p: Playbook) => {
    setSelected(p);
    setMessages([]);
    setThreadId(null);
    setInput("");
    setShowHistory(false);
    refreshThreads(p.id);
  };
  const back = () => {
    setSelected(null);
    setMessages([]);
    setThreadId(null);
  };
  const newChat = () => {
    setMessages([]);
    setThreadId(null);
    setShowHistory(false);
  };
  const openThread = async (tid: string) => {
    if (!ds) return;
    setShowHistory(false);
    try {
      const th = await getThread(ds, tid);
      setMessages(th.turns.map((tn) => ({ role: tn.role, text: tn.text, steps: tn.steps })));
      setThreadId(th.thread_id);
    } catch {
      /* ignore */
    }
  };

  const send = async () => {
    if (!selected || running) return;
    const q = input.trim();
    setRunning(true);
    setInput("");
    setMessages((m) => [...m, { role: "user", text: q || t("agents.runStandard", "Run standard playbook") }]);
    try {
      const r = await runAgent(ds, selected.id, q, lang, threadId ?? undefined);
      setThreadId(r.thread_id);
      setMessages((m) => [...m, { role: "agent", text: r.report, steps: r.steps }]);
      refreshThreads(selected.id);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "agent", text: `${t("agents.error", "Agent unavailable — is a dataset open and the LLM reachable?")}\n\n${String(e)}` },
      ]);
    } finally {
      setRunning(false);
    }
  };

  const openMemory = () => {
    if (ds) getAgentMemory(ds).then(setMemory).catch(() => {});
    setShowMemory(true);
  };
  const doClearMemory = async () => {
    if (!ds) return;
    try {
      await clearAgentMemory(ds);
      setMemory([]);
    } catch {
      /* ignore */
    }
  };

  // Memory panel overlay (shared, dataset-scoped) — rendered in both views.
  const memoryPanel = showMemory ? (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-ink/70 p-4 pt-24"
      onClick={() => setShowMemory(false)}
    >
      <div className="panel w-full max-w-lg p-4 border border-line" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-1">
          <div className="font-display uppercase tracking-wider text-amber flex items-center gap-2">
            <Brain size={16} /> {t("agents.memory", "Memory")}
          </div>
          <button onClick={() => setShowMemory(false)} className="text-dim hover:text-amber">
            <X size={16} />
          </button>
        </div>
        <div className="text-dim text-xs mb-3">
          {t("agents.memorySub", "Shared across all agents for this dataset.")}
        </div>
        {memory.length === 0 ? (
          <div className="text-dim text-sm value-mono py-6 text-center">
            {t("agents.memoryEmpty", "Nothing remembered yet. Chat with an agent and it will note key entities, findings, and your focus here.")}
          </div>
        ) : (
          <div className="space-y-2 max-h-[50vh] overflow-y-auto pr-1">
            {memory.map((it) => (
              <div key={it.id} className="flex gap-2 text-sm">
                <span className="label-hud text-teal shrink-0 mt-0.5">{it.kind}</span>
                <span className="text-text leading-snug">{it.text}</span>
              </div>
            ))}
          </div>
        )}
        {memory.length > 0 && (
          <div className="mt-3 pt-3 border-t border-line flex justify-end">
            <button
              onClick={doClearMemory}
              className="value-mono text-xs text-signal hover:text-amber flex items-center gap-1.5"
            >
              <Trash2 size={13} /> {t("agents.clear", "Clear memory")}
            </button>
          </div>
        )}
      </div>
    </div>
  ) : null;

  // ---------------- GRID VIEW ----------------
  if (!selected) {
    return (
      <div className="max-w-5xl mx-auto">
        {memoryPanel}
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <h2 className="font-display text-xl uppercase tracking-wider text-text mb-1">
              {t("agents.consoleTitle", "Agentic Console")}
            </h2>
            <p className="text-sm text-dim leading-relaxed max-w-2xl">
              {t("agents.consoleSub", "Pick an agent. Each one plans, calls live tools on your data, and explains every step — choose one to open its chat.")}
            </p>
          </div>
          {ds && (
            <button
              onClick={openMemory}
              className="shrink-0 panel px-3 py-2 border border-line hover:border-amber/50 flex items-center gap-2 value-mono text-xs text-teal"
              title={t("agents.memory", "Memory")}
            >
              <Brain size={14} /> {memory.length} {t("agents.remembered", "remembered")}
            </button>
          )}
        </div>

        <div className="grid sm:grid-cols-2 gap-4">
          {playbooks.map((p) => (
            <button
              key={p.id}
              onClick={() => open(p)}
              className="panel p-4 flex items-start gap-4 text-left hover:bg-ink-3/60 hover:border-amber/50 border border-line transition-colors group"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={avatarFor(p.id)} alt={p.name} width={66} height={66} className="rounded-md shrink-0 border border-line" />
              <div className="min-w-0">
                <div className="font-display text-lg uppercase tracking-wider text-amber">{p.name}</div>
                <div className="text-dim text-sm mt-1 leading-relaxed">{p.description}</div>
                <div className="label-hud mt-2 text-teal opacity-60 group-hover:opacity-100 transition-opacity">
                  {t("agents.openChat", "Open chat →")}
                </div>
              </div>
            </button>
          ))}
          {!playbooks.length && (
            <div className="text-dim text-sm value-mono animate-pulse">{t("agents.loading", "Loading agents…")}</div>
          )}
        </div>

        {!ds && (
          <div className="panel p-3 mt-5 value-mono text-xs text-amber border border-amber/40">
            {t("agents.noDataset", "Open a dataset from the home screen to run an agent.")}
          </div>
        )}
      </div>
    );
  }

  // ---------------- CHAT VIEW ----------------
  return (
    <div className="max-w-3xl mx-auto flex flex-col h-[calc(100vh-7.5rem)]">
      {memoryPanel}
      {/* header */}
      <div className="flex items-center gap-3 pb-3 border-b border-line shrink-0">
        <button
          onClick={back}
          className="w-8 h-8 flex items-center justify-center text-dim hover:text-amber transition-colors"
          title={t("agents.backToAgents", "Back to agents")}
        >
          <ArrowLeft size={18} />
        </button>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={avatarFor(selected.id)} alt={selected.name} width={42} height={42} className="rounded-md border border-line" />
        <div className="min-w-0 flex-1">
          <div className="font-display uppercase tracking-wider text-amber leading-none">{selected.name}</div>
          <div className="text-dim text-xs mt-1 truncate">{selected.description}</div>
        </div>
        {/* history + new chat */}
        <div className="relative shrink-0">
          <button
            onClick={() => { if (!showHistory) refreshThreads(selected.id); setShowHistory((s) => !s); }}
            className="px-2.5 py-1.5 border border-line text-dim hover:text-amber hover:border-amber/50 flex items-center gap-1.5 value-mono text-xs"
            title={t("agents.history", "History")}
          >
            <History size={14} /> {t("agents.history", "History")}
          </button>
          {showHistory && (
            <div className="absolute right-0 mt-1 w-72 panel border border-line z-30 max-h-80 overflow-y-auto">
              <button
                onClick={newChat}
                className="w-full text-left px-3 py-2 border-b border-line text-teal hover:bg-ink-3/60 flex items-center gap-2 value-mono text-xs"
              >
                <Plus size={13} /> {t("agents.newChat", "New chat")}
              </button>
              {threads.length === 0 ? (
                <div className="px-3 py-4 text-dim text-xs value-mono">
                  {t("agents.noThreads", "No saved conversations yet.")}
                </div>
              ) : (
                threads.map((th) => (
                  <button
                    key={th.thread_id}
                    onClick={() => openThread(th.thread_id)}
                    className={`w-full text-left px-3 py-2 hover:bg-ink-3/60 border-b border-line/50 ${th.thread_id === threadId ? "bg-ink-3/40" : ""}`}
                  >
                    <div className="text-sm text-text truncate">{th.title}</div>
                    <div className="value-mono text-[10px] text-dim mt-0.5">{relTime(th.updated_at)}</div>
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      </div>

      {/* conversation */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto py-4 space-y-4 pr-1">
        {!messages.length && !running && (
          <div className="text-dim text-sm text-center mt-12 value-mono">
            {t("agents.startHint", "Ask a question — or just hit send to run the standard playbook.")}
          </div>
        )}
        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="bg-amber/15 border border-amber/40 px-3 py-2 max-w-[80%] text-sm text-text rounded-sm">
                {m.text}
              </div>
            </div>
          ) : (
            <div key={i} className="flex gap-3 sweep-in">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={avatarFor(selected.id)} alt="" width={32} height={32} className="rounded shrink-0 border border-line h-8" />
              <div className="min-w-0 space-y-2 flex-1">
                {m.steps && m.steps.length > 0 && (
                  <details className="panel p-2">
                    <summary className="value-mono text-[11px] text-teal cursor-pointer select-none">
                      {m.steps.length} {t("agents.toolCalls", "live tool calls")}
                    </summary>
                    <div className="mt-2 space-y-1.5">
                      {m.steps.map((s, j) => (
                        <div key={j} className="value-mono text-[10px] leading-snug">
                          <span className="text-amber">[{String(j + 1).padStart(2, "0")}] {s.tool}</span>
                          <span className="text-dim break-all">
                            {" "}{JSON.stringify(s.args).slice(0, 90)} → {s.result_preview.slice(0, 130)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
                <div className="panel p-3 text-sm leading-relaxed whitespace-pre-wrap text-text">{m.text}</div>
              </div>
            </div>
          )
        )}
        {running && (
          <div className="flex items-center gap-3 text-amber">
            <Loader2 size={16} className="animate-spin" />
            <span className="value-mono text-xs animate-pulse">
              {t("agents.tracePlanning", "planning → querying → analyzing…")}
            </span>
          </div>
        )}
      </div>

      {/* composer */}
      <div className="shrink-0 pt-3 border-t border-line">
        <div className="flex items-center gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
            disabled={running}
            placeholder={
              selected.id === "case_linker"
                ? "e.g. Investigate FIR RING/2024/0002 for linked cases"
                : t("agents.chatPlaceholder", "Ask this agent anything…")
            }
            className="flex-1 bg-ink-3 border border-line px-3 py-2.5 text-sm value-mono outline-none focus:border-amber disabled:opacity-50"
          />
          <button
            onClick={send}
            disabled={running || !ds}
            className="px-4 py-2.5 font-display uppercase tracking-wider text-sm border border-amber text-amber hover:bg-amber hover:text-ink transition-colors disabled:opacity-40 flex items-center gap-2"
          >
            <Send size={15} /> {t("agents.send", "Send")}
          </button>
        </div>
        {!ds && (
          <div className="value-mono text-[11px] text-signal mt-2">
            {t("agents.noDataset", "Open a dataset from the home screen to run an agent.")}
          </div>
        )}
      </div>
    </div>
  );
}

function AgentsShell() {
  const { t } = useLang();
  return (
    <Shell title={t("agents.title", "Agents")}>
      <PageIntro
        id="agents"
        text={t(
          "agents.intro",
          "Ask in plain language. Each agent plans, runs live queries on your data, and shows every step it took."
        )}
      />
      <Suspense>
        <AgentsInner />
      </Suspense>
    </Shell>
  );
}

export default function AgentsPage() {
  return <AgentsShell />;
}
