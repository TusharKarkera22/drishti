from fastapi import APIRouter, HTTPException

from app.services import temporal as svc

router = APIRouter()


@router.get("/{dataset_id}/compare")
def compare(dataset_id: str, from_date: str, to_date: str, frame_days: int = 7,
            area: str | None = None, category: str | None = None) -> dict:
    try:
        return svc.compare_periods(
            dataset_id, from_date, to_date, frame_days=frame_days,
            area=area, category=category,
        )
    except FileNotFoundError:
        raise HTTPException(404, f"dataset '{dataset_id}' not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
