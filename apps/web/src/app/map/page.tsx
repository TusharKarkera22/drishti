"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import maplibregl from "maplibre-gl";
import Shell from "@/components/Shell";
import PageIntro from "@/components/PageIntro";
import TemporalControls from "@/components/TemporalControls";
import { useLang } from "@/lib/i18n";
import { contextFromSearchParams } from "@/lib/investigation-context";
import {
  byRole,
  getHotspots,
  getManifest,
  getRisk,
  getSpikes,
  primaryTable,
  runQuery,
  type Manifest,
  type TemporalComparisonFrame,
} from "@/lib/api";

function MapWorkspace({ query }: { query: string }) {
  const { t } = useLang();
  const initialContext = useMemo(() => contextFromSearchParams(query).context, [query]);
  const ds = initialContext.dataset ?? "";
  const mapDiv = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const riskMarkersRef = useRef<maplibregl.Marker[]>([]);
  const pendingPlaybackRef = useRef<TemporalComparisonFrame | null>(null);
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [category, setCategory] = useState(initialContext.category ?? "");
  const [band, setBand] = useState(() => ({ night: "0-6", morning: "6-12", afternoon: "12-18", evening: "18-23" } as Record<string, string>)[initialContext.band ?? ""] ?? "");
  const [overlay, setOverlay] = useState<"" | "risk" | "percap">(initialContext.overlay === "risk" ? "risk" : "");
  const [hotspotStatus, setHotspotStatus] = useState<number | "no-geo" | null>(null);
  const hotspotRequestRef = useRef(0);

  useEffect(() => {
    if (!ds) return;
    getManifest(ds).then(setManifest).catch(() => {});
  }, [ds]);

  const categories = useMemo(() => {
    if (!manifest) return [];
    const pt = primaryTable(manifest);
    const cat = byRole(pt, "category");
    if (!cat) return [];
    return cat.stats.top_values.map((item) => String(item.value)).slice(0, 8);
  }, [manifest]);
  const stats = typeof hotspotStatus === "number"
    ? `${hotspotStatus} ${t("map.hotspotCells", "hotspot cells")}`
    : hotspotStatus === "no-geo"
      ? t("map.noGeoData", "no geo data in this dataset")
      : "";
  const timeColumn = manifest ? (byRole(primaryTable(manifest), "timestamp") ?? byRole(primaryTable(manifest), "date")) : undefined;
  const maxDate = timeColumn?.stats.max ? String(timeColumn.stats.max).slice(0, 10) : "";

  const applyPlaybackFrame = useCallback((frame: TemporalComparisonFrame | null) => {
    pendingPlaybackRef.current = frame;
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    const data = { type: "FeatureCollection" as const, features: (frame?.cells ?? []).map((cell) => ({ type: "Feature" as const, geometry: { type: "Point" as const, coordinates: [cell.lng, cell.lat] }, properties: { count: cell.count, change: cell.change } })) };
    const source = map.getSource("playback") as maplibregl.GeoJSONSource | undefined;
    if (source) return source.setData(data);
    map.addSource("playback", { type: "geojson", data });
    map.addLayer({ id: "playback-points", type: "circle", source: "playback", paint: { "circle-radius": ["interpolate", ["linear"], ["get", "count"], 1, 5, 20, 16], "circle-color": ["match", ["get", "change"], "emerging", "#ff3b30", "declining", "#2dd4bf", "#ffb000"], "circle-opacity": 0.75, "circle-stroke-color": "#fff1c2", "circle-stroke-width": 1 } });
  }, []);

  // init map once
  useEffect(() => {
    if (!mapDiv.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: mapDiv.current,
      style: {
        version: 8,
        sources: {
          carto: {
            type: "raster",
            tiles: ["https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap © CARTO",
          },
        },
        layers: [{ id: "carto", type: "raster", source: "carto" }],
      },
      center: initialContext.center ? [initialContext.center[1], initialContext.center[0]] : [76.5, 14.5],
      zoom: initialContext.zoom ?? 6.2,
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    mapRef.current = map;
    map.once("load", () => applyPlaybackFrame(pendingPlaybackRef.current));
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [applyPlaybackFrame, initialContext.center, initialContext.zoom]);

  // hotspot layer (re-fetch on filter change)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ds) return;
    const p: Record<string, string> = { cell_km: "2" };
    if (category) p.category = category;
    if (band) {
      const [f, to] = band.split("-");
      p.hour_from = f;
      p.hour_to = to;
    }
    const requestId = ++hotspotRequestRef.current;
    getHotspots(ds, p)
      .then((r) => {
        if (requestId !== hotspotRequestRef.current) return;
        const geojson = {
          type: "FeatureCollection" as const,
          features: r.cells.map((c) => ({
            type: "Feature" as const,
            geometry: { type: "Point" as const, coordinates: [c.lng, c.lat] },
            properties: { count: c.count, intensity: c.intensity },
          })),
        };
        setHotspotStatus(r.cells.length);
        const apply = () => {
          const src = map.getSource("hotspots") as maplibregl.GeoJSONSource | undefined;
          if (src) {
            src.setData(geojson);
            return;
          }
          map.addSource("hotspots", { type: "geojson", data: geojson });
          map.addLayer({
            id: "hotspot-heat",
            type: "heatmap",
            source: "hotspots",
            paint: {
              "heatmap-weight": ["get", "intensity"],
              "heatmap-intensity": 1.1,
              "heatmap-radius": 22,
              "heatmap-opacity": 0.75,
              "heatmap-color": [
                "interpolate", ["linear"], ["heatmap-density"],
                0, "rgba(0,0,0,0)",
                0.3, "#173a4d",
                0.55, "#2dd4bf",
                0.78, "#ffb000",
                1, "#ff3b30",
              ],
            },
          });
          map.addLayer({
            id: "hotspot-pts",
            type: "circle",
            source: "hotspots",
            minzoom: 10,
            paint: {
              "circle-radius": ["interpolate", ["linear"], ["get", "count"], 3, 3, 200, 14],
              "circle-color": "#ffb000",
              "circle-opacity": 0.55,
            },
          });
        };
        if (map.isStyleLoaded()) apply();
        else map.once("load", apply);
      })
      .catch(() => requestId === hotspotRequestRef.current && setHotspotStatus("no-geo"));
    return () => { hotspotRequestRef.current += 1; };
  }, [ds, category, band]);

  useEffect(() => {
    const area = initialContext.area;
    const map = mapRef.current;
    if (!area || !map || !manifest || !ds) return;
    const pt = primaryTable(manifest);
    const admin = byRole(pt, "admin_area_1");
    const lat = byRole(pt, "latitude");
    const lng = byRole(pt, "longitude");
    if (!admin || !lat || !lng) return;
    let active = true;
    runQuery(ds, {
      table: pt.name,
      dimensions: [admin.name],
      measures: [{ agg: "avg", column: lat.name, alias: "lat" }, { agg: "avg", column: lng.name, alias: "lng" }],
      filters: { [admin.name]: area },
      limit: 1,
    }).then((result) => {
      if (!active || !result.rows[0]) return;
      map.flyTo({ center: [Number(result.rows[0][2]), Number(result.rows[0][1])], zoom: 10 });
    }).catch(() => {});
    return () => { active = false; };
  }, [ds, manifest, initialContext.area]);

  // pulsing red-zone markers on spiking areas
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ds || !manifest) return;
    const pt = primaryTable(manifest);
    const lat = byRole(pt, "latitude");
    const lng = byRole(pt, "longitude");
    const admin = byRole(pt, "admin_area_1");
    if (!lat || !lng || !admin) return;

    let active = true;
    Promise.all([
      getSpikes(ds),
      runQuery(ds, {
        table: pt.name,
        dimensions: [admin.name],
        measures: [
          { agg: "avg", column: lat.name, alias: "lat" },
          { agg: "avg", column: lng.name, alias: "lng" },
        ],
        limit: 200,
      }),
    ])
      .then(([spikes, centroids]) => {
        if (!active) return;
        markersRef.current.forEach((m) => m.remove());
        markersRef.current = [];
        const centers = new Map(
          centroids.rows.map((r) => [String(r[0]), [Number(r[2]), Number(r[1])] as [number, number]])
        );
        spikes.alerts.slice(0, 6).forEach((a) => {
          const area = String(a[admin.name] ?? a.district ?? "");
          const c = centers.get(area);
          if (!c) return;
          const el = document.createElement("div");
          el.className = "pulse-red";
          el.style.cssText =
            "width:16px;height:16px;border-radius:50%;background:#ff3b30;border:2px solid #ffd5d2;cursor:pointer";
          el.title = `${area}: +${a.pct_change}% (z=${a.z_score})`;
          markersRef.current.push(
            new maplibregl.Marker({ element: el }).setLngLat(c).addTo(map)
          );
        });
      })
      .catch(() => {});
    return () => { active = false; markersRef.current.forEach((marker) => marker.remove()); markersRef.current = []; };
  }, [ds, manifest]);

  // district risk overlay: composite score or per-capita rate as sized circles
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ds || !manifest) return;
    riskMarkersRef.current.forEach((m) => m.remove());
    riskMarkersRef.current = [];
    if (!overlay) return;
    const pt = primaryTable(manifest);
    const lat = byRole(pt, "latitude");
    const lng = byRole(pt, "longitude");
    const admin = byRole(pt, "admin_area_1");
    if (!lat || !lng || !admin) return;

    let active = true;
    Promise.all([
      getRisk(ds),
      runQuery(ds, {
        table: pt.name,
        dimensions: [admin.name],
        measures: [
          { agg: "avg", column: lat.name, alias: "lat" },
          { agg: "avg", column: lng.name, alias: "lng" },
        ],
        limit: 200,
      }),
    ])
      .then(([risk, centroids]) => {
        if (!active) return;
        const centers = new Map(
          centroids.rows.map((r) => [String(r[0]), [Number(r[2]), Number(r[1])] as [number, number]])
        );
        const vals = risk.areas.map((a) =>
          overlay === "percap" ? a.per_lakh_daily ?? 0 : a.risk_score
        );
        const max = Math.max(...vals, 0.001);
        risk.areas.forEach((a) => {
          const c = centers.get(a.area);
          if (!c) return;
          const v = overlay === "percap" ? a.per_lakh_daily ?? 0 : a.risk_score;
          const frac = v / max;
          const size = 14 + frac * 30;
          const color = frac > 0.66 ? "#ff3b30" : frac > 0.33 ? "#ffb000" : "#2dd4bf";
          const el = document.createElement("div");
          el.style.cssText = `width:${size}px;height:${size}px;border-radius:50%;background:${color};opacity:0.45;border:1.5px solid ${color};cursor:pointer`;
          el.title =
            overlay === "percap"
              ? `${a.area}: ${a.per_lakh_daily ?? "?"} cases/day per 1L pop (pop ${((a.population ?? 0) / 1e5).toFixed(1)} L)`
              : `${a.area}: composite risk ${a.risk_score}`;
          riskMarkersRef.current.push(
            new maplibregl.Marker({ element: el }).setLngLat(c).addTo(map)
          );
        });
      })
      .catch(() => {});
    return () => { active = false; riskMarkersRef.current.forEach((marker) => marker.remove()); riskMarkersRef.current = []; };
  }, [ds, manifest, overlay]);

  const OVERLAY_OPTIONS: { id: "" | "risk" | "percap"; labelKey: string; labelEn: string }[] = [
    { id: "", labelKey: "map.overlayOff", labelEn: "Off" },
    { id: "risk", labelKey: "map.overlayCompositeRisk", labelEn: "Composite Risk" },
    { id: "percap", labelKey: "map.overlayPerCap", labelEn: "Per 1L Pop" },
  ];

  const HOUR_BANDS: { id: string; labelKey: string; labelEn: string }[] = [
    { id: "", labelKey: "map.bandAllHours", labelEn: "All hours" },
    { id: "0-6", labelKey: "map.bandNight", labelEn: "Night 00–06" },
    { id: "6-12", labelKey: "map.bandMorning", labelEn: "Morning 06–12" },
    { id: "12-18", labelKey: "map.bandDay", labelEn: "Day 12–18" },
    { id: "18-23", labelKey: "map.bandEvening", labelEn: "Evening 18–23" },
  ];

  return (
    <div className="flex flex-col h-[calc(100vh-7.5rem)] gap-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="label-hud mr-2">{t("map.districtOverlay", "District overlay:")}</span>
        {OVERLAY_OPTIONS.map((o) => (
          <button
            key={o.id}
            onClick={() => setOverlay(o.id)}
            className={`px-2 py-1 text-xs value-mono border transition-colors ${
              overlay === o.id ? "border-amber text-amber" : "border-line text-dim hover:text-text"
            }`}
          >
            {t(o.labelKey, o.labelEn)}
          </button>
        ))}
        <span className="label-hud ml-4 mr-2">{t("map.timeBand", "Time band:")}</span>
        {HOUR_BANDS.map((b) => (
          <button
            key={b.id}
            onClick={() => setBand(b.id)}
            className={`px-2 py-1 text-xs value-mono border transition-colors ${
              band === b.id ? "border-amber text-amber" : "border-line text-dim hover:text-text"
            }`}
          >
            {t(b.labelKey, b.labelEn)}
          </button>
        ))}
        <span className="label-hud ml-4 mr-2">{t("map.category", "Category:")}</span>
        <button
          onClick={() => setCategory("")}
          className={`px-2 py-1 text-xs value-mono border ${
            !category ? "border-amber text-amber" : "border-line text-dim hover:text-text"
          }`}
        >
          {t("map.allCategories", "All")}
        </button>
        {categories.map((c) => (
          <button
            key={c}
            onClick={() => setCategory(c)}
            className={`px-2 py-1 text-xs value-mono border transition-colors ${
              category === c ? "border-amber text-amber" : "border-line text-dim hover:text-text"
            }`}
          >
            {c}
          </button>
        ))}
        <span className="value-mono text-xs text-teal ml-auto">{stats}</span>
      </div>
      <div ref={mapDiv} className="panel flex-1 min-h-0" />
      {maxDate && <TemporalControls key={`${ds}:${maxDate}:${initialContext.from}:${initialContext.to}:${initialContext.frame}`} ds={ds} maxDate={maxDate} area={initialContext.area} category={category || undefined} initialFrom={initialContext.from} initialTo={initialContext.to} initialFrame={initialContext.frame} onFrame={applyPlaybackFrame} />}
      <div className="label-hud">
        {t(
          "map.legend",
          "heat = spatiotemporal density · pulsing red = statistically spiking zones vs own baseline",
        )}
        <span className="ml-3 text-signal">● emerging</span><span className="ml-2 text-amber">● persistent</span><span className="ml-2 text-teal">● declining</span>
      </div>
    </div>
  );
}

function MapInner() {
  const params = useSearchParams();
  const query = params.toString();
  return <MapWorkspace key={query} query={query} />;
}

export default function MapPage() {
  const { t } = useLang();
  return (
    <Shell title={t("map.title", "Geospatial Intelligence")}>
      <PageIntro
        id="map"
        text={t(
          "map.intro",
          "Where crime concentrates. Use the hour bands to see how hotspots move through the day; districts are scored 0–100 for next-week risk."
        )}
      />
      <Suspense>
        <MapInner />
      </Suspense>
    </Shell>
  );
}
