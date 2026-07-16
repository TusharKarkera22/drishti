from fastapi import APIRouter, HTTPException

from app.core import store

router = APIRouter()


@router.get("")
def list_datasets() -> list[dict]:
    return [
        {
            "id": m.id,
            "name": m.name,
            "domain_pack": m.domain_pack,
            "created_at": m.created_at,
            "tables": [{"name": t.name, "row_count": t.row_count} for t in m.tables],
        }
        for m in store.list_datasets()
    ]


@router.get("/{dataset_id}/manifest")
def get_manifest(dataset_id: str) -> dict:
    try:
        return store.load_manifest(dataset_id).model_dump(mode="json")
    except FileNotFoundError:
        raise HTTPException(404, f"dataset '{dataset_id}' not found")


@router.get("/{dataset_id}/composition")
def composition(dataset_id: str) -> dict:
    try:
        m = store.load_manifest(dataset_id)
    except FileNotFoundError:
        raise HTTPException(404, f"dataset '{dataset_id}' not found")
    from app.services import append as append_svc
    return {
        "id": m.id, "name": m.name,
        "source": "seed" if append_svc.is_read_only(dataset_id, m) else m.source,
        "created_at": m.created_at, "updated_at": m.updated_at,
        "total_rows": sum(t.row_count for t in m.tables),
        "tables": [{"name": t.name, "row_count": t.row_count, "n_columns": len(t.columns)}
                   for t in m.tables],
        "history": append_svc.read_log(dataset_id),
        "read_only": append_svc.is_read_only(dataset_id, m),
    }
