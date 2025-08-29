HIPAA-Safe OSS LLM Agent — Build Context for Claude Code

Audience: Claude Code
Goal: Stand up a HIPAA-safe, open-source LLM endpoint today on Render (BAA in place), wire it to our existing FastAPI agent backend (private network), and keep PHI inside our compliant boundary. Include optional GCP GPU path for later.

⸻

Objectives (Do Today)
	•	Create a private Render service running Ollama (OSS LLM host) with an encrypted volume.
	•	Keep it internal-only (no public ingress). Agent backend calls it via private networking.
	•	Update the agent backend to use the OSS model endpoint.
	•	Add HIPAA guardrails: no PHI in logs, TLS between services if exposed, least privilege, etc.
	•	Smoke test with a simple chat; then integrate the existing tools (web_search with PHI scrubbing, file_search, browser_action).

⸻

Architecture (Today)

[ Client UI ]  --TLS-->  [ agent-backend (FastAPI, Private Service) ] --private-->
[ oss-llm (Ollama + model, Private Service) ]  (encrypted volume for models)
                                    |
                           [ encrypted DB / storage ]

	•	PHI never leaves Render’s HIPAA environment.
	•	No public routes to oss-llm. Only the backend can reach it.

⸻

Render Services to Create
	1.	oss-llm (Private Service)
	•	Docker image built from the Dockerfile below.
	•	Volume: /models (encrypted).
	•	Port: 11434.
	•	Health check: GET /api/tags or POST /api/chat (dry probe).
	•	Internal networking only (no public IP).
	2.	agent-backend (Private Service)
	•	Our existing FastAPI app.
	•	Can reach oss-llm via private DNS: http://oss-llm:11434.

Claude: If any toggles exist in Render to force private networking, enable them. Ensure logs are PHI-safe (mask request bodies).

⸻

Dockerfile for oss-llm (Ollama)

Create at repo root: ./Dockerfile

# Minimal Ubuntu base
FROM ubuntu:22.04

