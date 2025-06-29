#!/usr/bin/env python3
"""
Test script for analytics functionality
"""

import asyncio
import asyncpg
import json
from datetime import datetime, timedelta

async def test_analytics():
    # Connect to database
    pool = await asyncpg.create_pool(
        host='localhost',
        port=5432,
        user='postgres',
        password='postgres',
        database='chassis_ui'
    )
    
    async with pool.acquire() as conn:
        print("Testing analytics functionality...")
        
        # 1. Create some test models
        print("\n1. Creating test models...")
        model1_id = await conn.fetchval("""
            INSERT INTO models (name, description, owner_user_id, created_at)
            VALUES ($1, $2, $3, $4)
            RETURNING model_id
        """, "Test Model 1", "A test model for analytics", "test-user-1", datetime.now() - timedelta(days=5))
        
        model2_id = await conn.fetchval("""
            INSERT INTO models (name, description, owner_user_id, created_at)
            VALUES ($1, $2, $3, $4)
            RETURNING model_id
        """, "Test Model 2", "Another test model", "test-user-2", datetime.now() - timedelta(days=2))
        
        model3_id = await conn.fetchval("""
            INSERT INTO models (name, description, owner_user_id, created_at)
            VALUES ($1, $2, $3, $4)
            RETURNING model_id
        """, "New Model", "A brand new model", "test-user-3", datetime.now())
        
        print(f"Created models: {model1_id}, {model2_id}, {model3_id}")
        
        # 2. Create test conversations
        print("\n2. Creating test conversations...")
        conv1_id = await conn.fetchval("""
            INSERT INTO conversations (conversation_id, user_id, title, model_id)
            VALUES ($1, $2, $3, $4)
            RETURNING conversation_id
        """, "test-conv-1", "test-user-1", "Test Chat 1", model1_id)
        
        conv2_id = await conn.fetchval("""
            INSERT INTO conversations (conversation_id, user_id, title, model_id)
            VALUES ($1, $2, $3, $4)
            RETURNING conversation_id
        """, "test-conv-2", "test-user-2", "Test Chat 2", model2_id)
        
        print(f"Created conversations: {conv1_id}, {conv2_id}")
        
        # 3. Add usage analytics
        print("\n3. Adding usage analytics...")
        
        # Add some usage data for model1 (trending)
        for i in range(10):
            await conn.execute("""
                INSERT INTO model_usage_analytics 
                (model_id, user_id, conversation_id, usage_type, usage_count, created_at)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, model1_id, f"user-{i}", conv1_id, "conversation_start", 1, datetime.now() - timedelta(hours=i))
        
        # Add some usage data for model2 (recently used)
        await conn.execute("""
            INSERT INTO model_usage_analytics 
            (model_id, user_id, conversation_id, usage_type, usage_count, created_at)
            VALUES ($1, $2, $3, $4, $5, $6)
        """, model2_id, "test-user-2", conv2_id, "conversation_start", 1, datetime.now() - timedelta(hours=2))
        
        await conn.execute("""
            INSERT INTO model_usage_analytics 
            (model_id, user_id, conversation_id, usage_type, usage_count, created_at)
            VALUES ($1, $2, $3, $4, $5, $6)
        """, model2_id, "test-user-2", conv2_id, "message_sent", 1, datetime.now() - timedelta(hours=1))
        
        print("Added usage analytics data")
        
        # 4. Test analytics queries
        print("\n4. Testing analytics queries...")
        
        # Test trending models
        trending = await conn.fetch("""
            SELECT 
                m.model_id,
                m.name,
                COUNT(mua.id) as usage_count
            FROM models m
            LEFT JOIN model_usage_analytics mua ON m.model_id = mua.model_id 
                AND mua.created_at >= NOW() - INTERVAL '1 week'
            WHERE m.owner_user_id IS NOT NULL
            GROUP BY m.model_id, m.name
            ORDER BY usage_count DESC
        """)
        
        print("Trending models:")
        for row in trending:
            print(f"  {row['name']}: {row['usage_count']} uses")
        
        # Test user history
        history = await conn.fetch("""
            SELECT DISTINCT
                m.model_id,
                m.name,
                MAX(mua.created_at) as last_used
            FROM models m
            INNER JOIN model_usage_analytics mua ON m.model_id = mua.model_id
            WHERE mua.user_id = $1
            GROUP BY m.model_id, m.name
            ORDER BY last_used DESC
        """, "test-user-2")
        
        print("\nUser history for test-user-2:")
        for row in history:
            print(f"  {row['name']}: last used {row['last_used']}")
        
        # Test new models
        new_models = await conn.fetch("""
            SELECT 
                m.model_id,
                m.name,
                m.created_at
            FROM models m
            WHERE m.created_at >= NOW() - INTERVAL '30 days'
            AND m.owner_user_id IS NOT NULL
            AND m.model_id NOT IN (
                SELECT DISTINCT model_id 
                FROM model_usage_analytics 
                WHERE user_id = $1
            )
            ORDER BY m.created_at DESC
        """, "test-user-1")
        
        print("\nNew models for test-user-1:")
        for row in new_models:
            print(f"  {row['name']}: created {row['created_at']}")
        
        print("\nAnalytics test completed successfully!")
        
        # Clean up test data
        print("\n5. Cleaning up test data...")
        await conn.execute("DELETE FROM model_usage_analytics WHERE model_id IN ($1, $2, $3)", model1_id, model2_id, model3_id)
        await conn.execute("DELETE FROM conversations WHERE conversation_id IN ($1, $2)", conv1_id, conv2_id)
        await conn.execute("DELETE FROM models WHERE model_id IN ($1, $2, $3)", model1_id, model2_id, model3_id)
        print("Test data cleaned up")

if __name__ == "__main__":
    asyncio.run(test_analytics()) 