#!/usr/bin/env python3
"""
Script to check if a conversation exists in the database
"""

import asyncio
import asyncpg
from database import get_db_pool

async def check_conversation(conversation_id: str):
    """Check if a conversation exists and get its details"""
    pool = await get_db_pool()
    
    async with pool.acquire() as conn:
        # Check if conversation exists
        conversation = await conn.fetchrow(
            "SELECT conversation_id, user_id, title, created_at FROM conversations WHERE conversation_id = $1",
            conversation_id
        )
        
        if conversation:
            print(f"✅ Conversation found:")
            print(f"   ID: {conversation['conversation_id']}")
            print(f"   User ID: {conversation['user_id']}")
            print(f"   Title: {conversation['title']}")
            print(f"   Created: {conversation['created_at']}")
            
            # Check messages
            messages = await conn.fetch(
                "SELECT message_id, role, content, order_index FROM messages WHERE conversation_id = $1 ORDER BY order_index",
                conversation_id
            )
            print(f"   Messages count: {len(messages)}")
            
            # Check if there's background processing
            from routes import background_tasks_running
            is_processing = background_tasks_running.get(conversation_id, False)
            print(f"   Background processing: {is_processing}")
            
        else:
            print(f"❌ Conversation {conversation_id} not found")
            
            # List some recent conversations
            recent_conversations = await conn.fetch(
                "SELECT conversation_id, user_id, title FROM conversations ORDER BY created_at DESC LIMIT 5"
            )
            print(f"Recent conversations:")
            for conv in recent_conversations:
                print(f"   {conv['conversation_id']} - {conv['title']} (user: {conv['user_id']})")

if __name__ == "__main__":
    conversation_id = "292c4a74-7dc9-458c-a2ac-982c7bc09194"
    print(f"Checking conversation: {conversation_id}")
    asyncio.run(check_conversation(conversation_id)) 