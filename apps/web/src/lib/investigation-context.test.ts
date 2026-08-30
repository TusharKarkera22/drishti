import assert from "node:assert/strict";
import test from "node:test";

import {
  contextFromSearchParams,
  contextToPersistedState,
  contextToSearchParams,
  mergeContextIntoHref,
  type InvestigationContext,
} from "./investigation-context.ts";

test("safe investigation context round-trips", () => {
  const original: InvestigationContext = {
    version: 1,
    dataset: "ksp-crime",
    investigation: "hotspot-patrol",
    area: "Mysuru City",
    category: "Robbery",
    node: "person:42",
    from: "2026-07-01",
    to: "2026-08-01",
    band: "night",
    overlay: "change",
    frame: 3,
    center: [12.9716, 77.5946],
    zoom: 8.5,
  };

  const query = contextToSearchParams(original);
  assert.deepEqual(contextFromSearchParams(query).context, original);
  assert.deepEqual(contextFromSearchParams(query).discarded, []);
});

test("sensitive, unknown, and invalid state is discarded", () => {
  const query = new URLSearchParams({
    v: "99",
    ds: "ksp-crime",
    prompt: "name the suspect",
    memory: "secret",
    token: "credential",
    area: "x".repeat(300),
    zoom: "100",
    lat: "nan",
    lng: "77",
    frame: "-2",
    unexpected: "value",
  });

  const result = contextFromSearchParams(query);
  assert.deepEqual(result.context, { version: 1, dataset: "ksp-crime" });
  assert.ok(result.discarded.includes("v"));
  assert.ok(result.discarded.includes("area"));
  assert.ok(result.discarded.includes("zoom"));
  assert.ok(result.discarded.includes("prompt"));
  assert.ok(result.discarded.includes("unexpected"));
});

test("global navigation preserves only dataset and investigation", () => {
  const href = mergeContextIntoHref("/map", {
    version: 1,
    dataset: "ksp-crime",
    investigation: "emerging-threat",
    area: "Mysuru",
    category: "Robbery",
  }, "global");
  assert.equal(href, "/map?ds=ksp-crime&investigation=emerging-threat");
});

test("codec bounds the encoded query", () => {
  const query = contextToSearchParams({
    version: 1,
    dataset: "d".repeat(200),
    area: "a".repeat(200),
  });
  assert.ok(query.toString().length <= 1200);
  assert.equal(query.has("area"), false);
});

test("persisted state matches the backend allowlist", () => {
  assert.deepEqual(contextToPersistedState({
    version: 1,
    dataset: "demo",
    investigation: "hotspot-patrol",
    area: "Mysuru",
    category: "Robbery",
    node: "case-1",
    from: "2026-01-01",
    to: "2026-02-01",
    band: "night",
    overlay: "change",
    frame: 3,
    center: [12.97, 77.59],
    zoom: 9,
  }), {
    investigation: "hotspot-patrol",
    area: "Mysuru",
    category: "Robbery",
    node: "case-1",
    from: "2026-01-01",
    to: "2026-02-01",
    band: "night",
    overlay: "change",
    frame: 3,
  });
});

test("unsupported versions and oversized queries fail closed to dataset only", () => {
  assert.deepEqual(
    contextFromSearchParams("v=99&ds=demo&area=Mysuru").context,
    { version: 1, dataset: "demo" },
  );
  const oversized = new URLSearchParams({ ds: "demo", area: "Mysuru" });
  for (let index = 0; index < 140; index += 1) oversized.append("category", "Robbery");
  assert.deepEqual(
    contextFromSearchParams(oversized).context,
    { version: 1, dataset: "demo" },
  );
});

test("calendar dates are validated without normalization", () => {
  const result = contextFromSearchParams("ds=demo&from=2026-02-30&to=2026-03-01");
  assert.deepEqual(result.context, { version: 1, dataset: "demo", to: "2026-03-01" });
  assert.ok(result.discarded.includes("from"));
});
