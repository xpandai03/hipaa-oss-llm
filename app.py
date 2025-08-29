"""
HIPAA-compliant FastAPI Agent Backend
Connects to Ollama OSS LLM via private network
"""

from fastapi import FastAPI, WebSocket, HTTPException, WebSocketDisconnect, Depends, Security
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import os
import json
import logging
import asyncio
from typing import List, Dict, Optional
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from providers.ollama import chat_ollama, check_ollama_health

# API Key Authentication
security = HTTPBearer()

async def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Verify API key for HIPAA compliance"""
    api_key = os.getenv("API_KEY")
    
    # Allow no auth in development mode
    if os.getenv("ENVIRONMENT") == "development" and not api_key:
        return credentials
    
    # Require API key in production
    if not api_key:
        logger.error("API_KEY not configured")
        raise HTTPException(status_code=500, detail="API authentication not configured")
    
    if credentials.credentials != api_key:
        logger.warning(f"Invalid API key attempt")
        raise HTTPException(status_code=403, detail="Invalid API Key")
    
    return credentials

# Configure logging for HIPAA compliance
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="HIPAA-Compliant Agent Backend",
    description="OSS LLM Agent with PHI protection",
    version="1.0.0"
)

# CORS configuration for internal use only
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# System prompt with HIPAA guidelines
SYSTEM_PROMPT = """You are a HIPAA-compliant AI assistant powered by an open-source model.

Critical Guidelines:
- NEVER log or expose Protected Health Information (PHI)
- When using external tools, always de-identify data first
- Be concise and helpful
- For any browser automation, explain your plan and wait for explicit confirmation
- Cite sources when using search results

PHI includes but is not limited to:
- Names, addresses, phone numbers, emails
- Medical record numbers, account numbers
- Social Security numbers, dates of birth
- Health conditions, treatments, diagnoses
- Any identifiable patient information

You have access to these tools:
1. web_search: External search (PHI must be removed)
2. file_search: Internal document search (safe for PHI)
3. browser_action: Automated browser tasks (requires confirmation)"""

# Request/Response models
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None

class ChatResponse(BaseModel):
    reply: str
    session_id: Optional[str] = None
    timestamp: str

# Session management (in-memory for now, use Redis in production)
sessions = {}

# Minimal chat UI for testing
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8"/>
    <title>HIPAA Agent Chat</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            width: 100%;
            max-width: 800px;
            height: 600px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            text-align: center;
        }
        .header h2 {
            font-size: 24px;
            font-weight: 600;
        }
        .status {
            display: inline-block;
            padding: 4px 12px;
            background: rgba(255,255,255,0.2);
            border-radius: 20px;
            font-size: 12px;
            margin-top: 8px;
        }
        #chat-log {
            flex: 1;
            padding: 20px;
            overflow-y: auto;
            background: #f8f9fa;
        }
        .message {
            margin-bottom: 16px;
            animation: fadeIn 0.3s ease-in;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .message.user {
            text-align: right;
        }
        .message.assistant {
            text-align: left;
        }
        .message-content {
            display: inline-block;
            padding: 12px 16px;
            border-radius: 18px;
            max-width: 70%;
            word-wrap: break-word;
        }
        .user .message-content {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .assistant .message-content {
            background: white;
            color: #333;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .input-area {
            padding: 20px;
            background: white;
            border-top: 1px solid #e0e0e0;
            display: flex;
            gap: 10px;
        }
        #message-input {
            flex: 1;
            padding: 12px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 25px;
            font-size: 14px;
            outline: none;
            transition: border-color 0.3s;
        }
        #message-input:focus {
            border-color: #667eea;
        }
        #send-btn {
            padding: 12px 24px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 25px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }
        #send-btn:hover {
            transform: scale(1.05);
        }
        #send-btn:active {
            transform: scale(0.95);
        }
        .typing-indicator {
            display: none;
            padding: 20px;
            color: #666;
            font-style: italic;
        }
        .typing-indicator.show {
            display: block;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>HIPAA-Compliant Agent</h2>
            <span class="status" id="status">Connected</span>
        </div>
        <div id="chat-log"></div>
        <div class="typing-indicator" id="typing">Assistant is typing...</div>
        <div class="input-area">
            <input type="text" id="message-input" placeholder="Type your message..." autofocus/>
            <button id="send-btn" onclick="sendMessage()">Send</button>
        </div>
    </div>

    <script>
        const ws = new WebSocket(`ws://${location.host}/ws`);
        const chatLog = document.getElementById('chat-log');
        const messageInput = document.getElementById('message-input');
        const typingIndicator = document.getElementById('typing');
        const statusElement = document.getElementById('status');
        
        let isAssistantTyping = false;
        let currentAssistantMessage = null;

        ws.onopen = () => {
            statusElement.textContent = 'Connected';
            statusElement.style.background = 'rgba(76, 175, 80, 0.3)';
        };

        ws.onclose = () => {
            statusElement.textContent = 'Disconnected';
            statusElement.style.background = 'rgba(244, 67, 54, 0.3)';
        };

        ws.onmessage = (event) => {
            if (!isAssistantTyping) {
                isAssistantTyping = true;
                typingIndicator.classList.add('show');
                currentAssistantMessage = createMessage('assistant');
            }
            
            if (event.data === '\\n' || event.data === '[DONE]') {
                isAssistantTyping = false;
                typingIndicator.classList.remove('show');
                currentAssistantMessage = null;
            } else {
                currentAssistantMessage.querySelector('.message-content').textContent += event.data;
            }
            
            chatLog.scrollTop = chatLog.scrollHeight;
        };

        function createMessage(role, content = '') {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${role}`;
            
            const contentDiv = document.createElement('div');
            contentDiv.className = 'message-content';
            contentDiv.textContent = content;
            
            messageDiv.appendChild(contentDiv);
            chatLog.appendChild(messageDiv);
            
            return messageDiv;
        }

        function sendMessage() {
            const message = messageInput.value.trim();
            if (!message) return;
            
            createMessage('user', message);
            ws.send(message);
            messageInput.value = '';
            chatLog.scrollTop = chatLog.scrollHeight;
        }

        messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });

        // Auto-focus input
        messageInput.focus();
    </script>
</body>
</html>
"""

