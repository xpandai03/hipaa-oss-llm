Agent Build Context (Responses API + Agents SDK)

Audience: Claude Code (use this as project context)
Goal: Ship a minimal, production-able agent today that we can plug into a custom chat UI. Agent must support: chat, Web Search, File Search (RAG), and Computer Use (browser control). We’ll parameterize the system prompt and custom functions so Raunek can fill specifics quickly.

⸻

1) Objectives (non-negotiable)
	•	✅ Stand up a backend service that exposes a chat interface (WebSocket streaming + optional REST).
	•	✅ Use OpenAI Responses API via the Agents SDK.
	•	✅ Enable built-in tools: web_search, file_search, computer_use.
	•	✅ Support custom function tools (we’ll scaffold a few examples; Raunek will confirm which to keep).
	•	✅ Persist conversation state (lightweight): in-memory session with easy swap to Redis/DB.
	•	✅ Provide a tiny frontend (HTML/JS or Next.js page) for quick manual testing.
	•	✅ Include guardrails: auth stub, rate-limit stub, error handling, tracing hooks.

⸻

2) Assumptions & Open Questions (Claude must ask)
	1.	System prompt: what persona, tone, and hard rules?
	•	TODO: Ask user for domain focus (e.g., “medspa concierge + ops assistant”), voice, refusal rules, and citation policy.
	2.	Custom functions (beyond built-ins):
	•	Examples we can wire: create_trello_card, google_sheet_append_row, fetch_calendar_slots, send_email_draft.
	•	TODO: Ask which 2–4 to prioritize today.
	3.	Storage: start with in-memory, but do we switch to Redis/Postgres on day one?
	4.	Front-end: quick HTML test page OK, or do we drop a Next.js client component?
	5.	Deployment target: local first; later Render/Fly/Vercel?

⸻

3) Tech Stack
	•	Backend: Python 3.10+, FastAPI, uvicorn, python-dotenv
	•	OpenAI: Agents SDK (wraps Responses + tools)
	•	Streaming: WebSocket (server → client token stream)
	•	Optional: Redis (session store), Postgres (logs), S3/GCS (file uploads)
	•	Frontend (minimal): static HTML/JS page (upgradeable to Next.js later)

⸻

4) Project Structure

/agent-app
  ├─ app.py                    # FastAPI service (WS + REST)
  ├─ agent_runtime.py          # Agent/Session factory, tools, hooks
  ├─ tools/
  │   ├─ __init__.py
  │   ├─ trello.py             # example custom function tool (scaffold)
  │   ├─ sheets.py             # example custom function tool (scaffold)
  ├─ prompts/
  │   └─ system_prompt.md      # << FILLED BY USER >>
  ├─ public/
  │   └─ chat.html             # minimal chat client (WebSocket)
  ├─ .env.example
  ├─ requirements.txt
  └─ README.md


⸻

5) Environment & Secrets

.env.example

OPENAI_API_KEY=sk-xxxxx
# Optional 3P tool creds (only if we enable them today)
TRELLO_KEY=
TRELLO_TOKEN=
GOOGLE_SERVICE_ACCOUNT_JSON_BASE64=


⸻

6) Agents SDK Wiring (core)

Claude: implement agent_runtime.py first.

# agent_runtime.py
import os
from typing import AsyncIterator, Dict, Any, List

from dotenv import load_dotenv
load_dotenv()

# OpenAI Agents SDK primitives (adjust import names to actual SDK)
from openai_agents import Agent, Tool
from openai_agents.tools import WebSearchTool, FileSearchTool, ComputerUseTool

# --- Custom tools scaffolds (safe no-ops until configured) ---
from tools.trello import create_trello_card_tool   # Tool subclass
from tools.sheets import append_sheet_row_tool     # Tool subclass

DEFAULT_MODEL = "gpt-4o-mini"  # fast; can bump to gpt-4o if needed

def build_agent(
    system_instructions: str,
    enable_web: bool = True,
    enable_file: bool = True,
    enable_computer: bool = True,
    custom_tools: List[Tool] | None = None,
) -> Agent:
    tools: List[Tool] = []
    if enable_web:
        tools.append(WebSearchTool())
    if enable_file:
        tools.append(FileSearchTool())
    if enable_computer:
        tools.append(ComputerUseTool())

    if custom_tools:
        tools.extend(custom_tools)

    agent = Agent(
        model=DEFAULT_MODEL,
        instructions=system_instructions,
        tools=tools,
        # Optional defaults: temperature, max_output_tokens, etc.
    )
    return agent

def new_session(agent: Agent):
    """Return a new conversational session (SDK maintains short-term history).
       NOTE: For production, we may mirror history into Redis/DB.
    """
    return agent.new_session()

