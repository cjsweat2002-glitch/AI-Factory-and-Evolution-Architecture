"""
Seed Worker: A lightweight local AI worker for testing the factory.
Provides OpenAI-compatible /v1/chat/completions endpoint.

Usage:
    python3 -m uvicorn src.seed_worker:app --host 0.0.0.0 --port 11434 --reload
"""

import json
import uuid
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Seed Worker")


def generate_response(prompt: str, model: str) -> str:
    """Generate a basic response based on the prompt and model."""
    prompt_lower = prompt.lower()
    
    # Smart responses based on content
    if "curiosity" in prompt_lower or "research" in prompt_lower or "improve" in prompt_lower:
        return (
            "Based on the repository analysis, here are key improvement opportunities:\n"
            "1. Add comprehensive request validation to all endpoints\n"
            "2. Implement connection pooling for worker health checks\n"
            "3. Add structured logging for debugging factory loops\n"
            "4. Consider caching worker node discovery results\n"
            "5. Add metrics and monitoring to track AI learning progress\n\n"
            "These changes would enhance reliability and provide better observability."
        )
    
    elif "validation" in prompt_lower or "input" in prompt_lower:
        return (
            "Input validation improvements:\n"
            "- Add Pydantic models for request payload validation\n"
            "- Implement rate limiting per worker\n"
            "- Validate notebook content before import\n"
            "- Add JSON schema validation for all endpoints\n"
            "- Log validation failures for debugging\n\n"
            "This prevents malformed requests from reaching workers."
        )
    
    elif "health" in prompt_lower or "check" in prompt_lower or "resilience" in prompt_lower:
        return (
            "Health check resilience improvements:\n"
            "- Add exponential backoff for retry logic\n"
            "- Track health check history (last 10 checks)\n"
            "- Add separate timeout for health vs. chat endpoints\n"
            "- Implement circuit breaker pattern\n"
            "- Add detailed health status reporting\n\n"
            "These changes make the system more fault-tolerant."
        )
    
    elif "routing" in prompt_lower or "load" in prompt_lower:
        return (
            "Routing and load balancing enhancements:\n"
            "- Track worker response times and adjust weights\n"
            "- Implement least-connections strategy\n"
            "- Add affinity for streaming responses\n"
            "- Monitor queue depth per worker\n"
            "- Balance between round-robin and weighted selection\n\n"
            "This improves request distribution efficiency."
        )
    
    elif "github" in prompt_lower or "push" in prompt_lower or "commit" in prompt_lower:
        return (
            "GitHub integration enhancements:\n"
            "- Add commit signing for factory bot commits\n"
            "- Create semantic commit messages with timestamps\n"
            "- Add PR template for factory-generated changes\n"
            "- Track commit history for learning patterns\n"
            "- Add automated changelog generation\n\n"
            "These improve code governance and traceability."
        )
    
    else:
        return (
            f"Seed worker response to: '{prompt[:50]}...'\n\n"
            "The factory is learning and adapting. "
            "This response came from the seed worker running locally.\n"
            "Ask me about curiosity, validation, health checks, routing, or GitHub integration!"
        )


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """OpenAI-compatible chat completions endpoint."""
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
    
    model = payload.get("model", "seed-llama3")
    messages = payload.get("messages", [])
    stream = payload.get("stream", False)
    
    if not messages:
        raise HTTPException(status_code=400, detail="No messages provided")
    
    # Get the last user message as the prompt
    prompt = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            prompt = msg.get("content", "")
            break
    
    if not prompt:
        raise HTTPException(status_code=400, detail="No user message found")
    
    # Generate response using our seed logic
    content = generate_response(prompt, model)
    
    if stream:
        # Return streaming response
        async def stream_generator():
            # Send initial message chunk
            chunk = {
                "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                "object": "text_completion.chunk",
                "created": int(datetime.now().timestamp()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"role": "assistant", "content": content[:100]},
                    "finish_reason": None,
                }]
            }
            yield f"data: {json.dumps(chunk)}\n\n"
            
            # Send remaining content in chunks
            for i in range(100, len(content), 100):
                chunk = {
                    "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                    "object": "text_completion.chunk",
                    "created": int(datetime.now().timestamp()),
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": content[i:i+100]},
                        "finish_reason": None,
                    }]
                }
                yield f"data: {json.dumps(chunk)}\n\n"
            
            # Send final chunk
            chunk = {
                "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                "object": "text_completion.chunk",
                "created": int(datetime.now().timestamp()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }]
            }
            yield f"data: {json.dumps(chunk)}\n\n"
            yield "data: [DONE]\n\n"
        
        from fastapi.responses import StreamingResponse
        return StreamingResponse(stream_generator(), media_type="text/event-stream")
    
    else:
        # Return non-streaming response
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(datetime.now().timestamp()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": len(prompt.split()),
                "completion_tokens": len(content.split()),
                "total_tokens": len(prompt.split()) + len(content.split()),
            }
        }


@app.get("/v1/models")
async def list_models():
    """OpenAI-compatible models endpoint."""
    return {
        "object": "list",
        "data": [
            {"id": "seed-llama3", "object": "model", "owned_by": "seed-worker"},
            {"id": "seed-reasoning", "object": "model", "owned_by": "seed-worker"},
        ]
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "seed-worker",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    import uvicorn
    print("🌱 Starting Seed Worker on http://0.0.0.0:11434")
    print("   → Chat: POST /v1/chat/completions")
    print("   → Models: GET /v1/models")
    print("   → Health: GET /health")
    uvicorn.run(app, host="0.0.0.0", port=11434)
