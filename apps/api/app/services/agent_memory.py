"""Per-dataset agent memory: resumable chat threads + a shared long-term memory.

Two stores live under the dataset folder (store.dataset_dir):
  - agent_chats/{thread_id}.json : one resumable conversation each
  - agent_memory.jsonl           : distilled facts, shared across all agents

Distillation runs OFF the request path (daemon thread) so it never adds to the
~30s AppSail request budget. Memory is canonical English (it seeds the English
system prompt); only the user-facing report is translated.
"""

from __future__ import annotations

import datetime
import json
import re
import threading
import uuid

from app.core import store
from app.services import llm


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# paths
# --------------------------------------------------------------------------- #
def _chats_dir(dataset_id: str):
    d = store.dataset_dir(dataset_id) / "agent_chats"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _thread_path(dataset_id: str, thread_id: str):
    return _chats_dir(dataset_id) / f"{thread_id}.json"


# --------------------------------------------------------------------------- #
# threads
# --------------------------------------------------------------------------- #
def _title_from(text: str, limit: int = 60) -> str:
    t = " ".join((text or "").split()).strip()
    if not t:
        return "New conversation"
    if len(t) <= limit:
        return t
    return t[:limit].rsplit(" ", 1)[0] + "…"


def save_turn(dataset_id, thread_id, playbook, user_text, agent_text, steps, run_id) -> dict:
    """Append a (user, agent) exchange. Creates the thread if needed. Returns the thread."""
    now = _now()
    thread = load_thread(dataset_id, thread_id) if thread_id else None
    if thread is None:
        thread = {
            "thread_id": thread_id or uuid.uuid4().hex[:10],
            "playbook": playbook,
            "title": _title_from(user_text),
            "created_at": now,
            "updated_at": now,
            "turns": [],
        }
    thread["turns"].append({"role": "user", "text": user_text, "at": now})
    thread["turns"].append({"role": "agent", "text": agent_text,
                            "steps": steps, "run_id": run_id, "at": now})
    thread["updated_at"] = now
    _thread_path(dataset_id, thread["thread_id"]).write_text(json.dumps(thread))
    return thread


