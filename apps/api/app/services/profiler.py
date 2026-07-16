"""Profile any tabular dataset and infer what each column *means*.

Heuristics handle the common cases deterministically; the LLM (when
configured) is only consulted for columns the heuristics are unsure
about. The output is a DatasetManifest that drives every UI surface.
"""

from __future__ import annotations

import datetime
import re
import uuid

import duckdb

from app.models.manifest import (
    ChartSpec,
    ColumnSpec,
    ColumnStats,
    DatasetManifest,
    EntitySpec,
    KpiSpec,
    Relation,
    SemanticRole,
    TableSpec,
)

# (regex on column name, role) — first match wins. Order matters.
NAME_PATTERNS: list[tuple[str, SemanticRole]] = [
    (r"lat(itude)?$", SemanticRole.LATITUDE),
    (r"^(lng|lon|long|longitude)$|longitude", SemanticRole.LONGITUDE),
    (r"(^|_)(ts|timestamp|datetime|date_time|occurred|reported)(_|$)|_at$", SemanticRole.TIMESTAMP),
    (r"(^|_)date($|_)|_on$|dob|year_month", SemanticRole.DATE),
    (r"district", SemanticRole.ADMIN_AREA_1),
    (r"(police_)?station|taluk|tehsil|circle|sub_division", SemanticRole.ADMIN_AREA_2),
    (r"beat|locality|ward|village|area_name", SemanticRole.ADMIN_AREA_3),
    (r"phone|mobile|contact_no|msisdn", SemanticRole.PHONE),
    (r"address|residence", SemanticRole.ADDRESS),
    (r"upi|vpa|imei|aadhaa?r|passport|pan_no|acc(oun)?t_no|vehicle_(no|reg)|email", SemanticRole.IDENTIFIER),
    (r"population|density|household|literacy|urbani[sz]|_km2$|sq_km", SemanticRole.MEASURE),
    (r"(^|_)age($|_)", SemanticRole.AGE),
    (r"gender|sex", SemanticRole.GENDER),
    (r"(^|_)name($|_)", SemanticRole.PERSON_NAME),
    (r"amount|value|price|cost|loss|salary|income", SemanticRole.MONEY),
    (r"status|disposal|stage", SemanticRole.STATUS),
    (r"category|group|head|type|class(ification)?|crime|offence|modus|mo($|_)", SemanticRole.CATEGORY),
    (r"description|details|summary|narrative|remarks|text", SemanticRole.FREE_TEXT),
    (r"(^|_)(id|no|num|number|code)$|^fir", SemanticRole.ID),
]


def _dtype_of(duck_type: str) -> str:
    t = duck_type.upper()
    if "TIMESTAMP" in t or t == "DATETIME":
        return "timestamp"
    if t == "DATE":
        return "date"
    if t in ("TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT"):
        return "integer"
    if t in ("FLOAT", "DOUBLE", "DECIMAL", "REAL") or t.startswith("DECIMAL"):
        return "float"
    if t == "BOOLEAN":
        return "boolean"
    return "string"


def _profile_column(con: duckdb.DuckDBPyConnection, table: str, col: str, dtype: str, row_count: int) -> ColumnStats:
    q = f'SELECT count("{col}"), count(DISTINCT "{col}") FROM "{table}"'
    non_null, distinct = con.execute(q).fetchone()
    stats = ColumnStats(
        count=row_count,
        null_fraction=round(1 - non_null / row_count, 4) if row_count else 0.0,
        distinct_count=distinct,
    )
    if dtype in ("integer", "float"):
        mn, mx, mean = con.execute(
            f'SELECT min("{col}"), max("{col}"), avg("{col}") FROM "{table}"'
        ).fetchone()
        stats.min, stats.max = mn, mx
        stats.mean = round(mean, 4) if mean is not None else None
    elif dtype in ("timestamp", "date"):
        mn, mx = con.execute(f'SELECT min("{col}"), max("{col}") FROM "{table}"').fetchone()
        stats.min = str(mn) if mn else None
        stats.max = str(mx) if mx else None
    if dtype == "string" and distinct and distinct <= 5000:
        rows = con.execute(
            f'SELECT "{col}" AS v, count(*) AS c FROM "{table}" WHERE "{col}" IS NOT NULL '
            f"GROUP BY 1 ORDER BY c DESC LIMIT 10"
        ).fetchall()
        stats.top_values = [{"value": v, "count": c} for v, c in rows]
    return stats


