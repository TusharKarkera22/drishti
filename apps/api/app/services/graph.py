"""Network / link analysis built from the manifest's entities + relations.

Nodes: records of entity tables (e.g. accused persons) and of the primary
fact table (e.g. incidents). Edges: foreign keys (person ↔ case) and
shared identifiers (same phone / address across people) — the "hidden
associations impossible to spot in isolated Excel sheets".
"""

from __future__ import annotations

import itertools
import re

import community as community_louvain
import networkx as nx
import pandas as pd

from app.core import store
from app.models.manifest import DatasetManifest, SemanticRole


def _norm_name(name: str) -> str:
    """Token-sorted name with initials dropped: 'Ravi Kumar H' == 'Kumar Ravi'."""
    toks = [t for t in re.sub(r"[^a-z ]", " ", str(name).lower()).split() if len(t) > 1]
    return " ".join(sorted(toks))


def build_graph(dataset_id: str, manifest: DatasetManifest, max_rows: int = 250000) -> nx.Graph:
    g = nx.Graph()
    primary = manifest.primary_table()
    con = store.connect(dataset_id)
    try:
        for ent in manifest.entities:
            df = con.execute(f'SELECT * FROM "{ent.table}" LIMIT {max_rows}').df()
            for _, row in df.iterrows():
                nid = f"{ent.name}:{row[ent.id_column]}"
                g.add_node(
                    nid,
                    kind=ent.name,
                    label=str(row[ent.label_column]) if ent.label_column else nid,
                )
            # Shared identifiers (phone, address) create person↔person edges
            for link_col in ent.link_columns:
                if link_col not in df.columns:
                    continue
                shared = df.groupby(link_col)[ent.id_column].apply(lambda s: list(dict.fromkeys(s)))
                for value, ids in shared.items():
                    if pd.isna(value) or len(ids) < 2 or len(ids) > 20:
                        continue
                    for a, b in zip(ids, ids[1:]):
                        g.add_edge(
                            f"{ent.name}:{a}", f"{ent.name}:{b}",
                            kind=f"shared_{link_col}", value=str(value),
                        )

            # Fuzzy entity resolution: distinct ids whose names are variants of
            # each other ("Ravi Kumar" / "Ravi Kumar H"), corroborated by the
            # same locality (trailing address segment). Edge kind deliberately
            # does NOT start with "shared_" so unconfirmed identities stay out
            # of the Louvain community projection.
            tspec = manifest.table(ent.table)
            addr = tspec.first_by_role(SemanticRole.ADDRESS) if tspec else None
            if ent.label_column:
                cols = [ent.id_column, ent.label_column] + ([addr.name] if addr else [])
                work = df[cols].drop_duplicates(ent.id_column)
                key = work[ent.label_column].map(_norm_name)
                if addr is not None:
                    key = key + "|" + (
                        work[addr.name].astype(str)
                        .str.rsplit(",", n=1).str[-1].str.strip().str.lower()
                    )
                labels = dict(zip(work[ent.id_column], work[ent.label_column]))
                for ids in work.groupby(key)[ent.id_column].apply(list):
                    if not 2 <= len(ids) <= 4:
                        continue
                    for a, b in itertools.combinations(ids, 2):
                        # identical raw names prove nothing; only variants link
                        if str(labels[a]) != str(labels[b]):
                            g.add_edge(f"{ent.name}:{a}", f"{ent.name}:{b}",
                                       kind="possible_same_person",
                                       value=_norm_name(labels[a]))

        # FK edges: entity table → primary table (person ↔ case)
        for rel in manifest.relations:
            ent = next((e for e in manifest.entities if e.table == rel.from_table), None)
            if not ent or not primary or rel.to_table != primary.name:
                continue
            pk = primary.first_by_role(SemanticRole.ID)
            if not pk:
                continue
            df = con.execute(
                f'SELECT "{ent.id_column}", "{rel.from_column}" FROM "{ent.table}" LIMIT {max_rows}'
            ).df()
            for _, row in df.iterrows():
                case_id = row[rel.from_column]
                if pd.isna(case_id):
                    continue
                case_node = f"case:{case_id}"
                if case_node not in g:
                    g.add_node(case_node, kind="case", label=str(case_id))
                g.add_edge(f"{ent.name}:{row[ent.id_column]}", case_node, kind="involved_in")
    finally:
        con.close()
    return g


