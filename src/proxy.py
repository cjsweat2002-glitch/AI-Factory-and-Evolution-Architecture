def translate_openai_to_ollama(openai_payload):
    messages = openai_payload.get("messages", [])
    prompt = ""
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        prompt += f"{role.upper()}: {content}\n"
    
    return {
        "model": openai_payload.get("model", "llama3"),
        "prompt": prompt,
        "stream": openai_payload.get("stream", False)
    }

def translate_ollama_to_openai(ollama_response):
    return {
        "id": "chatcmpl-custom",
        "object": "chat.completion",
        "created": 1700000000,
        "model": ollama_response.get("model", "llama3"),
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": ollama_response.get("response", "")
            },
            "finish_reason": "stop"
        }]
    }
