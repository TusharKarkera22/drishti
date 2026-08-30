from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import investigations as svc

router = APIRouter()


class Payload(BaseModel):
    data: dict


def _call(fn, *args):
    try:
        return fn(*args)
    except FileNotFoundError:
        raise HTTPException(404, "dataset not found")
    except KeyError:
        raise HTTPException(404, "investigation object not found")
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc))


@router.get("/{dataset_id}/cards")
def cards(dataset_id: str): return _call(svc.list_cards, dataset_id)

@router.post("/{dataset_id}/cards")
def create_card(dataset_id: str, payload: Payload): return _call(svc.create_card, dataset_id, payload.data)

@router.patch("/{dataset_id}/cards/{card_id}")
def update_card(dataset_id: str, card_id: str, payload: Payload): return _call(svc.update_card, dataset_id, card_id, payload.data)

@router.delete("/{dataset_id}/cards/{card_id}")
def delete_card(dataset_id: str, card_id: str): return {"ok": _call(svc.delete_card, dataset_id, card_id)}

@router.get("/{dataset_id}/rules")
def rules(dataset_id: str): return _call(svc.list_rules, dataset_id)

@router.post("/{dataset_id}/rules")
def create_rule(dataset_id: str, payload: Payload): return _call(svc.create_rule, dataset_id, payload.data)

@router.patch("/{dataset_id}/rules/{rule_id}")
def update_rule(dataset_id: str, rule_id: str, payload: Payload): return _call(svc.update_rule, dataset_id, rule_id, payload.data)

@router.delete("/{dataset_id}/rules/{rule_id}")
def delete_rule(dataset_id: str, rule_id: str): return {"ok": _call(svc.delete_rule, dataset_id, rule_id)}

@router.post("/{dataset_id}/rules/{rule_id}/evaluate")
def evaluate(dataset_id: str, rule_id: str): return _call(svc.evaluate_rule, dataset_id, rule_id)

@router.get("/{dataset_id}/events")
def events(dataset_id: str): return _call(svc.list_events, dataset_id)
