from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import httpx
import json
import asyncio
from datetime import datetime
import time

app = FastAPI()

@app.get("/api/tags")
async def list_models():
    """Return available models (like Ollama's /api/tags)"""
    return {
        "models": [
            {
                "name": "Test",
                "modified_at": datetime.now().isoformat() + "Z",
                "size": 1234567890
            }
        ]
    }

async def generate_title(client, messages):
    """Generate a title using TinyLlama based on conversation summary"""
    try:
        # Create a conversation summary from the first few messages
        if len(messages) == 1:
            # Single message - use it directly
            conversation_summary = messages[0]["content"]
        else:
            # Multiple messages - create a summary including both user and assistant messages
            # Take first 6 messages (3 user-assistant pairs) or all if less than 6
            summary_messages = messages[:6]
            # Create a more natural conversation flow
            conversation_parts = []
            for msg in summary_messages:
                role = msg["role"]
                content = msg["content"]
                conversation_parts.append(f"{role}: {content}")
            conversation_summary = " | ".join(conversation_parts)
            # Limit total length to avoid overly long prompts
            if len(conversation_summary) > 200:
                conversation_summary = conversation_summary[:197] + "..."
        
        title_prompt = f"Generate a short, descriptive title (max 50 characters) for this conversation: {conversation_summary}"
        title_payload = {
            "model": "tinyllama",
            "messages": [{"role": "user", "content": title_prompt}],
            "stream": False,
            "options": {"temperature": 0.7, "num_predict": 50}
        }
        
        resp = await client.post("http://localhost:11434/api/chat", json=title_payload)
        if resp.status_code == 200:
            data = resp.json()
            title = data.get("message", {}).get("content", "").strip()
            # Clean up the title (remove quotes, extra spaces, etc.)
            title = title.replace('"', '').replace("'", "").strip()
            if len(title) > 50:
                title = title[:47] + "..."
            print(f"Title: {title}")
            return title if title else "New Chat"
    except Exception as e:
        print(f"Title generation error: {e}")
        return "New Chat"

@app.post("/api/chat")
async def chat(request: Request):
    """Handle chat requests and forward to Ollama"""
    
    # Parse the request body
    body = await request.json()
    print(f"Body: {body}")
    messages = body.get("messages", [])
    stream = body.get("stream", True)
    options = body.get("options", {})
    should_generate_title = body.get("generate_title", True)  # Default to True for backward compatibility
    
    # Prepare Ollama request
    ollama_payload = {
        "model": "mistral:7b",
        "messages": messages,
        "stream": stream,
        "options": options
    }
    
    async def event_generator():
        start_time = time.time()
        prompt_eval_count = 0
        prompt_eval_duration = 0
        eval_count = 0
        eval_duration = 0
        title_sent = False
        
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                # Start title generation task using conversation summary (only if should_generate_title is True)
                title_task = None
                if should_generate_title and messages:
                    # Only generate title on the first message of a conversation
                    user_messages = [msg for msg in messages if msg["role"] == "user"]
                    title_task = asyncio.create_task(generate_title(client, messages))
                
                # Main conversation stream
                async with client.stream("POST", "http://localhost:11434/api/chat", json=ollama_payload) as resp:
                    buffer = ""
                    async for chunk in resp.aiter_text():
                        buffer += chunk
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            if not line.strip():
                                continue
                            try:
                                data = json.loads(line)
                                
                                # Extract token from Ollama response
                                token = data.get("message", {}).get("content", "")
                                done = data.get("done", False)
                                
                                if token:
                                    # Stream token in Ollama format
                                    response_data = {
                                        "model": "Test",
                                        "created_at": datetime.now().isoformat() + "Z",
                                        "message": {"role": "assistant", "content": token},
                                        "done": False
                                    }
                                    print(f"Response data: {response_data}")
                                    yield json.dumps(response_data) + "\n"
                                
                                if done:
                                    # Wait for title to be generated before sending final response (only if should_generate_title is True)
                                    if should_generate_title and title_task and not title_sent:
                                        try:
                                            title = await title_task
                                            title_sent = True
                                            
                                            # Send title message
                                            title_response = {
                                                "model": "Test",
                                                "created_at": datetime.now().isoformat() + "Z",
                                                "message": {"title": title},
                                                "done": False
                                            }
                                            yield json.dumps(title_response) + "\n"
                                        except Exception as e:
                                            print(f"Error getting title: {e}")
                                            # If title generation fails, send a default title
                                            title_response = {
                                                "model": "Test",
                                                "created_at": datetime.now().isoformat() + "Z",
                                                "message": {"title": "New Chat"},
                                                "done": False
                                            }
                                            yield json.dumps(title_response) + "\n"
                                            title_sent = True
                                    
                                    # Final response with stats
                                    total_duration = int((time.time() - start_time) * 1_000_000_000)  # nanoseconds
                                    final_response = {
                                        "model": "Test",
                                        "created_at": datetime.now().isoformat() + "Z",
                                        "done": True,
                                        "total_duration": total_duration,
                                        "load_duration": 0,
                                        "prompt_eval_count": prompt_eval_count,
                                        "prompt_eval_duration": prompt_eval_duration,
                                        "eval_count": eval_count,
                                        "eval_duration": eval_duration
                                    }
                                    yield json.dumps(final_response) + "\n"
                                    break
                                    
                            except json.JSONDecodeError:
                                continue
                                
        except Exception as e:
            print(f"Error in streaming: {e}")
            # Send error response in Ollama format
            error_response = {
                "model": "Test",
                "created_at": datetime.now().isoformat() + "Z",
                "done": True,
                "error": str(e)
            }
            yield json.dumps(error_response) + "\n"
    
    return StreamingResponse(event_generator(), media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001) 