def graph_summary(g: nx.Graph, manifest: DatasetManifest, top: int = 25) -> dict:
    person_nodes = [n for n, d in g.nodes(data=True) if d.get("kind") != "case"]
    degree = dict(g.degree(person_nodes))
    top_nodes = sorted(degree.items(), key=lambda kv: -kv[1])[:top]

    repeat = []
    for n in person_nodes:
        cases = [m for m in g.neighbors(n) if g.nodes[m].get("kind") == "case"]
        if len(cases) >= 2:
            repeat.append({"node": n, "label": g.nodes[n].get("label", n), "case_count": len(cases)})
    repeat.sort(key=lambda r: -r["case_count"])

    # Louvain on the full 200k-row graph takes minutes; the clusters that matter
    # are the ones held together by shared identifiers or co-involvement in the
    # same case, so partition only that (much smaller) projected subgraph.
    communities = {}
    sg = nx.Graph()
    sg.add_edges_from(
        (a, b) for a, b, d in g.edges(data=True)
        if str(d.get("kind", "")).startswith("shared_")
    )
    for n, d in g.nodes(data=True):
        if d.get("kind") != "case":
            continue
        nbrs = [m for m in g.neighbors(n) if g.nodes[m].get("kind") != "case"]
        if 2 <= len(nbrs) <= 20:
            sg.add_edges_from(zip(nbrs, nbrs[1:]))
    if sg.number_of_edges() > 0:
        partition = community_louvain.best_partition(sg, random_state=42)
        sizes: dict[int, int] = {}
        for node, com in partition.items():
            sizes[com] = sizes.get(com, 0) + 1
        big = sorted(sizes.items(), key=lambda kv: -kv[1])[:10]
        communities = {str(com): size for com, size in big if size >= 3}

    return {
        "nodes": g.number_of_nodes(),
        "edges": g.number_of_edges(),
        "key_players": [
            {"node": n, "label": g.nodes[n].get("label", n), "connections": d}
            for n, d in top_nodes
        ],
        "repeat_offenders": repeat[:top],
        "communities": communities,
    }


def ego_network(g: nx.Graph, node_id: str, hops: int = 2, max_nodes: int = 150) -> dict:
    if node_id not in g:
        return {"nodes": [], "edges": [], "error": f"node '{node_id}' not in graph"}
    sub = nx.ego_graph(g, node_id, radius=hops)
    if sub.number_of_nodes() > max_nodes:
        keep = sorted(sub.degree, key=lambda kv: -kv[1])[:max_nodes]
        sub = sub.subgraph([n for n, _ in keep] + [node_id])
    return {
        "nodes": [
            {"id": n, "kind": d.get("kind", "unknown"), "label": d.get("label", n),
             "is_center": n == node_id}
            for n, d in sub.nodes(data=True)
        ],
        "edges": [
            {"source": a, "target": b, "kind": d.get("kind", ""), "value": d.get("value", "")}
            for a, b, d in sub.edges(data=True)
        ],
    }


