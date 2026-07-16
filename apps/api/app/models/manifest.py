"""Dataset Manifest — the core contract of the platform.

Every dashboard, chart, map, graph, and agent renders off a manifest,
never off hardcoded column names. The ingestion engine emits one for
any uploaded dataset; domain packs enrich it.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class SemanticRole(str, Enum):
    """What a column *means*, independent of its raw dtype."""

    ID = "id"
    TIMESTAMP = "timestamp"
    DATE = "date"
    LATITUDE = "latitude"
    LONGITUDE = "longitude"
    ADMIN_AREA_1 = "admin_area_1"  # e.g. district
    ADMIN_AREA_2 = "admin_area_2"  # e.g. police station / taluk
    ADMIN_AREA_3 = "admin_area_3"  # e.g. beat / locality
    CATEGORY = "category"
    SUBCATEGORY = "subcategory"
    STATUS = "status"
    PERSON_NAME = "person_name"
    PHONE = "phone"
    ADDRESS = "address"
    IDENTIFIER = "identifier"  # shared real-world ids: UPI/VPA, bank acct, IMEI, email…
    AGE = "age"
    GENDER = "gender"
    MEASURE = "measure"  # generic numeric metric
    MONEY = "money"
    FREE_TEXT = "free_text"
    BOOLEAN = "boolean"
    FOREIGN_KEY = "foreign_key"
    OTHER = "other"


class ColumnStats(BaseModel):
    count: int = 0
    null_fraction: float = 0.0
    distinct_count: int = 0
    min: Optional[Any] = None
    max: Optional[Any] = None
    mean: Optional[float] = None
    top_values: list[dict[str, Any]] = Field(default_factory=list)  # [{value, count}]


class ColumnSpec(BaseModel):
    name: str
    dtype: str  # raw storage type: string | integer | float | timestamp | boolean
    semantic_role: SemanticRole = SemanticRole.OTHER
    label: str = ""
    stats: ColumnStats = Field(default_factory=ColumnStats)
    role_confidence: float = 1.0  # heuristic/LLM confidence in the role assignment


class Relation(BaseModel):
    """FK-style link between tables, used for joins and the entity graph."""

    from_table: str
    from_column: str
    to_table: str
    to_column: str
    kind: str = "many_to_one"


class EntitySpec(BaseModel):
    """A real-world entity (person, location, phone) that can become a graph node."""

    name: str
    table: str
    id_column: str
    label_column: Optional[str] = None
    link_columns: list[str] = Field(default_factory=list)  # shared values create edges


class TableSpec(BaseModel):
    name: str
    row_count: int = 0
    columns: list[ColumnSpec] = Field(default_factory=list)
    is_primary: bool = False  # the main fact/event table of the dataset
    view_sql: Optional[str] = None  # if set, store.connect() creates this as a SQL
                                    # view instead of reading raw parquet. System-generated.

    def columns_by_role(self, role: SemanticRole) -> list[ColumnSpec]:
        return [c for c in self.columns if c.semantic_role == role]

    def first_by_role(self, role: SemanticRole) -> Optional[ColumnSpec]:
        cols = self.columns_by_role(role)
        return cols[0] if cols else None


class KpiSpec(BaseModel):
    id: str
    title: str
    table: str
    agg: str  # count | sum | avg | distinct
    column: Optional[str] = None
    filters: dict[str, Any] = Field(default_factory=dict)
    compare_window: Optional[str] = None  # e.g. "30d" for delta vs previous period


class ChartSpec(BaseModel):
    id: str
    title: str
    kind: str  # timeseries | bar | pie | map_heat | map_points | table | network
    table: str
    dimension: Optional[str] = None
    measure_agg: str = "count"
    measure_column: Optional[str] = None
    time_grain: Optional[str] = None  # day | week | month


class DatasetManifest(BaseModel):
    id: str
    name: str
    domain_pack: str = "generic"  # "crime" | "generic" | future packs
    created_at: str = ""
    updated_at: Optional[str] = None  # bumped when data is appended; created_at never changes
    source: str = "upload"  # "upload" | "seed" — seed demo datasets are read-only
    tables: list[TableSpec] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    entities: list[EntitySpec] = Field(default_factory=list)
    kpis: list[KpiSpec] = Field(default_factory=list)
    charts: list[ChartSpec] = Field(default_factory=list)
    notes: str = ""

    def primary_table(self) -> Optional[TableSpec]:
        for t in self.tables:
            if t.is_primary:
                return t
        return self.tables[0] if self.tables else None

    def table(self, name: str) -> Optional[TableSpec]:
        for t in self.tables:
            if t.name == name:
                return t
        return None