async def run_stream(session, user_message: str) -> AsyncIterator[str]:
    """Stream assistant output; the SDK handles tool calls inside."""
    async for chunk in session.run_stream(user_message):
        yield chunk.delta or ""


⸻

7) FastAPI App (WebSocket + REST)

Claude: implement app.py. Keep it minimal and robust.

# app.py
import os
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv

from agent_runtime import build_agent, new_session, run_stream
load_dotenv()

app = FastAPI(title="Agent Backend")

# ---- Load system prompt (fallback text if not provided yet) ----
DEFAULT_SYSTEM = (
    "You are Raunek's AI agent. Be concise, cite sources when using web_search. "
    "Prefer on-file answers with file_search. Use computer_use only when the user "
    "explicitly asks to perform an action in the browser."
)
try:
    with open("prompts/system_prompt.md", "r") as f:
        DEFAULT_SYSTEM = f.read().strip() or DEFAULT_SYSTEM
except FileNotFoundError:
    pass

# ---- Build the agent instance + create a new session per connection ----
BASE_AGENT = build_agent(
    system_instructions=DEFAULT_SYSTEM,
    enable_web=True, enable_file=True, enable_computer=True,
    custom_tools=[]  # attach create_trello_card_tool(), append_sheet_row_tool() when ready
)

# ---- Minimal HTML for smoke testing ----
HTML = """
<!doctype html><meta charset="utf-8"/>
<style>
body{font-family:system-ui;margin:2rem;max-width:780px}
#log{white-space:pre-wrap;border:1px solid #ddd;padding:12px;min-height:300px}
input{width:78%} button{width:20%}
</style>
<h3>Agent Chat (WebSocket)</h3>
<div id="log"></div>
<input id="q" placeholder="Ask me something..."/><button onclick="send()">Send</button>
<script>
const ws = new WebSocket(`ws://${location.host}/ws`);
ws.onmessage = (e)=>{document.getElementById('log').textContent += e.data}
function send(){
  const v=document.getElementById('q').value;
  ws.send(v);
  document.getElementById('log').textContent += "\\nYou: " + v + "\\n";
  document.getElementById('q').value="";
}
</script>
"""
@app.get("/")
def home(): return HTMLResponse(HTML)

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    session = new_session(BASE_AGENT)
    try:
        while True:
            user_msg = await websocket.receive_text()
            async for token in run_stream(session, user_msg):
                await websocket.send_text(token)
            await websocket.send_text("\n")  # end of turn
    except Exception:
        await websocket.close()

# Optional REST for non-stream usage (useful for n8n/Make)
@app.post("/chat")
async def chat(payload: dict):
    text = payload.get("message")
    if not text:
        raise HTTPException(400, "Missing 'message'")
    session = new_session(BASE_AGENT)
    out = []
    async for token in run_stream(session, text):
        out.append(token)
    return JSONResponse({"reply": "".join(out)})

Run locally

python -m venv .venv && source .venv/bin/activate
pip install fastapi uvicorn python-dotenv openai-agents
uvicorn app:app --reload
# open http://localhost:8000


⸻

8) File Search (RAG) Bootstrap
	•	Upload files via the OpenAI project console or API and ensure indexing is enabled for file_search.
	•	Policy: Prefer file content when relevant; cite doc titles/sections in answers.
	•	Claude: add a helper in README with exact steps to upload/index docs once Raunek supplies files.

⸻

9) Computer Use (Browser Control)
	•	Enabled via ComputerUseTool() in the agent.
	•	Usage policy in prompt: only invoke when user explicitly requests an action (“log into X”, “fill Y form”), narrate what you’re doing, ask for confirmation before high-risk steps.
	•	Claude: add a confirm-before-execute pattern in the system prompt section.

⸻

10) Custom Function Tools (placeholders)

Claude: scaffold these as Tools, but safe-no-op until env vars are present. Each tool should validate inputs, handle errors, and return a compact JSON result.

Example 1: Trello Card

# tools/trello.py
from openai_agents import Tool

class CreateTrelloCard(Tool):
    name = "create_trello_card"
    description = "Create a Trello card. Inputs: board_id, list_id, title, description (optional), labels (optional)"

    async def call(self, board_id: str, list_id: str, title: str, description: str = "", labels: list[str] = None):
        # TODO: implement real Trello call if creds present; else return mock
        return {"status": "ok", "id": "mock-123", "url": "https://trello.com/c/mock"}
        
create_trello_card_tool = CreateTrelloCard()

Example 2: Append row to Google Sheet

# tools/sheets.py
from openai_agents import Tool

