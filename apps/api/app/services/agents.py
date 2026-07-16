"""Agentic layer: a tool-calling loop over the platform's own APIs.

Agents don't chat about the data — they *act* on it: run aggregations,
pull spike alerts and risk scores, traverse the link graph, then write a
structured memo. Every step (thought, tool call, result) is recorded so
the UI can show visible reasoning, and runs are persisted as memory.
"""

from __future__ import annotations

import datetime
import json
import uuid

from app.core import store
from app.models.manifest import SemanticRole
from app.routers import graph as graph_router
from app.routers.query import Measure, QueryRequest, fetch_records, run_query
from app.services import analytics as analytics_svc
from app.services import graph as graph_svc
from app.services import agent_memory
from app.services import llm

MAX_STEPS = 8

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_query",
            "description": "Aggregate the dataset. Group by dimensions and/or time, with optional filters. Use the manifest's column names exactly.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {"type": "string"},
                    "dimensions": {"type": "array", "items": {"type": "string"}},
                    "time_dimension": {"type": "string"},
                    "time_grain": {"type": "string", "enum": ["day", "week", "month"]},
                    "agg": {"type": "string", "enum": ["count", "sum", "avg", "distinct"]},
                    "agg_column": {"type": "string"},
                    "filters": {"type": "object"},
                    "limit": {"type": "integer"},
                },
                "required": ["table"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_spike_alerts",
            "description": "Emerging-trend alerts: area/category cells whose recent volume spikes above their historical baseline.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_area_risk",
            "description": "Per-area risk scores (0-100) combining recent volume, trend slope, and spikes, with a short-term forecast.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "graph_search",
            "description": "Find people/cases in the link-analysis network by name or id.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "graph_ego",
            "description": "Get the connection network around a node id (e.g. 'case:FIR123' or 'accused:P42'): linked cases, associates, shared phones/addresses.",
            "parameters": {
                "type": "object",
                "properties": {"node_id": {"type": "string"}, "hops": {"type": "integer"}},
                "required": ["node_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_records",
            "description": "Fetch raw rows from a table with equality filters, for inspecting specific cases.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {"type": "string"},
                    "filters": {"type": "object"},
                    "limit": {"type": "integer"},
                },
                "required": ["table"],
            },
        },
    },
]


def _manifest_brief(dataset_id: str) -> str:
    m = store.load_manifest(dataset_id)
    lines = [f"Dataset: {m.name} (domain pack: {m.domain_pack})"]
    for t in m.tables:
        cols = ", ".join(f"{c.name}[{c.semantic_role.value}]" for c in t.columns)
        primary = " (PRIMARY/fact table)" if t.is_primary else ""
        lines.append(f"- table {t.name}{primary}, {t.row_count} rows: {cols}")
    for r in m.relations:
        lines.append(f"- relation: {r.from_table}.{r.from_column} -> {r.to_table}.{r.to_column}")
    return "\n".join(lines)


def _exec_tool(dataset_id: str, name: str, args: dict) -> dict:
    manifest = store.load_manifest(dataset_id)
    primary = manifest.primary_table()
    if name == "run_query":
        req = QueryRequest(
            table=args.get("table", primary.name if primary else ""),
            dimensions=args.get("dimensions", []),
            time_dimension=args.get("time_dimension"),
            time_grain=args.get("time_grain", "day"),
            measures=[Measure(agg=args.get("agg", "count"), column=args.get("agg_column"))],
            filters=args.get("filters", {}),
            limit=min(args.get("limit") or 50, 200),  # `or` guards against the model passing limit=null
        )
        return run_query(dataset_id, req)
    if name == "get_spike_alerts":
        t = primary
        time_col = t.first_by_role(SemanticRole.TIMESTAMP) or t.first_by_role(SemanticRole.DATE)
        cat = t.first_by_role(SemanticRole.CATEGORY)
        area = t.first_by_role(SemanticRole.ADMIN_AREA_1)
        return analytics_svc.spike_alerts(
            dataset_id, t, time_col.name,
            category_col=cat.name if cat else None,
            area_col=area.name if area else None,
            window_days=28, z_threshold=2.0,
        )
    if name == "get_area_risk":
        t = primary
        time_col = t.first_by_role(SemanticRole.TIMESTAMP) or t.first_by_role(SemanticRole.DATE)
        area = t.first_by_role(SemanticRole.ADMIN_AREA_1)
        demo = analytics_svc.load_demographics(dataset_id, manifest, area.name)
        return analytics_svc.area_risk(dataset_id, t, time_col.name, area.name,
                                       horizon_days=7, demographics=demo)
    if name == "graph_search":
        g, _ = graph_router._graph(dataset_id)  # shared in-process cache
        return {"results": graph_svc.find_node(g, args["query"])}
    if name == "graph_ego":
        g, _ = graph_router._graph(dataset_id)
        return graph_svc.ego_network(g, args["node_id"], hops=args.get("hops", 2))
    if name == "fetch_records":
        req = QueryRequest(table=args["table"], filters=args.get("filters", {}),
                           limit=min(args.get("limit") or 20, 50))
        return fetch_records(dataset_id, req)
    return {"error": f"unknown tool {name}"}


