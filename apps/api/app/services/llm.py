"""Chat client for the agent + report layers.

Two providers, selected by LLM_PROVIDER:
  - "openai":  OpenAI-compatible /chat/completions (Ollama locally, the scripted
               mock for offline demos, or any vLLM/TGI OpenAI endpoint).
  - "quickml": Zoho Catalyst QuickML LLM Serving (mandated on Catalyst). Its API is
               NOT OpenAI-shaped — it takes a single prompt + system_prompt and has
               no native tool-calling — so this module adapts both ways: it flattens
               the message list into a prompt, injects the tool schema as text, and
               parses tool calls back out of the completion. Callers (agents.py,
               reports.py) see the same {role, content, tool_calls?} dict either way.

QuickML auth: a static LLM_API_KEY is used if set; otherwise the backend self-mints a
short-lived access token from client credentials and refreshes it before the ~1h TTL,
so a long-running deployment never breaks mid-operation.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from app.core.config import (
    CATALYST_ORG,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_PROVIDER,
    QUICKML_MAX_TOKENS,
    QUICKML_OAUTH_SCOPE,
    QUICKML_OAUTH_SOID,
    ZOHO_ACCOUNTS_URL,
    ZOHO_CLIENT_ID,
    ZOHO_CLIENT_SECRET,
)


class LLMError(RuntimeError):
    pass


def chat(messages: list[dict], tools: list[dict] | None = None,
         temperature: float = 0.2, max_tokens: int = 1500) -> dict:
    """Return the assistant message dict ({role, content, tool_calls?})."""
    if LLM_PROVIDER == "quickml":
        return _chat_quickml(messages, tools, temperature, max_tokens)
    return _chat_openai(messages, tools, temperature, max_tokens)


# --------------------------------------------------------------------------- #
# OpenAI-compatible provider (unchanged behavior)
# --------------------------------------------------------------------------- #
def _chat_openai(messages: list[dict], tools: list[dict] | None,
                 temperature: float, max_tokens: int) -> dict:
    payload: dict[str, Any] = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    headers = {"Content-Type": "application/json"}
    if LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"
    try:
        r = httpx.post(f"{LLM_BASE_URL}/chat/completions", json=payload,
                       headers=headers, timeout=120)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise LLMError(f"LLM endpoint unreachable ({LLM_BASE_URL}): {e}") from e
    data = r.json()
    try:
        return data["choices"][0]["message"]
    except (KeyError, IndexError) as e:
        raise LLMError(f"unexpected LLM response: {json.dumps(data)[:500]}") from e


# --------------------------------------------------------------------------- #
# QuickML LLM Serving adapter
# --------------------------------------------------------------------------- #
_TOOL_FORMAT_INSTRUCTIONS = (
    "\n\nYou have tools that fetch REAL data. Never invent numbers — get them from a tool.\n"
    "AVAILABLE TOOLS:\n{tools}\n\n"
    "To call a tool, reply with ONLY one line of JSON and nothing else:\n"
    '{{"tool": "<name>", "arguments": {{ ... }}}}\n'
    "Call one tool at a time; you may call tools over several turns. When you have "
    "gathered enough information, reply with your FINAL answer as plain prose — not JSON."
)


def _render_tools_spec(tools: list[dict]) -> str:
    """Render an OpenAI tools list into a compact text spec for the prompt."""
    lines: list[str] = []
    for t in tools:
        fn = t.get("function", t)
        name = fn.get("name", "?")
        desc = fn.get("description", "")
        params = (fn.get("parameters") or {}).get("properties", {}) or {}
        required = set((fn.get("parameters") or {}).get("required", []) or [])
        arg_bits = []
        for pname, pschema in params.items():
            typ = (pschema or {}).get("type", "any")
            star = "*" if pname in required else ""
            arg_bits.append(f"{pname}{star}:{typ}")
        args = ", ".join(arg_bits) if arg_bits else "no arguments"
        lines.append(f"- {name}({args}) — {desc}")
    return "\n".join(lines)


def _flatten_messages(messages: list[dict]) -> tuple[str, str]:
    """Split the OpenAI-style message list into (system_prompt, conversation prompt)
    for QuickML's prompt/system_prompt fields."""
    system_bits: list[str] = []
    id_to_name: dict[str, str] = {}
    convo: list[str] = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            system_bits.append(m.get("content") or "")
        elif role == "user":
            convo.append(f"User: {m.get('content', '')}")
        elif role == "assistant":
            tcs = m.get("tool_calls") or []
            if tcs:
                for tc in tcs:
                    fn = tc.get("function", {})
                    nm = fn.get("name", "?")
                    id_to_name[tc.get("id", nm)] = nm
                    convo.append(
                        f"Assistant called tool {nm} with arguments {fn.get('arguments', '{}')}")
            else:
                convo.append(f"Assistant: {m.get('content', '')}")
        elif role == "tool":
            nm = id_to_name.get(m.get("tool_call_id", ""), "tool")
            convo.append(f"Result of {nm}: {m.get('content', '')}")
    system_prompt = "\n\n".join(b for b in system_bits if b)
    prompt = "\n".join(convo) + "\nAssistant:"
    return system_prompt, prompt


