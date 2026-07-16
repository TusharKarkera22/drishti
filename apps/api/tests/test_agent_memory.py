from app.core import store
from app.services import agent_memory as M


def _tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)


def test_save_turn_creates_thread_with_title(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    th = M.save_turn("ds1", None, "analyst", "Who is P42 linked to?", "REPORT", [], "run1")
    assert th["thread_id"] and th["playbook"] == "analyst"
    assert th["title"] == "Who is P42 linked to?"
    assert [t["role"] for t in th["turns"]] == ["user", "agent"]
    assert M.load_thread("ds1", th["thread_id"])["turns"][1]["text"] == "REPORT"


def test_save_turn_appends_to_existing(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    th = M.save_turn("ds1", None, "analyst", "Q1", "A1", [], "r1")
    th2 = M.save_turn("ds1", th["thread_id"], "analyst", "Q2", "A2", [], "r2")
    assert th2["thread_id"] == th["thread_id"]
    assert len(th2["turns"]) == 4
    assert th2["updated_at"] >= th2["created_at"]


def test_list_threads_filters_by_playbook(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    a = M.save_turn("ds1", None, "analyst", "Qa", "Aa", [], "r1")
    b = M.save_turn("ds1", None, "case_linker", "Qb", "Ab", [], "r2")
    assert {t["thread_id"] for t in M.list_threads("ds1")} == {a["thread_id"], b["thread_id"]}
    only = M.list_threads("ds1", playbook="case_linker")
    assert [t["thread_id"] for t in only] == [b["thread_id"]]
    assert only[0]["turn_count"] == 2 and only[0]["title"] == "Qb"


def test_delete_and_missing_thread(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    th = M.save_turn("ds1", None, "analyst", "Q", "A", [], "r1")
    M.delete_thread("ds1", th["thread_id"])
    assert M.load_thread("ds1", th["thread_id"]) is None
    assert M.list_threads("ds1") == []
    assert M.load_thread("ds1", "nope") is None


def test_history_messages_empty_for_fresh(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    assert M.history_messages("ds1", None) == []
    assert M.history_messages("ds1", "missing") == []


def test_history_messages_returns_prior_turns(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    th = M.save_turn("ds1", None, "analyst", "Q1", "A1", [], "r1")
    assert M.history_messages("ds1", th["thread_id"]) == [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "A1"},
    ]


def test_history_messages_caps_to_last_4_exchanges(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    tid = None
    for i in range(6):
        tid = M.save_turn("ds1", tid, "analyst", f"Q{i}", f"A{i}", [], f"r{i}")["thread_id"]
    msgs = M.history_messages("ds1", tid)
    assert len(msgs) == 8                # 4 exchanges
    assert msgs[0]["content"] == "Q2"    # Q0, Q1 dropped


def test_add_memories_dedups_and_caps(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    M.add_memories("ds1", [{"text": "P42 is a hub.", "kind": "entity"},
                           {"text": "p42 is a HUB.", "kind": "entity"}])  # normalized dup
    assert len(M.load_memory("ds1")) == 1
    M.add_memories("ds1", [{"text": f"fact {i}", "kind": "finding"} for i in range(40)])
    assert len(M.load_memory("ds1")) == 30   # capped


def test_load_memory_newest_first(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    M.add_memories("ds1", [{"text": "first", "kind": "finding"}])
    M.add_memories("ds1", [{"text": "second", "kind": "finding"}])
    assert [m["text"] for m in M.load_memory("ds1")][0] == "second"


def test_memory_block_format_and_empty(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    assert M.memory_block("ds1") == ""
    M.add_memories("ds1", [{"text": "P42 ties 9 cases.", "kind": "entity"}])
    blk = M.memory_block("ds1")
    assert "WHAT YOU REMEMBER" in blk and "[entity] P42 ties 9 cases." in blk


def test_clear_memory(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    M.add_memories("ds1", [{"text": "x", "kind": "finding"}])
    M.clear_memory("ds1")
    assert M.load_memory("ds1") == [] and M.memory_block("ds1") == ""


import time


def test_extract_merges_llm_and_seed(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    steps = [{"tool": "graph_ego", "args": {"node_id": "accused:P42"}, "result_preview": ""}]
    fake = lambda messages: '[{"text":"P42 ties 9 cases via 3 phones.","kind":"entity"}]'
    items = M.extract_memories("ds1", "case_linker", "Investigate P42", "report", steps,
                               fake, thread_id="t1")
    texts = [i["text"] for i in items]
    assert "P42 ties 9 cases via 3 phones." in texts
    assert any("accused:P42" in t for t in texts)          # deterministic seed
    assert all(i["source_playbook"] == "case_linker" for i in items)
    assert all(i["source_thread"] == "t1" for i in items)


def test_extract_tolerates_bad_llm_output(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    steps = [{"tool": "graph_search", "args": {"query": "RING/2024"}, "result_preview": ""}]
    items = M.extract_memories("ds1", "analyst", "q", "a", steps, lambda m: "sorry, no json")
    assert [i["text"] for i in items] == ["Looked up RING/2024 in the link graph."]


def test_extract_llm_raises_returns_seed_only(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    def boom(m):
        raise RuntimeError("down")
    assert M.extract_memories("ds1", "analyst", "q", "a", [], boom) == []  # no graph steps


def test_async_extract_persists(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    fake = lambda m: '[{"text":"async fact","kind":"finding"}]'
    M.extract_memories_async("ds1", "analyst", "q", "a", [], thread_id="t1", llm_fn=fake)
    for _ in range(40):
        if M.load_memory("ds1"):
            break
        time.sleep(0.05)
    assert any(i["text"] == "async fact" for i in M.load_memory("ds1"))


def test_async_extract_never_raises_on_llm_error(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    def boom(m):
        raise RuntimeError("down")
    M.extract_memories_async("ds1", "analyst", "q", "a", [], llm_fn=boom)  # must not raise
    time.sleep(0.2)
    assert M.load_memory("ds1") == []