PLAYBOOKS = {
    "analyst": (
        "You are an intelligence analyst agent. Answer the user's question about the dataset "
        "by calling tools — never guess numbers. Cite which tool results support each claim."
    ),
    "patrol_planner": (
        "You are the Patrol Planner agent for a state police command center. "
        "Workflow: 1) call get_area_risk, 2) call get_spike_alerts, 3) for the top 3 risk areas, "
        "use run_query to find their peak hours (dimension hour(<timestamp col>)) and top crime "
        "categories. Then write a deployment recommendation memo: which areas need additional "
        "patrols, at which hours, and why — grounded in the numbers you retrieved."
    ),
    "case_linker": (
        "You are the Case Linker agent. Given a case/FIR id, 1) graph_search for it, "
        "2) graph_ego around it (2 hops) to find linked people, their other cases, and shared "
        "phones/addresses, 3) fetch_records for the most connected linked cases to compare modus "
        "operandi. Write a case-linkage memo: likely related cases, the connecting evidence "
        "(shared person / phone / address), and recommended next investigative steps."
    ),
    "trend_sentinel": (
        "You are the Trend Sentinel agent. Call get_spike_alerts and get_area_risk, then for each "
        "significant spike use run_query to characterize it (when it started, which categories). "
        "Write an alert bulletin: what is spiking, where, how severe vs baseline, and what to watch."
    ),
}


def _system_prompt(dataset_id: str, playbook: str) -> str:
    base = PLAYBOOKS.get(playbook, PLAYBOOKS["analyst"])
    parts = [base]
    mem = agent_memory.memory_block(dataset_id)
    if mem:
        parts.append(mem)
    parts.append("DATASET SCHEMA:\n" + _manifest_brief(dataset_id))
    return "\n\n".join(parts)


def _finish(dataset_id, playbook, user_input, steps, final, thread_id) -> dict:
    run = _persist_run(dataset_id, playbook, user_input, steps, final)  # audit log (unchanged)
    thread = agent_memory.save_turn(dataset_id, thread_id, playbook,
                                    user_input, final, steps, run["run_id"])
    agent_memory.extract_memories_async(dataset_id, playbook, user_input, final, steps,
                                        thread_id=thread["thread_id"])
    return {"run_id": run["run_id"], "thread_id": thread["thread_id"],
            "steps": steps, "report": final}


def run_agent(dataset_id: str, playbook: str, user_input: str,
              language: str = "en", thread_id: str | None = None) -> dict:
    messages = [{"role": "system", "content": _system_prompt(dataset_id, playbook)}]
    messages += agent_memory.history_messages(dataset_id, thread_id)
    messages.append({"role": "user", "content": user_input or "Run your standard playbook."})
    steps: list[dict] = []

    for _ in range(MAX_STEPS):
        msg = llm.chat(messages, tools=TOOLS)
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            # Agent reasons in English; translate the final memo so Kannada is reliable.
            final = llm.translate(msg.get("content", ""), language)
            return _finish(dataset_id, playbook, user_input, steps, final, thread_id)

        messages.append(msg)
        for tc in tool_calls:
            fn = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            try:
                result = _exec_tool(dataset_id, fn, args)
            except Exception as e:  # surface tool failures to the model, don't crash the run
                result = {"error": str(e)}
            steps.append({"tool": fn, "args": args,
                          "result_preview": json.dumps(result, default=str)[:400]})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", fn),
                "content": json.dumps(result, default=str)[:6000],
            })

    final = llm.translate(
        "Agent reached its step limit before finishing. Partial findings are in the step log.",
        language)
    return _finish(dataset_id, playbook, user_input, steps, final, thread_id)


def _persist_run(dataset_id: str, playbook: str, user_input: str,
                 steps: list[dict], report: str) -> dict:
    record = {
        "run_id": uuid.uuid4().hex[:10],
        "playbook": playbook,
        "input": user_input,
        "steps": steps,
        "report": report,
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    path = store.dataset_dir(dataset_id) / "agent_runs.jsonl"
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")
    return record


def list_runs(dataset_id: str, limit: int = 20) -> list[dict]:
    path = store.dataset_dir(dataset_id) / "agent_runs.jsonl"
    if not path.exists():
        return []
    lines = path.read_text().strip().splitlines()
    return [json.loads(l) for l in lines[-limit:]][::-1]