_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_tool_call(text: str) -> dict | None:
    """Pull a {tool, arguments} object out of the model's text, if it issued one.
    Returns {"name", "arguments"} or None (None => treat the text as a final answer)."""
    if not text:
        return None
    candidate = text.strip()
    if candidate.startswith("```"):  # strip a ```json ... ``` fence
        candidate = candidate.strip("`")
        if "\n" in candidate:
            candidate = candidate.split("\n", 1)[1]
    m = _JSON_OBJ_RE.search(candidate)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    name = obj.get("tool") or obj.get("name") or obj.get("tool_name")
    if not name or not isinstance(name, str):
        return None
    args = obj.get("arguments")
    if args is None:
        args = obj.get("args", {})
    return {"name": name, "arguments": args if isinstance(args, dict) else {}}


def _extract_text(data: Any) -> str:
    """Tolerantly pull the generated text out of QuickML's JSON response. QuickML
    returns it under "response"; other common shapes are handled defensively."""
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        for k in ("response", "output", "text", "content", "result",
                  "answer", "generated_text", "completion", "message"):
            v = data.get(k)
            if isinstance(v, str) and v.strip():
                return v
        if "data" in data:
            inner = _extract_text(data["data"])
            if inner:
                return inner
        try:  # OpenAI-ish nesting, just in case
            ch = data["choices"][0]
            return ch.get("text") or ch["message"]["content"]
        except (KeyError, IndexError, TypeError):
            pass
    raise LLMError(f"could not find generated text in QuickML response: "
                   f"{json.dumps(data, default=str)[:500]}")


# A self-minted QuickML access token, cached and refreshed before its ~1h expiry so a
# long-running deployment never breaks at the token TTL.
_qml_token: dict[str, Any] = {"value": None, "exp": 0.0}


def _get_quickml_token(force_refresh: bool = False) -> str:
    """Return a valid QuickML bearer token: a static LLM_API_KEY if provided, else one
    self-minted (and cached) via the client_credentials grant."""
    if LLM_API_KEY:
        return LLM_API_KEY
    if not (ZOHO_CLIENT_ID and ZOHO_CLIENT_SECRET):
        raise LLMError("QuickML auth not configured: set LLM_API_KEY, or "
                       "ZOHO_CLIENT_ID + ZOHO_CLIENT_SECRET for self-minting")
    now = time.time()
    if not force_refresh and _qml_token["value"] and _qml_token["exp"] - now > 60:
        return _qml_token["value"]
    try:
        r = httpx.post(f"{ZOHO_ACCOUNTS_URL}/oauth/v2/token", data={
            "grant_type": "client_credentials",
            "client_id": ZOHO_CLIENT_ID,
            "client_secret": ZOHO_CLIENT_SECRET,
            "scope": QUICKML_OAUTH_SCOPE,
            "soid": QUICKML_OAUTH_SOID,
        }, timeout=30)
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError as e:
        raise LLMError(f"QuickML token mint failed ({ZOHO_ACCOUNTS_URL}): {e}") from e
    token = data.get("access_token")
    if not token:
        raise LLMError(f"QuickML token mint returned no access_token: {json.dumps(data)[:300]}")
    _qml_token["value"] = token
    _qml_token["exp"] = now + float(data.get("expires_in", 3600))
    return token


