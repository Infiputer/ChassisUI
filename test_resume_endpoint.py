#!/usr/bin/env python3
"""
Test script to verify the resume-stream endpoint works correctly
"""

import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
import jwt
from config import JWT_SECRET, JWT_ALGORITHM

def create_test_token(user_id: str = "test-user-123"):
    """Create a test JWT token for authentication"""
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(minutes=30),
        "type": "access"
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def test_resume_stream_endpoint():
    """Test the resume-stream endpoint"""
    # Create a test token
    token = create_test_token()
    
    # Test conversation ID (you can replace this with a real one)
    conversation_id = "292c4a74-7dc9-458c-a2ac-982c7bc09194"
    
    url = f"http://localhost:8000/api/conversations/{conversation_id}/resume-stream"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    print(f"Testing endpoint: {url}")
    print(f"Headers: {headers}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers) as response:
                print(f"Response status: {response.status}")
                print(f"Response headers: {dict(response.headers)}")
                
                if response.status == 200:
                    print("✅ Endpoint is working correctly!")
                    # Read the streaming response
                    async for line in response.content:
                        line_str = line.decode('utf-8').strip()
                        if line_str:
                            print(f"Stream data: {line_str}")
                else:
                    text = await response.text()
                    print(f"❌ Error response: {text}")
                    
    except Exception as e:
        print(f"❌ Exception occurred: {e}")

async def test_processing_status_endpoint():
    """Test the processing-status endpoint"""
    token = create_test_token()
    conversation_id = "292c4a74-7dc9-458c-a2ac-982c7bc09194"
    
    url = f"http://localhost:8000/api/conversations/{conversation_id}/processing-status"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    print(f"\nTesting processing status endpoint: {url}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                print(f"Response status: {response.status}")
                text = await response.text()
                print(f"Response: {text}")
                
    except Exception as e:
        print(f"❌ Exception occurred: {e}")

if __name__ == "__main__":
    print("Testing ChassisUI resume-stream endpoint...")
    asyncio.run(test_processing_status_endpoint())
    asyncio.run(test_resume_stream_endpoint()) 