@app.get("/")
async def home():
    """Serve the chat interface"""
    return HTMLResponse(HTML_TEMPLATE)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    ollama_health = check_ollama_health()
    
    return JSONResponse({
        "status": "healthy" if ollama_health["healthy"] else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "backend": "healthy",
            "ollama": ollama_health
        }
    })

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time chat"""
    await websocket.accept()
    
    # Initialize conversation with system prompt
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Log connection (no PHI)
    logger.info(f"WebSocket connection established")
    
    try:
        while True:
            # Receive message from user
            user_message = await websocket.receive_text()
            
            # Log metadata only
            logger.info(f"Received message, length={len(user_message)}")
            
            # Add user message to conversation
            messages.append({"role": "user", "content": user_message})
            
            # Stream response from Ollama
            assistant_message = ""
            try:
                for chunk in chat_ollama(messages, stream=True):
                    assistant_message += chunk
                    await websocket.send_text(chunk)
                
                # Send completion indicator
                await websocket.send_text("\n")
                
                # Add assistant response to conversation history
                messages.append({"role": "assistant", "content": assistant_message})
                
                # Log completion (no content)
                logger.info(f"Response completed, length={len(assistant_message)}")
                
            except Exception as e:
                logger.error(f"Error generating response: {type(e).__name__}")
                await websocket.send_text("\n[Error: Unable to generate response. Please try again.]\n")
                
    except WebSocketDisconnect:
        logger.info("WebSocket connection closed")
    except Exception as e:
        logger.error(f"WebSocket error: {type(e).__name__}")
        await websocket.close()

@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(verify_api_key)])
async def chat(request: ChatRequest):
    """REST endpoint for single-turn chat"""
    
    # Log request metadata only
    logger.info(f"Chat request received, session={request.session_id}")
    
    # Get or create session
    session_id = request.session_id or f"session_{datetime.utcnow().timestamp()}"
    
    if session_id not in sessions:
        sessions[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    messages = sessions[session_id]
    messages.append({"role": "user", "content": request.message})
    
    try:
        # Get response from Ollama
        response_chunks = []
        for chunk in chat_ollama(
            messages, 
            stream=True,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        ):
            response_chunks.append(chunk)
        
        assistant_response = "".join(response_chunks)
        
        # Update session
        messages.append({"role": "assistant", "content": assistant_response})
        
        # Limit session history to prevent memory issues
        if len(messages) > 20:
            messages = [messages[0]] + messages[-10:]  # Keep system prompt + last 10
            sessions[session_id] = messages
        
        return ChatResponse(
            reply=assistant_response,
            session_id=session_id,
            timestamp=datetime.utcnow().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Chat error: {type(e).__name__}")
        raise HTTPException(status_code=500, detail="Failed to generate response")

@app.post("/clear-session")
async def clear_session(session_id: Optional[str] = None):
    """Clear a specific session or all sessions"""
    if session_id:
        if session_id in sessions:
            del sessions[session_id]
            logger.info(f"Session cleared: {session_id}")
            return {"message": "Session cleared", "session_id": session_id}
        else:
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        sessions.clear()
        logger.info("All sessions cleared")
        return {"message": "All sessions cleared"}

# Tool endpoints (to be integrated with tool implementations)
@app.post("/tools/web-search")
async def web_search_endpoint(query: str):
    """Web search with PHI redaction"""
    # Import tool when available
    try:
        from tools.web_search import search_with_phi_protection
        results = await search_with_phi_protection(query)
        return JSONResponse(results)
    except ImportError:
        return JSONResponse({
            "error": "Web search tool not yet implemented",
            "query": query
        })

@app.post("/tools/file-search")
async def file_search_endpoint(query: str):
    """Internal file search (PHI-safe)"""
    try:
        from tools.file_search import search_internal_documents
        results = await search_internal_documents(query)
        return JSONResponse(results)
    except ImportError:
        return JSONResponse({
            "error": "File search tool not yet implemented",
            "query": query
        })

@app.post("/tools/browser-action")
async def browser_action_endpoint(action: Dict):
    """Browser automation with confirmation"""
    try:
        from tools.browser_action import execute_browser_action
        results = await execute_browser_action(action)
        return JSONResponse(results)
    except ImportError:
        return JSONResponse({
            "error": "Browser action tool not yet implemented",
            "action": action
        })

if __name__ == "__main__":
    import uvicorn
    
    # Get port from environment or use default
    port = int(os.getenv("PORT", "8000"))
    
    # Run with production settings
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=False  # Disable access logs to prevent PHI exposure
    )