def _chat_quickml(messages: list[dict], tools: list[dict] | None,
                  temperature: float, max_tokens: int) -> dict:
    if not CATALYST_ORG:
        raise LLMError("CATALYST_ORG env var is required for QuickML LLM Serving")
    system_prompt, prompt = _flatten_messages(messages)
    if tools:
        system_prompt += _TOOL_FORMAT_INSTRUCTIONS.format(tools=_render_tools_spec(tools))
    payload = {
        "prompt": prompt,
        "model": LLM_MODEL,
        "system_prompt": system_prompt,
        "top_p": 0.9,
        "top_k": 50,
        "temperature": temperature,
        # QuickML's max_tokens is the TOTAL (input+output) context budget, not just the
        # output length — so use a generous fixed budget, not the caller's output hint.
        "max_tokens": QUICKML_MAX_TOKENS,
    }
    headers = {"Content-Type": "application/json", "CATALYST-ORG": CATALYST_ORG}
    # LLM_BASE_URL is the full .../llm/chat URL in quickml mode. Retry once with a freshly
    # minted token if a cached one is rejected.
    data: Any = None
    for attempt in (1, 2):
        headers["Authorization"] = f"Bearer {_get_quickml_token(force_refresh=(attempt == 2))}"
        try:
            r = httpx.post(LLM_BASE_URL, json=payload, headers=headers, timeout=120)
            if r.status_code in (401, 403) and attempt == 1:
                continue  # token likely expired — refresh and retry once
            r.raise_for_status()
            data = r.json()
            break
        except httpx.HTTPError as e:
            if attempt == 2:
                raise LLMError(f"QuickML endpoint error ({LLM_BASE_URL}): {e}") from e
    text = _extract_text(data)
    if tools:
        call = _parse_tool_call(text)
        if call:
            return {
                "role": "assistant",
                "content": text,
                "tool_calls": [{
                    "id": "call_" + call["name"],
                    "type": "function",
                    "function": {
                        "name": call["name"],
                        "arguments": json.dumps(call["arguments"]),
                    },
                }],
            }
    return {"role": "assistant", "content": text}


# --------------------------------------------------------------------------- #
# Translation helper — used to localize generated/structured text (agent
# reports, insight findings) into Kannada. The model reasons in English (its
# strength for tool-calling and numbers); only the final user-facing text is
# translated, so output is reliably Kannada rather than a hit-or-miss inline hint.
# --------------------------------------------------------------------------- #
_KN_SYS = ("You are an expert English-to-Kannada translator for police intelligence "
           "reports. You always output fluent Kannada (ಕನ್ನಡ) script — never English prose.")


def translate(text: str, language: str) -> str:
    """Translate `text` into `language` (only 'kn' is non-trivial today). Returns the
    original on 'en', empty input, or any failure — never raises. The translation
    INSTRUCTION lives in the user turn with the text embedded, so the model translates
    instead of just continuing the English prose."""
    if language != "kn" or not text or not str(text).strip():
        return text
    try:
        msg = chat([
            {"role": "system", "content": _KN_SYS},
            {"role": "user", "content":
                "Translate the following police-report text into natural Kannada. Keep every "
                "number, date, percentage, z-score, ID/FIR and English proper name (places, "
                "people) unchanged. Output only the Kannada itself — no preamble, no quotes, "
                "no code fences.\n\n" + str(text)},
        ], max_tokens=2000)
        out = (msg.get("content") or "").strip()
        # the model sometimes wraps the result in a ``` or \"\"\" fence (and a meta preamble
        # before it) — unwrap to just the fenced content when that happens.
        m = re.search(r'(?:```|""")\s*(.+?)\s*(?:```|""")', out, re.DOTALL)
        if m:
            out = m.group(1).strip()
        return out or text
    except Exception:
        return text


def translate_batch(texts: list[str], language: str) -> list[str]:
    """Translate a list of short strings in ONE call as a numbered list (order
    preserved; parses each line back, per-item fallback on a miss)."""
    if language != "kn" or not texts:
        return texts
    try:
        numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
        msg = chat([
            {"role": "system", "content": _KN_SYS},
            {"role": "user", "content":
                "Translate each numbered line below into natural Kannada, keeping numbers, dates, "
                "IDs and English proper names (places, people) unchanged. Return the SAME numbered "
                "list with exactly one Kannada line per number, nothing else.\n\n" + numbered},
        ], max_tokens=3000)
        out: dict[int, str] = {}
        for line in (msg.get("content") or "").splitlines():
            m = re.match(r"\s*(\d+)[.)]\s*(.+)", line)
            if m:
                out[int(m.group(1))] = m.group(2).strip()
        return [out.get(i + 1) or texts[i] for i in range(len(texts))]
    except Exception:
        return texts