def infer_role(name: str, dtype: str, stats: ColumnStats, row_count: int) -> tuple[SemanticRole, float]:
    lname = name.lower()
    for pattern, role in NAME_PATTERNS:
        if re.search(pattern, lname):
            # Sanity-check geo roles against value ranges.
            if role in (SemanticRole.LATITUDE, SemanticRole.LONGITUDE):
                if dtype not in ("integer", "float"):
                    continue
                lo, hi = (-90, 90) if role == SemanticRole.LATITUDE else (-180, 180)
                if stats.min is None or stats.min < lo or stats.max > hi:
                    continue
            if role == SemanticRole.ID and dtype in ("float",):
                continue
            return role, 0.9

    if dtype in ("timestamp",):
        return SemanticRole.TIMESTAMP, 0.8
    if dtype == "date":
        return SemanticRole.DATE, 0.8
    if dtype == "boolean":
        return SemanticRole.BOOLEAN, 0.9

    if dtype == "string" and row_count:
        ratio = stats.distinct_count / row_count
        if ratio > 0.95:
            return SemanticRole.ID, 0.5
        if stats.distinct_count <= 50:
            return SemanticRole.CATEGORY, 0.7
        return SemanticRole.FREE_TEXT, 0.4

    if dtype in ("integer", "float"):
        if row_count and stats.distinct_count / max(row_count, 1) > 0.95 and dtype == "integer":
            return SemanticRole.ID, 0.5
        return SemanticRole.MEASURE, 0.6

    return SemanticRole.OTHER, 0.3


def profile_table(con: duckdb.DuckDBPyConnection, table: str) -> TableSpec:
    row_count = con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
    desc = con.execute(f'DESCRIBE "{table}"').fetchall()
    cols: list[ColumnSpec] = []
    for row in desc:
        name, duck_type = row[0], row[1]
        dtype = _dtype_of(duck_type)
        stats = _profile_column(con, table, name, dtype, row_count)
        role, conf = infer_role(name, dtype, stats, row_count)
        cols.append(
            ColumnSpec(
                name=name,
                dtype=dtype,
                semantic_role=role,
                role_confidence=conf,
                label=name.replace("_", " ").title(),
                stats=stats,
            )
        )
    return TableSpec(name=table, row_count=row_count, columns=cols)


def _near_unique(c: ColumnSpec, t: TableSpec) -> bool:
    return c.stats.distinct_count >= 0.9 * max(t.row_count, 1)


def detect_relations(tables: list[TableSpec]) -> list[Relation]:
    """Same-named columns across tables become FK relations. The column's
    "owner" (primary-key side) is the largest table where it is near-unique;
    every other occurrence is the many-side and gets the FOREIGN_KEY role."""
    relations = []
    # Only ID-shaped columns can participate in joins — otherwise generic
    # names like "name" or "status" create bogus cross-table relations.
    by_name: dict[str, list[tuple[TableSpec, ColumnSpec]]] = {}
    for t in tables:
        for c in t.columns:
            if c.semantic_role in (SemanticRole.ID, SemanticRole.FOREIGN_KEY):
                by_name.setdefault(c.name, []).append((t, c))

    for name, occurrences in by_name.items():
        if len(occurrences) < 2:
            continue
        unique_sides = [(t, c) for t, c in occurrences if _near_unique(c, t)]
        if not unique_sides:
            continue
        owner_t, owner_c = max(unique_sides, key=lambda tc: tc[0].row_count)
        owner_c.semantic_role = SemanticRole.ID
        for t, c in occurrences:
            if t.name == owner_t.name:
                continue
            relations.append(
                Relation(from_table=t.name, from_column=name,
                         to_table=owner_t.name, to_column=name)
            )
            c.semantic_role = SemanticRole.FOREIGN_KEY
    return relations


LOOKUP_MAX_ROWS = 2000  # a "lookup/master" table is small relative to the fact


def _descriptive_col(t: TableSpec) -> ColumnSpec | None:
    """A human-readable column of a lookup table (the first non-id string column)."""
    cands = [c for c in t.columns
             if c.dtype == "string"
             and c.semantic_role not in (SemanticRole.ID, SemanticRole.FOREIGN_KEY)]
    return cands[0] if len(cands) >= 1 else None


def resolve_fk_labels(manifest: DatasetManifest) -> None:
    """Single-hop FK->label: for each relation into a small lookup table with a
    descriptive column, expose that column as a derived label on the referencing
    table and back the referencing table with a LEFT JOIN view (view_sql)."""
    by_name = {t.name: t for t in manifest.tables}
    # group resolvable relations by the referencing (from) table
    joins: dict[str, list[tuple]] = {}
    for r in manifest.relations:
        master = by_name.get(r.to_table)
        child = by_name.get(r.from_table)
        if not master or not child or master.row_count > LOOKUP_MAX_ROWS:
            continue
        label = _descriptive_col(master)
        if not label or label.name in {c.name for c in child.columns}:
            continue
        joins.setdefault(child.name, []).append((r, master, label))

    for child_name, items in joins.items():
        child = by_name[child_name]
        select = [f'b.*']
        froms = [f'"{child_name}" b']
        for i, (r, master, label) in enumerate(items):
            alias = f"m{i}"
            select.append(f'{alias}."{label.name}" AS "{label.name}"')
            froms.append(
                f'LEFT JOIN "{master.name}" {alias} '
                f'ON {alias}."{r.to_column}" = b."{r.from_column}"')
            # mirror the master column's role onto the derived label
            child.columns.append(ColumnSpec(
                name=label.name, dtype="string", semantic_role=label.semantic_role,
                label=label.name.replace("_", " ").title(), role_confidence=0.8))
        child.view_sql = "SELECT " + ", ".join(select) + " FROM " + " ".join(froms)


