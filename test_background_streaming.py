#!/usr/bin/env python3
"""
Test script to verify background streaming functionality
"""

import asyncio
import httpx
import json
import time

async def test_background_streaming():
    """Test the background streaming functionality"""
    
    # Test data
    conversation_id = "test-conversation-123"
    user_id = "test-user-456"
    
    # Simulate a streaming request
    model_url = "http://localhost:8001/api/chat"
    model_payload = {
        "model": "Test",
        "messages": [
            {"role": "user", "content": "Hello, this is a test message for background streaming."}
        ],
        "stream": True,
        "generate_title": True
    }
    
    print("Starting background streaming test...")
    print(f"Model URL: {model_url}")
    print(f"Payload: {json.dumps(model_payload, indent=2)}")
    
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            print("Making streaming request to model...")
            async with client.stream("POST", model_url, json=model_payload) as resp:
                print(f"Response status: {resp.status_code}")
                
                buffer = ""
                token_count = 0
                
                async for chunk in resp.aiter_text():
                    buffer += chunk
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        if not line.strip():
                            continue
                        
                        try:
                            data = json.loads(line)
                            
                            # Check for title message
                            if data.get("message", {}).get("title"):
                                title = data["message"]["title"]
                                print(f"Received title: {title}")
                                continue
                            
                            # Check for done message
                            if data.get("done", False):
                                print("Received done message")
                                break
                            
                            # Regular token
                            token = data.get("message", {}).get("content", "")
                            if token:
                                token_count += 1
                                print(f"Token {token_count}: {token[:50]}...")
                                
                                # Simulate client disconnect after 5 tokens
                                if token_count >= 5:
                                    print("Simulating client disconnect...")
                                    break
                                    
                        except Exception as e:
                            print(f"Error parsing line: {e}")
                            continue
                
                print(f"Streaming completed. Received {token_count} tokens.")
                
    except Exception as e:
        print(f"Error during streaming: {e}")

if __name__ == "__main__":
    asyncio.run(test_background_streaming()) 