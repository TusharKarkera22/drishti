"""Offline checks for the QuickML adapter's pure logic (no network needed).
Run from apps/api:  PYTHONPATH=. .venv/bin/python scripts/test_quickml_adapter.py
The live HTTP/response-shape is confirmed separately against the real endpoint.
"""
import sys

from app.services.agents import TOOLS
from app.services.llm import (
    _extract_text,
    _flatten_messages,
    _parse_tool_call,
    _render_tools_spec,
)

fails: list[str] = []


def check(name: str, cond: bool) -> None:
    print(("PASS" if cond else "FAIL"), "-", name)
    if not cond:
        fails.append(name)


# --- _flatten_messages: a realistic agent turn (system, user, tool call, result) ---
msgs = [
    {"role": "system", "content": "You are the Trend Sentinel agent."},
    {"role": "user", "content": "What is spiking?"},
    {"role": "assistant", "content": '{"tool":"get_spike_alerts","arguments":{}}',
     "tool_calls": [{"id": "call_get_spike_alerts", "type": "function",
                     "function": {"name": "get_spike_alerts", "arguments": "{}"}}]},
    {"role": "tool", "tool_call_id": "call_get_spike_alerts",
     "content": '{"alerts":[{"area":"Bengaluru","z":10.1}]}'},
]
sysp, prompt = _flatten_messages(msgs)
check("system captured into system_prompt", "Trend Sentinel" in sysp)
check("user rendered", "User: What is spiking?" in prompt)
check("assistant tool-call rendered", "called tool get_spike_alerts" in prompt)
check("tool result labeled with tool name", "Result of get_spike_alerts" in prompt)
check("prompt ends with the assistant cue", prompt.rstrip().endswith("Assistant:"))

# --- _parse_tool_call ---
check("plain tool JSON parses",
      _parse_tool_call('{"tool":"run_query","arguments":{"table":"incidents"}}')
      == {"name": "run_query", "arguments": {"table": "incidents"}})
check("fenced ```json tool call parses",
      (_parse_tool_call('```json\n{"tool":"get_area_risk","arguments":{}}\n```') or {}).get("name")
      == "get_area_risk")
check("nested-object arguments parse",
      (_parse_tool_call('{"tool":"fetch_records","arguments":{"table":"accused","filters":{"id":"P42"}}}') or {})
      .get("arguments", {}).get("filters") == {"id": "P42"})
check("prose final answer is NOT a tool call",
      _parse_tool_call("Final report: crime is up in Mangaluru City per capita.") is None)
check("JSON without a tool key is NOT a tool call",
      _parse_tool_call('{"foo": 1, "bar": 2}') is None)

# --- _extract_text: tolerate several response shapes ---
check("extract {output}", _extract_text({"output": "hello"}) == "hello")
check("extract nested {data:{response}}", _extract_text({"data": {"response": "hi there"}}) == "hi there")
check("extract OpenAI-ish nesting",
      _extract_text({"choices": [{"message": {"content": "yo"}}]}) == "yo")

# --- _render_tools_spec ---
spec = _render_tools_spec(TOOLS)
check("tools spec includes run_query", "run_query(" in spec)
check("tools spec stars a required arg", "query*" in spec)  # graph_search.query is required

print()
if fails:
    print(f"RESULT: {len(fails)} FAILED -> {fails}")
    sys.exit(1)
print("RESULT: ALL PASS")
