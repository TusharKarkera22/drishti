"""Manifest-aware aggregation API. Powers every chart in the frontend.

The client never writes SQL: it sends a QueryRequest naming a table,
dimensions, measures, and filters; we compile safe SQL against DuckDB.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core import rescache, store

router = APIRouter()

TIME_GRAINS = {"hour", "day", "week", "month", "year"}
AGGS = {"count", "sum", "avg", "min", "max", "distinct"}


class Measure(BaseModel):
    agg: str = "count"
    column: Optional[str] = None
    alias: Optional[str] = None


class QueryRequest(BaseModel):
    table: str
    dimensions: list[str] = Field(default_factory=list)
    time_dimension: Optional[str] = None
    time_grain: str = "day"
    measures: list[Measure] = Field(default_factory=lambda: [Measure()])
    filters: dict[str, Any] = Field(default_factory=dict)  # col -> value | [values] | {"from","to"}
    order_by: Optional[str] = None
    desc: bool = True
    limit: int = 1000


def _ident(name: str, valid: set[str]) -> str:
    if name not in valid:
        raise HTTPException(400, f"unknown column '{name}'")
    return f'"{name}"'


def _compile(req: QueryRequest, columns: set[str]) -> tuple[str, list]:
    select, group, params = [], [], []

    if req.time_dimension:
        if req.time_grain not in TIME_GRAINS:
            raise HTTPException(400, f"bad time_grain '{req.time_grain}'")
        col = _ident(req.time_dimension, columns)
        # TRY_CAST: uploaded CSVs may carry timestamps as strings — the
        # semantic role says "time", the storage type shouldn't matter.
        expr = f"date_trunc('{req.time_grain}', TRY_CAST({col} AS TIMESTAMP))"
        select.append(f"{expr} AS period")
        group.append(expr)

    for d in req.dimensions:
        m = re.fullmatch(r"(hour|dayofweek|month)\((\w+)\)", d)
        if m:
            fn, col = m.group(1), _ident(m.group(2), columns)
            expr = f"{fn}(TRY_CAST({col} AS TIMESTAMP))"
            select.append(f"{expr} AS {m.group(1)}")
            group.append(expr)
        else:
            col = _ident(d, columns)
            select.append(f"{col} AS {d}")
            group.append(col)

    for i, ms in enumerate(req.measures):
        if ms.agg not in AGGS:
            raise HTTPException(400, f"bad agg '{ms.agg}'")
        alias = ms.alias or (f"{ms.agg}_{ms.column}" if ms.column else "count")
        if ms.agg == "count" and not ms.column:
            select.append(f'count(*) AS "{alias}"')
        elif ms.agg == "distinct":
            select.append(f'count(DISTINCT {_ident(ms.column, columns)}) AS "{alias}"')
        else:
            select.append(f'{ms.agg}({_ident(ms.column, columns)}) AS "{alias}"')

    where = []
    for col, val in req.filters.items():
        c = _ident(col, columns)
        if isinstance(val, dict):
            if "from" in val and val["from"] is not None:
                where.append(f"{c} >= ?")
                params.append(val["from"])
            if "to" in val and val["to"] is not None:
                where.append(f"{c} <= ?")
                params.append(val["to"])
        elif isinstance(val, list):
            where.append(f"{c} IN ({','.join('?' * len(val))})")
            params.extend(val)
        else:
            where.append(f"{c} = ?")
            params.append(val)

    sql = f'SELECT {", ".join(select)} FROM "{req.table}"'
    if where:
        sql += " WHERE " + " AND ".join(where)
    if group:
        sql += " GROUP BY " + ", ".join(group)
    if req.order_by:
        direction = "DESC" if req.desc else "ASC"
        sql += f' ORDER BY "{req.order_by}" {direction}'
    elif req.time_dimension:
        sql += " ORDER BY period ASC"
    sql += f" LIMIT {min(req.limit, 10000)}"
    return sql, params


@router.post("/{dataset_id}")
def run_query(dataset_id: str, req: QueryRequest, format: str = "json",
             refresh: bool = False) -> Any:
    try:
        manifest = store.load_manifest(dataset_id)
    except FileNotFoundError:
        raise HTTPException(404, f"dataset '{dataset_id}' not found")
    table = manifest.table(req.table)
    if not table:
        raise HTTPException(400, f"unknown table '{req.table}'")
    columns = {c.name for c in table.columns}

    def compute():
        sql, params = _compile(req, columns)
        con = store.connect(dataset_id)
        try:
            cur = con.execute(sql, params)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
        finally:
            con.close()
        rows = [[str(v) if hasattr(v, "isoformat") else v for v in r] for r in rows]
        return {"columns": cols, "rows": rows}

    if format == "csv":
        result = compute()  # exports stay uncached
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(result["columns"])
        w.writerows(result["rows"])
        return Response(
            buf.getvalue(), media_type="text/csv",
            headers={"Content-Disposition":
                     f'attachment; filename="{req.table}_export.csv"'},
        )
    return rescache.get_or_compute(dataset_id, "query", req.model_dump(mode="json"),
                                   compute, refresh)


@router.post("/{dataset_id}/records")
def fetch_records(dataset_id: str, req: QueryRequest) -> dict:
    """Raw row fetch (no aggregation) for detail tables and record drill-in."""
    try:
        manifest = store.load_manifest(dataset_id)
    except FileNotFoundError:
        raise HTTPException(404, f"dataset '{dataset_id}' not found")
    table = manifest.table(req.table)
    if not table:
        raise HTTPException(400, f"unknown table '{req.table}'")
    columns = {c.name for c in table.columns}

    where, params = [], []
    for col, val in req.filters.items():
        c = _ident(col, columns)
        if isinstance(val, list):
            where.append(f"{c} IN ({','.join('?' * len(val))})")
            params.extend(val)
        elif isinstance(val, dict):
            if val.get("from") is not None:
                where.append(f"{c} >= ?")
                params.append(val["from"])
            if val.get("to") is not None:
                where.append(f"{c} <= ?")
                params.append(val["to"])
        else:
            where.append(f"{c} = ?")
            params.append(val)
    sql = f'SELECT * FROM "{req.table}"'
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" LIMIT {min(req.limit, 500)}"

    con = store.connect(dataset_id)
    try:
        cur = con.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    finally:
        con.close()
    return {
        "columns": cols,
        "rows": [[str(v) if hasattr(v, "isoformat") else v for v in r] for r in rows],
    }
