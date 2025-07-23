#!/usr/bin/env python3
import os
"""
Script to add test models to the database for testing analytics
"""

import asyncio
import asyncpg
import uuid
from datetime import datetime, timedelta

async def add_test_models():
    # Connect to database using the provided connection string
    pool = await asyncpg.create_pool(
        os.environ.get("DATABASE_URL", "postgresql://chassis_user:@localhost/chassis_ui")
    )
    
    async with pool.acquire() as conn:
        print("Adding test models...")
        
        # First, get or create a test user
        test_user_id = await conn.fetchval("""
            SELECT user_id FROM users LIMIT 1
        """)
        
        if not test_user_id:
            # Create a test user if none exists
            test_user_id = await conn.fetchval("""
                INSERT INTO users (email, password_hash, name)
                VALUES ($1, $2, $3)
                RETURNING user_id
            """, "test@example.com", "hashed_password", "Test User")
            print(f"Created test user: {test_user_id}")
        else:
            print(f"Using existing user: {test_user_id}")
        
        # Add some test models
        models = [
            ("GPT-4 Assistant", "Advanced AI assistant for complex tasks", test_user_id, datetime.now() - timedelta(days=10)),
            ("Code Helper", "Specialized in programming and debugging", test_user_id, datetime.now() - timedelta(days=5)),
            ("Creative Writer", "Perfect for storytelling and creative content", test_user_id, datetime.now() - timedelta(days=2)),
            ("Math Tutor", "Expert in mathematics and problem solving", test_user_id, datetime.now() - timedelta(days=1)),
            ("Language Translator", "Multi-language translation and learning", test_user_id, datetime.now()),
        ]
        
        for name, description, owner_id, created_at in models:
            model_id = await conn.fetchval("""
                INSERT INTO models (name, description, owner_user_id, created_at)
                VALUES ($1, $2, $3, $4)
                RETURNING model_id
            """, name, description, owner_id, created_at)
            print(f"Added model: {name} (ID: {model_id})")
        
        # Add some usage analytics
        print("\nAdding usage analytics...")
        
        # Get the first model for trending
        model1_id = await conn.fetchval("SELECT model_id FROM models WHERE name = 'GPT-4 Assistant'")
        
        # Create test conversations first
        conversations = []
        for i in range(15):
            conv_id = str(uuid.uuid4())
            await conn.execute("""
                INSERT INTO conversations (conversation_id, user_id, title, model_id)
                VALUES ($1, $2, $3, $4)
            """, conv_id, test_user_id, f"Test Conversation {i+1}", model1_id)
            conversations.append(conv_id)
        
        # Add usage for trending
        for i, conv_id in enumerate(conversations):
            await conn.execute("""
                INSERT INTO model_usage_analytics 
                (model_id, user_id, conversation_id, usage_type, usage_count, created_at)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, model1_id, test_user_id, conv_id, "conversation_start", 1, datetime.now() - timedelta(hours=i))
        
        # Add usage for recently used
        model2_id = await conn.fetchval("SELECT model_id FROM models WHERE name = 'Code Helper'")
        recent_conv_id = str(uuid.uuid4())
        await conn.execute("""
            INSERT INTO conversations (conversation_id, user_id, title, model_id)
            VALUES ($1, $2, $3, $4)
        """, recent_conv_id, test_user_id, "Recent Code Chat", model2_id)
        
        await conn.execute("""
            INSERT INTO model_usage_analytics 
            (model_id, user_id, conversation_id, usage_type, usage_count, created_at)
            VALUES ($1, $2, $3, $4, $5, $6)
        """, model2_id, test_user_id, recent_conv_id, "conversation_start", 1, datetime.now() - timedelta(hours=2))
        
        print("Test data added successfully!")
        print("\nYou can now test the model selection interface.")

if __name__ == "__main__":
    asyncio.run(add_test_models()) 