class AppendSheetRow(Tool):
    name = "append_sheet_row"
    description = "Append a row to a Google Sheet. Inputs: sheet_id, values(list)"

    async def call(self, sheet_id: str, values: list[str]):
        # TODO: real Google Sheets API call; for now, echo
        return {"status":"ok","sheet_id":sheet_id,"rows_appended":1,"values":values}

append_sheet_row_tool = AppendSheetRow()

Attach them

# agent_runtime.py build_agent(... custom_tools=[create_trello_card_tool, append_sheet_row_tool])


⸻

11) Prompting: prompts/system_prompt.md (template)

Claude: create this file and keep it terse + enforce guardrails.

# Role
You are Raunek’s AI Agent. Be fast, concrete, and citation-first when using web_search. 
Prefer on-file answers from file_search; when using computer_use, always ask for confirmation before performing high-risk actions.

# Capabilities
- web_search: ground claims with citations (include 2–4 reputable sources).
- file_search: prefer relevant doc excerpts; cite doc name and section.
- computer_use: only when explicitly asked to perform actions in a browser or desktop.
- custom tools: call only when inputs are sufficient; otherwise ask for the missing fields.

# Style
- Concise, calm, professional. 
- Bullet lists > walls of text. 
- When uncertain, state assumptions and ask ONE clarifying question.

# Safety & Limits
- Never enter credentials or perform irreversible actions without explicit user approval.
- For computer_use, summarize intended steps and seek confirmation.
- If a requested action violates policy or lacks permissions, explain briefly and offer alternatives.

# Output Conventions
- For answers using web_search: end with “Sources:” and list citation titles + URLs.
- For function results: summarize outcome in 1–2 lines; include key IDs/links.

Raunek will revise this with domain-specific rules (tone, refusal boundaries, branded phrasing).

⸻

12) State, Auth, Rate Limits
	•	State: SDK session holds ephemeral history; mirror {session_id, messages[]} in memory now; provide a swap-in interface to Redis later.
	•	Auth: add a simple bearer token check on /chat and a CSRF token on the WebSocket upgrade (stub ok for local).
	•	Rate-limit: token bucket per IP/API key (stub counters in memory).

⸻

13) Error Handling & Observability
	•	Wrap tool calls with try/except; return structured errors to the model ({"error": "...", "hint": "..."}) to encourage graceful recovery.
	•	Add logging for: request id, model, tool invocations, token counts, latency.
	•	Provide a hook for tracing (console now; OpenTelemetry later).

⸻

14) Minimal Frontend (chat.html)
	•	Already included in app.py (embedded).
	•	Claude: also save a copy to public/chat.html and serve via StaticFiles for cleaner separation.

⸻

15) Test Plan (today)
	1.	Chat baseline: “Who is the CEO of OpenAI? Cite sources.” → Expect web_search + citations.
	2.	RAG: Upload a small PDF, ask a question covered inside → Expect file_search excerpt + citation.
	3.	Computer Use (dry run): “Open example.com and take a screenshot” → Expect confirm-before-execute step, then action summary (actual behavior depends on tool availability).
	4.	Custom tool: “Create a Trello card titled ‘Emer Final Scope’” → Expect mock success JSON.

⸻

16) Setup Commands

python -m venv .venv && source .venv/bin/activate
pip install fastapi uvicorn python-dotenv openai-agents
cp .env.example .env  # add OPENAI_API_KEY
uvicorn app:app --reload
# Visit http://localhost:8000


⸻

17) Tomorrow’s Upgrades (not blocking today)
	•	Swap in Redis for sessions; add /session/:id resume.
	•	Add Next.js client with SSE/WS streaming and nicer UI.
	•	Real implementations for Trello/Sheets tools.
	•	Persist transcripts to a DB; export to CSV.
	•	Per-tool allowlist/denylist and “dry-run” mode for computer_use.

⸻

18) Claude’s Next Steps (now)
	1.	Generate the files above exactly as structured.
	2.	Keep the custom tools as safe mocks unless env creds exist.
	3.	After boot check, prompt Raunek for:
	•	Final prompts/system_prompt.md content
	•	Which custom tools to enable today (pick 2)
	•	Whether to keep Computer Use enabled by default or require a toggle.

⸻

Ready-to-Paste One-Liners (for Raunek)
	•	Run backend: uvicorn app:app --reload → open http://localhost:8000
	•	Change model: in agent_runtime.py, set DEFAULT_MODEL = "gpt-4o"
	•	Attach a tool: add to custom_tools=[create_trello_card_tool, append_sheet_row_tool] in app.py’s BASE_AGENT

⸻

If you want, I can also drop a Next.js client component and the n8n HTTP node config that hits /chat—but this markdown gives Claude everything needed to scaffold the working agent today.