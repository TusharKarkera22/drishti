export const INVESTIGATION_CONTEXT_VERSION = 1 as const;
const MAX_QUERY_LENGTH = 1200;
const MAX_TEXT_LENGTH = 120;

export type InvestigationKind = "emerging-threat" | "hotspot-patrol" | "case-linkage";
export type TimeBand = "all" | "night" | "morning" | "afternoon" | "evening";
export type MapOverlay = "hotspots" | "spikes" | "risk" | "change";

export interface InvestigationContext {
  version: typeof INVESTIGATION_CONTEXT_VERSION;
  dataset?: string;
  investigation?: InvestigationKind;
  area?: string;
  category?: string;
  node?: string;
  from?: string;
  to?: string;
  band?: TimeBand;
  overlay?: MapOverlay;
  frame?: number;
  center?: [number, number];
  zoom?: number;
}

export type PersistedInvestigationState = Pick<
  InvestigationContext,
  "investigation" | "area" | "category" | "node" | "from" | "to" | "band" | "overlay" | "frame"
>;

const persistedKeys = ["investigation", "area", "category", "node", "from", "to", "band", "overlay", "frame"] as const;

export interface DecodedInvestigationContext {
  context: InvestigationContext;
  discarded: string[];
}

const acceptedKeys = new Set([
  "v", "ds", "investigation", "area", "category", "node", "from", "to",
  "band", "overlay", "frame", "lat", "lng", "zoom",
]);
const investigations = new Set<InvestigationKind>(["emerging-threat", "hotspot-patrol", "case-linkage"]);
const bands = new Set<TimeBand>(["all", "night", "morning", "afternoon", "evening"]);
const overlays = new Set<MapOverlay>(["hotspots", "spikes", "risk", "change"]);

function safeText(value: string | null): string | undefined {
  if (!value || value.length > MAX_TEXT_LENGTH || /[\u0000-\u001f]/.test(value)) return undefined;
  return value;
}

function safeDate(value: string | null): string | undefined {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return undefined;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year
    && parsed.getUTCMonth() === month - 1
    && parsed.getUTCDate() === day
    ? value
    : undefined;
}

function safeNumber(value: string | null, min: number, max: number): number | undefined {
  if (value === null || value.trim() === "") return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= min && parsed <= max ? parsed : undefined;
}

export function contextFromSearchParams(input: URLSearchParams | string): DecodedInvestigationContext {
  const params = typeof input === "string" ? new URLSearchParams(input) : input;
  const discarded = new Set<string>();
  const context: InvestigationContext = { version: INVESTIGATION_CONTEXT_VERSION };

  for (const key of params.keys()) if (!acceptedKeys.has(key)) discarded.add(key);
  const unsupportedVersion = params.has("v") && params.get("v") !== String(INVESTIGATION_CONTEXT_VERSION);
  const oversized = params.toString().length > MAX_QUERY_LENGTH;
  if (unsupportedVersion || oversized) {
    for (const key of params.keys()) if (key !== "ds") discarded.add(key);
    const dataset = safeText(params.get("ds"));
    return { context: { version: INVESTIGATION_CONTEXT_VERSION, ...(dataset ? { dataset } : {}) }, discarded: [...discarded].sort() };
  }

  const readText = (key: string) => {
    const raw = params.get(key);
    const value = safeText(raw);
    if (raw !== null && value === undefined) discarded.add(key);
    return value;
  };

  context.dataset = readText("ds");

  const investigation = readText("investigation");
  if (investigation && investigations.has(investigation as InvestigationKind)) context.investigation = investigation as InvestigationKind;
  else if (investigation) discarded.add("investigation");

  context.area = readText("area");
  context.category = readText("category");
  context.node = readText("node");

  for (const key of ["from", "to"] as const) {
    const raw = params.get(key);
    const value = safeDate(raw);
    if (value) context[key] = value;
    else if (raw !== null) discarded.add(key);
  }

  const band = readText("band");
  if (band && bands.has(band as TimeBand)) context.band = band as TimeBand;
  else if (band) discarded.add("band");
  const overlay = readText("overlay");
  if (overlay && overlays.has(overlay as MapOverlay)) context.overlay = overlay as MapOverlay;
  else if (overlay) discarded.add("overlay");

  const frameRaw = params.get("frame");
  const frame = safeNumber(frameRaw, 0, 100);
  if (frame !== undefined && Number.isInteger(frame)) context.frame = frame;
  else if (frameRaw !== null) discarded.add("frame");
  const latRaw = params.get("lat");
  const lngRaw = params.get("lng");
  const lat = safeNumber(latRaw, -90, 90);
  const lng = safeNumber(lngRaw, -180, 180);
  if (lat !== undefined && lng !== undefined) context.center = [lat, lng];
  else {
    if (latRaw !== null) discarded.add("lat");
    if (lngRaw !== null) discarded.add("lng");
  }
  const zoomRaw = params.get("zoom");
  const zoom = safeNumber(zoomRaw, 0, 24);
  if (zoom !== undefined) context.zoom = zoom;
  else if (zoomRaw !== null) discarded.add("zoom");

  for (const key of ["dataset", "area", "category", "node"] as const) {
    if (context[key] === undefined) delete context[key];
  }
  return { context, discarded: [...discarded].sort() };
}