def offender_profile(g: nx.Graph, dataset_id: str, manifest: DatasetManifest,
                     node_id: str) -> dict:
    """Return a visual profile for a repeat-offender graph node.

    Resolves the node's linked CASE ids from the graph (1-hop ego), then
    queries the primary table for district, subtype, and time-band per case.

    Always returns a valid dict; never raises.  Missing node or no resolvable
    cases → zero-filled shape.
    """
    _empty = {
        "node": node_id,
        "label": None,
        "case_count": 0,
        "districts": [],
        "mo": {"top_subtype": None, "peak_band": None},
        "cases": [],
    }

    if node_id not in g:
        return _empty

    label = g.nodes[node_id].get("label")
    case_neighbors = [
        m for m in g.neighbors(node_id)
        if g.nodes[m].get("kind") == "case"
    ]
    if not case_neighbors:
        return {**_empty, "label": label}

    # Extract the raw case id from "case:<id>" node names
    case_ids = [n.split(":", 1)[1] for n in case_neighbors]

    primary = manifest.primary_table()
    if not primary:
        return {**_empty, "label": label}

    id_spec = primary.first_by_role(SemanticRole.ID)
    area_spec = primary.first_by_role(SemanticRole.ADMIN_AREA_1)
    sub_spec = (primary.first_by_role(SemanticRole.SUBCATEGORY)
                or primary.first_by_role(SemanticRole.CATEGORY))
    time_spec = (primary.first_by_role(SemanticRole.TIMESTAMP)
                 or primary.first_by_role(SemanticRole.DATE))

    if not id_spec:
        return {**_empty, "label": label}

    # Build a DuckDB IN list of quoted ids for safe parameterised query
    placeholders = ", ".join("?" for _ in case_ids)

    select_parts = [f'"{id_spec.name}" AS fir_id']
    if area_spec:
        select_parts.append(f'"{area_spec.name}" AS district')
    else:
        select_parts.append("NULL AS district")
    if sub_spec:
        select_parts.append(f'"{sub_spec.name}" AS subtype')
    else:
        select_parts.append("NULL AS subtype")
    if time_spec:
        select_parts.append(
            f"CASE "
            f"WHEN hour(TRY_CAST(\"{time_spec.name}\" AS TIMESTAMP)) BETWEEN 0 AND 5 THEN 'Night' "
            f"WHEN hour(TRY_CAST(\"{time_spec.name}\" AS TIMESTAMP)) BETWEEN 6 AND 11 THEN 'Morning' "
            f"WHEN hour(TRY_CAST(\"{time_spec.name}\" AS TIMESTAMP)) BETWEEN 12 AND 17 THEN 'Afternoon' "
            f"ELSE 'Evening' "
            f"END AS band"
        )
    else:
        select_parts.append("NULL AS band")

    sql = (
        f'SELECT {", ".join(select_parts)} '
        f'FROM "{primary.name}" '
        f'WHERE CAST("{id_spec.name}" AS VARCHAR) IN ({placeholders})'
    )

    con = store.connect(dataset_id)
    try:
        rows = con.execute(sql, [str(c) for c in case_ids]).fetchall()
    except Exception:
        return {**_empty, "label": label}
    finally:
        con.close()

    if not rows:
        return {**_empty, "label": label}

    cases = []
    from collections import Counter
    subtype_counter: Counter = Counter()
    band_counter: Counter = Counter()
    district_set: set = set()

    for row in rows:
        fir, district, subtype, band = row
        if district:
            district_set.add(str(district))
        if subtype:
            subtype_counter[str(subtype)] += 1
        if band:
            band_counter[str(band)] += 1
        cases.append({
            "fir": str(fir),
            "district": str(district) if district is not None else "",
            "subtype": str(subtype) if subtype is not None else "",
            "band": str(band) if band is not None else "",
        })

    top_subtype = subtype_counter.most_common(1)[0][0] if subtype_counter else None
    peak_band = band_counter.most_common(1)[0][0] if band_counter else None

    return {
        "node": node_id,
        "label": label,
        "case_count": len(cases),
        "districts": sorted(district_set),
        "mo": {"top_subtype": top_subtype, "peak_band": peak_band},
        "cases": cases[:25],
    }


def find_node(g: nx.Graph, query: str, limit: int = 20) -> list[dict]:
    q = query.lower()
    hits = []
    for n, d in g.nodes(data=True):
        if q in n.lower() or q in str(d.get("label", "")).lower():
            hits.append({"id": n, "kind": d.get("kind"), "label": d.get("label"),
                         "connections": g.degree(n)})
            if len(hits) >= limit:
                break
    return hits
