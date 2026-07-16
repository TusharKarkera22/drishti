import pytest

from app.core import store
from app.services import agents as A


def _tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)


def test_system_prompt_includes_memory_and_schema(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    from app.services import agent_memory as M
    monkeypatch.setattr(A, "_manifest_brief", lambda ds: "SCHEMA-BRIEF")
    M.add_memories("ds1", [{"text": "P42 is a hub.", "kind": "entity"}])
    sp = A._system_prompt("ds1", "analyst")
    assert "P42 is a hub." in sp and "SCHEMA-BRIEF" in sp
    assert "intelligence analyst" in sp           # the analyst playbook base


def test_run_agent_threads_and_remembers(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    captured = []

    def fake_chat(messages, tools=None, **kw):
        captured.append(messages)
        return {"role": "assistant", "content": "REPORT", "tool_calls": []}

    monkeypatch.setattr(A.llm, "chat", fake_chat)
    monkeypatch.setattr(A, "_manifest_brief", lambda ds: "SCHEMA")
    monkeypatch.setattr(A.agent_memory, "extract_memories_async", lambda *a, **k: None)

    r1 = A.run_agent("ds1", "analyst", "First question", language="en")
    assert r1["thread_id"] and r1["report"] == "REPORT"

    r2 = A.run_agent("ds1", "analyst", "Second question",
                     language="en", thread_id=r1["thread_id"])
    assert r2["thread_id"] == r1["thread_id"]
    roles = [(m["role"], m.get("content")) for m in captured[-1]]
    assert ("assistant", "REPORT") in roles       # remembered the prior answer
    assert ("user", "Second question") in roles


def test_run_agent_fresh_thread_has_no_history(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    captured = []

    def fake_chat(messages, tools=None, **kw):
        captured.append(messages)
        return {"role": "assistant", "content": "R", "tool_calls": []}

    monkeypatch.setattr(A.llm, "chat", fake_chat)
    monkeypatch.setattr(A, "_manifest_brief", lambda ds: "SCHEMA")
    monkeypatch.setattr(A.agent_memory, "extract_memories_async", lambda *a, **k: None)

    A.run_agent("ds1", "analyst", "Only question", language="en")
    # system + the single user turn, nothing else
    assert [m["role"] for m in captured[0]] == ["system", "user"]


def test_router_threads_and_memory(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    from app.routers import agents as R
    from app.services import agent_memory as M
    th = M.save_turn("ds1", None, "analyst", "Q", "A", [], "r1")
    assert [t["thread_id"] for t in R.threads("ds1")] == [th["thread_id"]]
    assert R.thread("ds1", th["thread_id"])["turns"][0]["text"] == "Q"
    M.add_memories("ds1", [{"text": "remember me", "kind": "finding"}])
    assert any(m["text"] == "remember me" for m in R.memory("ds1"))
    R.clear_memory("ds1")
    assert R.memory("ds1") == []
    R.del_thread("ds1", th["thread_id"])
    assert R.threads("ds1") == []


def test_router_thread_404(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    from app.routers import agents as R
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        R.thread("ds1", "missing")