# System deps
RUN apt-get update && apt-get install -y curl ca-certificates && rm -rf /var/lib/apt/lists/*

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# Models dir (use encrypted Render volume)
RUN mkdir -p /models
ENV OLLAMA_MODELS=/models
ENV OLLAMA_HOST=0.0.0.0:11434
ENV OLLAMA_KEEP_ALIVE=24h

# Pre-pull a solid OSS instruct model
# Options: llama3.1:8b-instruct, qwen2.5:7b-instruct, mixtral:8x7b-instruct
RUN /bin/bash -lc "ollama serve & sleep 2 && ollama pull llama3.1:8b-instruct && pkill ollama || true"

EXPOSE 11434
CMD ["ollama", "serve"]

Render Build/Runtime Notes
	•	Attach encrypted volume to /models.
	•	Restrict egress after the image is built (model already pulled at build time).
	•	Keep service private (no public ingress).

⸻

Agent Backend — Minimal Provider for Ollama

Add a lightweight provider to call Ollama from the backend (same VPC).

providers/ollama.py

import os, json, requests
from typing import List, Dict, Iterator

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://oss-llm:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct")
TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "600"))

def chat_ollama(messages: List[Dict], stream: bool = True) -> Iterator[str] | str:
    """
    messages: [{"role": "system"|"user"|"assistant"|"tool", "content": "..."}]
    """
    payload = {"model": OLLAMA_MODEL, "messages": messages, "stream": stream}
    r = requests.post(OLLAMA_URL, json=payload, stream=stream, timeout=TIMEOUT)
    r.raise_for_status()
    if stream:
        for line in r.iter_lines():
            if not line:
                continue
            try:
                data = json.loads(line.decode("utf-8"))
                yield data.get("message", {}).get("content", "")
            except Exception:
                # Non-JSON keepalive lines may appear; ignore safely
                continue
    else:
        data = r.json()
        return data["message"]["content"]

Environment for agent-backend

# .env
OLLAMA_URL=http://oss-llm:11434/api/chat   # private DNS in Render
OLLAMA_MODEL=llama3.1:8b-instruct


⸻

WebSocket Handler (FastAPI) — Wire to OSS Provider

Replace your existing model call with chat_ollama.

app.py (snippet)

from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
import os

from providers.ollama import chat_ollama

app = FastAPI(title="Agent Backend (HIPAA-safe)")

SYSTEM_PROMPT = """You are Raunek’s OSS Agent.
- Be concise. Bullets > paragraphs.
- If using web_search or any external API, NEVER send PHI; de-identify first.
- For browser actions, propose a brief plan and request 'CONFIRM' before execution.
"""

HTML = """
<!doctype html><meta charset="utf-8"/>
<style>
body{font-family:system-ui;margin:2rem;max-width:780px}
#log{white-space:pre-wrap;border:1px solid #ddd;padding:12px;min-height:300px}
input{width:78%} button{width:20%}
</style>
<h3>Agent Chat (OSS Model)</h3>
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
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    try:
        while True:
            user_msg = await websocket.receive_text()
            messages.append({"role":"user","content": user_msg})
            for delta in chat_ollama(messages, stream=True):
                await websocket.send_text(delta)
            await websocket.send_text("\n")
            # Append assistant's final message to history if you want full state:
            # (Optionally buffer the streamed text to one message and append.)
    except Exception:
        await websocket.close()

@app.post("/chat")
async def chat(payload: dict):
    text = payload.get("message")
    if not text:
        raise HTTPException(400, "Missing 'message'")
    messages = [{"role":"system","content": SYSTEM_PROMPT}, {"role":"user","content": text}]
    out = []
    for delta in chat_ollama(messages, stream=True):
        out.append(delta)
    return JSONResponse({"reply": "".join(out)})


⸻

Tools (Web, File, Browser) — HIPAA Rules

We’ll use the same “function tool” pattern, but sanitize PHI for any external API.
	1.	web_search (external)
	•	Never send PHI. Redact names, phone, email, addresses, DOB, MRN.
	•	Return {title,url,snippet}; cite sources in the final answer.
	2.	file_search (internal RAG)
	•	Store and index inside Render (encrypted DB or vector store).
	•	Return {doc, chunk_id, excerpt}; the model composes the final answer.
	3.	browser_action (internal)
	•	Use Playwright inside the HIPAA environment.
	•	Confirm-before-execute: the model must print a short plan and wait for explicit user “CONFIRM.”
	•	Return {logs[], screenshots[]?}; store screenshots in encrypted storage.

Claude: scaffold Python functions for these tools (no external calls for web_search yet; stub it). Ensure each tool validates inputs and masks sensitive fields in logs.

⸻

HIPAA Guardrails (Enforce)
	•	Private services only for oss-llm and agent-backend.
	•	Encrypted volumes for /models and persistent storage.
	•	No PHI in logs: mask request/response bodies and tool inputs in logs; log only metadata (timestamp, tool name, user id).
	•	RBAC / least privilege on deploy keys and environment variable access.
	•	Backups: encrypted, with access logs enabled.
	•	External APIs (search, email, SMS): strip PHI first or ensure BAA (e.g., Twilio HIPAA product).
	•	Data retention policy: define how long transcripts and uploads are kept; add deletion routines.

⸻

Test Plan (Run Today)
	1.	Service reachability
	•	From agent-backend shell:
curl -s http://oss-llm:11434/api/tags → expect JSON list of models.
curl -s -H "Content-Type: application/json" -d '{"model":"llama3.1:8b-instruct","messages":[{"role":"user","content":"Say hello"}],"stream":false}' http://oss-llm:11434/api/chat
	2.	WS chat smoke test
	•	uvicorn app:app --reload → open backend URL (private access), chat “Brief hello”.
	3.	PHI policy check
	•	Ask: “Generate a response using external web search about clinic X at 123 Main St (John Doe).”
	•	Verify the agent redacts PHI before any external call (for now, web_search is stubbed; ensure the prompt instructs PHI redaction).
	4.	file_search stub
	•	Simulate query over internal doc → verify the agent prefers internal excerpts.
	5.	browser_action confirm
	•	“Log into portal and download last statement.” → expect a plan + ‘CONFIRM?’. Only act after we reply “CONFIRM”.

⸻

Variables to Expose / ENV

# Agent backend
OLLAMA_URL=http://oss-llm:11434/api/chat
OLLAMA_MODEL=llama3.1:8b-instruct
OLLAMA_TIMEOUT=600

# Tool creds (only if enabling real APIs; otherwise leave unset)
# TRELLO_KEY=
# TRELLO_TOKEN=
# GOOGLE_SERVICE_ACCOUNT_JSON_BASE64=


⸻

Prompts Claude Must Ask Me Before Finalizing
	1.	System prompt specifics (persona, tone, refusal rules, citation format).
	2.	Which two tools to enable first (web_search/file_search/browser_action).
	3.	Data retention window for transcripts and uploads.
	4.	Any real external APIs we plan to call under BAA (otherwise keep stubs).
	5.	Model choice (llama3.1:8b-instruct vs qwen2.5:7b-instruct) and memory constraints.

⸻

Optional Appendix — GCP GPU (vLLM) Path (Later)
	•	Spin up HIPAA-eligible GPU VM (e.g., L4), install Docker + vllm/vllm-openai.
	•	Bind vLLM to localhost :8000; front with internal Nginx TLS on :8443.
	•	Restrict firewall ingress to the agent’s subnet.
	•	Use OpenAI-compatible endpoint: https://llm.internal:8443/v1/chat/completions.
	•	Update backend to use OpenAI client with base_url= override.
	•	Keep no public ingress; encrypt disks; centralize logs; mask PHI from logs.

⸻

Deliverables Claude Should Produce
	•	Dockerfile (as above)
	•	providers/ollama.py
	•	Updated app.py WS + REST endpoints, wired to chat_ollama()
	•	requirements.txt (FastAPI, uvicorn, requests, python-dotenv)
	•	.env.example with variables above
	•	Stubs for tools/web_search.py, tools/file_search.py, tools/browser_action.py with HIPAA-safe patterns (PHI redaction, confirm-before-execute)

⸻

Success Criteria (Today)
	•	Both Render services deploy successfully, private only.
	•	Backend chat works end-to-end against the OSS model with no PHI leakage.
	•	Logs contain no PHI, only metadata.
	•	Tool stubs exist with the correct policy gates.

⸻

Notes for Claude:
	•	Prefer idempotent deploy scripts and clear error messages.
	•	Add comments in code where PHI could accidentally leak (logging, exceptions).
	•	Keep everything minimal and production-lean (no unnecessary packages, no public exposure).