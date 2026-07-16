"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import cytoscape from "cytoscape";
import Shell from "@/components/Shell";
import PageIntro from "@/components/PageIntro";
import { getEgo, getGraphSummary, getOffenderProfile, searchGraph, type OffenderProfile } from "@/lib/api";
import { useLang } from "@/lib/i18n";

const NODE_COLORS: Record<string, string> = {
  case: "#8aa3c0",
  accused: "#ffb000",
  victim: "#2dd4bf",
};

function NetworkInner() {
  const params = useSearchParams();
  const { t } = useLang();
  const ds = params.get("ds") ?? "";
  const cyDiv = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const [summary, setSummary] = useState<Awaited<ReturnType<typeof getGraphSummary>> | null>(null);
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Awaited<ReturnType<typeof searchGraph>>>([]);
  const [selected, setSelected] = useState("");
  const [edgeInfo, setEdgeInfo] = useState("");
  const [error, setError] = useState("");
  const [profile, setProfile] = useState<OffenderProfile | null>(null);

  useEffect(() => {
    if (!ds) return;
    setError("");
    setSummary(null);
    getGraphSummary(ds).then(setSummary).catch((e) => setError(String(e)));
  }, [ds]);

  useEffect(() => {
    if (!cyDiv.current || cyRef.current) return;
    const cy = cytoscape({
      container: cyDiv.current,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            label: "data(label)",
            color: "#c9d4e3",
            "font-size": "8px",
            "font-family": "IBM Plex Mono, monospace",
            "text-valign": "bottom",
            "text-margin-y": 4,
            width: "data(size)",
            height: "data(size)",
            "border-width": "data(border)",
            "border-color": "#ff3b30",
          },
        },
        {
          selector: "edge",
          style: {
            width: 1,
            "line-color": "#1d2836",
            "curve-style": "bezier",
          },
        },
        {
          selector: "edge[kind^='shared']",
          style: { "line-color": "#ff3b30", width: 2, "line-style": "dashed" },
        },
        {
          // money trail: same UPI/bank handle across people (mule networks)
          selector: "edge[kind='shared_upi_id']",
          style: { "line-color": "#ff9f0a", width: 2.5, "line-style": "dashed" },
        },
        {
          // fuzzy entity resolution: name variants, unconfirmed identity
          selector: "edge[kind='possible_same_person']",
          style: { "line-color": "#6b7a8f", width: 1.5, "line-style": "dotted" },
        },
      ],
      wheelSensitivity: 0.2,
    });
    cy.on("tap", "node", (e) => {
      const id = e.target.id();
      if (id.startsWith("accused:") || id.startsWith("victim:") || id.startsWith("case:")) {
        loadEgoRef.current?.(id);
      }
    });
    cy.on("tap", "edge", (e) => {
      const d = e.target.data();
      setEdgeInfo(d.kind ? `${d.kind}${d.value ? `: ${d.value}` : ""}` : "");
    });
    cyRef.current = cy;
    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, []);

  const loadEgo = useCallback(
    async (nodeId: string) => {
      if (!ds) return;
      setSelected(nodeId);
      setEdgeInfo("");
      const ego = await getEgo(ds, nodeId, 2);
      const cy = cyRef.current;
      if (!cy) return;
      cy.elements().remove();
      cy.add([
        ...ego.nodes.map((n) => ({
          data: {
            id: n.id,
            label: n.label.length > 16 ? n.label.slice(0, 15) + "…" : n.label,
            color: NODE_COLORS[n.kind] ?? "#6b7a8f",
            size: n.is_center ? 34 : n.kind === "case" ? 14 : 24,
            border: n.is_center ? 3 : 0,
          },
        })),
        ...ego.edges.map((e, i) => ({
          data: { id: `e${i}`, source: e.source, target: e.target, kind: e.kind, value: e.value },
        })),
      ]);
      cy.layout({ name: "cose", animate: false, nodeRepulsion: () => 8000 }).run();
      cy.fit(undefined, 30);
    },
    [ds]
  );
  const loadEgoRef = useRef(loadEgo);
  useEffect(() => {
    loadEgoRef.current = loadEgo;
  }, [loadEgo]);

  useEffect(() => {
    if (!ds || !selected) { setProfile(null); return; }
    let active = true;
    getOffenderProfile(ds, selected)
      .then((p) => active && setProfile(p.case_count > 0 ? p : null))
      .catch(() => active && setProfile(null));
    return () => { active = false; };
  }, [ds, selected]);

  const doSearch = useCallback(async () => {
    if (!ds || !q) return;
    setResults(await searchGraph(ds, q));
  }, [ds, q]);

  // "Not available" when the backend reports no linkable entities (400) OR the
  // graph is empty (0 nodes) — both mean there is nothing to map for this dataset.
  const unavailable = !!error || (summary !== null && summary.nodes === 0);

  if (unavailable)
    return (
      <div className="flex items-center justify-center h-[calc(100vh-10rem)]">
        <div className="panel border border-line max-w-md w-full p-8 text-center">
          <div className="text-4xl mb-4" aria-hidden>🕸️</div>
          <div className="font-display text-lg uppercase tracking-wider text-amber mb-3">
            {t("network.unavailableTitle", "Network analysis isn't available for this dataset")}
          </div>
          <p className="text-sm text-dim leading-relaxed mb-5">
            {t(
              "network.unavailableDesc",
              "Link analysis connects records through people and shared identifiers — names, phone numbers, addresses. This dataset has none, so there's no network to map."
            )}
          </p>
          <a
            href="/"
            className="value-mono text-xs px-4 py-2 border border-line text-dim hover:text-amber hover:border-amber transition-colors inline-block"
          >
            {t("network.switchDataset", "← Open a dataset with linkable people (e.g. the crime dataset)")}
          </a>
        </div>
      </div>
    );

  return (
    <div className="grid grid-cols-[280px_1fr] gap-4 h-[calc(100vh-7.5rem)]">
      <div className="space-y-4 overflow-y-auto pr-1">
        <div className="panel p-3">
          <div className="label-hud mb-2">{t("network.searchLabel", "Search Entities / Cases")}</div>
          <div className="flex gap-2">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && doSearch()}
              placeholder={t("network.searchPlaceholder", "name, FIR no…")}
              className="flex-1 bg-ink-3 border border-line px-2 py-1.5 text-xs value-mono outline-none focus:border-amber"
            />
            <button
              onClick={doSearch}
              className="px-3 py-1.5 text-xs font-display uppercase tracking-wider border border-amber text-amber hover:bg-ink-3"
            >
              {t("network.searchButton", "Find")}
            </button>
          </div>
          <div className="mt-2 space-y-1 max-h-40 overflow-y-auto">
            {results.map((r) => (
              <button
                key={r.id}
                onClick={() => loadEgo(r.id)}
                className="w-full text-left value-mono text-[11px] px-2 py-1 hover:bg-ink-3 text-text"
              >
                <span style={{ color: NODE_COLORS[r.kind] ?? "#6b7a8f" }}>●</span> {r.label}{" "}
                <span className="text-dim">({r.connections})</span>
              </button>
            ))}
          </div>
        </div>

        {profile && (
          <div className="panel p-3 border-l-2 border-amber/50">
            <div className="label-hud mb-2">{t("network.profileTitle", "Offender Profile")}</div>
            <div className="value-mono text-xs text-text mb-1 truncate">
              {profile.label ?? profile.node}
            </div>
            <div className="value-mono text-[11px] text-amber mb-2">
              {profile.case_count} {t("network.profileCases", "cases")}
            </div>
            {profile.districts.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-2">
                {profile.districts.map((d) => (
                  <span
                    key={d}
                    className="value-mono text-[9px] border border-line text-dim px-1.5 py-0.5 truncate max-w-full"
                  >
                    {d}
                  </span>
                ))}
              </div>
            )}
            {(profile.mo.top_subtype || profile.mo.peak_band) && (
              <div className="value-mono text-[11px] text-dim leading-snug">
                <span className="text-teal">{t("network.profileMO", "MO")}</span>{" "}
                {[profile.mo.top_subtype, profile.mo.peak_band ? `peak ${profile.mo.peak_band}` : null]
                  .filter(Boolean)
                  .join(" · ")}
              </div>
            )}
          </div>
        )}

        {summary && (
          <>
            <div className="panel p-3">
              <div className="label-hud mb-2">{t("network.networkSummary", "Network")}</div>
              <div className="value-mono text-xs text-dim">
                {summary.nodes.toLocaleString()} {t("network.nodes", "nodes")} · {summary.edges.toLocaleString()} {t("network.links", "links")} ·{" "}
                {Object.keys(summary.communities).length} {t("network.majorClusters", "major clusters")}
              </div>
            </div>
            <div className="panel p-3">
              <div className="label-hud mb-2">{t("network.repeatOffenders", "Repeat Offenders")}</div>
              {summary.repeat_offenders.slice(0, 10).map((r) => (
                <button
                  key={r.node}
                  onClick={() => loadEgo(r.node)}
                  className="w-full flex justify-between value-mono text-[11px] px-1 py-1 hover:bg-ink-3 text-text"
                >
                  <span className="truncate">{r.label}</span>
                  <span className="text-amber shrink-0 ml-2">{r.case_count} {t("network.cases", "cases")}</span>
                </button>
              ))}
            </div>
            <div className="panel p-3">
              <div className="label-hud mb-2">{t("network.keyPlayers", "Key Players · centrality")}</div>
              {summary.key_players.slice(0, 8).map((k) => (
                <button
                  key={k.node}
                  onClick={() => loadEgo(k.node)}
                  className="w-full flex justify-between value-mono text-[11px] px-1 py-1 hover:bg-ink-3 text-text"
                >
                  <span className="truncate">{k.label}</span>
                  <span className="text-teal shrink-0 ml-2">{k.connections}</span>
                </button>
              ))}
            </div>
          </>
        )}
      </div>

      <div className="flex flex-col gap-2 min-w-0">
        <div className="flex items-center gap-4">
          <span className="label-hud">
            {selected
              ? `${t("network.linkAnalysis", "Link analysis")} · ${selected}`
              : t("network.selectEntity", "Select an entity to map its network")}
          </span>
          {edgeInfo && (
            <span className="value-mono text-xs text-signal">⚠ {t("network.hiddenLink", "hidden link")} — {edgeInfo}</span>
          )}
          <span className="value-mono text-[10px] text-dim ml-auto">
            <span style={{ color: NODE_COLORS.accused }}>●</span> {t("network.legendAccused", "accused")}{" "}
            <span style={{ color: NODE_COLORS.victim }}>●</span> {t("network.legendVictim", "victim")}{" "}
            <span style={{ color: NODE_COLORS.case }}>●</span> {t("network.legendCase", "case")}{" "}
            <span className="text-signal">- - -</span> {t("network.legendSharedPhoneAddress", "shared phone/address")}{" "}
            <span style={{ color: "#ff9f0a" }}>- - -</span> {t("network.legendMoneyTrail", "shared UPI (money trail)")}{" "}
            <span>· · ·</span> {t("network.legendPossibleSamePerson", "possible same person")}
          </span>
        </div>
        <div ref={cyDiv} className="panel flex-1 min-h-0" />
      </div>
    </div>
  );
}

export default function NetworkPage() {
  const { t } = useLang();
  return (
    <Shell title={t("network.title", "Criminal Network Analysis")}>
      <PageIntro
        id="network"
        text={t(
          "network.intro",
          "Who's connected — people linked by shared phones, addresses and UPI ids. Click a repeat offender to see their profile and MO."
        )}
      />
      <Suspense>
        <NetworkInner />
      </Suspense>
    </Shell>
  );
}