def load_thread(dataset_id, thread_id) -> dict | None:
    if not thread_id:
        return None
    p = _thread_path(dataset_id, thread_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def list_threads(dataset_id, playbook: str | None = None) -> list[dict]:
    out = []
    for p in _chats_dir(dataset_id).glob("*.json"):
        try:
            t = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if playbook and t.get("playbook") != playbook:
            continue
        out.append({
            "thread_id": t["thread_id"],
            "playbook": t.get("playbook"),
            "title": t.get("title") or "Conversation",
            "updated_at": t.get("updated_at"),
            "turn_count": len(t.get("turns", [])),
        })
    out.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return out


def delete_thread(dataset_id, thread_id) -> None:
    p = _thread_path(dataset_id, thread_id)
    if p.exists():
        p.unlink()


def history_messages(dataset_id, thread_id, max_exchanges: int = 4) -> list[dict]:
    """Last N exchanges as chat messages (text only — no tool transcripts)."""
    thread = load_thread(dataset_id, thread_id)
    if not thread:
        return []
    turns = thread.get("turns", [])[-(max_exchanges * 2):]
    return [
        {"role": "assistant" if t.get("role") == "agent" else "user",
         "content": t.get("text", "")}
        for t in turns
    ]


# --------------------------------------------------------------------------- #
# long-term memory (shared per dataset, across all agents)
# --------------------------------------------------------------------------- #
_MEM_CAP = 30


def _memory_path(dataset_id: str):
    return store.dataset_dir(dataset_id) / "agent_memory.jsonl"


def _norm_mem(text: str) -> str:
    return re.sub(r"[\s\W]+", " ", (text or "").lower()).strip()


def load_memory(dataset_id, limit: int = _MEM_CAP) -> list[dict]:
    p = _memory_path(dataset_id)
    if not p.exists():
        return []
    items = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return items[-limit:][::-1]   # newest first


def add_memories(dataset_id, items: list[dict]) -> None:
    """Append new items, skipping near-duplicates, capped at _MEM_CAP (most recent)."""
    if not items:
        return
    kept = list(reversed(load_memory(dataset_id)))   # chronological (oldest first)
    seen = {_norm_mem(it.get("text")) for it in kept}
    for it in items:
        text = (it.get("text") or "").strip()
        key = _norm_mem(text)
        if not text or key in seen:
            continue
        seen.add(key)
        kept.append({
            "id": "m_" + uuid.uuid4().hex[:6],
            "text": text,
            "kind": it.get("kind") or "finding",
            "source_thread": it.get("source_thread"),
            "source_playbook": it.get("source_playbook"),
            "at": _now(),
        })
    kept = kept[-_MEM_CAP:]
    _memory_path(dataset_id).write_text(
        "".join(json.dumps(x) + "\n" for x in kept))


def clear_memory(dataset_id) -> None:
    p = _memory_path(dataset_id)
    if p.exists():
        p.unlink()


def memory_block(dataset_id) -> str:
    items = load_memory(dataset_id)
    if not items:
        return ""
    lines = ["WHAT YOU REMEMBER ABOUT THIS DATASET (shared across all agents):"]
    lines += [f"- [{it.get('kind', 'note')}] {it.get('text', '')}" for it in items]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# distillation (LLM extractor + deterministic seed) — runs off the request path
# --------------------------------------------------------------------------- #
_EXTRACT_SYS = (
    "You distill durable MEMORY items from a police-intelligence agent's answer. "
    "Output ONLY a JSON array of 0-3 short items worth remembering across future "
    "conversations about THIS dataset: key entities (suspects, cases, phones, "
    "addresses), confirmed findings, or the user's current investigative focus. "
    "Skip pleasantries and anything transient. "
    'Each item: {"text": "<one short sentence>", "kind": "entity|finding|focus|area"}.'
)


def _parse_mem_json(text: str) -> list[dict]:
    if not text:
        return []
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    out = []
    if isinstance(data, list):
        for d in data:
            if isinstance(d, dict) and d.get("text"):
                out.append({"text": str(d["text"]).strip(),
                            "kind": str(d.get("kind") or "finding")})
    return out


def _seed_from_steps(steps: list[dict]) -> list[dict]:
    """Deterministic fallback: entity ids the agent explicitly looked up."""
    seed = []
    for s in steps or []:
        args = s.get("args") or {}
        node = args.get("node_id") if s.get("tool") == "graph_ego" else (
            args.get("query") if s.get("tool") == "graph_search" else None)
        if node:
            seed.append({"text": f"Looked up {node} in the link graph.", "kind": "entity"})
    return seed


def extract_memories(dataset_id, playbook, user_text, agent_text, steps,
                     llm_fn, thread_id=None) -> list[dict]:
    """Synchronous core: LLM extraction + deterministic seed. Returns candidate items
    tagged with their source (NOT persisted — add_memories persists + dedups)."""
    items: list[dict] = []
    try:
        raw = llm_fn([
            {"role": "system", "content": _EXTRACT_SYS},
            {"role": "user", "content":
                "Extract memory items from this exchange.\n\n"
                f"QUESTION: {user_text}\n\nAGENT ANSWER:\n{agent_text}"},
        ]) if llm_fn else ""
        items.extend(_parse_mem_json(raw))
    except Exception:
        items = []
    items.extend(_seed_from_steps(steps))
    for it in items:
        it["source_playbook"] = playbook
        it["source_thread"] = thread_id
    return items


def _default_llm_fn(messages: list[dict]) -> str:
    return llm.chat(messages, max_tokens=400).get("content", "")


def extract_memories_async(dataset_id, playbook, user_text, agent_text, steps,
                           thread_id=None, llm_fn=None) -> None:
    """Fire-and-forget distillation on a daemon thread. Never raises."""
    fn = llm_fn or _default_llm_fn

    def _work():
        try:
            items = extract_memories(dataset_id, playbook, user_text, agent_text, steps,
                                     fn, thread_id=thread_id)
            add_memories(dataset_id, items)
        except Exception:
            pass   # memory is best-effort; never disturb the request

    threading.Thread(target=_work, daemon=True).start()
