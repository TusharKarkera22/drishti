"""Deterministic current-versus-prior comparison and bounded hotspot frames."""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from typing import Any

from app.core import rescache, store
from app.models.manifest import SemanticRole

MAX_WINDOW_DAYS = 366
MAX_FRAMES = 60


def _day(value: str) -> dt.datetime:
    try:
        # DuckDB TIMESTAMP columns are timezone-naive. Passing an aware value makes
        # the driver apply the host timezone and shifts half-open date boundaries.
        return dt.datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("dates must use YYYY-MM-DD") from exc


def compare_periods(
    dataset_id: str,
    from_date: str,
    to_date: str,
    *,
    frame_days: int = 7,
    area: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", dataset_id) or ".." in dataset_id:
        raise FileNotFoundError("dataset not found")
    manifest = store.load_manifest(dataset_id)
    table = manifest.primary_table()
    if not table:
        return {"available": False, "reason": "dataset has no primary table"}
    time_col = table.first_by_role(SemanticRole.TIMESTAMP) or table.first_by_role(SemanticRole.DATE)
    if not time_col:
        return {"available": False, "reason": "dataset has no time column"}
    area_col = table.first_by_role(SemanticRole.ADMIN_AREA_1)
    category_col = table.first_by_role(SemanticRole.CATEGORY)
    lat_col = table.first_by_role(SemanticRole.LATITUDE)
    lng_col = table.first_by_role(SemanticRole.LONGITUDE)

    start, end = _day(from_date), _day(to_date)
    if end <= start:
        raise ValueError("from date must be before to date")
    days = (end - start).days
    if days > MAX_WINDOW_DAYS:
        raise ValueError(f"comparison window cannot exceed {MAX_WINDOW_DAYS} days")
    if frame_days < 1 or frame_days > MAX_WINDOW_DAYS:
        raise ValueError("frame_days is outside the supported range")
    frame_count = (days + frame_days - 1) // frame_days
    if frame_count > MAX_FRAMES:
        raise ValueError(f"comparison cannot exceed {MAX_FRAMES} frames")
    prior_start = start - (end - start)

    where = [f'TRY_CAST("{time_col.name}" AS TIMESTAMP) >= ?', f'TRY_CAST("{time_col.name}" AS TIMESTAMP) < ?']
    filter_params: list[Any] = []
    if area and area_col:
        where.append(f'CAST("{area_col.name}" AS VARCHAR) = ?')
        filter_params.append(area)
    if category and category_col:
        where.append(f'CAST("{category_col.name}" AS VARCHAR) = ?')
        filter_params.append(category)
    predicate = " AND ".join(where)

    con = store.connect(dataset_id)
    try:
        def count_window(a: dt.datetime, b: dt.datetime) -> int:
            return int(con.execute(
                f'SELECT count(*) FROM "{table.name}" WHERE {predicate}',
                [a, b, *filter_params],
            ).fetchone()[0])

        current_rows = count_window(start, end)
        previous_rows = count_window(prior_start, start)

        def grouped(column: str | None) -> list[dict[str, Any]]:
            if not column:
                return []
            group_where = [
                f'TRY_CAST("{time_col.name}" AS TIMESTAMP) >= ?',
                f'TRY_CAST("{time_col.name}" AS TIMESTAMP) < ?',
            ]
            if area and area_col:
                group_where.append(f'CAST("{area_col.name}" AS VARCHAR) = ?')
            if category and category_col:
                group_where.append(f'CAST("{category_col.name}" AS VARCHAR) = ?')
            sql = f'''SELECT CAST("{column}" AS VARCHAR) AS key,
                             count(*) FILTER (WHERE TRY_CAST("{time_col.name}" AS TIMESTAMP) >= ?
                                                AND TRY_CAST("{time_col.name}" AS TIMESTAMP) < ?) AS current_n,
                             count(*) FILTER (WHERE TRY_CAST("{time_col.name}" AS TIMESTAMP) >= ?
                                                AND TRY_CAST("{time_col.name}" AS TIMESTAMP) < ?) AS previous_n
                      FROM "{table.name}"
                      WHERE {" AND ".join(group_where)}
                      GROUP BY 1 ORDER BY current_n - previous_n DESC LIMIT 100'''
            rows = con.execute(sql, [start, end, prior_start, start, prior_start, end, *filter_params]).fetchall()
            return [_delta_row(str(key), int(cur), int(prev)) for key, cur, prev in rows]

        frames = []
        for index in range(frame_count):
            frame_start = start + dt.timedelta(days=index * frame_days)
            frame_end = min(frame_start + dt.timedelta(days=frame_days), end)
            frame: dict[str, Any] = {
                "index": index,
                "from": frame_start.date().isoformat(),
                "to": frame_end.date().isoformat(),
                "rows": count_window(frame_start, frame_end),
                "cells": [],
            }
            if lat_col and lng_col:
                cell_sql = f'''SELECT round(CAST("{lat_col.name}" AS DOUBLE), 2) AS lat,
                                      round(CAST("{lng_col.name}" AS DOUBLE), 2) AS lng,
                                      count(*) AS n
                               FROM "{table.name}" WHERE {predicate}
                                 AND "{lat_col.name}" IS NOT NULL AND "{lng_col.name}" IS NOT NULL
                               GROUP BY 1, 2 HAVING count(*) >= 1 ORDER BY n DESC LIMIT 500'''
                cells = con.execute(cell_sql, [frame_start, frame_end, *filter_params]).fetchall()
                prior_frame_start = frame_start - (frame_end - frame_start)
                prior_cells = con.execute(cell_sql, [prior_frame_start, frame_start, *filter_params]).fetchall()
                prior_counts = {(float(lat), float(lng)): int(n) for lat, lng, n in prior_cells}
                frame["cells"] = []
                for lat, lng, count in cells:
                    lat_value, lng_value, current_count = float(lat), float(lng), int(count)
                    previous_count = prior_counts.get((lat_value, lng_value), 0)
                    change = "emerging" if previous_count == 0 else "declining" if current_count < previous_count else "persistent"
                    frame["cells"].append({
                        "lat": lat_value, "lng": lng_value, "count": current_count,
                        "previous_count": previous_count, "delta": current_count - previous_count,
                        "change": change,
                    })
            frames.append(frame)
        area_rows = grouped(area_col.name if area_col else None)
        category_rows = grouped(category_col.name if category_col else None)
    finally:
        con.close()

    version = rescache.dataset_version(manifest)
    current = {"rows": current_rows}
    previous = {"rows": previous_rows}
    result = {
        "available": previous_rows > 0,
        "current": current,
        "previous": previous,
        "delta": _delta(current_rows, previous_rows),
        "areas": area_rows,
        "categories": category_rows,
        "frames": frames,
        "window": {
            "current": {"from": start.date().isoformat(), "to": end.date().isoformat()},
            "previous": {"from": prior_start.date().isoformat(), "to": start.date().isoformat()},
        },
        "dataset_version": version,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "evidence_id": "temporal:" + hashlib.sha256(
            f"{dataset_id}|{version}|{from_date}|{to_date}|{area}|{category}".encode()
        ).hexdigest()[:16],
    }
    if previous_rows == 0:
        result["reason"] = "insufficient prior history"
    return result


def _delta(current: int, previous: int) -> dict[str, int | float | None]:
    return {
        "absolute": current - previous,
        "percent": round((current - previous) / previous * 100, 1) if previous else None,
    }


def _delta_row(key: str, current: int, previous: int) -> dict[str, Any]:
    delta = _delta(current, previous)
    return {"key": key, "current": current, "previous": previous, **delta}
