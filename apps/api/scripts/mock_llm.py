"""Tiny OpenAI-compatible mock LLM for testing the agent loop offline.

Tool-calling requests: turn 1 calls get_spike_alerts, turn 2 get_area_risk,
turn 3 writes a 'report' quoting the tool output it received. Plain requests
(no tools — e.g. the handbook executive summary) get a canned summary.
Kannada is returned when the system prompt asks for ಕನ್ನಡ.
Run: .venv/bin/python scripts/mock_llm.py  (listens on :11435)
"""

import json

import uvicorn
from fastapi import FastAPI, Request

app = FastAPI()

KN_BULLETIN = (
    "ಎಚ್ಚರಿಕೆ ಬುಲೆಟಿನ್ (mock): ಬೆಂಗಳೂರು ನಗರದಲ್ಲಿ ಸೈಬರ್ ಅಪರಾಧ ಪ್ರಕರಣಗಳು "
    "ಬೇಸ್‌ಲೈನ್‌ಗಿಂತ ಗಮನಾರ್ಹವಾಗಿ ಹೆಚ್ಚಾಗಿವೆ. ಹೂಡಿಕೆ ಆ್ಯಪ್ ವಂಚನೆ ಮತ್ತು UPI ವಂಚನೆ "
    "ಪ್ರಮುಖ ವಿಧಗಳು. ತಕ್ಷಣ ಸೈಬರ್ ಠಾಣೆಗಳಿಗೆ ಹೆಚ್ಚುವರಿ ಸಿಬ್ಬಂದಿ ನಿಯೋಜಿಸಲು ಶಿಫಾರಸು."
)
KN_SUMMARY = (
    "ಕಾರ್ಯನಿರ್ವಾಹಕ ಸಾರಾಂಶ (mock): ಈ ಅವಧಿಯಲ್ಲಿ ದಾಖಲಾದ ಒಟ್ಟು ಪ್ರಕರಣಗಳಲ್ಲಿ ಕಳ್ಳತನ "
    "ಮತ್ತು ಸೈಬರ್ ಅಪರಾಧ ಮುಂಚೂಣಿಯಲ್ಲಿವೆ. ಬೆಂಗಳೂರು ನಗರದಲ್ಲಿ ಸೈಬರ್ ಅಪರಾಧದ ತೀವ್ರ "
    "ಏರಿಕೆ ಕಂಡುಬಂದಿದೆ; ಜನಸಾಂದ್ರತೆ ಹೆಚ್ಚಿರುವ ಜಿಲ್ಲೆಗಳು ಹೆಚ್ಚಿನ ಅಪಾಯದಲ್ಲಿವೆ."
)


def _wants_kannada(messages: list[dict]) -> bool:
    sys_txt = " ".join(m.get("content") or "" for m in messages if m.get("role") == "system")
    return "ಕನ್ನಡ" in sys_txt or "Kannada" in sys_txt


@app.post("/v1/chat/completions")
async def completions(req: Request):
    body = await req.json()
    messages = body["messages"]
    tool_msgs = [m for m in messages if m.get("role") == "tool"]

    if not body.get("tools"):
        # Plain completion — the handbook executive summary path.
        if _wants_kannada(messages):
            content = KN_SUMMARY
        else:
            content = ("Executive summary (mock): overall case volume is stable, but "
                       "Cybercrime in Bengaluru City is running far above its baseline, "
                       "led by Investment App Fraud and UPI Fraud. Dense, urbanized "
                       "districts carry the highest composite risk; sustained attention "
                       "to cyber reporting capacity is recommended.")
        return {"choices": [{"message": {"role": "assistant", "content": content}}]}

    if len(tool_msgs) == 0:
        msg = {"role": "assistant", "content": None, "tool_calls": [
            {"id": "t1", "type": "function",
             "function": {"name": "get_spike_alerts", "arguments": "{}"}}]}
    elif len(tool_msgs) == 1:
        msg = {"role": "assistant", "content": None, "tool_calls": [
            {"id": "t2", "type": "function",
             "function": {"name": "get_area_risk", "arguments": "{}"}}]}
    elif _wants_kannada(messages):
        msg = {"role": "assistant", "content": KN_BULLETIN}
    else:
        spikes = json.loads(tool_msgs[0]["content"])
        top = spikes.get("alerts", [{}])[0]
        risk = json.loads(tool_msgs[1]["content"])
        top_risk = (risk.get("areas") or [{}])[0]
        per_capita = (f" Per-capita rate there is {top_risk.get('per_lakh_daily')} "
                      f"cases/day per lakh residents." if top_risk.get("per_lakh_daily") else "")
        msg = {"role": "assistant",
               "content": f"ALERT BULLETIN (mock): top spike is "
                          f"{top.get('crime_group')} in {top.get('district')} "
                          f"at +{top.get('pct_change')}% vs baseline (z={top.get('z_score')}). "
                          f"Highest composite risk: {top_risk.get('area')} "
                          f"(score {top_risk.get('risk_score')}).{per_capita}"}

    return {"choices": [{"message": msg}]}


if __name__ == "__main__":
    uvicorn.run(app, port=11435, log_level="warning")