export function contextToSearchParams(context: InvestigationContext): URLSearchParams {
  const params = new URLSearchParams({ v: String(INVESTIGATION_CONTEXT_VERSION) });
  const put = (key: string, value: string | undefined) => {
    const safe = safeText(value ?? null);
    if (safe) params.set(key, safe);
  };
  put("ds", context.dataset);
  if (context.investigation && investigations.has(context.investigation)) params.set("investigation", context.investigation);
  put("area", context.area);
  put("category", context.category);
  put("node", context.node);
  if (safeDate(context.from ?? null)) params.set("from", context.from!);
  if (safeDate(context.to ?? null)) params.set("to", context.to!);
  if (context.band && bands.has(context.band)) params.set("band", context.band);
  if (context.overlay && overlays.has(context.overlay)) params.set("overlay", context.overlay);
  if (Number.isInteger(context.frame) && context.frame! >= 0 && context.frame! <= 100) params.set("frame", String(context.frame));
  if (context.center) {
    const [lat, lng] = context.center;
    if (lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180) {
      params.set("lat", String(lat));
      params.set("lng", String(lng));
    }
  }
  if (context.zoom !== undefined && context.zoom >= 0 && context.zoom <= 24) params.set("zoom", String(context.zoom));
  if (params.toString().length > MAX_QUERY_LENGTH) return new URLSearchParams(context.dataset ? { ds: context.dataset } : {});
  return params;
}

export function mergeContextIntoHref(
  href: string,
  context: InvestigationContext,
  scope: "all" | "global" = "all",
): string {
  const selected = scope === "global"
    ? { version: INVESTIGATION_CONTEXT_VERSION, dataset: context.dataset, investigation: context.investigation } satisfies InvestigationContext
    : context;
  const params = contextToSearchParams(selected);
  if (scope === "global") params.delete("v");
  const query = params.toString();
  return query ? `${href}?${query}` : href;
}

export function contextToPersistedState(context: InvestigationContext): PersistedInvestigationState {
  return Object.fromEntries(
    persistedKeys.flatMap((key) => context[key] === undefined ? [] : [[key, context[key]]]),
  ) as PersistedInvestigationState;
}

export function daysBefore(date: string, days: number): string {
  const value = new Date(`${date}T00:00:00Z`);
  value.setUTCDate(value.getUTCDate() - days);
  return value.toISOString().slice(0, 10);
}

export function daysAfter(date: string, days: number): string {
  return daysBefore(date, -days);
}
