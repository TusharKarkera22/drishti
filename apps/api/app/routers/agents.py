from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import agent_memory as mem
from app.services import agents as svc
from app.services.llm import LLMError

router = APIRouter()


class AgentRequest(BaseModel):
    playbook: str = "analyst"  # analyst | patrol_planner | case_linker | trend_sentinel
    input: str = ""
    language: str = "en"  # en | kn (Kannada)
    thread_id: str | None = None


@router.get("/playbooks")
def playbooks() -> list[dict]:
    return [
        {"id": "analyst", "name": "Vishleshak",
         "description": "Analyst — ask anything about the dataset in natural language."},
        {"id": "patrol_planner", "name": "Rakshak",
         "description": "Guardian — forecasts high-risk areas and drafts a patrol deployment plan."},
        {"id": "case_linker", "name": "Sutradhar",
         "description": "Link analyst — traverses the network to find related cases and writes a linkage memo."},
        {"id": "trend_sentinel", "name": "Prahari",
         "description": "Sentinel — scans for statistical spikes and writes an alert bulletin."},
    ]


@router.post("/{dataset_id}/run")
def run(dataset_id: str, req: AgentRequest) -> dict:
    try:
        return svc.run_agent(dataset_id, req.playbook, req.input,
                             language=req.language, thread_id=req.thread_id)
    except LLMError as e:
        raise HTTPException(503, str(e))
    except FileNotFoundError:
        raise HTTPException(404, f"dataset '{dataset_id}' not found")


@router.get("/{dataset_id}/runs")
def runs(dataset_id: str) -> list[dict]:
    return svc.list_runs(dataset_id)


@router.get("/{dataset_id}/threads")
def threads(dataset_id: str, playbook: str | None = None) -> list[dict]:
    return mem.list_threads(dataset_id, playbook)


@router.get("/{dataset_id}/threads/{thread_id}")
def thread(dataset_id: str, thread_id: str) -> dict:
    t = mem.load_thread(dataset_id, thread_id)
    if t is None:
        raise HTTPException(404, "thread not found")
    return t


@router.delete("/{dataset_id}/threads/{thread_id}")
def del_thread(dataset_id: str, thread_id: str) -> dict:
    mem.delete_thread(dataset_id, thread_id)
    return {"ok": True}


@router.get("/{dataset_id}/memory")
def memory(dataset_id: str) -> list[dict]:
    return mem.load_memory(dataset_id)


@router.delete("/{dataset_id}/memory")
def clear_memory(dataset_id: str) -> dict:
    mem.clear_memory(dataset_id)
    return {"ok": True}
