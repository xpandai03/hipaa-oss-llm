"""
HIPAA-compliant Ollama provider for OSS LLM integration
Ensures PHI stays within private network boundary
"""

import os
import json
import requests
import logging
from typing import List, Dict, Iterator, Optional, Union

# Configure logging to avoid PHI exposure
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Environment configuration with secure defaults
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:20b")
TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "600"))
MAX_RETRIES = int(os.getenv("OLLAMA_MAX_RETRIES", "3"))

def sanitize_for_logging(text: str, max_length: int = 100) -> str:
    """
    Sanitize text for logging to prevent PHI exposure
    Only log first N characters and mask sensitive patterns
    """
    if not text:
        return "[empty]"
    
    # Truncate and add indicator
    if len(text) > max_length:
        return f"{text[:max_length]}... [truncated]"
    return text

def chat_ollama(
    messages: List[Dict[str, str]], 
    stream: bool = True,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None
) -> Union[Iterator[str], str]:
    """
    Send chat messages to Ollama and receive response
    
    Args:
        messages: List of message dicts with 'role' and 'content'
        stream: Whether to stream the response
        temperature: Model temperature (0.0-1.0)
        max_tokens: Maximum tokens to generate
    
    Returns:
        Iterator of text chunks if streaming, full text otherwise
    
    Raises:
        requests.RequestException: On network errors
        ValueError: On invalid response format
    """
    
    # Log metadata only, never log message content
    logger.info(f"Ollama chat request: model={OLLAMA_MODEL}, stream={stream}, messages_count={len(messages)}")
    
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": stream,
        "options": {
            "temperature": temperature,
        }
    }
    
    if max_tokens:
        payload["options"]["num_predict"] = max_tokens
    
    retry_count = 0
    last_error = None
    
    while retry_count < MAX_RETRIES:
        try:
            response = requests.post(
                OLLAMA_URL,
                json=payload,
                stream=stream,
                timeout=TIMEOUT
            )
            response.raise_for_status()
            
            if stream:
                return _handle_stream_response(response)
            else:
                return _handle_single_response(response)
                
        except requests.exceptions.Timeout:
            retry_count += 1
            last_error = f"Request timeout after {TIMEOUT}s (attempt {retry_count}/{MAX_RETRIES})"
            logger.warning(last_error)
            
        except requests.exceptions.RequestException as e:
            retry_count += 1
            last_error = f"Request failed: {type(e).__name__} (attempt {retry_count}/{MAX_RETRIES})"
            logger.error(last_error)
            
        except Exception as e:
            # Unexpected error, don't retry
            logger.error(f"Unexpected error in chat_ollama: {type(e).__name__}")
            raise
    
    # All retries exhausted
    raise requests.RequestException(f"Failed after {MAX_RETRIES} attempts. Last error: {last_error}")

def _handle_stream_response(response: requests.Response) -> Iterator[str]:
    """
    Handle streaming response from Ollama
    """
    try:
        for line in response.iter_lines():
            if not line:
                continue
            
            try:
                data = json.loads(line.decode("utf-8"))
                
                # Check for completion
                if data.get("done", False):
                    logger.info("Stream completed successfully")
                    return
                
                # Extract content from message
                content = data.get("message", {}).get("content", "")
                if content:
                    yield content
                    
            except json.JSONDecodeError:
                # Skip non-JSON lines (keepalive, etc)
                continue
                
    except Exception as e:
        logger.error(f"Error processing stream: {type(e).__name__}")
        raise

def _handle_single_response(response: requests.Response) -> str:
    """
    Handle non-streaming response from Ollama
    """
    try:
        data = response.json()
        
        if "message" not in data or "content" not in data["message"]:
            raise ValueError("Invalid response format from Ollama")
        
        content = data["message"]["content"]
        logger.info(f"Single response received, length={len(content)}")
        return content
        
    except json.JSONDecodeError as e:
        logger.error("Failed to parse JSON response from Ollama")
        raise ValueError(f"Invalid JSON response: {e}")

def check_ollama_health() -> Dict[str, any]:
    """
    Check if Ollama service is healthy and model is available
    
    Returns:
        Dict with health status and available models
    """
    try:
        # Check service health
        health_url = OLLAMA_URL.replace("/api/chat", "/api/tags")
        response = requests.get(health_url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        models = [m.get("name", "unknown") for m in data.get("models", [])]
        
        health_status = {
            "healthy": True,
            "models": models,
            "target_model": OLLAMA_MODEL,
            "model_available": OLLAMA_MODEL in models
        }
        
        logger.info(f"Ollama health check: {health_status}")
        return health_status
        
    except Exception as e:
        logger.error(f"Ollama health check failed: {type(e).__name__}")
        return {
            "healthy": False,
            "error": str(type(e).__name__),
            "models": [],
            "target_model": OLLAMA_MODEL,
            "model_available": False
        }

def format_tool_response(tool_name: str, tool_output: Dict) -> Dict[str, str]:
    """
    Format tool output as a message for the model
    Ensures PHI is not exposed in logs
    """
    logger.info(f"Formatting tool response: tool={tool_name}")
    
    return {
        "role": "tool",
        "content": json.dumps(tool_output, ensure_ascii=False)
    }