def detect_entities(tables: list[TableSpec]) -> list[EntitySpec]:
    entities = []
    for t in tables:
        name_col = t.first_by_role(SemanticRole.PERSON_NAME)
        id_cols = t.columns_by_role(SemanticRole.ID)
        # Prefer a *recurring* id (same person across many rows) over a
        # per-row id — that's what makes repeat-entity tracking possible.
        recurring = [c for c in id_cols if not _near_unique(c, t)]
        id_col = recurring[0] if recurring else (id_cols[0] if id_cols else None)
        if name_col and id_col:
            links = [
                c.name
                for c in t.columns
                if c.semantic_role in (SemanticRole.PHONE, SemanticRole.ADDRESS,
                                       SemanticRole.IDENTIFIER)
            ]
            entities.append(
                EntitySpec(
                    name=t.name.rstrip("s") or t.name,
                    table=t.name,
                    id_column=id_col.name,
                    label_column=name_col.name,
                    link_columns=links,
                )
            )
    return entities


def pick_primary_table(tables: list[TableSpec]) -> None:
    """The fact table: prefer one with a timestamp; tie-break on row count."""

    def score(t: TableSpec) -> tuple:
        has_time = any(
            c.semantic_role in (SemanticRole.TIMESTAMP, SemanticRole.DATE) for c in t.columns
        )
        return (has_time, t.row_count)

    if tables:
        max(tables, key=score).is_primary = True


def suggest_kpis_and_charts(manifest: DatasetManifest) -> None:
    t = manifest.primary_table()
    if not t:
        return
    time_col = t.first_by_role(SemanticRole.TIMESTAMP) or t.first_by_role(SemanticRole.DATE)
    cat_cols = t.columns_by_role(SemanticRole.CATEGORY)[:3]
    admin1 = t.first_by_role(SemanticRole.ADMIN_AREA_1)
    lat = t.first_by_role(SemanticRole.LATITUDE)
    lng = t.first_by_role(SemanticRole.LONGITUDE)
    money = t.first_by_role(SemanticRole.MONEY)

    manifest.kpis.append(
        KpiSpec(id="total_records", title=f"Total {t.name.replace('_', ' ').title()}", table=t.name, agg="count",
                compare_window="30d" if time_col else None)
    )
    if admin1:
        manifest.kpis.append(
            KpiSpec(id="active_areas", title=f"Active {admin1.label}s", table=t.name,
                    agg="distinct", column=admin1.name)
        )
    if money:
        manifest.kpis.append(
            KpiSpec(id="total_value", title=f"Total {money.label}", table=t.name,
                    agg="sum", column=money.name)
        )

    if time_col:
        manifest.charts.append(
            ChartSpec(id="trend", title="Trend Over Time", kind="timeseries", table=t.name,
                      dimension=time_col.name, time_grain="week")
        )
    for i, c in enumerate(cat_cols):
        manifest.charts.append(
            ChartSpec(id=f"by_{c.name}", title=f"By {c.label}", kind="bar", table=t.name,
                      dimension=c.name)
        )
    if admin1:
        manifest.charts.append(
            ChartSpec(id="by_area", title=f"By {admin1.label}", kind="bar", table=t.name,
                      dimension=admin1.name)
        )
    if lat and lng:
        manifest.charts.append(
            ChartSpec(id="map", title="Geographic Distribution", kind="map_heat", table=t.name)
        )


def build_manifest(
    con: duckdb.DuckDBPyConnection,
    tables: list[str],
    name: str,
    dataset_id: str | None = None,
    domain_pack: str = "generic",
) -> DatasetManifest:
    specs = [profile_table(con, t) for t in tables]
    relations = detect_relations(specs)
    pick_primary_table(specs)
    manifest = DatasetManifest(
        id=dataset_id or uuid.uuid4().hex[:12],
        name=name,
        domain_pack=domain_pack,
        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        tables=specs,
        relations=relations,
        entities=detect_entities(specs),
    )
    resolve_fk_labels(manifest)
    suggest_kpis_and_charts(manifest)
    return manifest
